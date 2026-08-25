from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


admin_trials_module = importlib.import_module("app.api.routers.admin_trials")


class _FakeCursor:
    def __init__(self, records):
        self._records = list(records)

    async def to_list(self, length=None):
        if length is None:
            return list(self._records)
        return list(self._records)[:length]


class _FakeUsersCollection:
    def __init__(self, records):
        self._records = list(records)

    def find(self, *args, **kwargs):
        return _FakeCursor(self._records)


class AdminTrialDashboardFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_outcomes_only_count_selected_market_and_range(self) -> None:
        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        users = [
            {
                "_id": "de-converted",
                "country": "Germany",
                "country_code": "DE",
                "trial_tier_granted": "gold",
                "trial_start_at": now - timedelta(days=1),
                "trial_end_at": now + timedelta(days=4),
                "trial_outcome": "converted_gold",
                "subscription_purchase_source": "app",
            },
            {
                "_id": "gh-pending",
                "country": "Ghana",
                "country_code": "GH",
                "trial_tier_granted": "gold",
                "trial_start_at": now - timedelta(days=1),
                "trial_end_at": now + timedelta(days=4),
                "subscription_purchase_source": "app",
            },
            {
                "_id": "old-de",
                "country": "Germany",
                "country_code": "DE",
                "trial_tier_granted": "gold",
                "trial_start_at": now - timedelta(days=10),
                "trial_end_at": now - timedelta(days=5),
                "trial_outcome": "lapsed",
                "subscription_purchase_source": "app",
            },
        ]

        with patch.object(admin_trials_module, "users_collection", _FakeUsersCollection(users)), patch.object(
            admin_trials_module,
            "datetime",
            SimpleNamespace(now=lambda tz=None: now),
        ):
            response = await admin_trials_module.admin_gold_trial_outcomes(
                preset="this_week",
                market="germany",
            )

        self.assertEqual(response.totalTrials, 1)
        self.assertEqual(response.convertedGold, 1)
        self.assertEqual(response.activeTrials, 0)
        self.assertEqual(response.pendingDecision, 0)

    async def test_cohorts_only_include_selected_period_users(self) -> None:
        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        users = [
            {
                "_id": "recent-de",
                "name": "Recent Germany",
                "country": "Germany",
                "country_code": "DE",
                "signup_source": "organic",
                "trial_start_at": now - timedelta(days=1),
                "trial_outcome": "converted_gold",
                "subscription_is_purchased": True,
                "subscription_status": "ACTIVE",
                "subscription_tier": "GOLD",
                "trial_engagement": {"days": [0, 1, 3]},
                "subscription_purchase_source": "app",
            },
            {
                "_id": "recent-gh",
                "name": "Recent Ghana",
                "country": "Ghana",
                "country_code": "GH",
                "signup_source": "organic",
                "trial_start_at": now - timedelta(days=1),
                "trial_engagement": {"days": [0]},
                "subscription_purchase_source": "app",
            },
            {
                "_id": "old-de",
                "name": "Old Germany",
                "country": "Germany",
                "country_code": "DE",
                "signup_source": "ads",
                "trial_start_at": now - timedelta(days=20),
                "trial_outcome": "lapsed",
                "trial_engagement": {"days": [0, 1, 2, 3, 4]},
                "subscription_purchase_source": "app",
            },
        ]

        with patch.object(admin_trials_module, "users_collection", _FakeUsersCollection(users)), patch.object(
            admin_trials_module,
            "datetime",
            SimpleNamespace(now=lambda tz=None: now),
        ):
            response = await admin_trials_module.admin_trial_cohorts(
                preset="this_week",
                market="germany",
            )

        self.assertEqual(len(response.cohorts), 1)
        cohort = response.cohorts[0]
        self.assertEqual(cohort.totalUsers, 1)
        self.assertEqual(cohort.convertedUsers, 1)
        self.assertEqual(cohort.signupSource, "organic")

    async def test_dropouts_respect_market_range_and_limit_after_filtering(self) -> None:
        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        users = [
            {
                "_id": "dropout-1",
                "name": "Dropout One",
                "email": "dropout1@example.com",
                "country": "Germany",
                "country_code": "DE",
                "signup_source": "organic",
                "marketing_consent": True,
                "trial_start_at": now - timedelta(days=7),
                "trial_engagement": {"days": [0, 1], "coach_messages": 2},
                "trial_campaign_sent_days": [0, 1, 3, 4, 5],
                "subscription_purchase_source": "app",
            },
            {
                "_id": "dropout-2",
                "name": "Dropout Two",
                "email": "dropout2@example.com",
                "country": "Germany",
                "country_code": "DE",
                "signup_source": "organic",
                "marketing_consent": True,
                "trial_start_at": now - timedelta(days=8),
                "trial_engagement": {"days": [0], "coach_messages": 0},
                "trial_campaign_sent_days": [0, 1, 3],
                "subscription_purchase_source": "app",
            },
            {
                "_id": "recent-user",
                "name": "Recent User",
                "email": "recent@example.com",
                "country": "Germany",
                "country_code": "DE",
                "signup_source": "organic",
                "marketing_consent": True,
                "trial_start_at": now - timedelta(days=1),
                "trial_engagement": {"days": [0]},
                "subscription_purchase_source": "app",
            },
            {
                "_id": "ghana-user",
                "name": "Ghana User",
                "email": "ghana@example.com",
                "country": "Ghana",
                "country_code": "GH",
                "signup_source": "organic",
                "marketing_consent": True,
                "trial_start_at": now - timedelta(days=7),
                "trial_engagement": {"days": [0, 1]},
                "subscription_purchase_source": "app",
            },
        ]

        with patch.object(admin_trials_module, "users_collection", _FakeUsersCollection(users)), patch.object(
            admin_trials_module,
            "datetime",
            SimpleNamespace(now=lambda tz=None: now),
        ):
            response = await admin_trials_module.admin_trial_dropouts(
                preset="custom",
                from_date=(now - timedelta(days=10)).date(),
                to_date=(now - timedelta(days=5)).date(),
                market="germany",
                limit=1,
            )

        self.assertEqual(response.total, 1)
        self.assertEqual(len(response.users), 1)
        self.assertEqual(response.users[0].id, "dropout-1")


if __name__ == "__main__":
    unittest.main()
