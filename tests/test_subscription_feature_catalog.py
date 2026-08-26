from __future__ import annotations

import unittest

from app.dependencies import (
    find_invalid_subscription_features,
    list_subscription_feature_catalog,
    normalize_subscription_feature_access,
)


class SubscriptionFeatureCatalogTests(unittest.TestCase):
    def test_catalog_contains_real_unlockable_feature_metadata(self) -> None:
        items = list_subscription_feature_catalog()

        self.assertGreater(len(items), 0)
        challenge_item = next(item for item in items if item["key"] == "challenge")

        self.assertEqual(challenge_item["label"], "Challenges")
        self.assertIn("/challenges", challenge_item["routeHints"])
        self.assertIn("SILVER", challenge_item["defaultTiers"])

    def test_invalid_feature_keys_are_reported(self) -> None:
        invalid = find_invalid_subscription_features(["challenge", "unknown_feature", "mealPlan"])

        self.assertEqual(invalid, ["unknown_feature"])

    def test_feature_access_is_normalized_and_deduplicated(self) -> None:
        normalized = normalize_subscription_feature_access(
            [" challenge ", "mealPlan", "challenge", "", None, "fake_key"]
        )

        self.assertEqual(normalized, ["challenge", "mealPlan"])


if __name__ == "__main__":
    unittest.main()
