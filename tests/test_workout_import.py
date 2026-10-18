from __future__ import annotations

from typing import Any
import pytest
from app.workout_import import (
    count_expected_days_in_input,
    extract_expected_duration_minutes,
    is_custom_workout_import_request,
    parse_custom_workout,
    validate_parsed_workout_plan,
    convert_custom_plan_to_strength_plan_dict,
)
from app.api.routers import ai_coach_victor as coach_router


VICTOR_FIVE_DAY_INPUT = """
Here is my workout routine, please import this into my workout plan:

Day 1: Upper Body Power (90 min) - Barbell, Dumbbells
- Bench Press - 80kg - 4x8 - 90s rest (heavy warm up first)
- Barbell Row - 70kg - 4x10 - 90s rest
- Overhead Press - 50kg - 3x8 - 90s rest
- Incline Dumbbell Press - 28kg - 3x10 - 60s rest
- Cable Face Pulls - 25kg - 3x15 - 60s rest

Day 2: Lower Body Strength (90 min) - Barbell, Squat Rack
- Back Squat - 100kg - 4x6 - 120s rest
- Romanian Deadlift - 80kg - 3x8 - 90s rest
- Leg Press - 160kg - 3x10 - 90s rest
- Standing Calf Raise - 40kg - 4x12 - 60s rest
- Hanging Leg Raise - Bodyweight - 3x12 - 60s rest

Day 3: Push Hypertrophy (90 min) - Dumbbells, Bench, Cables
- Incline Barbell Bench - 70kg - 4x8 - 90s rest
- Flat Dumbbell Press - 30kg - 3x10 - 60s rest
- Dumbbell Lateral Raise - 12kg - 4x15 - 45s rest
- Cable Flyes - 15kg - 3x12 - 60s rest
- Overhead Tricep Extension - 24kg - 3x12 - 60s rest

Day 4: Pull Hypertrophy (90 min) - Pull-up Bar, Barbell, Cables
- Weighted Pull-ups - +10kg - 4x6 - 120s rest
- One-Arm Dumbbell Row - 32kg - 3x10 - 90s rest
- Lat Pulldown - 60kg - 3x10 - 60s rest
- Barbell Bicep Curl - 30kg - 3x10 - 60s rest
- Hammer Curl - 14kg - 3x12 - 60s rest

Day 5: Legs & Posterior Chain (90 min) - Barbell, Cables
- Front Squat - 70kg - 4x8 - 90s rest
- Bulgarian Split Squat - 20kg - 3x10 - 60s rest
- Hamstring Curl - 50kg - 3x12 - 60s rest
- Seated Calf Raise - 35kg - 4x15 - 60s rest
- Ab Wheel Rollout - Bodyweight - 3x10 - 60s rest
"""


def test_is_custom_workout_import_request() -> None:
    assert is_custom_workout_import_request(VICTOR_FIVE_DAY_INPUT) is True
    assert is_custom_workout_import_request("Import my workout routine:\nDay 1: Bench Press 80kg 3x8\nDay 2: Squat 100kg 3x5") is True
    assert is_custom_workout_import_request("What should I eat before training?") is False
    assert is_custom_workout_import_request("My knee hurts today") is False


def test_count_expected_days_in_input() -> None:
    assert count_expected_days_in_input(VICTOR_FIVE_DAY_INPUT) == 5
    assert count_expected_days_in_input("I train 5 days a week: Monday, Tuesday, Thursday, Friday, Saturday") == 5
    assert count_expected_days_in_input("Day 1: Push\nDay 2: Pull\nDay 3: Legs") == 3


def test_victor_style_five_day_workout_preserves_all_five_days() -> None:
    plan = parse_custom_workout(VICTOR_FIVE_DAY_INPUT)

    assert plan.is_valid is True
    assert len(plan.days) == 5, f"Expected exactly 5 days, got {len(plan.days)}"

    day_names = [d.day_name for d in plan.days]
    assert any("Day 1" in name for name in day_names)
    assert any("Day 2" in name for name in day_names)
    assert any("Day 3" in name for name in day_names)
    assert any("Day 4" in name for name in day_names)
    assert any("Day 5" in name for name in day_names)

    # Ensure each day has exercises
    for day in plan.days:
        assert len(day.exercises) >= 4, f"Day {day.day_name} should have at least 4 exercises"


def test_session_duration_ninety_minutes_preserved_never_downgraded_to_25() -> None:
    duration = extract_expected_duration_minutes(VICTOR_FIVE_DAY_INPUT)
    assert duration == 90

    plan = parse_custom_workout(VICTOR_FIVE_DAY_INPUT)
    assert plan.expected_duration == 90

    for day in plan.days:
        assert day.expected_duration == 90, f"Expected 90 minutes for {day.day_name}, got {day.expected_duration}"

    strength_dict = convert_custom_plan_to_strength_plan_dict(plan)
    for day_dict in strength_dict["days"]:
        assert day_dict["est_time"] == "90 min", f"Day est_time must be 90 min, got {day_dict['est_time']}"
        assert "25 min" not in day_dict["est_time"]


