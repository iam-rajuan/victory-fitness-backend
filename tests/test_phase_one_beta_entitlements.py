from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone


legacy_module = importlib.import_module("app.core.legacy")


class PhaseOneBetaEntitlementTests(unittest.TestCase):
    def test_beta_users_honor_configured_subscription_access(self) -> None:
        now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        user = {
            "subscription_purchase_source": "beta_trial",
            "trial_start_at": now - timedelta(days=2),
            "trial_end_at": now + timedelta(days=19),
            "subscription_access": ["home", "challenge", "coach_victor"],
        }

        self.assertTrue(legacy_module._user_has_subscription_access(user, "coach_victor"))
        self.assertFalse(legacy_module._user_has_subscription_access(user, "application"))

    def test_beta_subscription_summary_preserves_configured_access_and_beta_tier(self) -> None:
        now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        summary = legacy_module._build_subscription_summary(
            {
                "subscription_tier": "GOLD_BETA",
                "subscription_role": "GOLD_BETA",
                "subscription_status": "ACTIVE",
                "subscription_purchase_source": "beta_trial",
                "trial_start_at": now - timedelta(days=3),
                "trial_end_at": now + timedelta(days=18),
                "subscription_access": ["home", "mealPlan", "workoutplan", "coach_victor"],
            }
        )

        self.assertEqual(summary["tier"], "GOLD_BETA")
        self.assertEqual(summary["status"], "ACTIVE")
        self.assertEqual(
            summary["access"],
            ["home", "mealPlan", "workoutplan", "coach_victor"],
        )


if __name__ == "__main__":
    unittest.main()
