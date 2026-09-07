import os
import sys

sys.path.insert(0, os.path.abspath("."))
import app.workout_plan_ai as wai
from app.api.routers.ai_workout_plan import _hydrate_strength_plan_input
from app.models import StrengthWorkoutPlanRequest
from app.workout_plan_ai import (
    StrengthWorkoutPlanInput,
    _classify_equipment,
    generate_strength_workout_plan,
)

wai._generate_strength_workout_plan_with_ai = lambda _: None


def test_equipment_classification():
    assert _classify_equipment(["No equipment"]) == "bodyweight_only"
    assert _classify_equipment(["bodyweight"]) == "bodyweight_only"
    assert _classify_equipment(["Outdoors"]) == "bodyweight_only"
    assert _classify_equipment(["Dumbbells"]) == "dumbbells_only"
    assert _classify_equipment(["Gym", "Barbell"]) == "full_gym"


def test_bodyweight_workout_plan_strictly_excludes_gym_equipment():
    bw_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Upper / Lower",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["No equipment"],
        frequency="4",
        days=["Mon", "Tue", "Thu", "Fri"],
        age="28",
        weight="75",
        language="en",
    )

    plan = generate_strength_workout_plan(bw_input)
    assert len(plan["days"]) == 4

    forbidden_words = ["barbell", "cable", "machine", "leg press", "smith", "rack"]
    for day in plan["days"]:
        assert "min" in day["est_time"]
        for ex in day["exercises"]:
            name_lower = ex["name"].lower()
            for bad in forbidden_words:
                assert bad not in name_lower, f"Forbidden gym equipment '{bad}' found in exercise '{ex['name']}'"
            assert ex["weight"] in ["Bodyweight", "-"], f"Weight should be Bodyweight or -, got '{ex['weight']}'"


def test_hydration_from_onboarding_profile():
    mock_user = {
        "_id": "user-123",
        "onboarding": {
            "anamnese": {
                "primaryGoal": "Fat loss",
                "activityLevel": "Moderate",
                "daysPerWeek": "3 days",
                "timePerSession": "30 min",
                "equipmentAccess": "No equipment",
            },
            "personalProfile": {
                "age": "32",
                "gender": "Female",
                "height": "165",
                "weight": "62",
            },
        },
    }

    empty_payload = StrengthWorkoutPlanRequest()
    hydrated = _hydrate_strength_plan_input(empty_payload, mock_user)
    assert hydrated.goal == "Body Recomp"
    assert hydrated.level == "Intermediate"
    assert hydrated.frequency == "3"
    assert hydrated.split == "Full Body"
    assert hydrated.equipment == ["No equipment"]
    assert hydrated.weight == "62"
    assert hydrated.age == "32"


def test_serialization_strength_workout_plan_record():
    from app.core.legacy import _serialize_strength_workout_plan_record
    from bson import ObjectId
    from datetime import datetime, timezone

    bw_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Upper / Lower",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["No equipment"],
        frequency="4",
        days=["Mon", "Tue", "Thu", "Fri"],
        age="28",
        weight="75",
        language="en",
    )
    plan = generate_strength_workout_plan(bw_input)
    record = {
        "_id": ObjectId(),
        "plan": plan,
        "progress": [],
        "created_at": datetime.now(timezone.utc),
    }

    serialized = _serialize_strength_workout_plan_record(record)
    assert serialized is not None
    assert len(serialized.days) == 4
    for day in serialized.days:
        assert len(day.sections) > 0
        for section in day.sections:
            assert section.estimated_minutes >= 5


def test_session_duration_serialization_and_card_render():
    from app.core.legacy import (
        _build_strength_workout_completion_png,
        _serialize_strength_workout_plan_record,
    )
    from bson import ObjectId
    from datetime import datetime, timezone

    bw_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Full Body",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["No equipment"],
        frequency="3",
        days=["Day 1", "Day 2", "Day 3"],
        age="25",
        weight="70",
        language="en",
    )
    plan = generate_strength_workout_plan(bw_input)
    record = {
        "_id": ObjectId(),
        "plan": plan,
        "progress": [
            {
                "day": "Day 1",
                "started": True,
                "completed": True,
                "completed_section_ids": ["day-1-section-1"],
                "completed_exercise_ids": ["day-1-ex-1"],
                "started_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "duration_seconds": 1420,
            }
        ],
        "created_at": datetime.now(timezone.utc),
    }

    serialized = _serialize_strength_workout_plan_record(record)
    assert serialized.progress[0].duration_seconds == 1420

    # Test PNG generation with duration_seconds
    png_bytes, msg = _build_strength_workout_completion_png(
        serialized,
        "Test Athlete",
        completed_day="Day 1",
        full_plan=False,
        duration_seconds=1420,
    )
    assert len(png_bytes) > 1000
    assert "Victory Fitness" in msg

