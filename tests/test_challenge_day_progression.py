from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.core.legacy import (
    _get_current_challenge_day_number,
    _get_next_challenge_day_unlock_at,
    _ensure_challenge_day_is_current,
    _serialize_challenge_plan_progress_response,
)


PLAN_DAYS = [
    {"day_number": 1, "title": "Day 1", "focus": "Start", "sections": []},
    {"day_number": 2, "title": "Day 2", "focus": "Continue", "sections": []},
    {"day_number": 3, "title": "Day 3", "focus": "Finish", "sections": []},
]


def test_challenge_day_advances_by_utc_calendar_day_not_completion() -> None:
    membership = {"started_at": "2026-10-19T15:30:00+00:00", "plan_progress": {}}

    assert _get_current_challenge_day_number(
        membership,
        PLAN_DAYS,
        3,
        now=datetime(2026, 10, 19, 23, 59, tzinfo=timezone.utc),
    ) == 1
    assert _get_current_challenge_day_number(
        membership,
        PLAN_DAYS,
        3,
        now=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
    ) == 2


def test_next_day_unlock_is_next_utc_midnight() -> None:
    membership = {"started_at": "2026-10-19T15:30:00+00:00", "plan_progress": {}}

    assert _get_next_challenge_day_unlock_at(
        membership,
        3,
        now=datetime(2026, 10, 19, 23, 59, tzinfo=timezone.utc),
    ) == datetime(
        2026, 10, 20, 0, 0, tzinfo=timezone.utc
    )


def test_future_challenge_day_cannot_be_updated() -> None:
    membership = {"started_at": "2026-10-19T15:30:00+00:00", "plan_progress": {}}

    with pytest.raises(HTTPException) as error:
        _ensure_challenge_day_is_current(
            membership,
            PLAN_DAYS,
            3,
            day_number=2,
            now=datetime(2026, 10, 19, 23, 59, tzinfo=timezone.utc),
        )

    assert error.value.status_code == 409
    assert "not unlocked yet" in str(error.value.detail)


def test_progress_response_keeps_current_day_and_counts_completed_day() -> None:
    membership = {
        "status": "ACTIVE",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "challenge_points": 30,
        "plan_progress": {
            "1": {
                "completed": True,
                "completed_section_ids": [],
                "completed_exercise_ids": [],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    }

    response = _serialize_challenge_plan_progress_response("challenge-1", membership, PLAN_DAYS)

    assert response.current_day_number == 1
    assert response.viewer_progress_days_completed == 1
    assert response.completed_today is True
    assert response.next_day_unlock_at is not None
