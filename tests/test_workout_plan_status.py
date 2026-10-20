from datetime import datetime, timedelta, timezone

from app.workout_plan_status import newest_active_strength_plan, strength_plan_is_complete_or_expired


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _record(*, day: str, created_at: datetime, completed: bool = False) -> dict:
    return {
        "created_at": created_at,
        "plan": {"days": [{"day": day, "title": f"{day} workout"}]},
        "progress": [{"day": day, "completed": True}] if completed else [],
    }


def test_newest_completed_plan_does_not_hide_older_active_plan() -> None:
    completed_newest = _record(day="Mon", created_at=NOW - timedelta(minutes=1), completed=True)
    active_older = _record(day="Tue", created_at=NOW - timedelta(minutes=5))

    assert newest_active_strength_plan([completed_newest, active_older], NOW) is active_older


def test_expired_plan_is_not_active() -> None:
    expired = _record(day="Mon", created_at=NOW - timedelta(days=8))

    assert strength_plan_is_complete_or_expired(expired, NOW) is True
    assert newest_active_strength_plan([expired], NOW) is None
