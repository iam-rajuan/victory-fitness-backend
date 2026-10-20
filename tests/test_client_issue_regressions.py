from app.models import CustomWorkoutDay, CustomWorkoutExercise, CustomWorkoutPlan
from app.nutrition_ai import _meal_plan_practical_constraints_instruction
from app.utils.currency import currency_for_country, normalize_weekly_food_budget
from app.workout_import import convert_custom_plan_to_strength_plan_dict, parse_custom_workout


def test_custom_workout_missing_load_never_inherits_user_bodyweight() -> None:
    plan = CustomWorkoutPlan(
        plan_name="Leg Day",
        days=[
            CustomWorkoutDay(
                day_name="Leg Day",
                day_key="Mon",
                exercises=[
                    CustomWorkoutExercise(exercise_name="Warm-up", weight="", type="Warmup"),
                    CustomWorkoutExercise(exercise_name="Cuff external rotations + band pull-aparts", weight="", type="Isolation"),
                    CustomWorkoutExercise(exercise_name="Leg Press", weight="160kg", type="Compound"),
                    CustomWorkoutExercise(exercise_name="Seated Hamstring Curl", weight="72.5kg", type="Isolation"),
                    CustomWorkoutExercise(exercise_name="Pike Push-Up", weight="", type="Compound"),
                ],
            )
        ],
    )

    converted = convert_custom_plan_to_strength_plan_dict(
        plan,
        user={"onboarding": {"personalProfile": {"weight": "75"}}},
    )
    exercises = converted["days"][0]["exercises"]

    assert [exercise["weight"] for exercise in exercises] == ["", "", "160kg", "72.5kg", "Bodyweight"]
    assert all(exercise["weight"] != "75 kg" for exercise in exercises)


def test_custom_workout_parser_preserves_independent_decimal_and_range_loads() -> None:
    parsed = parse_custom_workout(
        """
        Monday - Legs
        - Quad extension: 3 x 8, 90-95 kg, 90s rest
        - Leg press: 3 x 8, 160 kg, 90s rest
        - Hamstring curl: 3 x 10, 72.5 kg, 90s rest
        - Warm-up: 2 x 12, 60s rest
        """
    )
    exercises = parsed.days[0].exercises

    assert [exercise.weight for exercise in exercises] == ["90-95kg", "160kg", "72.5kg", ""]


def test_country_currency_mapping_covers_supported_markets() -> None:
    assert currency_for_country("DE", "Germany") == "EUR"
    assert currency_for_country("GH", "Ghana") == "GHS"
    assert currency_for_country("GB", "United Kingdom") == "GBP"
    assert currency_for_country("US", "United States") == "USD"


def test_structured_budget_uses_country_currency_and_reaches_ai_prompt() -> None:
    payload = normalize_weekly_food_budget(
        {"weekly_food_budget_amount": 500},
        country_code="GH",
        country="Ghana",
    )

    assert payload["weekly_food_budget_amount"] == 500
    assert payload["weekly_food_budget_currency"] == "GHS"
    assert payload["weekly_food_budget"] == "500 GHS"
    assert "Weekly food budget: 500 GHS" in _meal_plan_practical_constraints_instruction(payload)


def test_legacy_numeric_budget_remains_eur_after_country_change() -> None:
    payload = normalize_weekly_food_budget(
        {"weekly_food_budget": "120"},
        country_code="GH",
        country="Ghana",
    )

    assert payload["weekly_food_budget_amount"] == 120
    assert payload["weekly_food_budget_currency"] == "EUR"
    assert payload["weekly_food_budget"] == "120 EUR"


def test_budget_accepts_any_three_letter_currency_code() -> None:
    payload = normalize_weekly_food_budget({"weekly_food_budget": "10000 JPY"})

    assert payload["weekly_food_budget_amount"] == 10000
    assert payload["weekly_food_budget_currency"] == "JPY"
    assert payload["weekly_food_budget"] == "10000 JPY"
    assert "Weekly food budget: 10000 JPY" in _meal_plan_practical_constraints_instruction(payload)
