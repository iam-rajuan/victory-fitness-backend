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
    assert _classify_equipment(["Cable Machine", "Gym Machines"]) == "full_gym"
    assert _classify_equipment(["Squat Rack", "Bench"]) == "full_gym"
    assert _classify_equipment(["Resistance Bands", "Pull-up Bar"]) == "dumbbells_only"


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
    assert hydrated.muscle_group == "Full Body"
    assert hydrated.duration_minutes == "30"


def test_leg_workout_excludes_unrelated_chest_exercises():
    plan_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Upper / Lower",
        muscle_group="Legs",
        duration_minutes="45",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Gym", "Barbell", "Dumbbells", "Machines"],
        frequency="3",
        days=["Mon", "Wed", "Fri"],
        age="28",
        weight="75",
        language="en",
    )

    plan = generate_strength_workout_plan(plan_input)

    assert [day["day"] for day in plan["days"]] == ["Mon", "Wed", "Fri"]
    forbidden = ["bench", "chest", "press", "push-up", "flye"]
    for day in plan["days"]:
        for exercise in day["exercises"]:
            lowered = exercise["name"].lower()
            assert not any(term in lowered for term in forbidden), exercise["name"]


def test_goal_and_level_change_strength_prescription():
    beginner_hypertrophy = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Beginner",
        split="Full Body",
        muscle_group="Legs",
        duration_minutes="45",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Gym", "Barbell"],
        frequency="3",
        days=["Mon", "Wed", "Fri"],
        age="28",
        weight="75",
        language="en",
    )
    advanced_strength = StrengthWorkoutPlanInput(
        **{**beginner_hypertrophy.__dict__, "goal": "Pure Strength", "level": "Advanced"}
    )

    beginner_plan = generate_strength_workout_plan(beginner_hypertrophy)
    advanced_plan = generate_strength_workout_plan(advanced_strength)

    assert beginner_plan["days"][0]["intensity"] == "RPE 7.0 (Controlled)"
    assert advanced_plan["days"][0]["intensity"] == "RPE 8.5 (High)"
    assert advanced_plan["days"][0]["exercises"][0]["reps"] == "3-5"
    assert beginner_plan["days"][0]["exercises"][0]["sets"] <= advanced_plan["days"][0]["exercises"][0]["sets"]


def test_duration_and_equipment_constraints_are_applied():
    plan_input = StrengthWorkoutPlanInput(
        goal="Body Recomp",
        level="Beginner",
        split="Full Body",
        muscle_group="Full Body",
        duration_minutes="30",
        height="165",
        gender="Female",
        bench="",
        squat="",
        deadlift="",
        equipment=["No equipment"],
        frequency="4",
        days=["Monday", "Tuesday", "Thursday", "Friday"],
        age="32",
        weight="62",
        language="en",
    )

    plan = generate_strength_workout_plan(plan_input)

    assert len(plan["days"]) == 4
    assert [day["day"] for day in plan["days"]] == ["Mon", "Tue", "Thu", "Fri"]
    for day in plan["days"]:
        assert len(day["exercises"]) <= 3
        assert int(day["est_time"].split()[0]) <= 35
        for exercise in day["exercises"]:
            assert exercise["weight"] in ["Bodyweight", "-"]


def test_full_gym_focused_plan_prioritizes_gym_equipment_over_bodyweight():
    plan_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Upper / Lower",
        muscle_group="Legs",
        duration_minutes="45",
        height="175",
        gender="Male",
        bench="",
        squat="100",
        deadlift="120",
        equipment=["Cable Machine", "Gym Machines", "Squat Rack", "Bench"],
        frequency="3",
        days=["Mon", "Wed", "Fri"],
        age="28",
        weight="75",
        language="en",
    )

    plan = generate_strength_workout_plan(plan_input)
    names = [exercise["name"] for day in plan["days"] for exercise in day["exercises"]]
    gym_terms = ["Barbell", "Romanian Deadlift", "Leg Press", "Leg Extension", "Hamstring Curl", "Hip Thrust"]
    bodyweight_terms = ["Bodyweight", "Push-Up", "Glute Bridge", "Lunge"]

    assert any(any(term in name for term in gym_terms) for name in names)
    first_day_names = [exercise["name"] for exercise in plan["days"][0]["exercises"]]
    assert not any(any(term in name for term in bodyweight_terms) for name in first_day_names[:3])


def test_home_gym_plan_uses_dumbbell_or_bodyweight_without_barbells_or_machines():
    plan_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Full Body",
        muscle_group="Full Body",
        duration_minutes="45",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Dumbbells", "Resistance Bands", "Bench"],
        frequency="3",
        days=["Mon", "Wed", "Fri"],
        age="28",
        weight="75",
        language="en",
    )

    plan = generate_strength_workout_plan(plan_input)
    names = [exercise["name"].lower() for day in plan["days"] for exercise in day["exercises"]]

    assert any("dumbbell" in name for name in names)
    assert not any(any(term in name for term in ["barbell", "cable", "machine", "leg press"]) for name in names)


def test_ai_response_is_corrected_before_returning():
    bad_ai_plan = {
        "summary": "Bad plan",
        "days": [
            {
                "day": "Mon",
                "title": "Legs",
                "est_time": "60 min",
                "volume": "",
                "intensity": "",
                "exercises": [
                    {"id": "x", "name": "Bench Press", "sets": 5, "reps": "5", "rest": "180s", "weight": "80kg", "type": "Compound"},
                    {"id": "y", "name": "Imaginary Chest Blaster", "sets": 3, "reps": "12", "rest": "60s", "weight": "20kg", "type": "Accessory"},
                ],
            }
        ],
    }
    original = wai._generate_strength_workout_plan_with_ai
    wai._generate_strength_workout_plan_with_ai = lambda _: bad_ai_plan
    try:
        plan = generate_strength_workout_plan(
            StrengthWorkoutPlanInput(
                goal="Hypertrophy",
                level="Intermediate",
                split="Upper / Lower",
                muscle_group="Legs",
                duration_minutes="45",
                height="175",
                gender="Male",
                bench="",
                squat="",
                deadlift="",
                equipment=["Gym", "Barbell"],
                frequency="3",
                days=["Mon", "Wed", "Fri"],
                age="28",
                weight="75",
                language="en",
            )
        )
    finally:
        wai._generate_strength_workout_plan_with_ai = original

    names = [exercise["name"].lower() for day in plan["days"] for exercise in day["exercises"]]
    assert "bench press" not in names
    assert "imaginary chest blaster" not in names
    assert len(plan["days"]) == 3


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
        identity_statement="I am someone who keeps their word to themselves.",
    )
    assert len(png_bytes) > 1000
    assert "Victory Fitness" in msg
    assert "I am someone who keeps their word to themselves." in msg
