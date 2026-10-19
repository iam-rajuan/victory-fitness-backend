"""Regression tests for AI workout-generation/coaching context, prompts, and intent separation.

CLIENT EXPECTATION & REGRESSION COVERAGE:
- Deterministic context before generation (10 dimensions: goal, level, age, equipment,
  injuries, training days, duration, existing routine, known weights, recent plan)
- Clear intent separation:
  - Use Case A: CREATE a workout (AI recommends new program tailored to context)
  - Use Case B: IMPORT/USE existing workout (AI preserves routine verbatim without inventing replacement)
- Structural completeness and validation before saving
- Regression tests for:
  1. Beginner new plan
  2. Home equipment
  3. Full gym
  4. Experienced user importing own plan
  5. Five-day split
  6. 90-minute requested duration
"""

from typing import Any
import pytest

from app.coach_victor import (
    build_coach_victor_system_prompt,
    _generate_intelligent_fallback_reply,
)
from app.workout_import import (
    WorkoutIntent,
    assemble_deterministic_workout_context,
    classify_workout_message_intent,
    parse_custom_workout,
    validate_strength_plan_structure,
)
from app.workout_plan_ai import (
    StrengthWorkoutPlanInput,
    _build_strength_workout_plan,
    generate_strength_workout_plan,
)
import app.api.routers.ai_coach_victor as coach_router

SAMPLE_USER_CONTEXT = {
    "name": "Sarah",
    "country": "Germany",
    "country_code": "DE",
    "subscription_tier": "GOLD",
    "onboarding": {
        "personalProfile": {
            "age": "32",
            "gender": "Female",
            "height": "172",
            "heightUnit": "cm",
            "weight": "68",
            "weightUnit": "kg",
            "bench": "60",
            "squat": "90",
            "deadlift": "110",
        },
        "anamnese": {
            "primaryGoal": "Hypertrophy",
            "activityLevel": "Intermediate",
            "daysPerWeek": "4",
            "timePerSession": "60 min",
            "equipmentAccess": "Gym",
            "healthNotes": "None",
        },
    },
    "medical": {
        "health_notes": "Mild left wrist sensitivity",
        "injury": "Wrist",
    },
    "progress": {
        "streak_days": 12,
        "recent_completed_workouts": 8,
        "current_home_workout_plan": {
            "summary": "4-Day Upper / Lower Split",
            "sessions": [
                {"day": "Mon", "completed": True},
                {"day": "Tue", "completed": False},
            ],
        },
    },
}

EXPERIENCED_FIVE_DAY_IMPORT_TEXT = """
Day 1 - Chest & Triceps:
- Bench Press: 4 sets of 8 reps @ 80kg, 90s rest
- Incline Dumbbell Press: 3 sets of 10 reps @ 28kg, 60s rest
- Cable Tricep Pushdown: 3 sets of 12 reps @ 35kg, 45s rest
- Dips: 3 sets of 10 reps, 60s rest

Day 2 - Back & Biceps:
- Barbell Deadlift: 4 sets of 6 reps @ 140kg, 120s rest
- Pull-ups: 4 sets of 8 reps, 90s rest
- Barbell Bent-Over Row: 3 sets of 10 reps @ 75kg, 60s rest
- Dumbbell Hammer Curl: 3 sets of 12 reps @ 16kg, 45s rest

Day 3 - Legs:
- Barbell Back Squat: 4 sets of 8 reps @ 120kg, 120s rest
- Romanian Deadlift: 3 sets of 10 reps @ 100kg, 90s rest
- Leg Press: 3 sets of 12 reps @ 180kg, 60s rest
- Standing Calf Raise: 4 sets of 15 reps, 45s rest

Day 4 - Shoulders & Abs:
- Overhead Barbell Press: 4 sets of 8 reps @ 50kg, 90s rest
- Dumbbell Lateral Raise: 4 sets of 15 reps @ 12kg, 45s rest
- Face Pulls: 3 sets of 15 reps @ 25kg, 45s rest
- Hanging Leg Raise: 3 sets of 15 reps, 45s rest

Day 5 - Full Body Hypertrophy:
- Front Squat: 3 sets of 8 reps @ 80kg, 90s rest
- Incline Dumbbell Row: 3 sets of 10 reps @ 30kg, 60s rest
- Dumbbell Flat Bench: 3 sets of 10 reps @ 32kg, 60s rest
- Cable Lateral Raise: 3 sets of 15 reps, 45s rest

Target 90 minutes per session. Full gym access.
"""


