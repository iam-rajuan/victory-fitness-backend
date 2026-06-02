from __future__ import annotations

import base64
import hashlib
import importlib
import hmac
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

wearables_router_module = importlib.import_module("app.wearables.router")
wearables_service_module = importlib.import_module("app.wearables.service")
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


def _junction_webhook_headers(payload: dict, message_id: str = "msg_test_123", timestamp: int | None = None) -> dict[str, str]:
    secret = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
    if timestamp is None:
        timestamp = int(_utc_now().timestamp())
    secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
    body = json.dumps(payload).encode("utf-8")
    signed_content = b".".join((message_id.encode("utf-8"), str(timestamp).encode("utf-8"), body))
    signature = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode("utf-8")
    return {
        "svix-id": message_id,
        "svix-timestamp": str(timestamp),
        "svix-signature": f"v1,{signature}",
        "content-type": "application/json",
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

    def test_vital_create_user_uses_service_helper(self) -> None:
        with patch.object(
            wearables_router_module,
            "ensure_vital_user",
            AsyncMock(return_value={
                "vital_user_id": "vital-user-1",
                "client_user_id": "user-1",
                "created": True,
                "message": "Junction user ready.",
            }),
        ) as ensure_vital_user:
            response = self.client.post("/vital/create-user")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["vital_user_id"], "vital-user-1")
        ensure_vital_user.assert_awaited_once_with("user-1")

    def test_vital_link_token_returns_link_url(self) -> None:
        with patch.object(
            wearables_router_module,
            "create_vital_link_token",
            AsyncMock(return_value={
                "vital_user_id": "vital-user-1",
                "link_token": "token-123",
                "link_web_url": "https://link.tryvital.io/?token=token-123",
                "message": "Junction link token ready.",
            }),
        ) as create_vital_link_token:
            response = self.client.post("/vital/link-token", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["link_token"], "token-123")
        create_vital_link_token.assert_awaited_once()

    def test_vital_webhook_uses_ingestion_helper(self) -> None:
        payload = {"user_id": "vital-user-1", "provider": "fitbit", "metrics": []}
        headers = _junction_webhook_headers(payload)
        body = json.dumps(payload)
        with (
            patch.object(
                wearables_service_module.settings,
                "junction_webhook_secret",
                "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw",
            ),
            patch.object(
                wearables_router_module,
                "ingest_vital_webhook",
                AsyncMock(return_value={
                    "accepted": True,
                    "user_id": "user-1",
                    "vital_user_id": "vital-user-1",
                    "provider": "fitbit",
                    "stored_records": 2,
                    "message": "Junction webhook processed.",
                }),
            ) as ingest_vital_webhook,
        ):
            response = self.client.post("/webhooks/vital", content=body.encode("utf-8"), headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stored_records"], 2)
        ingest_vital_webhook.assert_awaited_once()

    def test_junction_webhook_rejects_missing_signature(self) -> None:
        with patch.object(
            wearables_service_module.settings,
            "junction_webhook_secret",
            "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw",
        ):
            response = self.client.post("/webhooks/junction", json={"user_id": "vital-user-1"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Missing Junction webhook id")

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


class StoreNormalizedMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_metrics_are_skipped_idempotently(self) -> None:
        seen_dedupe_keys: set[str] = set()

        class FakeCollection:
            async def bulk_write(self, operations, ordered=False):  # noqa: ARG002
                inserted = 0
                for operation in operations:
                    dedupe_key = operation["filter"]["dedupe_key"]
                    if dedupe_key not in seen_dedupe_keys:
                        seen_dedupe_keys.add(dedupe_key)
                        inserted += 1
                return SimpleNamespace(upserted_count=inserted)

        def fake_update_one(filter_doc, update_doc, upsert=False):  # noqa: ARG001
            return {
                "filter": filter_doc,
                "update": update_doc,
                "upsert": upsert,
            }

        metric = {
            "metric_type": "steps",
            "value": 4321,
            "unit": "count",
            "start_time": _utc_now(),
            "end_time": _utc_now(),
            "source_device": "Apple Watch",
            "metadata": {"external_id": "steps-4321"},
        }

        with patch("app.wearables.service.health_metrics_collection", FakeCollection()), patch(
            "app.wearables.service.UpdateOne",
            side_effect=fake_update_one,
        ):
            inserted_first, skipped_first = await store_normalized_metrics("user-1", "apple-health", [metric])
            inserted_second, skipped_second = await store_normalized_metrics("user-1", "apple-health", [metric])

        self.assertEqual((inserted_first, skipped_first), (1, 0))
        self.assertEqual((inserted_second, skipped_second), (0, 1))


if __name__ == "__main__":
    unittest.main()
