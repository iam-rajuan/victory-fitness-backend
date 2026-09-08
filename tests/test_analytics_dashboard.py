from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


analytics_module = importlib.import_module("app.analytics")


class AnalyticsDashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_market_revenue_attributes_stripe_row_through_user_id(self) -> None:
        now = datetime.now(timezone.utc)
        ledger_row = {"recognized_amount": 19.5, "currency": "eur"}
        safe_find = AsyncMock(return_value=[ledger_row])

        with patch.object(analytics_module, "_safe_find", safe_find):
            amount, currency = await analytics_module._market_revenue(
                "Ghana", "GH", ["user-1"], now - timedelta(days=7), now
            )

        self.assertEqual(amount, 19.5)
        self.assertEqual(currency, "EUR")
        query = safe_find.await_args.args[1]
        owner_filter = query["$and"][-1]
        self.assertIn({"user_id": {"$in": ["user-1"]}}, owner_filter["$or"])

    def test_trial_conversion_uses_trials_decided_in_period(self) -> None:
        now = datetime.now(timezone.utc)
        users = [
            {
                "trial_start_at": now - timedelta(days=6),
                "trial_outcome": "converted_gold",
                "trial_outcome_at": now - timedelta(days=1),
            },
            {
                "trial_start_at": now - timedelta(days=6),
                "trial_outcome": "lapsed",
                "trial_outcome_at": now - timedelta(days=2),
            },
        ]

        result = analytics_module._trial_conversion_for_period(
            users, now - timedelta(days=7), now
        )

        self.assertEqual(result, 50.0)

    async def test_daily_wins_counts_uppercase_completed_challenges(self) -> None:
        challenge_memberships_collection = SimpleNamespace(
            count_documents=AsyncMock(return_value=2),
        )

        with patch.object(analytics_module, "completion_cards_collection", None), patch.object(
            analytics_module, "accountability_pairs_collection", None
        ), patch.object(
            analytics_module, "challenge_memberships_collection", challenge_memberships_collection
        ), patch.object(
            analytics_module, "payment_events_collection", None
        ), patch.object(
            analytics_module, "analytics_events_collection", None
        ), patch.object(
            analytics_module, "_market_user_filter", AsyncMock(return_value={})
        ):
            response = await analytics_module.daily_wins_widget(preset="this_week", market="all", _={})

        self.assertTrue(any(event.type == "challenge_completed" and event.count == 2 for event in response.events))

        challenge_query = challenge_memberships_collection.count_documents.await_args.args[0]
        self.assertEqual(
            challenge_query["$and"][-1],
            {"status": {"$in": ["completed", "COMPLETED"]}},
        )
