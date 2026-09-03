from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


legacy_module = importlib.import_module("app.core.legacy")
auth_router_module = importlib.import_module("app.api.routers.auth")


class GoogleIdentityUpsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_google_user_is_created_with_google_subject_and_defaults(self) -> None:
        inserted_user = {
            "_id": "google-user-1",
            "email": "new@example.com",
            "name": "New Person",
            "google_sub": "google-sub-1",
            "auth_provider": "google",
            "auth_providers": ["google"],
            "is_verified": True,
            "subscription_purchase_source": "",
            "onboarding_completed": False,
        }
        users_collection = SimpleNamespace(
            find_one=AsyncMock(side_effect=[None, None, inserted_user]),
            insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id="google-user-1")),
            update_one=AsyncMock(),
        )

        with patch.object(legacy_module, "users_collection", users_collection):
            result = await legacy_module._upsert_google_user(
                {
                    "sub": "google-sub-1",
                    "email": "new@example.com",
                    "email_verified": True,
                    "name": "New Person",
                    "picture": "https://example.com/avatar.jpg",
                }
            )

        self.assertEqual(result["_id"], "google-user-1")
        insert_doc = users_collection.insert_one.await_args.args[0]
        self.assertEqual(insert_doc["google_sub"], "google-sub-1")
        self.assertEqual(insert_doc["auth_provider_user_id"], "google-sub-1")
        self.assertEqual(insert_doc["auth_provider"], "google")
        self.assertEqual(insert_doc["auth_providers"], ["google"])
        self.assertEqual(insert_doc["signup_source"], "google_oauth")
        self.assertEqual(insert_doc["password_hash"], "")
        self.assertFalse(insert_doc["onboarding_completed"])

    async def test_existing_email_password_user_is_linked_without_duplicate_insert(self) -> None:
        existing_user = {
            "_id": "local-user-1",
            "email": "linked@example.com",
            "name": "Linked User",
            "password_hash": "hashed-password",
            "is_verified": True,
            "auth_provider": "",
        }
        linked_user = {
            **existing_user,
            "google_sub": "google-sub-2",
            "auth_provider_user_id": "google-sub-2",
            "auth_providers": ["google"],
        }
        users_collection = SimpleNamespace(
            find_one=AsyncMock(side_effect=[None, existing_user, linked_user]),
            insert_one=AsyncMock(),
            update_one=AsyncMock(),
        )

        with patch.object(legacy_module, "users_collection", users_collection):
            result = await legacy_module._upsert_google_user(
                {
                    "sub": "google-sub-2",
                    "email": "linked@example.com",
                    "email_verified": True,
                    "name": "Linked User",
                }
            )

        self.assertEqual(result["google_sub"], "google-sub-2")
        self.assertFalse(users_collection.insert_one.await_count)
        update_doc = users_collection.update_one.await_args.args[1]["$set"]
        self.assertEqual(update_doc["google_sub"], "google-sub-2")
        self.assertEqual(update_doc["auth_provider_user_id"], "google-sub-2")
        self.assertEqual(update_doc["auth_providers"], ["google"])


class GoogleRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(auth_router_module.router)
        cls.client = TestClient(app)

    def test_google_route_requires_id_token(self) -> None:
        response = self.client.post("/auth/google", json={"access_token": "access-only-token-0123456789"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Missing Google ID token")

    def test_google_route_reuses_existing_token_issuer_flow(self) -> None:
        user = {
            "_id": "google-user-2",
            "email": "google@example.com",
            "name": "Google User",
            "is_verified": True,
            "updated_at": datetime.now(timezone.utc),
        }
        token_response = legacy_module.TokenResponse(
            access_token="access-token",
            session_token="session-token",
            expires_in=600,
            user={"id": "google-user-2", "name": "Google User", "email": "google@example.com", "is_verified": True},
            returning_user=None,
        )

        with patch.object(auth_router_module, "_resolve_google_profile", return_value=({"sub": "google-sub-2", "email": "google@example.com"}, "google")), patch.object(
            auth_router_module, "_upsert_google_user", AsyncMock(return_value=user)
        ) as upsert_google_user, patch.object(
            auth_router_module, "_maybe_activate_phase_one_beta_subscription", AsyncMock(return_value=user)
        ) as maybe_activate, patch.object(
            auth_router_module, "_issue_tokens", AsyncMock(return_value=token_response)
        ) as issue_tokens:
            response = self.client.post(
                "/auth/google",
                json={"id_token": "mock-google-id-token-value"},
                headers={"X-Victory-Client": "app"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["access_token"], "access-token")
        upsert_google_user.assert_awaited_once()
        maybe_activate.assert_awaited_once_with(user)
        self.assertFalse(issue_tokens.await_args.kwargs["issue_cookies"])