def test_exact_weights_preserved_including_80kg() -> None:
    plan = parse_custom_workout(VICTOR_FIVE_DAY_INPUT)

    # Find Bench Press in Day 1
    day_1 = next(d for d in plan.days if "Day 1" in d.day_name)
    bench = next((ex for ex in day_1.exercises if "Bench Press" in ex.exercise_name), None)
    assert bench is not None
    assert bench.weight.lower().replace(" ", "") == "80kg"
    assert bench.sets == 4
    assert bench.reps == "8"
    assert "heavy warm up first" in bench.notes

    # Find Barbell Row in Day 1
    row = next((ex for ex in day_1.exercises if "Row" in ex.exercise_name), None)
    assert row is not None
    assert row.weight.lower().replace(" ", "") == "70kg"

    # Find Back Squat in Day 2
    day_2 = next(d for d in plan.days if "Day 2" in d.day_name)
    squat = next((ex for ex in day_2.exercises if "Squat" in ex.exercise_name), None)
    assert squat is not None
    assert squat.weight.lower().replace(" ", "") == "100kg"

    # Find Weighted Pull-ups in Day 4
    day_4 = next(d for d in plan.days if "Day 4" in d.day_name)
    pullup = next((ex for ex in day_4.exercises if "Pull-up" in ex.exercise_name or "Pull" in ex.exercise_name), None)
    assert pullup is not None
    assert "+10kg" in pullup.weight.lower().replace(" ", "")


def test_unknown_exercises_preserved_no_silent_replacements() -> None:
    plan = parse_custom_workout(VICTOR_FIVE_DAY_INPUT)
    all_exercise_names = [ex.exercise_name for d in plan.days for ex in d.exercises]

    # Verify custom exercise names are strictly kept
    assert any("Romanian Deadlift" in name for name in all_exercise_names)
    assert any("Incline Dumbbell Press" in name or "Incline Barbell Bench" in name for name in all_exercise_names)
    assert any("Bulgarian Split Squat" in name for name in all_exercise_names)
    assert any("Cable Face Pulls" in name or "Face Pull" in name for name in all_exercise_names)
    assert any("Hanging Leg Raise" in name for name in all_exercise_names)
    assert any("Ab Wheel Rollout" in name for name in all_exercise_names)


def test_incomplete_output_detection_and_validation() -> None:
    # If raw input mentions 5 days but only 2 day blocks are provided
    incomplete_text = """
    Import my 5-day workout routine:
    Day 1: Push
    Bench Press 80kg 3x8
    Day 2: Pull
    Barbell Row 70kg 3x10
    """
    plan = parse_custom_workout(incomplete_text)
    is_valid, uncertainties = validate_parsed_workout_plan(plan, incomplete_text)

    # Must detect that 5 days were requested but only 2 were present
    assert is_valid is False or len(uncertainties) > 0
    assert any("5" in u and "2" in u for u in uncertainties)


def test_coach_plan_action_generates_custom_workout_import_action() -> None:
    action = coach_router._coach_plan_action_from_message(VICTOR_FIVE_DAY_INPUT, {})

    assert action is not None
    assert action["type"] == "custom_workout_import"
    assert action["scope"] == "full_plan"
    assert action["day_count"] == 5
    assert action["target_minutes"] == 90
    assert "Import 5-Day Plan" in action["button_label"]
    assert "preview" in action
    assert len(action["preview"]["days"]) == 5


@pytest.mark.anyio
async def test_apply_coach_workout_plan_action_preserves_five_days_and_ninety_min(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_inserted = []

    class FakeCollection:
        async def insert_one(self, doc: dict) -> Any:
            fake_inserted.append(doc)
            class Result:
                inserted_id = "fake-custom-plan-id"
            return Result()

        async def find_one(self, *args: Any, **kwargs: Any) -> Any:
            return None

    monkeypatch.setattr(coach_router, "strength_workout_plans_collection", FakeCollection())

    fake_user = {
        "_id": "user-12345",
        "weight": 80,
        "onboarding": {
            "personalProfile": {"weight": "80", "height": "180"},
            "anamnese": {"timePerSession": "90"},
        },
    }

    result = await coach_router._apply_coach_workout_plan_action(
        fake_user,
        source_prompt=VICTOR_FIVE_DAY_INPUT,
        scope="full_plan",
    )

    assert result is not None
    assert len(fake_inserted) == 1
    saved_doc = fake_inserted[0]

    saved_plan = saved_doc["plan"]
    assert len(saved_plan["days"]) == 5

    # Check 90 min est_time on all 5 days
    for day in saved_plan["days"]:
        assert day["est_time"] == "90 min"

    # Check 80kg Bench Press preserved on Day 1
    day_1 = saved_plan["days"][0]
    bench = next(ex for ex in day_1["exercises"] if "Bench Press" in ex["name"])
    assert "80kg" in bench["weight"].replace(" ", "")
