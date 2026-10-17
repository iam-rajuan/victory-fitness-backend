from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.legacy import _require_access_user


class NotificationBulkManagementTests(unittest.TestCase):
    def setUp(self):
        self.mock_user_1 = {
            "_id": "user-test-1",
            "email": "user1@example.com",
            "app_notifications": [
                {"id": "notif-1", "title": "Notification 1", "message": "Body 1", "read": False},
                {"id": "notif-2", "title": "Notification 2", "message": "Body 2", "read": True},
                {"id": "notif-3", "title": "Notification 3", "message": "Body 3", "read": False},
            ],
            "dismissed_activity_notification_ids": ["old-dismissed-1"],
        }
        self.mock_user_2 = {
            "_id": "user-test-2",
            "email": "user2@example.com",
            "app_notifications": [
                {"id": "user2-notif-1", "title": "User 2 Notif", "message": "Protected", "read": False},
            ],
        }

    def test_single_delete_notification(self):
        app.dependency_overrides[_require_access_user] = lambda: self.mock_user_1
        client = TestClient(app)

        with patch("app.api.routers.me_notifications.users_collection.update_one", new_callable=AsyncMock) as mock_update:
            mock_update.return_value.modified_count = 1
            response = client.delete("/me/notifications/notif-1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"deleted": True})

            # Ensure update_one is scoped strictly to user 1
            mock_update.assert_called_once()
            filter_arg, update_arg = mock_update.call_args[0]
            self.assertEqual(filter_arg, {"_id": "user-test-1"})
            self.assertEqual(update_arg, {"$pull": {"app_notifications": {"id": "notif-1"}}})
        app.dependency_overrides.clear()

    def test_delete_batch_notifications(self):
        app.dependency_overrides[_require_access_user] = lambda: self.mock_user_1
        client = TestClient(app)

        with patch("app.api.routers.me_notifications.users_collection.update_one", new_callable=AsyncMock) as mock_update:
            mock_update.return_value.modified_count = 1
            # Test POST batch delete
            response = client.post("/me/notifications/delete-batch", json={"ids": ["notif-1", "notif-3"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"deleted": True, "count": 2})

            filter_arg, update_arg = mock_update.call_args[0]
            self.assertEqual(filter_arg, {"_id": "user-test-1"})
            self.assertEqual(update_arg, {"$pull": {"app_notifications": {"id": {"$in": ["notif-1", "notif-3"]}}}})

            # Test DELETE batch delete
            mock_update.reset_mock()
            mock_update.return_value.modified_count = 1
            response_del = client.request("DELETE", "/me/notifications/batch", json={"ids": ["notif-2"]})
            self.assertEqual(response_del.status_code, 200)
            self.assertEqual(response_del.json(), {"deleted": True, "count": 1})
        app.dependency_overrides.clear()

    def test_clear_all_notifications_batch_flag(self):
        app.dependency_overrides[_require_access_user] = lambda: self.mock_user_1
        client = TestClient(app)

        with patch("app.api.routers.me_notifications.users_collection.update_one", new_callable=AsyncMock) as mock_update:
            mock_update.return_value.modified_count = 1
            response = client.post("/me/notifications/delete-batch", json={"clear_all": True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"deleted": True, "count": 3})

            filter_arg, update_arg = mock_update.call_args[0]
            self.assertEqual(filter_arg, {"_id": "user-test-1"})
            self.assertEqual(update_arg, {"$set": {"app_notifications": []}})
        app.dependency_overrides.clear()

    def test_clear_all_notifications_endpoint(self):
        app.dependency_overrides[_require_access_user] = lambda: self.mock_user_1
        client = TestClient(app)

        with patch("app.api.routers.me_notifications.users_collection.update_one", new_callable=AsyncMock) as mock_update:
            mock_update.return_value.modified_count = 1
            response = client.delete("/me/notifications/all")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"deleted": True, "count": 3})

            filter_arg, update_arg = mock_update.call_args[0]
            self.assertEqual(filter_arg, {"_id": "user-test-1"})
            self.assertEqual(update_arg, {"$set": {"app_notifications": []}})
        app.dependency_overrides.clear()

    def test_activity_notifications_batch_delete(self):
        app.dependency_overrides[_require_access_user] = lambda: self.mock_user_1
        client = TestClient(app)

        with patch("app.api.routers.me_notifications.users_collection.update_one", new_callable=AsyncMock) as mock_update:
            mock_update.return_value.modified_count = 1
            response = client.post("/me/activity-notifications/delete-batch", json={"ids": ["act-1", "act-2"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"deleted": True, "count": 2})

            filter_arg, update_arg = mock_update.call_args[0]
            self.assertEqual(filter_arg, {"_id": "user-test-1"})
            self.assertEqual(update_arg, {"$addToSet": {"dismissed_activity_notification_ids": {"$each": ["act-1", "act-2"]}}})
        app.dependency_overrides.clear()

    def test_unauthorized_user_cannot_delete(self):
        client = TestClient(app)
        # Test with invalid token
        headers = {"Authorization": "Bearer invalid_token"}
        res1 = client.delete("/me/notifications/notif-1", headers=headers)
        self.assertEqual(res1.status_code, 401)

        res2 = client.post("/me/notifications/delete-batch", json={"ids": ["notif-1"]}, headers=headers)
        self.assertEqual(res2.status_code, 401)

        res3 = client.delete("/me/notifications/all", headers=headers)
        self.assertEqual(res3.status_code, 401)

        res4 = client.post("/me/activity-notifications/delete-batch", json={"ids": ["act-1"]}, headers=headers)
        self.assertEqual(res4.status_code, 401)

        # Test with missing token when audit bypass is disabled
        with patch.dict("os.environ", {"EXPO_PUBLIC_REQUIREMENT_AUDIT": "false", "VITE_REQUIREMENT_AUDIT": "false"}):
            res_missing = client.delete("/me/notifications/notif-1")
            self.assertEqual(res_missing.status_code, 401)

    def test_cross_user_isolation(self):
        # User 2 tries to delete User 1's notification ID
        app.dependency_overrides[_require_access_user] = lambda: self.mock_user_2
        client = TestClient(app)

        with patch("app.api.routers.me_notifications.users_collection.update_one", new_callable=AsyncMock) as mock_update:
            mock_update.return_value.modified_count = 0
            response = client.post("/me/notifications/delete-batch", json={"ids": ["notif-1"]})
            self.assertEqual(response.status_code, 200)

            # Query MUST be scoped to user-test-2, never touching user-test-1
            filter_arg, update_arg = mock_update.call_args[0]
            self.assertEqual(filter_arg, {"_id": "user-test-2"})
            self.assertNotEqual(filter_arg["_id"], self.mock_user_1["_id"])
        app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
