import pytest
from app.nutrition_ai import (
    _build_fallback_nutrition_plan,
    _favorite_meals_instruction,
    _workout_nutrient_timing_instruction,
    _protein_target_instruction,
    _normalize_nutrition_plan,
    calculate_protein_target,
)


def test_feature_favourite_meals_ghana_user_italian_favourites():
    """Verify Ghana user with Italian favourites gets Italian meals, never country defaults."""
    payload = {
        "weight": "80",
        "goal": "g3",
        "country": "Ghana",
        "cuisine": "Italian",
        "favorite_meals": ["Pasta Carbonara", "Margherita Pizza", "Mushroom Risotto"],
    }

    # 1. Verify prompt instruction strictly mandates Italian favourites over country defaults
    prompt_inst = _favorite_meals_instruction(payload)
    assert "CRITICAL FAVOURITE MEALS & CULINARY MANDATE" in prompt_inst
    assert "Ghana" in prompt_inst
    assert "Pasta Carbonara, Margherita Pizza, Mushroom Risotto" in prompt_inst
    assert "Italian" in prompt_inst
    assert "STRICTLY FORBIDDEN: NEVER fall back to or introduce country-of-origin" in prompt_inst

    # 2. Verify generated fallback plan exclusively uses the Italian dishes, NO Ghanaian defaults
    plan = _build_fallback_nutrition_plan(payload)
    plan_text = str(plan).lower()

    # Must contain the Italian favourites
    assert "pasta carbonara" in plan_text or "margherita pizza" in plan_text
    # Must NOT contain Ghanaian country defaults
    assert "fufu" not in plan_text
    assert "banku" not in plan_text
    assert "jollof" not in plan_text


def test_feature_pre_workout_meal_scheduled_60_90_mins_before_carb_forward():
    """Verify pre-workout meal is scheduled 60-90 mins before workout and is carb-forward."""
    payload = {
        "weight": "80",
        "goal": "g3",
        "workout_time": "17:30",
        "favorite_meals": ["Pasta Carbonara", "Chicken Rice Bowl", "Salmon Quinoa"],
    }

    timing_inst = _workout_nutrient_timing_instruction(payload)
    assert "PRE-WORKOUT MEAL" in timing_inst
    assert "60–90 minutes BEFORE" in timing_inst
    assert "CARB-FORWARD" in timing_inst

    plan = _build_fallback_nutrition_plan(payload)
    mon = plan["days"][0]
    lunch = mon["lunch"]

    # Must note scheduling 60-90 mins before workout
    assert "60–90 mins before" in lunch["desc"].lower() or "pre-workout" in lunch["name"].lower()
    # Must be carb-forward (carbs higher than fat and substantial)
    assert lunch["c"] >= 50
    assert lunch["c"] > lunch["f"]


def test_feature_post_workout_meal_scheduled_within_45_mins_protein_forward():
    """Verify post-workout meal is scheduled within 45 mins of workout end and is protein-forward."""
    payload = {
        "weight": "80",
        "goal": "g3",
        "workout_time": "17:30",
        "favorite_meals": ["Pasta Carbonara", "Chicken Rice Bowl", "Salmon Quinoa"],
    }

    timing_inst = _workout_nutrient_timing_instruction(payload)
    assert "POST-WORKOUT MEAL" in timing_inst
    assert "within 45 minutes AFTER" in timing_inst
    assert "PROTEIN-FORWARD" in timing_inst

    plan = _build_fallback_nutrition_plan(payload)
    mon = plan["days"][0]
    post_meal = mon.get("post_workout") or mon["dinner"]

    # Must note post-workout timing within 45 mins
    assert "within 45 mins" in post_meal["desc"].lower() or "post-workout" in post_meal["name"].lower()
    # Must be protein-forward (high protein)
    assert post_meal["p"] >= 25


