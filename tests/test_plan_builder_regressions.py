from app.api.routers.ai_workout_plan import _hydrate_strength_plan_input
from app.models import StrengthWorkoutPlanRequest
from app.workout_plan_ai import StrengthWorkoutPlanInput, _build_strength_workout_plan, EXERCISE_BY_NAME


def _builder_input(**overrides) -> StrengthWorkoutPlanInput:
    values = {
        "goal": "Get stronger",
        "level": "Intermediate",
        "split": "Upper / Lower",
        "height": "175",
        "gender": "Other",
        "bench": "",
        "squat": "",
        "deadlift": "",
        "equipment": ["Gym", "Barbell", "Dumbbells", "Cables", "Machines"],
        "frequency": "4",
        "days": ["Mon", "Tue", "Thu", "Fri"],
        "age": "28",
        "weight": "75",
        "muscle_group": "Full Body",
        "duration_minutes": "90",
        "injury_flags": ["knee"],
        "custom_notes": "Plan builder priority",
    }
    values.update(overrides)
    return StrengthWorkoutPlanInput(**values)


def test_four_day_builder_creates_real_upper_lower_sessions() -> None:
    plan = _build_strength_workout_plan(_builder_input())

    assert [day["title"] for day in plan["days"]] == [
        "Upper Body Strength",
        "Lower Body Strength",
        "Upper Body Volume",
        "Lower Body Volume",
    ]
    lower_muscles = {"legs", "quads", "hamstrings", "glutes", "calves"}
    upper_muscles = {"chest", "back", "shoulders", "arms", "biceps", "triceps"}
    for index, day in enumerate(plan["days"]):
        for exercise in day["exercises"]:
            muscles = set(EXERCISE_BY_NAME[exercise["name"].lower()]["muscles"])
            if index % 2 == 0:
                assert muscles & upper_muscles, exercise["name"]
                assert not muscles & lower_muscles, exercise["name"]
            else:
                assert muscles & (lower_muscles | {"core"}), exercise["name"]
                assert not muscles & upper_muscles, exercise["name"]


def test_knee_substitutions_are_unique_and_do_not_create_three_deadlifts() -> None:
    plan = _build_strength_workout_plan(_builder_input())

    for day in plan["days"]:
        names = [exercise["name"] for exercise in day["exercises"]]
        assert len(names) == len(set(names))
        assert sum("deadlift" in name.lower() for name in names) <= 1
        assert not any(term in name.lower() for name in names for term in ("squat", "lunge", "leg press", "leg extension", "jump"))


def test_builder_without_verified_lifts_does_not_invent_precise_kg() -> None:
    plan = _build_strength_workout_plan(_builder_input(injury_flags=[]))
    weights = [exercise["weight"] for day in plan["days"] for exercise in day["exercises"]]

    assert "68kg" not in weights
    assert "43kg" not in weights
    assert "34kg" not in weights
    assert "Set starting weight" in weights


def test_current_builder_answers_override_older_onboarding_preferences() -> None:
    user = {
        "_id": "user-1",
        "injury_flags": ["knee"],
        "onboarding": {
            "anamnese": {
                "primaryGoal": "Lose weight",
                "daysPerWeek": "2 days",
                "timePerSession": "25 min",
                "equipmentAccess": "No equipment",
            },
            "personalProfile": {"weight": "82"},
        },
    }
    payload = StrengthWorkoutPlanRequest(
        goal="Get stronger",
        split="Upper / Lower",
        muscle_group="Full Body",
        duration_minutes="90",
        equipment=["Gym", "Barbell", "Dumbbells", "Cables", "Machines"],
        frequency="4",
        days=["Mon", "Tue", "Thu", "Fri"],
    )

    hydrated = _hydrate_strength_plan_input(payload, user)

    assert hydrated.goal == "Get stronger"
    assert hydrated.split == "Upper / Lower"
    assert hydrated.duration_minutes == "90"
    assert hydrated.frequency == "4"
    assert hydrated.days == ["Mon", "Tue", "Thu", "Fri"]
    assert hydrated.equipment == ["Gym", "Barbell", "Dumbbells", "Cables", "Machines"]
    assert hydrated.injury_flags == ["knee"]
