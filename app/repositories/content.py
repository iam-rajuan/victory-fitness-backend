from datetime import datetime, timezone

from ..database import app_content_collection


APP_CONTENT_PROJECTION = {
    "_id": 0,
    "key": 1,
    "title": 1,
    "html_content": 1,
    "created_at": 1,
    "updated_at": 1,
}


async def ensure_content_record(
    *,
    key: str,
    default_title: str,
    default_html_content: str,
) -> dict:
    record = await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION)
    if record:
        return record

    now = datetime.now(timezone.utc)
    record = {
        "key": key,
        "title": default_title,
        "html_content": default_html_content,
        "created_at": now,
        "updated_at": now,
    }
    await app_content_collection.update_one(
        {"key": key},
        {"$setOnInsert": record},
        upsert=True,
    )
    saved = await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION)
    return saved or record


async def upsert_content_record(
    *,
    key: str,
    title: str,
    html_content: str,
) -> dict | None:
    now = datetime.now(timezone.utc)
    await app_content_collection.update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "title": title.strip(),
                "html_content": html_content.strip(),
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )
    return await app_content_collection.find_one({"key": key}, projection=APP_CONTENT_PROJECTION)
