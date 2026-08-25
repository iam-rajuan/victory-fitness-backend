from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app import conversion_service
from app.core.legacy import _serialize_onboarding_state


class ConversionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_should_show_post_workout_upsell_requires_more_than_first_workout(self) -> None:
        user = {"_id": "user-1", "subscription_tier": "GOLD", "workouts_completed": 1}

        eligible, reason = await conversion_service.should_show_post_workout_upsell(user)

        self.assertFalse(eligible)
        self.assertEqual(reason, "first_workout")

    async def test_should_show_post_workout_upsell_respects_48_hour_cooldown(self) -> None:
        user = {"_id": "user-1", "subscription_tier": "SILVER", "workouts_completed": 5}
        fake_collection = type(
            "Collection",
            (),
            {"find_one": AsyncMock(return_value={"_id": "card-1"})},
        )()

        with patch.object(conversion_service, "completion_cards_collection", fake_collection):
            eligible, reason = await conversion_service.should_show_post_workout_upsell(user)

        self.assertFalse(eligible)
        self.assertEqual(reason, "cooldown")

    async def test_resolve_notification_variant_uses_template_bucket(self) -> None:
        user = {"_id": "user-variant"}
        templates = [
            {
                "id": "workout_reminder",
                "type": "workout_reminder",
                "title": "Workout reminder",
                "frequencyCapHours": 24,
                "variants": [
                    {"key": "a", "title": "A title", "message": "A body"},
                    {"key": "b", "title": "B title", "message": "B body"},
                ],
            }
        ]

        with patch.object(conversion_service, "list_notification_templates", AsyncMock(return_value=templates)), patch.object(
            conversion_service, "assign_notification_variant", return_value=1
        ):
            title, message, variant = await conversion_service.resolve_notification_variant(
                user,
                "workout_reminder",
                "Fallback title",
                "Fallback body",
            )

        self.assertEqual(title, "B title")
        self.assertEqual(message, "B body")
        self.assertEqual(variant, "b")


class OnboardingSerializationTests(unittest.TestCase):
    def test_serialize_onboarding_state_includes_motivation_statement(self) -> None:
        now = datetime.now(timezone.utc)
        record = {
            "_id": "user-99",
            "country": "Germany",
            "country_code": "DE",
            "motivation_statement": "feel stronger for my kids",
            "body_metrics": {"age": "31"},
            "onboarding_completed": False,
            "onboarding_state": {
                "currentStep": 4,
                "language": "en",
                "motivationStatement": "feel stronger for my kids",
                "updatedAt": now,
            },
        }

        serialized = _serialize_onboarding_state(record)

        self.assertEqual(serialized["motivationStatement"], "feel stronger for my kids")
        self.assertEqual(serialized["countryCode"], "DE")


if __name__ == "__main__":
    unittest.main()