def test_deterministic_workout_context_assembly() -> None:
    """Verifies that all 10 deterministic training context dimensions are accurately extracted."""
    message = "I want to build a pure strength program, I am an advanced lifter, 5 days per week, 90 minutes per workout"
    context = assemble_deterministic_workout_context(
        user=None,
        user_context=SAMPLE_USER_CONTEXT,
        message=message,
    )

    # 1. User goal
    assert context["goal"] == "Pure Strength"
    # 2. Experience level
    assert context["experience_level"] == "Advanced"
    # 3. Age
    assert context["age"] == "32"
    # 4. Equipment
    assert "Gym" in context["equipment"] or "Barbell" in context["equipment"]
    # 5. Injuries / Restrictions
    assert "wrist" in context["injuries_restrictions"] or "Mild left wrist sensitivity" in context["health_notes"]
    # 6. Training days & Frequency
    assert context["frequency"] == 5
    assert len(context["training_days"]) == 5
    # 7. Expected workout duration (NEVER collapse to 25!)
    assert context["expected_duration_minutes"] == 90
    # 8. Known weights/reps
    assert context["known_weights"]["bench"] == "60"
    assert context["known_weights"]["squat"] == "90"
    assert context["known_weights"]["deadlift"] == "110"
    assert context["known_weights"]["bodyweight"] == "68"
    # 9. Existing routine (None supplied for creation intent)
    assert context["existing_routine"] is None
    # 10. Recent plan info
    assert "Upper / Lower" in context["recent_plan_summary"]


def test_intent_separation_create_vs_import() -> None:
    """Strictly verifies that Create New (Use Case A) and Import Existing (Use Case B) are not mixed."""
    # Use Case A: CREATE
    create_queries = [
        "Create a 5-day workout plan for 90 minutes",
        "Build me a beginner workout routine with dumbbells",
        "Make a new strength training program for full gym",
        "Can you recommend a 3-day hypertrophy plan?",
    ]
    for q in create_queries:
        intent = classify_workout_message_intent(q, SAMPLE_USER_CONTEXT)
        assert intent == WorkoutIntent.CREATE_NEW, f"Expected CREATE_NEW for query: '{q}', got {intent}"

    # Use Case B: IMPORT
    import_queries = [
        EXPERIENCED_FIVE_DAY_IMPORT_TEXT,
        "Here is my existing workout:\nDay 1: Bench Press 3x10 @ 80kg\nDay 2: Squat 3x8 @ 100kg\nImport this into my plan.",
        "Use my current routine:\nMonday - Push: Dumbbell Press 4x8, Tricep Pushdown 3x12\nWednesday - Pull: Pull-ups 3x8, Rows 3x10\nFriday - Legs: Squats 4x10",
    ]
    for q in import_queries:
        intent = classify_workout_message_intent(q, SAMPLE_USER_CONTEXT)
        assert intent == WorkoutIntent.IMPORT_EXISTING, f"Expected IMPORT_EXISTING for query: '{q[:50]}...', got {intent}"


def test_system_prompt_includes_deterministic_layers_and_intent_boundaries() -> None:
    """Verifies that Coach Victor's system prompt deterministically provides context and intent boundaries."""
    prompt = build_coach_victor_system_prompt(
        user_context=SAMPLE_USER_CONTEXT,
        recent_messages=[
            {"role": "user", "content": "Create a 5-day workout plan for 90 minutes"},
        ],
    )

    assert "Layer 3.5 - Deterministic Workout & Coaching Context:" in prompt
    assert "user goal: Hypertrophy" in prompt or "Pure Strength" in prompt
    assert "training days (5 days/week):" in prompt
    assert "base workout duration: 90 minutes per session" in prompt
    assert "latest user message explicitly requests a different duration" in prompt
    assert "TWO DISTINCT WORKOUT USE CASES (DO NOT MIX INTENTS):" in prompt
    assert "A. User asks AI to CREATE a workout:" in prompt
    assert "B. User asks AI to IMPORT/USE their existing workout:" in prompt


