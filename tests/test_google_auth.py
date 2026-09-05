from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
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
        self.assertEqual(insert_doc["profile_image"], "https://example.com/avatar.jpg")
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
                    "picture": "https://example.com/linked-avatar.jpg",
                }
            )

        self.assertEqual(result["google_sub"], "google-sub-2")
        self.assertFalse(users_collection.insert_one.await_count)
        update_doc = users_collection.update_one.await_args.args[1]["$set"]
        self.assertEqual(update_doc["google_sub"], "google-sub-2")
        self.assertEqual(update_doc["auth_provider_user_id"], "google-sub-2")
        self.assertEqual(update_doc["auth_providers"], ["google"])
        self.assertEqual(update_doc["profile_image"], "https://example.com/linked-avatar.jpg")


class GoogleTokenVerificationTests(unittest.TestCase):
    def test_tokeninfo_fallback_validates_google_claims(self) -> None:
        expires_at = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())

        with patch.object(
            legacy_module,
            "_read_json_url",
            return_value={
                "aud": "google-client-id",
                "iss": "https://accounts.google.com",
                "exp": str(expires_at),
                "sub": "google-sub-3",
                "email": "verified@example.com",
                "email_verified": "true",
                "name": "Verified User",
            },
        ):
            profile = legacy_module._verify_google_id_token_with_tokeninfo(
                "id-token-value",
                "google-client-id",
                fallback_reason="local_verify_failed",
            )

        self.assertEqual(profile["sub"], "google-sub-3")
        self.assertEqual(profile["email"], "verified@example.com")


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


class GoogleOAuthCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_start_uses_request_host_when_configured_redirect_is_localhost(self) -> None:
        app = FastAPI()
        app.include_router(auth_router_module.router)
        client = TestClient(app)

        with patch.object(auth_router_module.settings, "google_client_id", "google-client-id"), patch.object(
            auth_router_module.settings, "google_redirect_uri", "http://localhost:8000/auth/google/callback"
        ), patch.object(
            auth_router_module, "_is_allowed_google_return_origin", return_value=True
        ), patch.object(
            auth_router_module, "create_token", return_value="state-token"
        ):
            response = client.get(
                "/auth/google/start?return_origin=https%3A%2F%2Fvictory-fitness-app.vercel.app&flow_id=flow-123456789",
                headers={"host": "victory-fitness-backend.onrender.com", "x-forwarded-proto": "https"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 307)
        self.assertIn(
            "redirect_uri=https%3A%2F%2Fvictory-fitness-backend.onrender.com%2Fauth%2Fgoogle%2Fcallback",
            response.headers["location"],
        )

    async def test_google_callback_exchange_uses_request_host_when_configured_redirect_is_localhost(self) -> None:
        user = {
            "_id": "google-user-4",
            "email": "callback-host@example.com",
            "name": "Callback Host",
            "is_verified": True,
            "updated_at": datetime.now(timezone.utc),
        }
        token_response = legacy_module.TokenResponse(
            access_token="access-token",
            session_token="session-token",
            expires_in=600,
            user={"id": "google-user-4", "name": "Callback Host", "email": "callback-host@example.com", "is_verified": True},
            returning_user=None,
        )
        app = FastAPI()
        app.include_router(auth_router_module.router)
        client = TestClient(app)

        with patch.object(auth_router_module.settings, "google_redirect_uri", "http://localhost:8000/auth/google/callback"), patch.object(
            auth_router_module, "decode_token", return_value={"sub": "https://victory-fitness-app.vercel.app", "flow_id": "flow-123456789"}
        ), patch.object(
            auth_router_module, "_is_allowed_google_return_origin", return_value=True
        ), patch.object(
            auth_router_module, "_exchange_google_oauth_code", return_value={"id_token": "id-token"}
        ) as exchange_google_oauth_code, patch.object(
            auth_router_module,
            "_verify_google_id_token",
            return_value={"sub": "google-sub-4", "email": "callback-host@example.com", "email_verified": True, "name": "Callback Host"},
        ), patch.object(
            auth_router_module, "_upsert_google_user", AsyncMock(return_value=user)
        ), patch.object(
            auth_router_module, "_maybe_activate_phase_one_beta_subscription", AsyncMock(return_value=user)
        ), patch.object(
            auth_router_module, "_issue_tokens", AsyncMock(return_value=token_response)
        ), patch.object(
            auth_router_module, "_store_google_oauth_result"
        ):
            response = client.get(
                "/auth/google/callback?code=code&state=state",
                headers={"host": "victory-fitness-backend.onrender.com", "x-forwarded-proto": "https"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 307)
        exchange_google_oauth_code.assert_called_once_with(
            "code",
            "https://victory-fitness-backend.onrender.com/auth/google/callback",
        )

    async def test_google_callback_saves_userinfo_picture_before_issuing_tokens(self) -> None:
        user = {
            "_id": "google-user-3",
            "email": "callback@example.com",
            "name": "Callback User",
            "profile_image": "https://example.com/callback-avatar.jpg",
            "is_verified": True,
            "updated_at": datetime.now(timezone.utc),
        }
        token_response = legacy_module.TokenResponse(
            access_token="access-token",
            session_token="session-token",
            expires_in=600,
            user={
                "id": "google-user-3",
                "name": "Callback User",
                "email": "callback@example.com",
                "is_verified": True,
                "profileImage": "https://example.com/callback-avatar.jpg",
            },
            returning_user=None,
        )

        with patch.object(auth_router_module, "decode_token", return_value={"sub": "http://localhost:8081", "flow_id": "flow-123456789"}), patch.object(
            auth_router_module, "_is_allowed_google_return_origin", return_value=True
        ), patch.object(
            auth_router_module, "_exchange_google_oauth_code", return_value={"id_token": "id-token", "access_token": "access-token"}
        ), patch.object(
            auth_router_module, "_verify_google_id_token",
            return_value={"sub": "google-sub-3", "email": "callback@example.com", "email_verified": True, "name": "Callback User"},
        ), patch.object(
            auth_router_module,
            "_fetch_google_userinfo",
            return_value={
                "sub": "google-sub-3",
                "email": "callback@example.com",
                "email_verified": True,
                "name": "Callback User",
                "picture": "https://example.com/callback-avatar.jpg",
            },
        ), patch.object(
            auth_router_module, "_upsert_google_user", AsyncMock(return_value=user)
        ) as upsert_google_user, patch.object(
            auth_router_module, "_maybe_activate_phase_one_beta_subscription", AsyncMock(return_value=user)
        ), patch.object(
            auth_router_module, "_issue_tokens", AsyncMock(return_value=token_response)
        ), patch.object(
            auth_router_module, "_store_google_oauth_result"
        ):
            response = await auth_router_module.google_oauth_callback(
                request=SimpleNamespace(headers={}, base_url="http://testserver/"),
                code="code",
                state="state",
            )

        self.assertEqual(response.status_code, 307)
        profile = upsert_google_user.await_args.args[0]
        self.assertEqual(profile["picture"], "https://example.com/callback-avatar.jpg")