def test_feature_total_protein_80kg_user_hits_128g_average():
    """Verify 80kg user plan hits 1.6g/kg ±5g (128g ± 5g: 123g–133g)."""
    payload = {
        "weight": "80",
        "goal": "g3",
        "cuisine": "Italian",
        "favorite_meals": ["Pasta Carbonara", "Margherita Pizza", "Mushroom Risotto"],
    }

    # Prompt instruction
    p_inst = _protein_target_instruction(payload)
    assert "128g" in p_inst
    assert "1.6g/kg ±5g" in p_inst

    # Fallback plan
    plan = _build_fallback_nutrition_plan(payload)
    assert plan["daily_protein_target"] == 128
    assert plan["protein_per_kg"] == 1.6

    # Verify 7-day average protein
    days = plan["days"]
    assert len(days) == 7
    daily_totals = [sum(m["p"] for k, m in d.items() if k != "day" and isinstance(m, dict)) for d in days]
    avg_protein = sum(daily_totals) / 7.0

    # 1.6g/kg of 80kg = 128g. Must be 128g ± 5g
    assert abs(avg_protein - 128.0) <= 5.0
    assert 123.0 <= avg_protein <= 133.0


def test_normalizer_enforces_1_6g_per_kg_even_with_deviant_plan():
    """Verify normalizer auto-adjusts any raw LLM plan so the 7-day average hits 1.6g/kg ± 5g."""
    deviant_plan = {
        "summary": "Raw plan with low protein",
        "goal_label": "Test",
        "baseline_weight": 80.0,
        "daily_protein_target": 70,  # Far below 128g
        "days": [
            {
                "day": day,
                "breakfast": {"name": "Toast", "desc": "Light toast", "kcal": 200, "p": 5, "c": 30, "f": 5, "ingredients": [], "instructions": []},
                "lunch": {"name": "Salad", "desc": "Light salad", "kcal": 250, "p": 10, "c": 20, "f": 5, "ingredients": [], "instructions": []},
                "dinner": {"name": "Soup", "desc": "Veg soup", "kcal": 200, "p": 8, "c": 25, "f": 5, "ingredients": [], "instructions": []},
            }
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ],
        "shopping_list": [],
    }

    normalized = _normalize_nutrition_plan(deviant_plan)
    daily_totals = [sum(m["p"] for k, m in d.items() if k != "day" and isinstance(m, dict)) for d in normalized["days"]]
    avg_p = sum(daily_totals) / 7.0

    # Must be corrected to 128g ± 5g
    assert abs(avg_p - 128.0) <= 5.0
    assert normalized["daily_protein_target"] == 128


@pytest.mark.anyio
async def test_trial_campaign_day1_nutrition_nudge():
    """Verify trial user who hasn't used Nutrition Planner by Day 1 receives targeted nudge."""
    from unittest.mock import AsyncMock, patch
    from datetime import datetime, timezone, timedelta
    from app.trial_campaign import process_trial_campaign
    from bson import ObjectId

    now = datetime.now(timezone.utc)
    started_at = now - timedelta(days=1, hours=2)  # Day 1 of trial

    user = {
        "_id": ObjectId(),
        "name": "TrialUser",
        "email": "trial@example.com",
        "trial_tier_granted": "gold",
        "trial_start_at": started_at,
        "subscription_tier": "GOLD",
        "subscription_purchase_source": "beta_trial",
        "trial_campaign_sent_days": [0],  # Day 0 sent, Day 1 due
        "marketing_consent": True,
    }

    from unittest.mock import MagicMock
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[user])
    mock_users_collection = MagicMock()
    mock_users_collection.find.return_value = mock_cursor
    mock_users_collection.update_one = AsyncMock()

    mock_app_content = MagicMock()
    mock_app_content.find_one = AsyncMock(return_value=None)

    # Empty nutrition collections -> user hasn't used nutrition planner
    mock_threads_cursor = MagicMock()
    mock_threads_cursor.to_list = AsyncMock(return_value=[])
    mock_threads = MagicMock()
    mock_threads.find.return_value = mock_threads_cursor
    mock_plans = MagicMock()
    mock_plans.count_documents = AsyncMock(return_value=0)
    mock_logs = MagicMock()
    mock_logs.count_documents = AsyncMock(return_value=0)

    with patch("app.trial_campaign.notify_user", new_callable=AsyncMock) as mock_notify, \
         patch("app.trial_campaign.send_trial_campaign_email") as mock_email:
        await process_trial_campaign(
            users_collection=mock_users_collection,
            challenge_memberships_collection=None,
            challenges_collection=None,
            coach_threads_collection=mock_threads,
            nutrition_plans_collection=mock_plans,
            nutrition_logs_collection=mock_logs,
            app_content_collection=mock_app_content,
            now=now,
        )

        assert mock_notify.called
        call_args = mock_notify.call_args[0]
        # Signature: notify_user(users_collection, user, title, message, notification_type, data)
        title = call_args[2]
        message = call_args[3]
        notification_type = call_args[4]
        data = call_args[5]

        assert "Nutrition" in title or "meal plan" in title.lower()
        assert "haven't set up your" in message.lower() or "meal plan" in message.lower()
        assert notification_type == "trial_day_1_nutrition_nudge"
        assert data.get("route") == "/mealPlan"
        assert data.get("targeted_nudge") == "nutrition_planner_unused"


