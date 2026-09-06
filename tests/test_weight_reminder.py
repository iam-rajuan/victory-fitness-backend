from datetime import datetime, timedelta, timezone
from app.api.routers.me import _should_prompt_weight_update


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
