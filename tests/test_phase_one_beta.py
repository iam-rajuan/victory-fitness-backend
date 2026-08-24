from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


backend_module = importlib.import_module("app.main")
admin_trials_router_module = importlib.import_module("app.api.routers.admin_trials")
beta_analytics_service_module = importlib.import_module("app.services.beta_analytics")
payments_router_module = importlib.import_module("app.api.routers.payments")
stripe_payments_module = importlib.import_module("app.services.stripe_payments")
trial_router_module = importlib.import_module("app.api.routers.trial")
dependencies_module = importlib.import_module("app.dependencies")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PhaseOneBetaEntitlementTests(unittest.TestCase):
    def test_active_beta_user_gets_gold_access_without_purchase(self) -> None:
        now = _utc_now()
        user = {
            "_id": "user-1",
            "trial_tier_granted": "gold",
            "trial_start_at": now - timedelta(days=1),
            "trial_end_at": now + timedelta(days=20),
            "subscription_tier": "GOLD",
            "subscription_purchase_source": "beta_trial",
            "subscription_access": ["home", "workout"],
        }

        summary = backend_module._build_subscription_summary(user)

        self.assertEqual(summary["tier"], "GOLD")
        self.assertEqual(summary["status"], "ACTIVE")
        self.assertFalse(summary["is_purchased"])
        self.assertIn("mealPlan", summary["access"])
        self.assertTrue(backend_module._user_has_subscription_access(user, "mealPlan"))

    def test_expired_beta_user_loses_gold_access(self) -> None:
        now = _utc_now()
        user = {
            "_id": "user-2",
            "trial_tier_granted": "gold",
            "trial_start_at": now - timedelta(days=30),
            "trial_end_at": now - timedelta(seconds=1),
            "subscription_tier": "GOLD",
            "subscription_purchase_source": "beta_trial",
            "subscription_access": backend_module._resolve_subscription_access("GOLD"),
        }

        summary = backend_module._build_subscription_summary(user)

        self.assertEqual(summary["status"], "EXPIRED")
        self.assertEqual(summary["access"], [])
        self.assertFalse(backend_module._user_has_subscription_access(user, "mealPlan"))


class PhaseOneBetaActivationTests(unittest.IsolatedAsyncioTestCase):
    async def test_activation_creates_21_day_zero_cost_gold_beta_subscription(self) -> None:
        now = _utc_now()
        user = {
            "_id": "user-3",
            "email": "beta@example.com",
            "name": "Beta User",
            "phase_one_beta_requested_code": "BETA-001",
        }
        updated_user = {
            **user,
            "subscription_purchase_source": "beta_trial",
            "trial_tier_granted": "gold",
            "trial_start_at": now,
            "trial_end_at": now + timedelta(days=21),
        }
        users_collection = SimpleNamespace(
            update_one=AsyncMock(),
            find_one=AsyncMock(return_value=updated_user),
        )
        phase_one_beta_slots_collection = SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            find_one_and_update=AsyncMock(return_value={"slot_number": 1, "claimed_by": "user-3"}),
        )
        settings = SimpleNamespace(
            phase_one_beta_enabled=True,
            phase_one_beta_duration_days=21,
            phase_one_beta_max_users=300,
            phase_one_beta_access_codes=["BETA-001"],
        )

        with patch.object(backend_module, "users_collection", users_collection), patch.object(
            backend_module, "phase_one_beta_slots_collection", phase_one_beta_slots_collection
        ), patch.object(
            backend_module, "settings", settings
        ):
            result = await backend_module._maybe_activate_phase_one_beta_subscription(user)

        self.assertEqual(result["subscription_purchase_source"], "beta_trial")
        update_doc = users_collection.update_one.await_args.args[1]["$set"]
        self.assertEqual(update_doc["subscription_tier"], "GOLD")
        self.assertEqual(update_doc["subscription_price_amount"], 0)
        self.assertFalse(update_doc["subscription_is_purchased"])
        self.assertEqual(update_doc["subscription"]["currency"], "EUR")
        self.assertFalse(update_doc["subscription"]["payment_required"])
        self.assertEqual(
            update_doc["trial_end_at"] - update_doc["trial_start_at"],
            timedelta(days=21),
        )

    async def test_existing_beta_user_does_not_restart_trial_window(self) -> None:
        now = _utc_now()
        user = {
            "_id": "user-4",
            "subscription_purchase_source": "beta_trial",
            "trial_start_at": now - timedelta(days=22),
            "trial_end_at": now - timedelta(days=1),
        }

        result = await backend_module._maybe_activate_phase_one_beta_subscription(user, requested_code="BETA-001")

        self.assertIs(result, user)

    async def test_301st_user_is_rejected_when_no_slot_is_available(self) -> None:
        user = {
            "_id": "user-301",
            "phase_one_beta_requested_code": "BETA-001",
        }
        phase_one_beta_slots_collection = SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            find_one_and_update=AsyncMock(return_value=None),
        )
        settings = SimpleNamespace(
            phase_one_beta_enabled=True,
            phase_one_beta_duration_days=21,
            phase_one_beta_max_users=300,
            phase_one_beta_access_codes=["BETA-001"],
        )

        with patch.object(
            backend_module, "phase_one_beta_slots_collection", phase_one_beta_slots_collection
        ), patch.object(
            backend_module, "settings", settings
        ):
            with self.assertRaises(Exception) as context:
                await backend_module._maybe_activate_phase_one_beta_subscription(user)

        self.assertIn("capacity", str(context.exception).lower())


