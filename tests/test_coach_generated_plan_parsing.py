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
