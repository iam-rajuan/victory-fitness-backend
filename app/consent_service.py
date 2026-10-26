from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from .database import consents_collection, users_collection


CONSENT_VERSIONS = {"email": "email-1.0", "whatsapp": "whatsapp-1.0", "journal": "journal-1.0"}
CONSENT_SOURCES = {"web_form", "journal_dialog", "app_settings", "whatsapp_stop"}


def normalize_consent_language(value: str | None) -> str:
    return "de" if str(value or "").lower().startswith("de") else "en"


async def append_consent_event(*, user_id: str, consent_id: str, granted: bool, language: str,
                               source: str, ip_address: str | None = None) -> dict:
    if consent_id not in CONSENT_VERSIONS or source not in CONSENT_SOURCES:
        raise ValueError("Invalid consent event")
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    document = {
        "_id": event_id,
        "id": event_id,
        "user_id": str(user_id),
        "consent_id": consent_id,
        "version": CONSENT_VERSIONS[consent_id],
        "granted": bool(granted),
        "language": normalize_consent_language(language),
        "timestamp_utc": now,
        "source": source,
        "ip_address": ip_address or None,
    }
    await consents_collection.insert_one(document)

    mirror_field = {
        "email": "marketing_consent",
        "whatsapp": "whatsapp_consent",
        "journal": "journal_consent_granted",
    }[consent_id]
    await users_collection.update_one(
        {"_id": await _resolve_user_id(user_id)},
        {"$set": {mirror_field: bool(granted), f"{mirror_field}_at": now}},
    )
    return document


async def _resolve_user_id(user_id: str):
    from bson import ObjectId
    try:
        return ObjectId(user_id)
    except Exception:
        return user_id


async def latest_consent_statuses(user_id: str) -> dict[str, dict]:
    statuses: dict[str, dict] = {}
    for consent_id, version in CONSENT_VERSIONS.items():
        row = await consents_collection.find_one(
            {"user_id": str(user_id), "consent_id": consent_id},
            sort=[("timestamp_utc", -1), ("_id", -1)],
        )
        statuses[consent_id] = {
            "consent_id": consent_id,
            "version": row.get("version", version) if row else version,
            "granted": bool(row and row.get("granted")),
            "language": row.get("language") if row else None,
            "timestamp_utc": row.get("timestamp_utc") if row else None,
        }
    return statuses


async def require_journal_consent(user_id: str) -> None:
    latest = await consents_collection.find_one(
        {"user_id": str(user_id), "consent_id": "journal"},
        sort=[("timestamp_utc", -1), ("_id", -1)],
    )
    if not latest or not latest.get("granted"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "journal_consent_required", "message": "Journal consent is required."},
        )
