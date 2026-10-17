import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime, timezone
from app.main import app
from app.api.routers import workout_logs as workout_logs_router
from app.models import (
    StrengthWorkoutPlanResponse,
    StrengthWorkoutDay,
    StrengthWorkoutSection,
    StrengthWorkoutExercise,
)
from app.core.legacy import _build_strength_workout_completion_png


@pytest.mark.anyio
async def test_create_workout_log_with_4_exercises():
    """Validates: Complete workout with 4 exercises, confirm all 4 appear in response."""
    inserted_id = ObjectId()
    fake_doc = {}

    class FakeCollection:
        async def insert_one(self, doc):
            nonlocal fake_doc
            fake_doc = doc
            m = MagicMock()
            m.inserted_id = inserted_id
            return m

        async def count_documents(self, *args, **kwargs):
            return 0

        def find(self, *args, **kwargs):
            mock_cursor = MagicMock()
            mock_cursor.sort = MagicMock(return_value=mock_cursor)
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

    mock_coll = FakeCollection()
    user = {
        "_id": ObjectId(),
        "name": "Test Athlete",
        "email": "test@victory.test",
        "streak_days": 13,
        "subscription_tier": "GOLD",
    }

    req = workout_logs_router.WorkoutLogCreateRequest(
        workout_id="upper-body-01",
        title="Upper Body",
        duration_seconds=2400,
        sets_logged=12,
        volume_kg=840,
        movements=[
            {"name": "Bench Press", "prescription": "3 sets"},
            {"name": "Lat Pulldown", "prescription": "3 sets"},
            {"name": "Shoulder Press", "prescription": "3 sets"},
            {"name": "Biceps Curl", "prescription": "3 sets"},
        ],
        status="completed",
    )

    with patch.object(workout_logs_router, "workout_logs_collection", mock_coll), \
         patch.object(workout_logs_router, "points_log_collection", mock_coll), \
         patch.object(workout_logs_router, "users_collection", mock_coll):
        res = await workout_logs_router.create_workout_log(req, user=user)

    assert res["id"] == str(inserted_id)
    assert res["title"] == "Upper Body"
    assert res["sets_logged"] == 12
    assert res["volume_kg"] == 840.0
    assert len(res["movements"]) == 4
    movement_names = [m["name"] for m in res["movements"]]
    assert movement_names == ["Bench Press", "Lat Pulldown", "Shoulder Press", "Biceps Curl"]


@pytest.mark.anyio
async def test_create_workout_log_with_skipped_exercise():
    """Validates: When 1 exercise is skipped, confirm it is not falsely shown."""
    inserted_id = ObjectId()

    class FakeCollection:
        async def insert_one(self, doc):
            m = MagicMock()
            m.inserted_id = inserted_id
            return m

        async def count_documents(self, *args, **kwargs):
            return 0

        def find(self, *args, **kwargs):
            mock_cursor = MagicMock()
            mock_cursor.sort = MagicMock(return_value=mock_cursor)
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

    mock_coll = FakeCollection()
    user = {"_id": ObjectId(), "name": "Test Athlete"}

    # User did Bench Press, Lat Pulldown, and Biceps Curl; Shoulder Press was skipped
    req = workout_logs_router.WorkoutLogCreateRequest(
        workout_id="upper-body-01",
        title="Upper Body",
        duration_seconds=1800,
        sets_logged=9,
        volume_kg=620,
        movements=[
            {"name": "Bench Press", "prescription": "3 sets"},
            {"name": "Lat Pulldown", "prescription": "3 sets"},
            {"name": "Biceps Curl", "prescription": "3 sets"},
        ],
        status="completed",
    )

    with patch.object(workout_logs_router, "workout_logs_collection", mock_coll), \
         patch.object(workout_logs_router, "points_log_collection", mock_coll), \
         patch.object(workout_logs_router, "users_collection", mock_coll):
        res = await workout_logs_router.create_workout_log(req, user=user)

    assert len(res["movements"]) == 3
    movement_names = [m["name"] for m in res["movements"]]
    assert "Shoulder Press" not in movement_names
    assert movement_names == ["Bench Press", "Lat Pulldown", "Biceps Curl"]


@pytest.mark.anyio
async def test_create_workout_log_with_swapped_and_long_name():
    """Validates: Swapped exercise and long exercise names are preserved cleanly."""
    inserted_id = ObjectId()

    class FakeCollection:
        async def insert_one(self, doc):
            m = MagicMock()
            m.inserted_id = inserted_id
            return m

        async def count_documents(self, *args, **kwargs):
            return 0

        def find(self, *args, **kwargs):
            mock_cursor = MagicMock()
            mock_cursor.sort = MagicMock(return_value=mock_cursor)
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor

    mock_coll = FakeCollection()
    user = {"_id": ObjectId(), "name": "Test Athlete"}

    long_name = "Incline Dumbbell Bench Press with 3-Second Eccentric Pause and Peak Contraction Hold"
    req = workout_logs_router.WorkoutLogCreateRequest(
        workout_id="upper-body-01",
        title="Upper Body",
        duration_seconds=2200,
        sets_logged=12,
        volume_kg=780,
        movements=[
            {"name": long_name, "prescription": "3 sets"},
            {"name": "Lat Pulldown", "prescription": "3 sets"},
            {"name": "Incline Dumbbell Curl", "prescription": "3 sets"},  # Swapped from Biceps Curl
        ],
        status="completed",
    )

    with patch.object(workout_logs_router, "workout_logs_collection", mock_coll), \
         patch.object(workout_logs_router, "points_log_collection", mock_coll), \
         patch.object(workout_logs_router, "users_collection", mock_coll):
        res = await workout_logs_router.create_workout_log(req, user=user)

    assert len(res["movements"]) == 3
    assert res["movements"][0]["name"] == long_name
    assert res["movements"][2]["name"] == "Incline Dumbbell Curl"


def test_strength_completion_png_generation_with_long_exercises():
    """Validates: PNG report generation gracefully handles long exercise names."""
    plan = StrengthWorkoutPlanResponse(
        plan_id="plan-123",
        summary="6-Week Hypertrophy Plan",
        days=[
            StrengthWorkoutDay(
                day="Day 1",
                title="Upper Body Strength",
                est_time="45 min",
                volume="high",
                intensity="high",
                sections=[
                    StrengthWorkoutSection(
                        id="sec-1",
                        title="Compound Lifts",
                        exercises=[
                            StrengthWorkoutExercise(
                                id="ex-1",
                                name="Incline Dumbbell Bench Press with 3-Second Eccentric Pause",
                                sets=3,
                                reps="8-10",
                                rest="60s",
                                type="strength",
                            ),
                            StrengthWorkoutExercise(
                                id="ex-2",
                                name="Lat Pulldown - Wide Grip",
                                sets=3,
                                reps="10",
                                rest="60s",
                                type="strength",
                            ),
                        ],
                    )
                ],
            )
        ],
        progress=[
            StrengthWorkoutPlanResponse.DayProgress(
                day="Day 1",
                started=True,
                completed=True,
                completed_exercise_ids=["ex-1", "ex-2"],
                completed_section_ids=["sec-1"],
                duration_seconds=2700,
            )
        ],
    )

    png_bytes, share_message = _build_strength_workout_completion_png(
        plan=plan,
        user_name="Michael Krause",
        completed_day="Day 1",
        duration_seconds=2700,
        identity_statement="I am someone who trains even when it is hard.",
    )

    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 1000
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert "Michael Krause" in share_message
    assert "Upper Body Strength" in share_message
