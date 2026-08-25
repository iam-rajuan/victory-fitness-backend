from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


analytics_module = importlib.import_module("app.analytics")


class AnalyticsDashboardTests(unittest.IsolatedAsyncioTestCase):
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

