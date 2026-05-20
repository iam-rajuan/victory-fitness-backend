from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
        "scopes": [],
        "provider_user_id": None,
        "connected_at": now,
        "last_synced_at": now,
        "last_sync_status": "success",
        "last_sync_message": f"{provider} connected",
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
            AsyncMock(return_value=None),
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