def test_feature_separate_pre_and_post_workout_distinct_meals():
    """Verify distinct pre_workout and post_workout meal slots exist and sum accurately."""
    payload = {
        "weight": "80",
        "goal": "g3",
        "workout_time": "17:30",
        "cuisine": "Italian",
        "favorite_meals": ["Pasta Carbonara", "Margherita Pizza", "Mushroom Risotto"],
    }
    plan = _build_fallback_nutrition_plan(payload)
    mon = plan["days"][0]

    # Verify all 5 distinct meal slots exist
    assert "breakfast" in mon
    assert "lunch" in mon
    assert "pre_workout" in mon
    assert "post_workout" in mon
    assert "dinner" in mon

    # Pre-workout meal: carb-forward, 60-90m before workout
    pre = mon["pre_workout"]
    assert "pre-workout" in pre["name"].lower()
    assert pre["c"] >= 50
    assert pre["c"] > pre["f"]
    assert pre["f"] <= 8

    # Post-workout meal: high protein, within 45m
    post = mon["post_workout"]
    assert "post-workout" in post["name"].lower()
    assert post["p"] >= 25

    # Verify total daily protein calculation sums accurately across all meals
    total_p = mon["breakfast"]["p"] + mon["lunch"]["p"] + mon["pre_workout"]["p"] + mon["post_workout"]["p"] + mon["dinner"]["p"]
    # 80kg * 1.6 = 128g ± 5g
    assert 120 <= total_p <= 140

    # Verify each meal strictly adheres to macro math kcal = (p*4) + (c*4) + (f*9)
    for k in ["breakfast", "lunch", "pre_workout", "post_workout", "dinner"]:
        meal = mon[k]
        expected_kcal = (meal["p"] * 4) + (meal["c"] * 4) + (meal["f"] * 9)
        assert abs(meal["kcal"] - expected_kcal) <= 5


def test_nutrition_json_schemas_require_pre_and_post_workout():
    """Verify NUTRITION_PLAN_JSON_SCHEMA, Monday schema, and Day schema require pre_workout and post_workout."""
    from app.nutrition_ai import (
        NUTRITION_PLAN_JSON_SCHEMA,
        NUTRITION_PLAN_MONDAY_JSON_SCHEMA,
        NUTRITION_PLAN_DAY_JSON_SCHEMA,
    )

    day_schema = NUTRITION_PLAN_JSON_SCHEMA["schema"]["properties"]["days"]["items"]
    assert "pre_workout" in day_schema["required"]
    assert "post_workout" in day_schema["required"]
    assert "pre_workout" in day_schema["properties"]
    assert "post_workout" in day_schema["properties"]

    mon_day_schema = NUTRITION_PLAN_MONDAY_JSON_SCHEMA["schema"]["properties"]["day"]
    assert "pre_workout" in mon_day_schema["required"]
    assert "post_workout" in mon_day_schema["required"]

    single_day_schema = NUTRITION_PLAN_DAY_JSON_SCHEMA["schema"]["properties"]["day"]
    assert "pre_workout" in single_day_schema["required"]
    assert "post_workout" in single_day_schema["required"]


