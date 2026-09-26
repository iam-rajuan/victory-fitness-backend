from datetime import datetime, timezone

from ..utils.datetime import as_utc


def _serialize_workout_movements(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    movements: list[dict] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            rest_seconds = int(item.get("restSeconds") or item.get("rest_seconds") or 0)
        except (TypeError, ValueError):
            rest_seconds = 0
        try:
            order = int(item.get("order") if item.get("order") is not None else idx)
        except (TypeError, ValueError):
            order = idx
        movements.append(
            {
                "id": str(item.get("id") or f"movement-{idx + 1}"),
                "name": name,
                "sets": str(item.get("sets") or ""),
                "reps": str(item.get("reps") or ""),
                "load": str(item.get("load") or ""),
                "equipment": str(item.get("equipment") or ""),
                "restSeconds": max(0, min(rest_seconds, 3600)),
                "notes": str(item.get("notes") or ""),
                "order": max(0, min(order, 500)),
            }
        )
    return sorted(movements, key=lambda movement: (int(movement.get("order") or 0), str(movement.get("name") or "")))


def serialize_public_workout_record(record: dict) -> dict:
    created_at = as_utc(record.get("created_at") or datetime.now(timezone.utc))
    return {
        "id": str(record["_id"]),
        "title": str(record.get("title") or ""),
        "vimeoId": str(record.get("vimeo_id") or ""),
        "videoUrl": str(record.get("video_url") or ""),
        "videoSource": str(record.get("video_source") or "VIMEO"),
        "tag": str(record.get("tag") or "Workout"),
        "equipment": str(record.get("equipment") or ""),
        "level": str(record.get("level") or ""),
        "durationMinutes": int(record.get("duration_minutes") or record.get("durationMinutes") or 0),
        "thumbnail": str(record.get("thumbnail") or ""),
        "movements": _serialize_workout_movements(record.get("movements") or []),
        "dateAdded": created_at,
    }
