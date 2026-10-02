from datetime import datetime, timezone

from ..utils.datetime import as_utc

VALID_WORKOUT_LEVELS = {"Beginner", "Intermediate", "Advanced"}
VALID_WORKOUT_PURPOSES = (
    "Strength",
    "Full Body Workout",
    "Mobility",
    "Core",
    "Conditioning",
    "Recovery",
    "Lower body",
    "Upper body",
)


def workout_default_thumbnail(record: dict) -> str:
    return str(record.get("thumbnail") or record.get("thumbnail_url") or "").strip()


def workout_custom_thumbnail(record: dict) -> str:
    return str(record.get("custom_thumbnail") or record.get("customThumbnail") or "").strip()


def workout_effective_thumbnail(record: dict) -> str:
    return workout_custom_thumbnail(record) or workout_default_thumbnail(record)


def normalize_workout_levels(record: dict) -> list[str]:
    raw_levels = record.get("levels")
    candidates = raw_levels if isinstance(raw_levels, list) else []
    if not candidates:
        candidates = [record.get("level")]
    levels: list[str] = []
    for item in candidates:
        label = str(item or "").strip()
        canonical = next((valid for valid in VALID_WORKOUT_LEVELS if valid.lower() == label.lower()), "")
        if canonical and canonical not in levels:
            levels.append(canonical)
    return levels


def normalize_workout_purposes(record: dict) -> list[str]:
    raw_purposes = record.get("purposes")
    candidates = raw_purposes if isinstance(raw_purposes, list) else []
    if not candidates:
        candidates = [record.get("tag")]
    purposes: list[str] = []
    for item in candidates:
        label = str(item or "").strip()
        canonical = next((valid for valid in VALID_WORKOUT_PURPOSES if valid.lower() == label.lower()), label)
        if canonical and canonical not in purposes:
            purposes.append(canonical)
    return purposes


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
    levels = normalize_workout_levels(record)
    purposes = normalize_workout_purposes(record)
    return {
        "id": str(record["_id"]),
        "title": str(record.get("title") or ""),
        "vimeoId": str(record.get("vimeo_id") or ""),
        "videoUrl": str(record.get("video_url") or ""),
        "videoSource": str(record.get("video_source") or "VIMEO"),
        "tag": purposes[0] if purposes else str(record.get("tag") or "Workout"),
        "purposes": purposes,
        "equipment": str(record.get("equipment") or ""),
        "level": levels[0] if levels else str(record.get("level") or ""),
        "levels": levels,
        "durationMinutes": int(record.get("duration_minutes") or record.get("durationMinutes") or 0),
        "durationSeconds": int(record.get("duration_seconds") or record.get("durationSeconds") or 0),
        "thumbnail": workout_effective_thumbnail(record),
        "movements": _serialize_workout_movements(record.get("movements") or []),
        "dateAdded": created_at,
    }