def test_regression_beginner_new_plan() -> None:
    """Regression test 1: Beginner new plan must respect beginner level, moderate sets, and safe movements."""
    inp = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Beginner",
        split="Full Body",
        height="175",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Gym", "Barbell", "Dumbbells"],
        frequency="3",
        days=["Mon", "Wed", "Fri"],
        age="24",
        weight="70",
        duration_minutes="45",
    )
    plan = _build_strength_workout_plan(inp)

    assert len(plan["days"]) == 3
    for day in plan["days"]:
        # Beginner exercises should have reasonable set volumes (typically 3 sets, not excessive 5 sets)
        for ex in day["exercises"]:
            assert 1 <= ex["sets"] <= 4, f"Beginner set count unexpected: {ex['sets']}"
            assert ex["name"], "Exercise name must be present"

    is_valid, errors = validate_strength_plan_structure(plan, expected_days=3)
    assert is_valid, f"Beginner plan validation failed: {errors}"


def test_regression_home_equipment() -> None:
    """Regression test 2: Home equipment plan must contain strictly dumbbell/bodyweight movements (no barbells/cables)."""
    inp = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Full Body",
        height="180",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Dumbbells"],
        frequency="3",
        days=["Mon", "Wed", "Fri"],
        age="30",
        weight="78",
        duration_minutes="45",
    )
    plan = _build_strength_workout_plan(inp)

    forbidden_equipment_terms = ["barbell", "cable", "machine", "smith", "rack", "leg press", "lat pulldown"]
    for day in plan["days"]:
        for ex in day["exercises"]:
            name_lower = ex["name"].lower()
            for forbidden in forbidden_equipment_terms:
                assert forbidden not in name_lower, f"Home equipment plan contains forbidden equipment: {ex['name']}"

    is_valid, errors = validate_strength_plan_structure(plan, expected_days=3)
    assert is_valid, f"Home equipment plan validation failed: {errors}"


def test_regression_full_gym() -> None:
    """Regression test 3: Full gym plan must include compound barbell and cable/machine work."""
    inp = StrengthWorkoutPlanInput(
        goal="Pure Strength",
        level="Advanced",
        split="Push Pull Legs",
        height="185",
        gender="Male",
        bench="100",
        squat="140",
        deadlift="180",
        equipment=["Gym", "Barbell", "Dumbbells", "Cables", "Machines"],
        frequency="5",
        days=["Mon", "Tue", "Wed", "Fri", "Sat"],
        age="28",
        weight="85",
        duration_minutes="90",
    )
    plan = _build_strength_workout_plan(inp)

    all_exercises = [ex["name"].lower() for day in plan["days"] for ex in day["exercises"]]
    # Should include compound barbell movements
    has_barbell = any("barbell" in name or "deadlift" in name or "squat" in name or "bench" in name for name in all_exercises)
    assert has_barbell, "Full gym plan missing barbell/compound movements"

    is_valid, errors = validate_strength_plan_structure(plan, expected_days=5, min_duration_minutes=90)
    assert is_valid, f"Full gym plan validation failed: {errors}"


def test_regression_experienced_user_import_own_plan() -> None:
    """Regression test 4: Experienced user importing own plan must preserve routine verbatim without substitution."""
    parsed = parse_custom_workout(EXPERIENCED_FIVE_DAY_IMPORT_TEXT, SAMPLE_USER_CONTEXT)

    assert parsed.is_valid
    assert len(parsed.days) == 5, f"Expected all 5 days preserved, got {len(parsed.days)}"
    assert parsed.expected_duration == 90, f"Expected 90 minutes, got {parsed.expected_duration}"

    # Check Day 1 exercises and 80kg weight retention
    day1 = parsed.days[0]
    bench_ex = next((e for e in day1.exercises if "Bench Press" in e.exercise_name), None)
    assert bench_ex is not None, "Bench Press must be preserved verbatim in Day 1"
    assert "80" in bench_ex.weight, f"Expected 80kg Bench Press preserved, got {bench_ex.weight}"
    assert bench_ex.sets == 4 or bench_ex.sets == 3
    assert "8" in str(bench_ex.reps)

    # Convert to strength plan and validate
    plan_dict = coach_router.convert_custom_plan_to_strength_plan_dict(parsed, SAMPLE_USER_CONTEXT)
    is_valid, errors = validate_strength_plan_structure(
        plan_dict,
        expected_days=5,
        min_duration_minutes=90,
        required_weights=["80kg"],
    )
    assert is_valid, f"Experienced user import structural validation failed: {errors}"


