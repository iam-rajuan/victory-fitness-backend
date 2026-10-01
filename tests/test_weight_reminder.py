from datetime import datetime, timedelta, timezone
import asyncio

from app.api.routers import me as me_router
from app.api.routers.me import _should_prompt_weight_update, _touch_daily_login_streak


class _FakeUsersCollection:
    def __init__(self):
        self.updates = []

    async def update_one(self, query, update):
        self.updates.append((query, update))


def test_no_prompt_when_no_weight():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    metrics = {"age": "25", "weight": ""}
    user = {"created_at": now - timedelta(days=60), "onboarding_completed": True}
    assert _should_prompt_weight_update(metrics, user, now) is False


def test_no_prompt_when_snoozed():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    metrics = {
        "weight": "75",
        "weight_updated_at": (now - timedelta(days=35)).isoformat(),
        "weight_snoozed_until": (now + timedelta(days=3)).isoformat(),
    }
    user = {"created_at": now - timedelta(days=60), "onboarding_completed": True}
    assert _should_prompt_weight_update(metrics, user, now) is False


def test_prompt_when_elapsed_over_28_days():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    metrics = {
        "weight": "75",
        "weight_updated_at": (now - timedelta(days=29)).isoformat(),
    }
    user = {"created_at": now - timedelta(days=60), "onboarding_completed": True}
    assert _should_prompt_weight_update(metrics, user, now) is True


def test_no_prompt_when_recently_confirmed():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    metrics = {
        "weight": "75",
        "weight_updated_at": (now - timedelta(days=40)).isoformat(),
        "weight_confirmed_at": (now - timedelta(days=10)).isoformat(),
    }
    user = {"created_at": now - timedelta(days=60), "onboarding_completed": True}
    assert _should_prompt_weight_update(metrics, user, now) is False


def test_prompt_after_snooze_expires():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    metrics = {
        "weight": "75",
        "weight_updated_at": (now - timedelta(days=35)).isoformat(),
        "weight_snoozed_until": (now - timedelta(hours=1)).isoformat(),
    }
    user = {"created_at": now - timedelta(days=60), "onboarding_completed": True}
    assert _should_prompt_weight_update(metrics, user, now) is True


def test_daily_login_streak_increments_from_yesterday(monkeypatch):
    fake_users = _FakeUsersCollection()
    monkeypatch.setattr(me_router, "users_collection", fake_users)
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    user = {
        "_id": "user-1",
        "login_streak_days": 3,
        "best_login_streak_days": 5,
        "last_login_streak_date": "2026-09-30",
    }

    updated = asyncio.run(_touch_daily_login_streak(user, now=now))

    assert updated["login_streak_days"] == 4
    assert updated["best_login_streak_days"] == 5
    assert updated["streak_days"] == 4
    assert fake_users.updates[0][1]["$set"]["last_login_streak_date"] == "2026-10-01"


def test_daily_login_streak_resets_after_missed_day_and_keeps_best(monkeypatch):
    fake_users = _FakeUsersCollection()
    monkeypatch.setattr(me_router, "users_collection", fake_users)
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    user = {
        "_id": "user-1",
        "login_streak_days": 8,
        "best_login_streak_days": 8,
        "last_login_streak_date": "2026-09-28",
    }

    updated = asyncio.run(_touch_daily_login_streak(user, now=now))

    assert updated["login_streak_days"] == 1
    assert updated["best_login_streak_days"] == 8
    assert updated["streak_days"] == 1


def test_daily_login_streak_same_day_does_not_increment(monkeypatch):
    fake_users = _FakeUsersCollection()
    monkeypatch.setattr(me_router, "users_collection", fake_users)
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    user = {
        "_id": "user-1",
        "login_streak_days": 4,
        "best_login_streak_days": 4,
        "last_login_streak_date": "2026-10-01",
    }

    updated = asyncio.run(_touch_daily_login_streak(user, now=now))

    assert updated is user
    assert fake_users.updates == []
