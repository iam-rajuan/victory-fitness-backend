import unittest

from app.coach_victor import build_coach_victor_system_prompt


class CoachVictorPromptAssemblyTests(unittest.TestCase):
    def test_prompt_contains_section_thirteen_layers(self) -> None:
        prompt = build_coach_victor_system_prompt(
            user_context={
                "country": "Germany",
                "country_code": "DE",
                "subscription_tier": "GOLD",
                "onboarding": {
                    "personalProfile": {"age": "29", "gender": "Male", "height": "180", "heightUnit": "cm", "weight": "82", "weightUnit": "kg"},
                    "anamnese": {"primaryGoal": "Fat loss", "activityLevel": "Moderate", "daysPerWeek": "4", "timePerSession": "45 min", "equipmentAccess": "Gym"},
                },
                "nutrition_profile": {"protein_target_g": 180, "favorite_meals_json": ["eggs", "rice bowl"], "health_conditions": ["asthma"]},
                "habit_fields": {
                    "identity_statement": "I train even when work is busy",
                    "workout_unlock_label": "After work",
                    "training_trigger_context": "Right after office",
                },
                "longevity": {"completed_habits": ["Walk after dinner"], "pending_habits": ["Water before coffee"]},
                "progress": {"streak_days": 6, "recent_completed_workouts": 3, "recent_nutrition_actions": 5},
                "medical": {"health_notes": "Old knee irritation", "injury": "Left knee"},
            },
            recent_messages=[
                {"role": "user", "content": "How should I train legs this week?"},
                {"role": "assistant", "content": "Keep one hard and one moderate session."},
            ],
        )

        self.assertIn("Layer 1 - Coach identity", prompt)
        self.assertIn("Layer 2 - Country context", prompt)
        self.assertIn("Layer 3 - User profile and personalization", prompt)
        self.assertIn("Layer 4 - Progress and adaptation data", prompt)
        self.assertIn("Layer 5 - Today's context", prompt)
        self.assertIn("Layer 6 - Last 10 conversation messages", prompt)
        self.assertIn("Layer 7 - Medical and scope boundaries", prompt)
        self.assertIn("Favorite meals JSON", prompt)
        self.assertIn("Section 20 habit fields - identity statement", prompt)
        self.assertIn("How should I train legs this week?", prompt)
        self.assertIn("Old knee irritation", prompt)

    def test_prompt_limits_recent_messages_to_last_ten(self) -> None:
        prompt = build_coach_victor_system_prompt(
            user_context={},
            recent_messages=[{"role": "user", "content": f"message {index}"} for index in range(12)],
        )
        self.assertNotIn("user: message 0", prompt)
        self.assertNotIn("user: message 1\n", prompt)
        self.assertIn("user: message 2", prompt)
        self.assertIn("user: message 11", prompt)


if __name__ == "__main__":
    unittest.main()
