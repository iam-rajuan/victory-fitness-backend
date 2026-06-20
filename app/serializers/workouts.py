from datetime import datetime, timezone

from ..utils.datetime import as_utc


def serialize_public_workout_record(record: dict) -> dict:
    created_at = as_utc(record.get("created_at") or datetime.now(timezone.utc))
    return {
        "id": str(record["_id"]),
        "title": str(record.get("title") or ""),
        "vimeoId": str(record.get("vimeo_id") or ""),
        "videoUrl": str(record.get("video_url") or ""),
        "videoSource": str(record.get("video_source") or "VIMEO"),
        "tag": str(record.get("tag") or "Workout"),
        "thumbnail": str(record.get("thumbnail") or ""),
        "dateAdded": created_at,
    }
