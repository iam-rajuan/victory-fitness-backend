import asyncio
import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings


MONGODB_NOT_CONFIGURED_MESSAGE = (
    "MongoDB is not configured. Set MONGODB_URI or MONGO_URL to your MongoDB Atlas connection string."
)
LOCAL_DATABASE_MESSAGE = "MongoDB is not configured. Using local development data files."


class DatabaseNotConfiguredError(RuntimeError):
    pass


class _UnavailableCollection:
    def __getattr__(self, _name: str):
        async def _missing_database(*_args, **_kwargs):
            raise DatabaseNotConfiguredError(MONGODB_NOT_CONFIGURED_MESSAGE)

        return _missing_database


def _encode_json(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return {"$oid": str(value)}
    if isinstance(value, datetime):
        return {"$date": value.isoformat()}
    if isinstance(value, list):
        return [_encode_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode_json(item) for key, item in value.items()}
    return value


def _decode_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_json(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$oid"}:
            return ObjectId(value["$oid"])
        if set(value) == {"$date"}:
            return datetime.fromisoformat(value["$date"])
        return {key: _decode_json(item) for key, item in value.items()}
    return value


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, ObjectId) or isinstance(right, ObjectId):
        return str(left) == str(right)
    return left == right


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    return all(_values_equal(document.get(key), value) for key, value in query.items())


class _LocalCollection:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def create_index(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def find_one(
        self,
        query: dict[str, Any],
        sort: list[tuple[str, int]] | None = None,
    ) -> dict[str, Any] | None:
        async with self._lock:
            documents = [document for document in self._load() if _matches(document, query)]

        if sort:
            for key, direction in reversed(sort):
                documents.sort(
                    key=lambda document: document.get(key) or datetime.min,
                    reverse=direction < 0,
                )

        return copy.deepcopy(documents[0]) if documents else None

    async def insert_one(self, document: dict[str, Any]) -> SimpleNamespace:
        async with self._lock:
            documents = self._load()
            stored = copy.deepcopy(document)
            stored.setdefault("_id", ObjectId())
            documents.append(stored)
            self._save(documents)

        return SimpleNamespace(inserted_id=stored["_id"])

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> SimpleNamespace:
        async with self._lock:
            documents = self._load()
            index = next(
                (position for position, document in enumerate(documents) if _matches(document, query)),
                None,
            )
            inserted = False

            if index is None:
                if not upsert:
                    return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

                document = copy.deepcopy(query)
                document["_id"] = ObjectId()
                documents.append(document)
                index = len(documents) - 1
                inserted = True

            document = documents[index]

            if inserted:
                for key, value in update.get("$setOnInsert", {}).items():
                    document[key] = copy.deepcopy(value)

            for key, value in update.get("$set", {}).items():
                document[key] = copy.deepcopy(value)

            for key in update.get("$unset", {}):
                document.pop(key, None)

            for key, value in update.get("$push", {}).items():
                items = value.get("$each", []) if isinstance(value, dict) and "$each" in value else [value]
                document.setdefault(key, []).extend(copy.deepcopy(items))

            documents[index] = document
            self._save(documents)

        return SimpleNamespace(
            matched_count=0 if inserted else 1,
            modified_count=1,
            upserted_id=document["_id"] if inserted else None,
        )

    def _load(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []

        with self._path.open("r", encoding="utf-8") as file:
            return _decode_json(json.load(file))

    def _save(self, documents: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as file:
            json.dump(_encode_json(documents), file, indent=2)


if settings.mongodb_configured:
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
    db = client[settings.mongodb_db]
    users_collection = db["users"]
    nutrition_plans_collection = db["nutrition_plans"]
    coach_victor_threads_collection = db["coach_victor_threads"]
elif settings.environment != "production":
    client = None
    db = None
    local_data_dir = Path(__file__).resolve().parents[1] / ".local-data"
    users_collection = _LocalCollection(local_data_dir / "users.json")
    nutrition_plans_collection = _LocalCollection(local_data_dir / "nutrition_plans.json")
    coach_victor_threads_collection = _LocalCollection(local_data_dir / "coach_victor_threads.json")
else:
    client = None
    db = None
    users_collection = _UnavailableCollection()
    nutrition_plans_collection = _UnavailableCollection()
    coach_victor_threads_collection = _UnavailableCollection()


async def ensure_indexes() -> None:
    if not settings.mongodb_configured and settings.environment == "production":
        return

    await users_collection.create_index("email", unique=True)
    await nutrition_plans_collection.create_index([("user_id", 1), ("created_at", -1)])
    await coach_victor_threads_collection.create_index([("user_id", 1), ("updated_at", -1)])
