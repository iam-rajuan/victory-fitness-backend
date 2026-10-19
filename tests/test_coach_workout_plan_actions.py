from __future__ import annotations

import importlib

import pytest

from app.coach_victor import _generate_intelligent_fallback_reply
from app.workout_import import WorkoutIntent, classify_workout_message_intent, parse_custom_workout


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


def test_plan_action_is_hidden_when_generated_reply_is_not_insertable() -> None:
    action = coach_router._insertable_coach_plan_action(
        "Generate a new workout plan for my week",
        "Focus on consistent training and progressive overload this week.",
        {},
    )

    assert action is None


def test_plan_action_is_visible_when_generated_reply_is_insertable() -> None:
    generated_reply = """
    Day 1 — Full Body
    - Barbell squat: 3 x 8, 60kg, 90s rest
    - Bench press: 3 x 8, 50kg, 90s rest
    """

    action = coach_router._insertable_coach_plan_action(
        "Generate a new workout plan for my week",
        generated_reply,
        {},
    )

    assert action is not None
    assert action["day_count"] == 1
    assert action["preview"]["days"]


def test_generated_markdown_plan_is_parseable_and_insertable() -> None:
    generated_reply = _generate_intelligent_fallback_reply(
        [{"role": "user", "content": "Generate a new 5-day workout plan for 45 minutes"}],
        user_context={},
    )

    parsed = parse_custom_workout(generated_reply, {})
    action = coach_router._insertable_coach_plan_action(
        "Generate a new 5-day workout plan for 45 minutes",
        generated_reply,
        {},
    )

    assert parsed.is_valid is True
    assert len(parsed.days) == 5
    assert action is not None
    assert action["day_count"] == 5


def test_dense_existing_routine_uses_structured_generated_reply_for_card() -> None:
    dense_message = (
        "I want exactly this 2 day workout: Day 1 bench press 100kg 3x7 and rows 90kg 3x8. "
        "Day 2 squat 130kg 3x8 and RDL 160kg 3x8. Keep these exact weights."
    )
    generated_reply = """
Day 1 (Mon): Upper
- Bench Press: 3 x 7, 120s rest, 100kg, Compound
- Barbell Row: 3 x 8, 90s rest, 90kg, Compound
Est. time: 90 min
Day 2 (Tue): Lower
- Back Squat: 3 x 8, 120s rest, 130kg, Compound
- RDL: 3 x 8, 120s rest, 160kg, Compound
Est. time: 90 min
"""

    action = coach_router._insertable_coach_plan_action(dense_message, generated_reply, {})

    assert action is not None
    assert action["day_count"] == 2
    assert len(action["preview"]["days"]) == 2


def test_insert_confirmation_reuses_persisted_draft_instead_of_parsing_claim_text() -> None:
    preview = {
        "plan_name": "Five Day Plan",
        "expected_duration": 90,
        "equipment": ["Barbell"],
        "days": [{"day_name": "Day 1", "day_key": "Mon", "expected_duration": 90, "equipment": ["Barbell"], "exercises": []}],
        "is_valid": True,
    }
    context = {
        "recent_messages": [{"role": "assistant", "content": "Day 1 workout plan"}],
        "workout_draft_state": {"preview": preview, "scope": "full_plan", "version": 1},
    }

    action = coach_router._insertable_coach_plan_action(
        "Insert it to my workout plan",
        "Your plan is now active.",
        context,
    )

    assert action is not None
    assert action["preview"] == preview
    assert action["button_label"] == "Apply to Home plan"


@pytest.mark.parametrize(
    "message",
    [
        "Swap bench press for push-ups in my workout",
        "Reduce my workout volume to 2 sets",
        "Change my plan to bodyweight only",
        "Shorten tonight's session to 20 minutes",
        "Add curls to my pull workout",
        "Remove squats because my knee is sore",
    ],
)
def test_common_home_plan_adjustments_are_recognized(message: str) -> None:
    assert classify_workout_message_intent(message, {}) == WorkoutIntent.ADJUST_CURRENT


def test_follow_up_plan_refinement_uses_recent_conversation_context() -> None:
    context = {
        "recent_messages": [
            {"role": "assistant", "content": "Day 1: Push workout plan with 3 sets and 10 reps."},
        ]
    }

    action = coach_router._coach_plan_action_from_message("Make it shorter instead", context)

    assert action is not None


def test_five_minute_day_update_keeps_exercises_from_fallback() -> None:
    fallback_day = {
        "day": "Mon",
        "title": "Full Body Strength",
        "est_time": "25 min",
        "volume": "3 exercises",
        "intensity": "Moderate",
        "exercises": [
            {"id": "ex-1", "name": "Push-Up", "sets": 3, "reps": "8-12", "rest": "60s", "weight": "Bodyweight", "type": "Compound"},
            {"id": "ex-2", "name": "Bodyweight Squat", "sets": 3, "reps": "8-12", "rest": "60s", "weight": "Bodyweight", "type": "Compound"},
            {"id": "ex-3", "name": "Plank", "sets": 3, "reps": "30s", "rest": "45s", "weight": "Bodyweight", "type": "Core"},
        ],
    }

    adjusted = coach_router._ensure_adjusted_day_has_exercises(
        {"day": "Mon", "title": "Upper Body Strength", "est_time": "5 min", "exercises": []},
        fallback_day=fallback_day,
        target_day="Mon",
        minutes=5,
    )

    assert adjusted["est_time"] == "5 min"
    assert len(adjusted["exercises"]) == 2
    assert adjusted["exercises"][0]["sets"] <= 2
    assert adjusted["exercises"][0]["rest"] == "45s"