def test_regression_five_day_split() -> None:
    """Regression test 5: 5-day split produces exactly 5 distinct training days."""
    inp = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Push Pull Legs",
        height="180",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Gym", "Barbell", "Dumbbells"],
        frequency="5",
        days=["Mon", "Tue", "Wed", "Fri", "Sat"],
        age="26",
        weight="77",
        duration_minutes="60",
    )
    plan = _build_strength_workout_plan(inp)

    assert len(plan["days"]) == 5, f"Expected 5 days, got {len(plan['days'])}"
    day_names = [d["day"] for d in plan["days"]]
    assert len(set(day_names)) == 5, f"Duplicate day keys in 5-day split: {day_names}"
    for day in plan["days"]:
        assert len(day["exercises"]) >= 3, f"Day {day['day']} has insufficient exercises"

    is_valid, errors = validate_strength_plan_structure(plan, expected_days=5)
    assert is_valid, f"5-day split validation failed: {errors}"


def test_regression_ninety_minute_requested_duration() -> None:
    """Regression test 6: 90-minute requested duration preserves 90 min and never collapses to 25 min."""
    # Test generation with 90 min
    inp = StrengthWorkoutPlanInput(
        goal="Pure Strength",
        level="Intermediate",
        split="Upper / Lower",
        height="180",
        gender="Male",
        bench="",
        squat="",
        deadlift="",
        equipment=["Gym", "Barbell", "Dumbbells"],
        frequency="4",
        days=["Mon", "Tue", "Thu", "Fri"],
        age="29",
        weight="82",
        duration_minutes="90",
    )
    plan = _build_strength_workout_plan(inp)

    for day in plan["days"]:
        est_time = day["est_time"]
        assert est_time == "90 min", f"Expected 90 min, got {est_time} (collapsed!)"
        # 90-minute session should have expanded volume (at least 5-7 exercises)
        assert len(day["exercises"]) >= 5, f"90-minute day has only {len(day['exercises'])} exercises"

    is_valid, errors = validate_strength_plan_structure(plan, min_duration_minutes=90)
    assert is_valid, f"90-minute validation failed: {errors}"


@pytest.mark.anyio
async def test_structural_validation_rejects_corrupted_plan_before_saving(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensures that invalid/incomplete plans are rejected before saving to DB."""
    fake_inserted = []

    class FakeCollection:
        async def insert_one(self, doc: dict) -> Any:
            fake_inserted.append(doc)
            class Result:
                inserted_id = "fake-id"
            return Result()

        async def find_one(self, *args: Any, **kwargs: Any) -> Any:
            return None

    monkeypatch.setattr(coach_router, "strength_workout_plans_collection", FakeCollection())

    fake_user = {
        "_id": "user-test-val",
        "onboarding": {"personalProfile": {}, "anamnese": {}},
    }

    # 1. Direct structural validation rejection on incomplete/corrupted plan
    corrupted_plan = {
        "days": [
            {
                "day": "Mon",
                "title": "Corrupted Day",
                "est_time": "20 min",  # Much lower than 90 min requested
                "exercises": [
                    {"name": "Bad Exercise 1", "sets": 0},  # Invalid sets (< 1)
                    {"name": "Exercise 2", "sets": 3},
                ],
            }
        ]
    }
    is_valid, errors = validate_strength_plan_structure(corrupted_plan, expected_days=5, min_duration_minutes=90)
    assert not is_valid
    assert any("expected 5 days" in e.lower() for e in errors)
    assert any("lower than requested 90 min" in e.lower() for e in errors)
    assert any("invalid sets count" in e.lower() for e in errors)

    # 2. Verify _apply_coach_workout_plan_action raises 422 HTTPException if plan is corrupted
    monkeypatch.setattr(coach_router, "generate_strength_workout_plan", lambda *args, **kwargs: {"days": []})
    with pytest.raises(coach_router.HTTPException) as exc_info:
        await coach_router._apply_coach_workout_plan_action(
            fake_user,
            source_prompt="Create a workout plan",
            scope="full_plan",
        )
    assert exc_info.value.status_code == 422

    # Verify nothing was inserted into DB
    assert len(fake_inserted) == 0, "Corrupted plan was inserted into database!"
