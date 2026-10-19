from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.routers import ai_coach_victor as coach_router
from app.workout_import import parse_custom_workout


GENERATED_COACH_PLAN = """
Your 5-Day Custom Routine — Locked & Ready

Day 1 (Mon): Torso A — Push Focus
- **Flat Bench (Smith/Machine): 3 × 6–7**, 2 min rest, 100kg, Compound
Mobilize shoulders first. If all three sets hit 7, add 2.5kg next week.
- **Incline Cable Fly: 3 × 10–12**, 90s rest, 32.5kg, Isolation
Nudge from controlled movement.
- **Pull-ups (Weighted): 3 × 6–7**, 2 min rest, +20kg, Compound
Chase the 7th rep on set one before adding load.
Est. time: 90 min | Intensity: RPE 8

Day 2 (Tue): Limbs A
- Quad Extension: 3 x 10-12, 90s rest, 100kg, Isolation
Est. time: 90 min | Intensity: RPE 8

Day 3 (Wed): Torso B
- Wide-Grip Pulldown: 4 x 8, 90s rest, 95kg, Compound
Est. time: 90 min | Intensity: RPE 8

Day 4 (Thu): Limbs B
- Preacher Curl (Unilateral): 3 x 8-10, 90s rest, 32.5kg/arm, Isolation
Est. time: 90 min | Intensity: RPE 8

Day 5 (Fri): Posterior Chain + Pull
- Deadlift Option A: 5 x 5, 2 min rest, 185kg, Compound
Est. time: 90 min | Intensity: RPE 8

Key Notes for This Week
- Mobilize before Day 1 and Day 3.
- Shoulder health first.

Tap the Import button below to lock this into your Home workout plan.
"""


def test_generated_coach_plan_uses_session_duration_not_rest_duration() -> None:
    plan = parse_custom_workout(GENERATED_COACH_PLAN)

    assert plan.is_valid is True
    assert plan.expected_duration == 90
    assert len(plan.days) == 5
    assert all(day.expected_duration == 90 for day in plan.days)


def test_generated_coach_plan_does_not_turn_metadata_into_exercises() -> None:
    plan = parse_custom_workout(GENERATED_COACH_PLAN)

    assert [exercise.exercise_name for exercise in plan.days[0].exercises] == [
        "Flat Bench",
        "Incline Cable Fly",
        "Pull-ups",
    ]
    assert [exercise.type for exercise in plan.days[0].exercises] == [
        "Compound",
        "Isolation",
        "Compound",
    ]
    assert all("Est. time" not in exercise.exercise_name for day in plan.days for exercise in day.exercises)
    assert all("Mobilize before" not in exercise.exercise_name for day in plan.days for exercise in day.exercises)
    assert all("**" not in exercise.exercise_name for day in plan.days for exercise in day.exercises)
    assert all("Mobilize shoulders" not in exercise.exercise_name for day in plan.days for exercise in day.exercises)
    assert all("Nudge from" not in exercise.exercise_name for day in plan.days for exercise in day.exercises)
    assert plan.days[3].exercises[0].exercise_name == "Preacher Curl"
    assert plan.days[3].exercises[0].weight == "32.5kg/arm"


def test_versioned_draft_merges_a_single_day_without_dropping_other_days() -> None:
    parsed_full_plan = parse_custom_workout(GENERATED_COACH_PLAN)
    full_action = {
        "type": "custom_workout_import",
        "source_prompt": "Use this exact five-day plan",
        "scope": "full_plan",
        "target_days": [day.day_key for day in parsed_full_plan.days],
        "target_minutes": 90,
        "summary": "Import five-day plan",
        "button_label": "Apply to Home plan",
        "preview": parsed_full_plan.model_dump(),
    }
    original_draft, _ = coach_router._build_versioned_workout_draft(
        None,
        full_action,
        draft_id="thread-1",
        now=datetime.now(timezone.utc),
    )
    assert original_draft is not None

    monday_update = parse_custom_workout(
        "Day 1 (Mon): Short Bodyweight Session\n- Push-up: 2 x 10, 45s rest, Bodyweight, Compound\nEst. time: 25 min"
    )
    update_action = {
        "type": "home_workout_plan_update",
        "source_prompt": "Only change Monday to 25 minutes",
        "scope": "day",
        "target_days": ["Mon"],
        "target_minutes": 25,
        "summary": "Update Mon",
        "button_label": "Update Mon",
        "preview": monday_update.model_dump(),
    }
    merged_draft, merged_action = coach_router._build_versioned_workout_draft(
        {"workout_draft": original_draft},
        update_action,
        draft_id="thread-1",
        now=datetime.now(timezone.utc),
    )

    assert merged_draft is not None
    assert merged_action is not None
    assert merged_draft["version"] == 2
    assert len(merged_draft["preview"]["days"]) == 5
    assert merged_draft["preview"]["days"][0]["expected_duration"] == 25
    assert merged_draft["preview"]["days"][1] == original_draft["preview"]["days"][1]
    assert merged_action["draft_id"] == "thread-1"
    assert merged_action["draft_version"] == 2


@pytest.mark.anyio
async def test_apply_uses_exact_versioned_draft_and_rejects_stale_version(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed_plan = parse_custom_workout(GENERATED_COACH_PLAN)
    for day in parsed_plan.days:
        if len(day.exercises) == 1:
            duplicate = day.exercises[0].model_copy(deep=True)
            duplicate.exercise_name = f"{duplicate.exercise_name} Variation"
            day.exercises.append(duplicate)
    thread_id = ObjectId()
    thread = {
        "_id": thread_id,
        "user_id": "user-1",
        "workout_draft": {
            "id": str(thread_id),
            "version": 3,
            "status": "ready",
            "preview": parsed_plan.model_dump(),
            "source_prompt": "Use my exact plan",
        },
    }
    inserted: list[dict] = []

    class FakeThreadCollection:
        async def find_one(self, query: dict, **_: object) -> dict | None:
            return thread if query.get("_id") == thread_id and query.get("user_id") == "user-1" else None

        async def update_one(self, *_: object, **__: object) -> None:
            thread["workout_draft"]["status"] = "applied"

    class FakePlanCollection:
        async def insert_one(self, document: dict):
            inserted.append(document)

            class Result:
                inserted_id = ObjectId()

            return Result()

    monkeypatch.setattr(coach_router, "coach_victor_threads_collection", FakeThreadCollection())
    monkeypatch.setattr(coach_router, "strength_workout_plans_collection", FakePlanCollection())

    result = await coach_router._apply_coach_workout_plan_action(
        {"_id": "user-1"},
        source_prompt="Use my exact plan",
        draft_id=str(thread_id),
        draft_version=3,
        scope="full_plan",
    )

    assert len(result["plan"]["days"]) == 5
    assert inserted[0]["input"]["draft_version"] == 3
    assert thread["workout_draft"]["status"] == "applied"

    thread["workout_draft"]["status"] = "ready"
    with pytest.raises(HTTPException) as error:
        await coach_router._apply_coach_workout_plan_action(
            {"_id": "user-1"},
            source_prompt="Use my exact plan",
            draft_id=str(thread_id),
            draft_version=2,
            scope="full_plan",
        )
    assert error.value.status_code == 409