class DependencyEntitlementTests(unittest.TestCase):
    def test_dependencies_module_denies_expired_beta_gold_access(self) -> None:
        now = _utc_now()
        user = {
            "subscription_purchase_source": "beta_trial",
            "trial_start_at": now - timedelta(days=30),
            "trial_end_at": now,
            "subscription_tier": "GOLD",
            "subscription_access": dependencies_module.resolve_subscription_access("GOLD"),
        }

        self.assertFalse(dependencies_module.user_has_active_gold_trial(user, now))
        self.assertFalse(dependencies_module.user_has_subscription_access(user, "longevity"))


class StripePhaseOneRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(payments_router_module.router)
        app.dependency_overrides[payments_router_module._require_access_user] = lambda: {
            "_id": "user-1",
            "is_verified": True,
        }
        cls.client = TestClient(app)

    def test_checkout_session_endpoint_is_disabled_during_phase_one_beta(self) -> None:
        with patch.object(
            payments_router_module,
            "settings",
            SimpleNamespace(stripe_payments_enabled=False, phase_one_beta_enabled=True),
        ), patch.object(
            stripe_payments_module,
            "settings",
            SimpleNamespace(stripe_payments_enabled=False, phase_one_beta_enabled=True),
        ):
            response = self.client.post(
                "/payments/stripe/checkout-session",
                json={
                    "subscription_tier": "GOLD",
                    "billing_cycle": "yearly",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("temporarily disabled", response.json()["detail"])

    def test_checkout_session_endpoint_is_disabled_when_phase_one_beta_flag_is_true(self) -> None:
        with patch.object(
            payments_router_module,
            "settings",
            SimpleNamespace(stripe_payments_enabled=True, phase_one_beta_enabled=True),
        ), patch.object(
            stripe_payments_module,
            "settings",
            SimpleNamespace(stripe_payments_enabled=True, phase_one_beta_enabled=True),
        ):
            response = self.client.post(
                "/payments/stripe/checkout-session",
                json={
                    "subscription_tier": "GOLD",
                    "billing_cycle": "yearly",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("temporarily disabled", response.json()["detail"])

    def test_webhook_returns_received_without_processing_when_disabled(self) -> None:
        with patch.object(
            payments_router_module,
            "settings",
            SimpleNamespace(stripe_payments_enabled=False),
        ):
            response = self.client.post("/webhooks/stripe", data=b"{}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True})


class PhaseOneBetaActivationRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(trial_router_module.router)
        app.dependency_overrides[trial_router_module._require_access_user] = lambda: {
            "_id": "beta-user-1",
            "name": "Beta User",
            "email": "beta@example.com",
            "subscription_tier": "NONE",
            "country_code": "DE",
            "is_verified": True,
        }
        cls.client = TestClient(app)

    def test_phase_one_beta_start_activates_user_without_stripe(self) -> None:
        now = _utc_now()
        feature_access = backend_module._resolve_subscription_access("GOLD")
        updated_user = {
            "_id": "beta-user-1",
            "name": "Beta User",
            "email": "beta@example.com",
            "is_verified": True,
            "subscription_tier": "GOLD",
            "subscription_role": "GOLD",
            "subscription_status": "ACTIVE",
            "subscription_billing_cycle": "yearly",
            "subscription_is_purchased": False,
            "subscription_purchase_source": "beta_trial",
            "subscription_access": feature_access,
            "subscription_started_at": now,
            "subscription_confirmed_at": now,
            "trial_tier_granted": "gold",
            "trial_start_at": now,
            "trial_end_at": now + timedelta(days=21),
            "country_code": "DE",
            "country": "Germany",
            "beta_phase_one": {"is_beta_tester": True},
            "subscription": {
                "tier": "GOLD",
                "role": "GOLD",
                "status": "ACTIVE",
                "billing_cycle": "yearly",
                "is_purchased": False,
                "purchase_source": "beta_trial",
                "access": feature_access,
                "started_at": now,
                "confirmed_at": now,
                "trial_type": "beta_trial",
                "payment_required": False,
                "price": 0,
                "currency": "EUR",
                "expires_at": now + timedelta(days=21),
            },
        }

        with patch.object(trial_router_module, "_is_phase_one_beta_enabled", return_value=True), patch.object(
            trial_router_module, "_is_phase_one_beta_user", return_value=False
        ), patch.object(
            trial_router_module, "_normalize_subscription_tier", return_value="NONE"
        ), patch.object(
            trial_router_module, "_claim_phase_one_beta_slot", AsyncMock(return_value={"slot_number": 1})
        ), patch.object(
            trial_router_module, "_activate_phase_one_beta_subscription", AsyncMock(return_value=updated_user)
        ), patch.object(
            trial_router_module, "_serialize_me_record", AsyncMock(return_value=backend_module._serialize_me_record(updated_user))
        ), patch.object(
            trial_router_module, "notify_user", AsyncMock()
        ) as notify_mock, patch.object(
            trial_router_module, "_record_analytics_event", AsyncMock()
        ) as analytics_mock:
            response = self.client.post("/me/trial/phase-one-beta/start")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["subscription_tier"], "GOLD")
        self.assertEqual(payload["subscription_purchase_source"], "beta_trial")
        self.assertFalse(payload["subscription_is_purchased"])
        notify_mock.assert_awaited()
        analytics_mock.assert_awaited()


class PhaseOneBetaAdminSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_returns_overview_activity_windows_and_checkpoints(self) -> None:
        now = _utc_now()
        beta_users = [
            {
                "_id": "beta-1",
                "name": "Ama Gold",
                "email": "ama@example.com",
                "country": "Ghana",
                "country_code": "GH",
                "trial_tier_granted": "gold",
                "trial_start_at": now - timedelta(days=8),
                "trial_end_at": now + timedelta(days=13),
                "subscription_tier": "GOLD",
                "subscription_status": "ACTIVE",
                "subscription_purchase_source": "beta_trial",
                "subscription_price_amount": 0,
                "subscription": {"currency": "EUR", "payment_required": False},
            },
            {
                "_id": "beta-2",
                "name": "Expired Beta",
                "email": "expired@example.com",
                "country": "Germany",
                "country_code": "DE",
                "trial_tier_granted": "gold",
                "trial_start_at": now - timedelta(days=25),
                "trial_end_at": now - timedelta(days=1),
                "subscription_tier": "GOLD",
                "subscription_status": "ACTIVE",
                "subscription_purchase_source": "beta_trial",
                "subscription_price_amount": 0,
                "subscription": {"currency": "EUR", "payment_required": False},
            },
            {
                "_id": "beta-3",
                "name": "New Beta",
                "email": "new@example.com",
                "country": "Ghana",
                "country_code": "GH",
                "trial_tier_granted": "gold",
                "trial_start_at": now - timedelta(days=2),
                "trial_end_at": now + timedelta(days=19),
                "subscription_tier": "GOLD",
                "subscription_status": "ACTIVE",
                "subscription_purchase_source": "beta_trial",
                "subscription_price_amount": 0,
                "subscription": {"currency": "EUR", "payment_required": False},
            },
        ]
        thread_messages = {
            "beta-1": [
                {"role": "user", "created_at": now - timedelta(days=7)},
                {"role": "assistant", "created_at": now - timedelta(days=7)},
                {"role": "user", "created_at": now - timedelta(days=3)},
                {"role": "user", "created_at": now - timedelta(days=30)},
            ],
            "beta-3": [
                {"role": "user", "created_at": now - timedelta(days=3)},
            ],
        }
        nutrition_jobs = [
            {"user_id": "beta-1", "created_at": now - timedelta(days=6)},
            {"user_id": "beta-3", "created_at": now + timedelta(days=30)},
        ]
        meal_entries = [
            {"user_id": "beta-1", "created_at": now - timedelta(days=5)},
            {"user_id": "beta-1", "created_at": now - timedelta(days=12)},
        ]
        workout_logs = [
            {"user_id": "beta-1", "started_at": now - timedelta(days=4), "completed_at": now - timedelta(days=4), "status": "completed"},
            {"user_id": "beta-3", "started_at": now - timedelta(days=5), "completed_at": now - timedelta(days=5), "status": "completed"},
        ]
        challenge_memberships = [
            {"user_id": "beta-1", "joined_at": now - timedelta(days=2), "completed_at": None, "status": "ACTIVE"},
            {"user_id": "beta-1", "joined_at": now - timedelta(days=15), "completed_at": now + timedelta(days=2), "status": "COMPLETED"},
        ]
        community_posts = [{"author_id": "beta-1", "created_at": now - timedelta(days=1)}]
        community_comments = [{"author_id": "beta-1", "created_at": now - timedelta(days=1)}]
        community_reactions = [{"user_id": "beta-1", "created_at": now - timedelta(days=1)}]
        support_messages = [{"user_id": "beta-1", "created_at": now - timedelta(days=2)}]

        collection_map = {}

        async def fake_load_records(collection, query, projection=None):
            return collection_map.get(collection, [])

        with patch.object(beta_analytics_service_module, "users_collection", "users"), patch.object(
            beta_analytics_service_module,
            "nutrition_plan_jobs_collection",
            "nutrition_jobs",
        ), patch.object(
            beta_analytics_service_module,
            "meal_analysis_entries_collection",
            "meal_entries",
        ), patch.object(
            beta_analytics_service_module,
            "workout_logs_collection",
            "workout_logs",
        ), patch.object(
            beta_analytics_service_module,
            "challenge_memberships_collection",
            "challenge_memberships",
        ), patch.object(
            beta_analytics_service_module,
            "community_posts_collection",
            "community_posts",
        ), patch.object(
            beta_analytics_service_module,
            "community_comments_collection",
            "community_comments",
        ), patch.object(
            beta_analytics_service_module,
            "community_reactions_collection",
            "community_reactions",
        ), patch.object(
            beta_analytics_service_module,
            "support_messages_collection",
            "support_messages",
        ), patch.object(
            beta_analytics_service_module,
            "_load_records",
            side_effect=fake_load_records,
        ), patch.object(
            beta_analytics_service_module,
            "_load_beta_thread_messages",
            AsyncMock(return_value=thread_messages),
        ), patch.object(
            beta_analytics_service_module,
            "_phase_one_beta_max_users",
            return_value=300,
        ):
            collection_map.update(
                {
                    "users": beta_users,
                    "nutrition_jobs": nutrition_jobs,
                    "meal_entries": meal_entries,
                    "workout_logs": workout_logs,
                    "challenge_memberships": challenge_memberships,
                    "community_posts": community_posts,
                    "community_comments": community_comments,
                    "community_reactions": community_reactions,
                    "support_messages": support_messages,
                }
            )
            response = await beta_analytics_service_module.build_phase_one_beta_analytics(limit=300)

        self.assertEqual(response.totalBetaUsers, 3)
        self.assertEqual(response.remainingSlots, 297)
        self.assertEqual(response.activeBetaUsers, 2)
        self.assertEqual(response.expiredBetaUsers, 1)
        self.assertEqual(response.goldBetaUsers, 3)
        self.assertEqual(response.averageDaysRemaining, 16.0)
        self.assertEqual(response.countriesRepresented, 2)
        self.assertEqual(response.participation.neverActiveUsers, 2)
        self.assertEqual(response.featureAdoption.aiCoach.users, 1)
        self.assertEqual(response.featureAdoption.aiCoach.total, 2)
        self.assertEqual(response.featureAdoption.nutrition.users, 1)
        self.assertEqual(response.featureAdoption.workouts.users, 1)
        self.assertEqual(response.featureAdoption.challenges.users, 1)
        self.assertEqual(response.featureAdoption.community.users, 1)
        self.assertEqual(response.crossFeatureAdoption.usedThreePlusFeatures, 1)
        self.assertEqual(response.crossFeatureAdoption.usedNoTrackedFeature, 2)
        self.assertEqual(response.support.totalSupportMessages, 1)
        self.assertEqual(len(response.checkpoints), 21)
        self.assertEqual(response.checkpoints[0].day, 1)
        self.assertEqual(response.checkpoints[0].eligibleUsers, 3)
        self.assertEqual(response.checkpoints[2].day, 3)
        self.assertEqual(response.checkpoints[2].eligibleUsers, 2)
        self.assertEqual(response.checkpoints[2].anyFeatureUsers, 1)
        self.assertEqual(response.checkpoints[6].day, 7)
        self.assertEqual(response.checkpoints[6].eligibleUsers, 2)
        self.assertEqual(response.checkpoints[6].anyFeatureUsers, 1)
        self.assertEqual(response.checkpoints[13].day, 14)
        self.assertEqual(response.checkpoints[13].eligibleUsers, 1)
        self.assertEqual(response.checkpoints[-1].day, 21)
        self.assertEqual(response.checkpoints[-1].eligibleUsers, 1)
        self.assertEqual(response.checkpoints[-1].anyFeatureUsers, 0)
        self.assertEqual([(item.label, item.count, item.activeUsers) for item in response.countries], [("Ghana", 2, 2), ("Germany", 1, 0)])
        active_user = next(user for user in response.users if user.id == "beta-1")
        self.assertEqual(active_user.country, "Ghana")
        self.assertEqual(active_user.countryCode, "GH")
        self.assertEqual(active_user.activity.aiMessages, 2)
        self.assertEqual(active_user.activity.nutritionLogs, 1)
        self.assertEqual(active_user.activity.workoutsCompleted, 1)
        self.assertEqual(active_user.activity.challengesJoined, 1)
        self.assertEqual(active_user.activity.communityPosts, 1)
        self.assertEqual(active_user.price, 0)
        self.assertFalse(active_user.paymentRequired)
        self.assertTrue(all(user.trialType == "beta_trial" for user in response.users))

    def test_admin_route_requires_admin_auth(self) -> None:
        app = FastAPI()
        app.include_router(admin_trials_router_module.router)
        client = TestClient(app)
        response = client.get("/admin/trials/phase-one-beta")
        self.assertIn(response.status_code, {401, 403})


if __name__ == "__main__":
    unittest.main()
