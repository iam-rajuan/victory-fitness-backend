from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


admin_support_module = importlib.import_module("app.api.routers.admin_support")


class _FakeCursor:
    def __init__(self, records):
        self._records = list(records)

    async def to_list(self, length=None):
        if length is None:
            return list(self._records)
        return list(self._records)[:length]


class _FakeSupportCollection:
    def __init__(self, records):
        self._records = list(records)

    def find(self, *args, **kwargs):
        return _FakeCursor(self._records)


class AdminSupportInboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_support_inbox_returns_summary_for_filtered_results(self) -> None:
        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        records = [
            {
                "_id": "msg-1",
                "user_id": "user-1",
                "user_name": "Rajuan Hossen",
                "user_email": "rajuan@example.com",
                "subject": "Payment issue",
                "message": "Need help with billing.",
                "status": "OPEN",
                "admin_notes": "",
                "created_at": now - timedelta(days=1),
                "updated_at": now - timedelta(days=1),
            },
            {
                "_id": "msg-2",
                "user_id": "user-2",
                "user_name": "Test User",
                "user_email": "test@example.com",
                "subject": "Coach question",
                "message": "Need help from coach.",
                "status": "IN_PROGRESS",
                "admin_notes": "Following up",
                "created_at": now - timedelta(days=2),
                "updated_at": now - timedelta(days=1),
            },
            {
                "_id": "msg-3",
                "user_id": "user-3",
                "user_name": "Other User",
                "user_email": "other@example.com",
                "subject": "Resolved issue",
                "message": "Everything is fine now.",
                "status": "RESOLVED",
                "admin_notes": "Closed",
                "created_at": now - timedelta(days=10),
                "updated_at": now - timedelta(days=9),
            },
        ]

        with patch.object(admin_support_module, "support_messages_collection", _FakeSupportCollection(records)), patch.object(
            admin_support_module,
            "datetime",
            SimpleNamespace(now=lambda tz=None: now),
        ):
            response = await admin_support_module.admin_get_support_messages(
                query="help",
                status="ALL",
                limit=500,
            )

        self.assertEqual(response.summary.totalMessages, 3)
        self.assertEqual(response.summary.visibleMessages, 3)
        self.assertEqual(response.summary.openMessages, 1)
        self.assertEqual(response.summary.inProgressMessages, 1)
        self.assertEqual(response.summary.resolvedMessages, 1)
        self.assertEqual(response.summary.submittedLast7Days, 2)
        self.assertEqual(response.query, "help")
        self.assertEqual(response.statusFilter, "ALL")

    async def test_support_inbox_status_filter_limits_visible_rows(self) -> None:
        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        records = [
            {
                "_id": "msg-1",
                "user_id": "user-1",
                "user_name": "Open User",
                "user_email": "open@example.com",
                "subject": "Open case",
                "message": "Open ticket",
                "status": "OPEN",
                "admin_notes": "",
                "created_at": now,
                "updated_at": now,
            },
            {
                "_id": "msg-2",
                "user_id": "user-2",
                "user_name": "Resolved User",
                "user_email": "resolved@example.com",
                "subject": "Resolved case",
                "message": "Resolved ticket",
                "status": "RESOLVED",
                "admin_notes": "",
                "created_at": now,
                "updated_at": now,
            },
        ]

        with patch.object(admin_support_module, "support_messages_collection", _FakeSupportCollection(records)), patch.object(
            admin_support_module,
            "datetime",
            SimpleNamespace(now=lambda tz=None: now),
        ):
            response = await admin_support_module.admin_get_support_messages(
                status="RESOLVED",
                limit=500,
            )

        self.assertEqual(len(response.messages), 1)
        self.assertEqual(response.messages[0].status, "RESOLVED")
        self.assertEqual(response.summary.totalMessages, 2)
        self.assertEqual(response.summary.visibleMessages, 1)


if __name__ == "__main__":
    unittest.main()
