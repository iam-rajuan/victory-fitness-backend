import hashlib
import importlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security import hash_password, verify_password

auth = importlib.import_module("app.api.routers.auth")
legacy = importlib.import_module("app.core.legacy")


class AdminPasswordRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.user = {"_id": ObjectId(), "email": "office@example.com", "is_admin": True,
                     "role": "admin", "is_verified": True, "password_hash": hash_password("Original123!")}
        self.db = SimpleNamespace(find_one=AsyncMock(return_value=self.user),
                                  update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
                                  find_one_and_update=AsyncMock(return_value=None))
        self.sender = Mock()
        for patcher in [patch.object(auth, "users_collection", self.db),
                        patch.object(auth, "send_password_reset_email", self.sender),
                        patch.object(auth.settings, "admin_seed_accounts", [{"email": "office@example.com", "password": "Seed123!"}])]:
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(auth.router)
        self.client = TestClient(app)

    def post(self, path, **payload):
        return self.client.post("/admin/auth/" + path, json=payload)

    def challenge(self):
        self.db.find_one_and_update.return_value = {
            **self.user, "admin_reset_code_hash": hash_password("1234"), "admin_reset_attempts": 0,
            "admin_reset_code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}

    def test_unlisted_email_rejected_before_database_or_email(self):
        response = self.post("forgot-password", email="other@example.com")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid credentials")
        self.db.find_one.assert_not_awaited()
        self.db.update_one.assert_not_awaited()
        self.sender.assert_not_called()

    def test_empty_allowlist_fails_closed(self):
        with patch.object(auth.settings, "admin_seed_accounts", []):
            response = self.post("forgot-password", email=self.user["email"])
        self.assertEqual(response.status_code, 401)
        self.sender.assert_not_called()

    def test_seed_email_normalized_and_otp_sent_only_to_database_email(self):
        response = self.post("forgot-password", email="OFFICE@example.com")
        self.assertEqual(response.status_code, 200)
        email, code = self.sender.call_args.args
        self.assertEqual(email, self.user["email"])
        saved = self.db.update_one.await_args.args[1]
        self.assertTrue(verify_password(code, saved["$set"]["admin_reset_code_hash"]))
        self.assertIn("admin_reset_token_hash", saved["$unset"])
        self.assertNotIn("password_hash", saved["$set"])

    def test_missing_blocked_and_nonadmin_users_rejected(self):
        for user in [None, {**self.user, "is_blocked": True},
                     {**self.user, "is_admin": False, "role": "member"}]:
            self.db.find_one.return_value = user
            self.assertEqual(self.post("forgot-password", email="office@example.com").status_code, 401)
        self.sender.assert_not_called()

    def test_resend_cooldown_does_not_send(self):
        self.db.update_one.return_value = SimpleNamespace(matched_count=0)
        self.assertEqual(self.post("forgot-password", email=self.user["email"]).status_code, 429)
        self.sender.assert_not_called()

    def test_delivery_failure_invalidates_challenge(self):
        self.sender.side_effect = RuntimeError("provider failed")
        self.assertEqual(self.post("forgot-password", email=self.user["email"]).status_code, 503)
        cleanup = self.db.update_one.await_args.args
        self.assertIn("admin_reset_code_hash", cleanup[0])
        self.assertIn("admin_reset_sent_at", cleanup[1]["$unset"])

    def test_unlisted_email_cannot_verify(self):
        self.assertEqual(self.post("verify-reset-code", email="other@example.com", code="1234").status_code, 401)
        self.db.find_one_and_update.assert_not_awaited()

    def test_expired_or_exhausted_otp_rejected(self):
        self.assertEqual(self.post("verify-reset-code", email=self.user["email"], code="1234").status_code, 400)
        query = self.db.find_one_and_update.await_args.args[0]
        self.assertEqual(query["admin_reset_attempts"], {"$lt": 5})
        self.assertIn("$gt", query["admin_reset_code_expires_at"])
        self.db.update_one.assert_not_awaited()

    def test_wrong_otp_does_not_issue_token(self):
        self.challenge()
        self.assertEqual(self.post("verify-reset-code", email=self.user["email"], code="9999").status_code, 400)
        self.db.update_one.assert_not_awaited()

    def test_successful_verification_consumes_otp_and_hashes_token(self):
        self.challenge()
        response = self.post("verify-reset-code", email=self.user["email"], code="1234")
        self.assertEqual(response.status_code, 200)
        token = response.json()["reset_token"]
        write = self.db.update_one.await_args.args[1]
        self.assertEqual(write["$set"]["admin_reset_token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertIn("admin_reset_code_hash", write["$unset"])

    def test_concurrent_or_replayed_otp_cannot_issue_second_token(self):
        self.challenge()
        self.db.update_one.return_value = SimpleNamespace(matched_count=0)
        self.assertEqual(self.post("verify-reset-code", email=self.user["email"], code="1234").status_code, 400)

    def test_reset_without_valid_token_rejected(self):
        self.db.find_one.return_value = None
        self.assertEqual(self.post("reset-password", reset_token="x" * 43, new_password="Updated123!").status_code, 401)
        self.db.update_one.assert_not_awaited()

    def test_reset_rechecks_seed_allowlist(self):
        self.db.find_one.return_value = {**self.user, "email": "removed@example.com"}
        self.assertEqual(self.post("reset-password", reset_token="x" * 43, new_password="Updated123!").status_code, 401)
        self.db.update_one.assert_not_awaited()

    def test_successful_reset_records_timestamp_revokes_sessions_and_consumes_token(self):
        response = self.post("reset-password", reset_token="x" * 43, new_password="Updated123!")
        self.assertEqual(response.status_code, 200)
        query, write = self.db.update_one.await_args.args
        self.assertIn("admin_reset_token_hash", query)
        self.assertIn("$gt", query["admin_reset_token_expires_at"])
        self.assertTrue(verify_password("Updated123!", write["$set"]["password_hash"]))
        self.assertIn("password_changed_at", write["$set"])
        self.assertEqual(write["$inc"]["auth_session_version"], 1)
        self.assertIn("admin_reset_token_hash", write["$unset"])

    def test_concurrent_reset_cannot_reuse_token(self):
        self.db.update_one.return_value = SimpleNamespace(matched_count=0)
        self.assertEqual(self.post("reset-password", reset_token="x" * 43, new_password="Updated123!").status_code, 401)

    def test_long_utf8_password_rejected_instead_of_silently_truncated(self):
        self.assertEqual(self.post("reset-password", reset_token="x" * 43, new_password="é" * 40).status_code, 400)
        self.db.update_one.assert_not_awaited()

    def test_member_routes_cannot_reset_admins(self):
        for path, payload in [("forgot-password", {"email": self.user["email"]}),
                              ("verify-reset-code", {"email": self.user["email"], "code": "1234"}),
                              ("reset-password", {"reset_token": "x" * 43, "new_password": "Updated123!"})]:
            with patch.object(auth, "decode_token", return_value={"sub": str(self.user["_id"])}):
                response = self.client.post("/auth/" + path, json=payload)
            self.assertEqual(response.status_code, 401)
        self.sender.assert_not_called()
        self.db.update_one.assert_not_awaited()

    def test_ordinary_member_recovery_still_sends(self):
        self.db.find_one.return_value = {**self.user, "email": "member@example.com", "role": "member", "is_admin": False}
        self.assertEqual(self.client.post("/auth/forgot-password", json={"email": "member@example.com"}).status_code, 200)
        self.sender.assert_called_once()


class SeedPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_changed_password_survives_seed_sync(self):
        current_hash = hash_password("Changed123!")
        db = SimpleNamespace(find_one=AsyncMock(return_value={
            "_id": ObjectId(), "email": "office@example.com", "password_hash": current_hash,
            "password_changed_at": datetime.now(timezone.utc)}), update_one=AsyncMock())
        settings = SimpleNamespace(admin_seed_enabled=True, admin_seed_sync_password=True,
                                   admin_seed_accounts=[{"email": "office@example.com", "password": "Seed123!"}])
        with patch.object(legacy, "users_collection", db), patch.object(legacy, "settings", settings):
            await legacy._seed_admin_user()
        self.assertNotIn("password_hash", db.update_one.await_args.args[1]["$set"])


if __name__ == "__main__":
    unittest.main()
