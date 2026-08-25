from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


legacy_module = importlib.import_module("app.core.legacy")


class _FakeCursor:
    def __init__(self, records):
        self._records = records

    async def to_list(self, length=None):
        return list(self._records)


class AdminUserManagementSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_counts_status_active_users_as_active_even_without_is_verified(self) -> None:
        august = datetime(2026, 8, 25, tzinfo=timezone.utc)
        yearly_users = [
            {"created_at": august, "is_verified": True, "status": "ACTIVE"},
            {"created_at": august, "is_verified": False, "status": "ACTIVE"},
            {"created_at": august, "is_verified": False, "status": "PENDING"},
        ]

        fake_collection = SimpleNamespace(
            count_documents=AsyncMock(side_effect=[3, 2]),
            find=lambda *args, **kwargs: _FakeCursor(yearly_users),
        )

        with patch.object(legacy_module, "users_collection", fake_collection):
            summary = await legacy_module._build_admin_user_summary_response(2026)

        self.assertEqual(summary.totalUsers, 3)
        self.assertEqual(summary.activeUsers, 2)
        self.assertEqual(summary.pendingUsers, 1)

        august_point = next(point for point in summary.userChart if point.month == "Aug")
        self.assertEqual(august_point.userCount, 3)
        self.assertEqual(august_point.activeUserCount, 2)
