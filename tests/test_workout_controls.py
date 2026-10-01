from datetime import datetime, timezone

from bson import ObjectId

from app.core.legacy import _serialize_admin_workout_record
from app.serializers.workouts import serialize_public_workout_record


def _workout_record(**overrides):
    record = {
        "_id": ObjectId(),
        "title": "Full Body Builder",
        "video_url": "https://example.com/workout.mp4",
        "video_source": "UPLOAD",
        "tag": "Full Body Workout",
        "equipment": "Dumbbells",
        "duration_minutes": 30,
        "duration_seconds": 1800,
        "visibility": "Published",
        "thumbnail": "",
        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }
    record.update(overrides)
    return record


def test_public_workout_serializes_multiple_levels_and_full_body_purpose():
    payload = serialize_public_workout_record(
        _workout_record(level="Beginner", levels=["Beginner", "Advanced"])
    )

    assert payload["tag"] == "Full Body Workout"
    assert payload["level"] == "Beginner"
    assert payload["levels"] == ["Beginner", "Advanced"]


def test_public_workout_backfills_levels_from_legacy_single_level():
    payload = serialize_public_workout_record(_workout_record(level="Intermediate"))

    assert payload["level"] == "Intermediate"
    assert payload["levels"] == ["Intermediate"]


def test_admin_workout_serializes_multiple_levels_for_editor():
    payload = _serialize_admin_workout_record(
        _workout_record(level="Beginner", levels=["Beginner", "Intermediate", "Advanced"])
    )

    assert payload["level"] == "Beginner"
    assert payload["levels"] == ["Beginner", "Intermediate", "Advanced"]
