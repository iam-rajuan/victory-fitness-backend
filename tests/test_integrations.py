from __future__ import annotations

import hashlib
import importlib
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

backend_module = importlib.import_module("app.main")
wearables_router_module = importlib.import_module("app.wearables.router")
from app.wearables.service import store_normalized_metrics


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _connection_payload(provider: str) -> dict:
    now = _utc_now()
    return {
        "id": f"{provider}-connection",
        "user_id": "user-1",
        "provider": provider,
        "status": "connected",
        "device_name": "Apple Watch" if provider == "apple-health" else "Android Phone",
        "scopes": [],
        "provider_user_id": None,
        "connected_at": now,
        "disconnected_at": None,
        "last_synced_at": now,
        "last_sync_status": "success",
        "last_sync_message": f"{provider} connected",
        "permission_granted": True,
        "source_device": "Apple Watch" if provider == "apple-health" else "Android Phone",
        "platform": "ios" if provider == "apple-health" else "android",
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }


class IntegrationRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(wearables_router_module.router)
        app.dependency_overrides[wearables_router_module.require_longevity_access_user] = lambda: {
            "_id": "user-1",
            "is_verified": True,
            "subscription_tier": "INNER_CIRCLE",
        }
        cls.client = TestClient(app)

    def test_list_integrations_returns_statuses(self) -> None:
        payload = [
            {
                "provider": "fitbit",
                "display_name": "Fitbit",
                "connection_type": "oauth",
                "status": "connected",
                "connected": True,
                "needs_permission": False,
                "connected_at": _utc_now(),
                "last_synced_at": _utc_now(),
                "last_error": "",
                "last_sync_message": "Fitbit sync completed.",
            }
        ]
        with patch.object(wearables_router_module, "list_integrations", AsyncMock(return_value=payload)):
            response = self.client.get("/integrations")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"][0]["provider"], "fitbit")
        self.assertEqual(body["items"][0]["status"], "connected")

    def test_fitbit_callback_uses_oauth_exchange(self) -> None:
        with patch.object(
            wearables_router_module,
            "exchange_fitbit_code",
            AsyncMock(return_value=_connection_payload("fitbit")),
        ) as exchange_fitbit_code:
            response = self.client.get("/integrations/fitbit/callback?code=abc123&state=state-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "fitbit")
        exchange_fitbit_code.assert_awaited_once_with("state-1", "abc123")

    def test_google_fit_callback_uses_oauth_exchange(self) -> None:
        with patch.object(
            wearables_router_module,
            "exchange_google_fit_code",
            AsyncMock(return_value=_connection_payload("google-fit")),
        ) as exchange_google_fit_code:
            response = self.client.get("/integrations/google-fit/callback?code=abc123&state=state-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "google-fit")
        exchange_google_fit_code.assert_awaited_once_with("state-1", "abc123")

    def test_garmin_connect_returns_provider_not_configured(self) -> None:
        with patch.object(wearables_router_module, "is_provider_configured", return_value=False):
            response = self.client.get("/integrations/garmin/connect")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "provider_not_configured")

    def test_native_connected_marks_provider_connected(self) -> None:
        with patch.object(
            wearables_router_module,
            "mark_native_provider_connected",
            AsyncMock(return_value=_connection_payload("apple-health")),
        ) as mark_connected:
            response = self.client.post(
                "/integrations/native/connected",
                json={
                    "provider": "apple-health",
                    "source_device": "Apple Watch",
                    "permission_granted": True,
                    "platform": "ios",
                    "metadata": {"source": "healthkit"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "apple-health")
        self.assertEqual(response.json()["source_device"], "Apple Watch")
        self.assertEqual(response.json()["platform"], "ios")
        mark_connected.assert_awaited_once()

    def test_native_samples_maps_this_phone_to_ios_provider(self) -> None:
        now = _utc_now().isoformat()
        with patch.object(
            wearables_router_module,
            "ingest_mobile_sync",
            AsyncMock(
                return_value={
                    "inserted": 1,
                    "skipped": 0,
                    "connection": {"status": "connected"},
                    "last_synced_at": _utc_now(),
                }
            ),
        ) as ingest_mobile_sync:
            response = self.client.post(
                "/integrations/native/samples",
                json={
                    "provider": "this-phone",
                    "source_device": "This iPhone",
                    "batch_id": "batch-1",
                    "platform": "ios",
                    "metrics": [
                        {
                            "metric_type": "steps",
                            "value": 1200,
                            "unit": "count",
                            "start_time": now,
                            "end_time": now,
                            "source_device": "This iPhone",
                            "metadata": {"external_id": "steps-1"},
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "apple-health")
        ingest_mobile_sync.assert_awaited_once()
        self.assertEqual(ingest_mobile_sync.await_args.args[1], "apple-health")

    def test_disconnect_provider_endpoint(self) -> None:
        with patch.object(
            wearables_router_module,
            "disconnect_provider",
            AsyncMock(
                return_value={
                    "provider": "garmin",
                    "disconnected": True,
                    "status": "disconnected",
                    "device_name": "Garmin",
                    "source_device": "Garmin",
                    "platform": "android",
                    "disconnected_at": _utc_now(),
                    "permission_granted": False,
                    "message": "Provider disconnected by user.",
                }
            ),
        ) as disconnect_provider:
            response = self.client.delete("/integrations/garmin")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "garmin")
        disconnect_provider.assert_awaited_once_with("user-1", "garmin")

    def test_fitbit_sync_queues_job(self) -> None:
        with patch.object(
            wearables_router_module,
            "enqueue_provider_sync_job",
            AsyncMock(return_value="job-123"),
        ) as enqueue_provider_sync_job:
            response = self.client.post("/integrations/fitbit/sync")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["connection_status"], "syncing")
        enqueue_provider_sync_job.assert_awaited_once_with("user-1", "fitbit")

    def test_google_fit_connect_returns_provider_not_configured(self) -> None:
        with patch.object(wearables_router_module, "is_provider_configured", side_effect=lambda provider: False if provider == "google-fit" else True):
            response = self.client.get("/integrations/google-fit/connect")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "provider_not_configured")

    def test_admin_backfill_current_health_metrics(self) -> None:
        app = FastAPI()
        app.include_router(wearables_router_module.router)
        app.dependency_overrides[wearables_router_module.require_admin_user] = lambda: {
            "_id": "admin-1",
            "is_admin": True,
            "is_verified": True,
        }
        client = TestClient(app)

        with patch.object(
            wearables_router_module,
            "backfill_current_health_metrics_from_history",
            AsyncMock(return_value=12),
        ) as backfill_current_health_metrics_from_history:
            response = client.post("/admin/wearables/backfill-current-health-metrics?force=true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["processed"], 12)
        self.assertTrue(response.json()["force"])
        backfill_current_health_metrics_from_history.assert_awaited_once_with(force=True)


class CommunityPostUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(backend_module.app.router)
        app.dependency_overrides[backend_module._require_community_access_user] = lambda: {
            "_id": "user-1",
            "is_verified": True,
            "subscription_tier": "GOLD",
        }
        cls.client = TestClient(app)

    def test_create_community_post_accepts_image_multipart(self) -> None:
        upload_mock = Mock(return_value="https://cdn.example.com/community-images/image.png")
        serialize_mock = AsyncMock(
            return_value=[
                {
                    "id": "post-1",
                    "author_id": "user-1",
                    "author_name": "Tester",
                    "author_role": "Member",
                    "author_profile_image": "",
                    "audience": "ALL",
                    "content": "image post",
                    "image_url": "https://cdn.example.com/community-images/image.png",
                    "video_url": "",
                    "like_count": 0,
                    "comment_count": 0,
                    "viewer_has_liked": False,
                    "can_delete": True,
                    "comments": [],
                    "reactions": [],
                    "created_at": _utc_now(),
                    "updated_at": _utc_now(),
                }
            ]
        )
        collection = SimpleNamespace(insert_one=AsyncMock())

        with patch.object(backend_module, "_upload_binary_bytes_to_s3", upload_mock), patch.object(
            backend_module, "_serialize_community_post_records", serialize_mock
        ), patch.object(backend_module, "community_posts_collection", collection):
            response = self.client.post(
                "/community/posts",
                data={
                    "content": "image post",
                    "mime_type": "image/png",
                    "file_name": "image.png",
                },
                files={
                    "media_file": ("image.png", b"png-bytes", "image/png"),
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["image_url"], "https://cdn.example.com/community-images/image.png")
        upload_mock.assert_called_once()
        self.assertEqual(upload_mock.call_args.args[0], "community-images")
        collection.insert_one.assert_awaited_once()

    def test_create_community_post_accepts_video_multipart(self) -> None:
        upload_mock = Mock(return_value="https://cdn.example.com/community-videos/video.mp4")
        serialize_mock = AsyncMock(
            return_value=[
                {
                    "id": "post-2",
                    "author_id": "user-1",
                    "author_name": "Tester",
                    "author_role": "Member",
                    "author_profile_image": "",
                    "audience": "ALL",
                    "content": "video post",
                    "image_url": "",
                    "video_url": "https://cdn.example.com/community-videos/video.mp4",
                    "like_count": 0,
                    "comment_count": 0,
                    "viewer_has_liked": False,
                    "can_delete": True,
                    "comments": [],
                    "reactions": [],
                    "created_at": _utc_now(),
                    "updated_at": _utc_now(),
                }
            ]
        )
        collection = SimpleNamespace(insert_one=AsyncMock())

        with patch.object(backend_module, "_upload_binary_bytes_to_s3", upload_mock), patch.object(
            backend_module, "_serialize_community_post_records", serialize_mock
        ), patch.object(backend_module, "community_posts_collection", collection):
            response = self.client.post(
                "/community/posts",
                data={
                    "content": "video post",
                    "mime_type": "video/mp4",
                    "file_name": "video.mp4",
                },
                files={
                    "media_file": ("video.mp4", b"mp4-bytes", "video/mp4"),
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["video_url"], "https://cdn.example.com/community-videos/video.mp4")
        upload_mock.assert_called_once()
        self.assertEqual(upload_mock.call_args.args[0], "community-videos")
        collection.insert_one.assert_awaited_once()

    def test_create_community_post_rejects_oversized_image_multipart(self) -> None:
        upload_mock = Mock(return_value="https://cdn.example.com/community-images/image.png")
        collection = SimpleNamespace(insert_one=AsyncMock())

        with patch.object(backend_module, "COMMUNITY_IMAGE_MAX_SIZE_BYTES", 1 * 1024 * 1024), patch.object(
            backend_module, "_upload_binary_bytes_to_s3", upload_mock
        ), patch.object(backend_module, "community_posts_collection", collection):
            response = self.client.post(
                "/community/posts",
                data={
                    "content": "image post",
                    "mime_type": "image/png",
                    "file_name": "image.png",
                },
                files={
                    "media_file": ("image.png", b"1" * (1 * 1024 * 1024 + 1), "image/png"),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("1MB or smaller", response.json()["detail"])
        upload_mock.assert_not_called()
        collection.insert_one.assert_not_awaited()

    def test_create_community_post_rejects_oversized_video_multipart(self) -> None:
        upload_mock = Mock(return_value="https://cdn.example.com/community-videos/video.mp4")
        collection = SimpleNamespace(insert_one=AsyncMock())

        with patch.object(backend_module, "COMMUNITY_VIDEO_MAX_SIZE_BYTES", 20 * 1024 * 1024), patch.object(
            backend_module, "_upload_binary_bytes_to_s3", upload_mock
        ), patch.object(backend_module, "community_posts_collection", collection):
            response = self.client.post(
                "/community/posts",
                data={
                    "content": "video post",
                    "mime_type": "video/mp4",
                    "file_name": "video.mp4",
                },
                files={
                    "media_file": ("video.mp4", b"1" * (20 * 1024 * 1024 + 1), "video/mp4"),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("20MB or smaller", response.json()["detail"])
        upload_mock.assert_not_called()
        collection.insert_one.assert_not_awaited()


class CommunityPostDeletePermissionTests(unittest.TestCase):
    def _build_client(self, user: dict) -> TestClient:
        app = FastAPI()
        app.include_router(backend_module.app.router)
        app.dependency_overrides[backend_module._require_community_access_user] = lambda: user
        return TestClient(app)

    def test_community_post_delete_is_owner_only(self) -> None:
        record = {"_id": "post-1", "author_id": "user-1"}
        self.assertTrue(backend_module._can_delete_community_post(record, {"_id": "user-1"}))
        self.assertFalse(backend_module._can_delete_community_post(record, {"_id": "user-2"}))
        self.assertTrue(backend_module._can_delete_community_post(record, {"_id": "admin-1", "is_admin": True}))

    def test_delete_own_community_post_rejects_non_owner(self) -> None:
        client = self._build_client({"_id": "user-2", "is_verified": True, "subscription_tier": "GOLD"})
        record = {"_id": "post-1", "author_id": "user-1", "audience": "ALL"}

        with patch.object(backend_module, "_get_community_post_or_404", AsyncMock(return_value=record)), patch.object(
            backend_module, "_ensure_community_post_access", lambda *_args, **_kwargs: None
        ), patch.object(
            backend_module, "community_posts_collection", SimpleNamespace(delete_one=AsyncMock())
        ), patch.object(
            backend_module, "community_comments_collection", SimpleNamespace(delete_many=AsyncMock())
        ), patch.object(
            backend_module, "community_reactions_collection", SimpleNamespace(delete_many=AsyncMock())
        ):
            response = client.delete("/community/posts/post-1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "You can only delete your own post")

    def test_delete_own_community_post_allows_owner(self) -> None:
        client = self._build_client({"_id": "user-1", "is_verified": True, "subscription_tier": "GOLD"})
        record = {"_id": "post-1", "author_id": "user-1", "audience": "ALL"}
        delete_one = AsyncMock(return_value=SimpleNamespace(deleted_count=1))
        delete_many = AsyncMock()

        with patch.object(backend_module, "_get_community_post_or_404", AsyncMock(return_value=record)), patch.object(
            backend_module, "_ensure_community_post_access", lambda *_args, **_kwargs: None
        ), patch.object(
            backend_module, "community_posts_collection", SimpleNamespace(delete_one=delete_one)
        ), patch.object(
            backend_module, "community_comments_collection", SimpleNamespace(delete_many=delete_many)
        ), patch.object(
            backend_module, "community_reactions_collection", SimpleNamespace(delete_many=delete_many)
        ):
            response = client.delete("/community/posts/post-1")

        self.assertEqual(response.status_code, 204)
        delete_one.assert_awaited_once()
        self.assertEqual(delete_many.await_count, 2)

    def test_delete_own_community_post_allows_admin(self) -> None:
        client = self._build_client({"_id": "admin-1", "is_admin": True, "is_verified": True, "subscription_tier": "GOLD"})
        record = {"_id": "post-1", "author_id": "user-1", "audience": "ALL"}
        delete_one = AsyncMock(return_value=SimpleNamespace(deleted_count=1))
        delete_many = AsyncMock()

        with patch.object(backend_module, "_get_community_post_or_404", AsyncMock(return_value=record)), patch.object(
            backend_module, "_ensure_community_post_access", lambda *_args, **_kwargs: None
        ), patch.object(
            backend_module, "community_posts_collection", SimpleNamespace(delete_one=delete_one)
        ), patch.object(
            backend_module, "community_comments_collection", SimpleNamespace(delete_many=delete_many)
        ), patch.object(
            backend_module, "community_reactions_collection", SimpleNamespace(delete_many=delete_many)
        ):
            response = client.delete("/community/posts/post-1")

        self.assertEqual(response.status_code, 204)
        delete_one.assert_awaited_once()
        self.assertEqual(delete_many.await_count, 2)


class ChallengeStartTests(unittest.TestCase):
    def _build_client(self) -> TestClient:
        app = FastAPI()
        app.include_router(backend_module.app.router)
        app.dependency_overrides[backend_module._require_challenge_access_user] = lambda: {
            "_id": "user-1",
            "name": "Test User",
            "is_verified": True,
            "subscription_tier": "GOLD",
        }
        return TestClient(app)

    def test_start_challenge_returns_success_for_existing_active_membership(self) -> None:
        client = self._build_client()
        challenge_id = "6a25c55f6dbb4f1f0f4d1111"
        existing_membership = {
            "_id": "membership-1",
            "user_id": "user-1",
            "challenge_id": challenge_id,
            "status": "ACTIVE",
        }
        challenge_record = {
            "_id": backend_module.ObjectId(challenge_id),
            "status": "ACTIVE",
        }

        with patch.object(
            backend_module,
            "challenges_collection",
            SimpleNamespace(find_one=AsyncMock(return_value=challenge_record)),
        ), patch.object(
            backend_module,
            "challenge_memberships_collection",
            SimpleNamespace(
                count_documents=AsyncMock(return_value=0),
                find_one=AsyncMock(return_value=existing_membership),
            ),
        ), patch.object(
            backend_module,
            "challenge_chat_messages_collection",
            SimpleNamespace(insert_one=AsyncMock()),
        ):
            response = client.post(f"/challenges/{challenge_id}/start")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["membership_id"], "membership-1")


class FaviconRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(backend_module.app)

    def test_favicon_ico_returns_content(self) -> None:
        response = self.client.get("/favicon.ico")
        self.assertIn(response.status_code, {200, 204})

    def test_favicon_png_returns_content(self) -> None:
        response = self.client.get("/favicon.png")
        self.assertIn(response.status_code, {200, 204})


class StoreNormalizedMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_metrics_are_skipped_idempotently(self) -> None:
        class SnapshotCursor:
            def __init__(self, documents):
                self.documents = documents

            async def to_list(self, length=None):  # noqa: ARG002
                return list(self.documents)

        class SnapshotCollection:
            def __init__(self) -> None:
                self.documents: list[dict[str, object]] = []

            def find(self, filter_doc, **kwargs):  # noqa: ARG002
                user_id = filter_doc.get("user_id")
                return SnapshotCursor([document for document in self.documents if document.get("user_id") == user_id])

            async def find_one(self, filter_doc):
                user_id = filter_doc.get("user_id")
                for document in self.documents:
                    if document.get("user_id") == user_id:
                        return document
                return None

            async def replace_one(self, filter_doc, replacement, upsert=False):  # noqa: ARG002
                user_id = filter_doc.get("user_id")
                self.documents = [document for document in self.documents if document.get("user_id") != user_id]
                self.documents.append(replacement)
                return SimpleNamespace(modified_count=1, upserted_id=replacement.get("_id"))

            async def delete_many(self, filter_doc):  # noqa: ARG002
                return SimpleNamespace(deleted_count=0)

        metric = {
            "metric_type": "steps",
            "value": 4321,
            "unit": "count",
            "start_time": _utc_now(),
            "end_time": _utc_now(),
            "source_device": "Apple Watch",
            "metadata": {"external_id": "steps-4321"},
        }

        with patch("app.wearables.service.health_samples_collection", SnapshotCollection()), patch(
            "app.wearables.service.health_metrics_collection", SnapshotCollection()
        ):
            inserted_first, skipped_first = await store_normalized_metrics("user-1", "apple-health", [metric])
            inserted_second, skipped_second = await store_normalized_metrics("user-1", "apple-health", [metric])

        self.assertEqual((inserted_first, skipped_first), (1, 0))
        self.assertEqual((inserted_second, skipped_second), (0, 1))


if __name__ == "__main__":
    unittest.main()
