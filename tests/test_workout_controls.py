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
        "tag": "Full Body",
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

    assert payload["tag"] == "Full Body"
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


def test_public_workout_uses_custom_thumbnail_before_default():
    payload = serialize_public_workout_record(
        _workout_record(
            thumbnail="https://vimeo.example/default.jpg",
            custom_thumbnail="https://cdn.example/custom.jpg",
        )
    )

    assert payload["thumbnail"] == "https://cdn.example/custom.jpg"


def test_public_workout_falls_back_to_default_thumbnail():
    payload = serialize_public_workout_record(
        _workout_record(thumbnail="https://vimeo.example/default.jpg", custom_thumbnail="")
    )

    assert payload["thumbnail"] == "https://vimeo.example/default.jpg"


def test_admin_workout_exposes_custom_and_default_thumbnails():
    payload = _serialize_admin_workout_record(
        _workout_record(
            thumbnail="https://vimeo.example/default.jpg",
            custom_thumbnail="https://cdn.example/custom.jpg",
        )
    )

    assert payload["thumbnail"] == "https://cdn.example/custom.jpg"
    assert payload["defaultThumbnail"] == "https://vimeo.example/default.jpg"
    assert payload["customThumbnail"] == "https://cdn.example/custom.jpg"
