from datetime import datetime, timezone
from uuid import uuid4

from ..database import app_content_collection


APP_CONTENT_PROJECTION = {
    "_id": 0,
    "key": 1,
    "title": 1,
    "html_content": 1,
    "created_at": 1,
    "updated_at": 1,
    "versions": 1,
    "published_version_id": 1,
    "status": 1,
}

ALLOWED_MARKETS = {"ALL", "EU", "DE", "GH", "IN"}


def _normalize_markets(values: list[str] | None) -> list[str]:
    markets = [str(item or "").strip().upper() for item in (values or [])]
    normalized = [item for item in markets if item in ALLOWED_MARKETS]
    if not normalized or "ALL" in normalized:
        return ["ALL"]
    return list(dict.fromkeys(normalized))


def _version_label(next_index: int) -> str:
    return f"v{max(1, next_index)}"


def _base_version_from_record(record: dict, *, now: datetime) -> dict:
    return {
        "id": str(record.get("published_version_id") or uuid4().hex),
        "version": "v1",
        "title": str(record.get("title") or ""),
        "html_content": str(record.get("html_content") or ""),
        "filename": str(record.get("filename") or ""),
        "applies_to": _normalize_markets(record.get("applies_to") if isinstance(record.get("applies_to"), list) else ["ALL"]),
        "notification_behavior": str(record.get("notification_behavior") or "silent"),
        "status": str(record.get("status") or "Published"),
        "published_at": record.get("published_at") or record.get("updated_at") or now,
        "effective_at": record.get("effective_at") or record.get("updated_at") or now,
        "created_at": record.get("created_at") or now,
    }


def ensure_content_versions(record: dict, *, default_title: str, default_html_content: str) -> dict:
    now = datetime.now(timezone.utc)
    if not record.get("title"):
        record["title"] = default_title
    if not record.get("html_content"):
        record["html_content"] = default_html_content
    versions = [dict(item) for item in (record.get("versions") or []) if isinstance(item, dict)]
    if not versions:
        versions = [_base_version_from_record(record, now=now)]
    published_id = str(record.get("published_version_id") or versions[-1].get("id") or "")
    current = next((item for item in versions if str(item.get("id") or "") == published_id), None) or versions[-1]
    record["versions"] = versions
    record["published_version_id"] = str(current.get("id") or published_id)
    record["title"] = str(current.get("title") or record.get("title") or default_title)
    record["html_content"] = str(current.get("html_content") or record.get("html_content") or default_html_content)
    record["updated_at"] = current.get("published_at") or record.get("updated_at") or now
    record["status"] = str(current.get("status") or record.get("status") or "Published")
    return record


async def ensure_content_record(
    *,
    key: str,
    default_title: str,
    default_html_content: str,
) -> dict:
    record = await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION)
    if record:
        normalized = ensure_content_versions(record, default_title=default_title, default_html_content=default_html_content)
        if not record.get("versions"):
            await app_content_collection.update_one(
                {"key": key},
                {"$set": {"versions": normalized["versions"], "published_version_id": normalized["published_version_id"], "status": normalized["status"]}},
            )
        return normalized

    now = datetime.now(timezone.utc)
    record = {
        "key": key,
        "title": default_title,
        "html_content": default_html_content,
        "created_at": now,
        "updated_at": now,
        "status": "Published",
    }
    version = _base_version_from_record(record, now=now)
    version["title"] = default_title
    version["html_content"] = default_html_content
    record["versions"] = [version]
    record["published_version_id"] = version["id"]
    await app_content_collection.update_one(
        {"key": key},
        {"$setOnInsert": record},
        upsert=True,
    )
    saved = await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION)
    return ensure_content_versions(saved or record, default_title=default_title, default_html_content=default_html_content)


async def upsert_content_record(
    *,
    key: str,
    title: str,
    html_content: str,
    filename: str | None = None,
    applies_to: list[str] | None = None,
    notification_behavior: str = "silent",
    effective_at: datetime | None = None,
) -> dict | None:
    now = datetime.now(timezone.utc)
    existing = await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION) or {}
    versions = [dict(item) for item in (existing.get("versions") or []) if isinstance(item, dict)]
    version = {
        "id": uuid4().hex,
        "version": _version_label(len(versions) + 1),
        "title": title.strip(),
        "html_content": html_content.strip(),
        "filename": str(filename or "").strip(),
        "applies_to": _normalize_markets(applies_to),
        "notification_behavior": notification_behavior if notification_behavior in {"all", "eu", "silent"} else "silent",
        "status": "Published",
        "published_at": now,
        "effective_at": effective_at or now,
        "created_at": now,
    }
    versions.append(version)
    await app_content_collection.update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "title": version["title"],
                "html_content": version["html_content"],
                "filename": version["filename"],
                "applies_to": version["applies_to"],
                "notification_behavior": version["notification_behavior"],
                "published_at": version["published_at"],
                "effective_at": version["effective_at"],
                "status": version["status"],
                "versions": versions,
                "published_version_id": version["id"],
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )
    return await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION)
