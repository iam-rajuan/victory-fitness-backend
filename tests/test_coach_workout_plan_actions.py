from __future__ import annotations

import importlib


coach_router = importlib.import_module("app.api.routers.ai_coach_victor")


def test_coach_plan_action_targets_named_day_and_minutes() -> None:
    action = coach_router._coach_plan_action_from_message("Make Monday workout 20 minutes and pull only", {})

    assert action is not None
    assert action["scope"] == "day"
    assert action["target_days"] == ["Mon"]
    assert action["target_minutes"] == 20


def test_coach_plan_action_maps_tonight_to_active_home_session() -> None:
    context = {
        "progress": {
            "current_home_workout_plan": {
                "sessions": [
                    {"day": "Mon", "completed": True},
                    {"day": "Tue", "completed": False},
                ]
            }
        }
    }

    action = coach_router._coach_plan_action_from_message("I only have 25 minutes tonight and no equipment", context)

    assert action is not None
    assert action["scope"] == "day"
    assert action["target_days"] == ["Tue"]
    assert action["target_minutes"] == 25


def test_coach_plan_action_rebuilds_full_plan() -> None:
    action = coach_router._coach_plan_action_from_message("Generate a new workout plan for my week", {})

    assert action is not None
    assert action["scope"] == "full_plan"
    assert action["target_days"] == []
