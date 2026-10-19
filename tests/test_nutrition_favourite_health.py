from __future__ import annotations

import unittest
from app.nutrition_ai import (
    _build_fallback_nutrition_plan,
    _normalize_nutrition_plan,
    calculate_protein_target,
    build_nutrition_plan_signature,
    _favorite_meals_instruction,
)
from app.models import NutritionPlanRequest, FavoriteFoodPreference


class NutritionFavouriteFoodsHealthTests(unittest.TestCase):
    """
    Test suite verifying the 8 specific test cases required for Victory Fitness
    favourite foods health suitability option and meal plan generation.
    """

    def test_case_1_maintenance(self) -> None:
        """
        TEST 1 — Maintenance:
        70kg, Goal = maintenance, Favourite = Fufu, Not healthy for me
        Expected:
        - protein >= ~112g/day
        - Fufu approximately 1–3 meals/week
        - not daily
        - calories/macros remain valid
        - meal variety remains good
        """
        payload = {
            "weight": "70",
            "goal": "g3",
            "cuisine": "Ghanaian",
            "favorite_meals": ["Fufu"],
            "favorite_meals_preferences": {"Fufu": "not_healthy_for_me"},
            "favorite_foods_details": [
                {"name": "Fufu", "is_favourite": True, "health_preference": "not_healthy_for_me"}
            ],
        }
        req = NutritionPlanRequest(**payload)
        self.assertEqual(req.favorite_meals_preferences.get("Fufu"), "not_healthy_for_me")

        plan = _build_fallback_nutrition_plan(req.model_dump())
        self.assertGreaterEqual(plan["daily_protein_target"], 112)

        fufu_count = 0
        all_dishes = []
        for day in plan["days"]:
            day_p = 0
            for slot in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"):
                meal = day[slot]
                name = meal["name"].lower()
                all_dishes.append(name)
                if "fufu" in name:
                    fufu_count += 1
                # Validate macro math: kcal = (p * 4) + (c * 4) + (f * 9) within ±5
                expected_kcal = (meal["p"] * 4) + (meal["c"] * 4) + (meal["f"] * 9)
                self.assertAlmostEqual(meal["kcal"], expected_kcal, delta=5)
                day_p += meal["p"]
            self.assertEqual(day_p, plan["daily_protein_target"])

        # Fufu appears approx 1–3 meals/week, NEVER daily
        self.assertGreaterEqual(fufu_count, 1)
        self.assertLessEqual(fufu_count, 3)
        self.assertLess(fufu_count, 7)

        # Pre/post workout must never be Fufu
        for day in plan["days"]:
            self.assertNotIn("fufu", day["pre_workout"]["name"].lower())
            self.assertNotIn("fufu", day["post_workout"]["name"].lower())

        # Meal variety: multiple distinct meals across the week
        unique_dishes = set(all_dishes)
        self.assertGreaterEqual(len(unique_dishes), 8)

    def test_case_2_weight_loss(self) -> None:
        """
        TEST 2 — Weight Loss:
        Goal = weight loss, Favourite = high-calorie food (Pizza), Not healthy for me
        Expected:
        - favourite may still appear occasionally
        - normally toward lower end of 1–3 frequency (1–2 meals)
        - calorie deficit remains priority
        - portions controlled
        - no daily repetition
        """
        payload = {
            "weight": "80",
            "goal": "g1",
            "cuisine": "Italian",
            "favorite_meals": ["Pizza"],
            "favorite_meals_preferences": {"Pizza": "not_healthy_for_me"},
            "favorite_foods_details": [
                {"name": "Pizza", "is_favourite": True, "health_preference": "not_healthy_for_me"}
            ],
        }
        req = NutritionPlanRequest(**payload)
        plan = _build_fallback_nutrition_plan(req.model_dump())

        pizza_count = 0
        for day in plan["days"]:
            for slot in ("lunch", "dinner"):
                meal = day[slot]
                if "pizza" in meal["name"].lower():
                    pizza_count += 1
                    # Controlled portions: calorie compliance
                    self.assertLessEqual(meal["kcal"], 650)

        # Weight loss frequency: 1–2 meals across the week
        self.assertGreaterEqual(pizza_count, 1)
        self.assertLessEqual(pizza_count, 2)

    def test_case_3_muscle_gain(self) -> None:
        """
        TEST 3 — Muscle Gain:
        Goal = muscle gain, Favourite = Fufu, Not healthy for me
        Expected:
        - may appear occasionally
        - protein pairing appropriate
        - protein/calories meet muscle-gain target
        - does not dominate plan
        """
        payload = {
            "weight": "75",
            "goal": "muscle gain",
            "cuisine": "Ghanaian",
            "favorite_meals": ["Fufu"],
            "favorite_meals_preferences": {"Fufu": "not_healthy_for_me"},
        }
        req = NutritionPlanRequest(**payload)
        plan = _build_fallback_nutrition_plan(req.model_dump())

        # Protein multiplier for muscle gain is 2.0-2.2 g/kg (>= 150g for 75kg user)
        self.assertGreaterEqual(plan["daily_protein_target"], 150)

        fufu_count = sum(
            1 for day in plan["days"]
            for slot in ("lunch", "dinner")
            if "fufu" in day[slot]["name"].lower()
        )
        # Occasional 1–3 times, does not dominate
        self.assertGreaterEqual(fufu_count, 1)
        self.assertLessEqual(fufu_count, 3)

    def test_case_4_healthy_favourite(self) -> None:
        """
        TEST 4 — Healthy Favourite:
        Favourite = grilled fish, Healthy for me
        Expected:
        - may appear more frequently
        - but still not blindly every day
        - maintain variety
        """
        payload = {
            "weight": "70",
            "goal": "g3",
            "cuisine": "Mediterranean",
            "favorite_meals": ["Grilled fish"],
            "favorite_meals_preferences": {"Grilled fish": "healthy_for_me"},
        }
        req = NutritionPlanRequest(**payload)
        plan = _build_fallback_nutrition_plan(req.model_dump())

        fish_count = sum(
            1 for day in plan["days"]
            for slot in ("lunch", "dinner")
            if "fish" in day[slot]["name"].lower()
        )
        # Can appear more regularly (e.g. 3-4 times), but NOT 7/7 days
        self.assertGreaterEqual(fish_count, 2)
        self.assertLessEqual(fish_count, 5)

        # Other meals provide variety
        all_lunches_and_dinners = [
            day[slot]["name"].lower()
            for day in plan["days"]
            for slot in ("lunch", "dinner")
        ]
        non_fish = [d for d in all_lunches_and_dinners if "fish" not in d]
        self.assertGreater(len(non_fish), 3)

    def test_case_5_allergy_conflict(self) -> None:
        """
        TEST 5 — Allergy Conflict:
        Favourite food conflicts with known allergy.
        Expected:
        - food NEVER appears
        - safety overrides favourite and health-preference status
        """
        payload = {
            "weight": "75",
            "goal": "g3",
            "cuisine": "Ghanaian",
            "allergies": "peanut, tree nuts",
            "favorite_meals": ["Groundnut soup", "Peanut butter stew"],
            "favorite_meals_preferences": {
                "Groundnut soup": "healthy_for_me",
                "Peanut butter stew": "healthy_for_me",
            },
        }
        req = NutritionPlanRequest(**payload)
        plan = _build_fallback_nutrition_plan(req.model_dump())

        # Hard Safety Exception: Groundnut and Peanut must NEVER appear
        for day in plan["days"]:
            for slot in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"):
                name = day[slot]["name"].lower()
                self.assertNotIn("groundnut", name)
                self.assertNotIn("peanut", name)
                ingredients = [i.lower() for i in day[slot]["ingredients"]]
                self.assertFalse(any("groundnut" in ing or "peanut" in ing for ing in ingredients))

    def test_case_6_ghana_country_priority(self) -> None:
        """
        TEST 6 — Ghana:
        Country = Ghana, Favourite = Fufu, Not healthy for me
        Expected:
        - Ghana approved-food data prioritized
        - Fufu approximately 1–3 times when appropriate
        - other Ghana foods provide variety
        - macros/goals preserved
        """
        payload = {
            "weight": "72",
            "goal": "g3",
            "country": "Ghana",
            "country_code": "GH",
            "cuisine": "Ghanaian",
            "favorite_meals": ["Fufu"],
            "favorite_meals_preferences": {"Fufu": "not_healthy_for_me"},
        }
        req = NutritionPlanRequest(**payload)
        plan = _build_fallback_nutrition_plan(req.model_dump())

        fufu_count = 0
        ghana_dishes_found = set()
        approved_ghana_markers = ["waakye", "banku", "yam", "kontomire", "jollof", "red red", "light soup", "tilapia"]

        for day in plan["days"]:
            for slot in ("lunch", "dinner"):
                name = day[slot]["name"].lower()
                if "fufu" in name:
                    fufu_count += 1
                for marker in approved_ghana_markers:
                    if marker in name:
                        ghana_dishes_found.add(marker)

        # Fufu appears approx 1–3 times, NOT every day
        self.assertGreaterEqual(fufu_count, 1)
        self.assertLessEqual(fufu_count, 3)

        # Other Ghana approved foods provide authentic variety
        self.assertGreaterEqual(len(ghana_dishes_found), 3)

    def test_case_7_existing_user_backward_compatibility(self) -> None:
        """
        TEST 7 — Existing User:
        Favourite = Fufu, No stored health preference
        Expected:
        - generation still works
        - health preference treated as unknown / unspecified
        - backward compatibility preserved
        """
        # Legacy payload without health_preference or favorite_foods_details
        payload = {
            "weight": "70",
            "goal": "g3",
            "cuisine": "Ghanaian",
            "favorite_meals": ["Fufu"],
        }
        req = NutritionPlanRequest(**payload)
        # Default is unspecified
        self.assertEqual(req.favorite_meals_preferences.get("Fufu"), "unspecified")
        self.assertEqual(req.favorite_foods_details[0].health_preference, "unspecified")

        plan = _build_fallback_nutrition_plan(req.model_dump())
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan["days"]), 7)

        # Normal limit applies, does not crash, does not repeat every day
        fufu_count = sum(
            1 for day in plan["days"]
            for slot in ("lunch", "dinner")
            if "fufu" in day[slot]["name"].lower()
        )
        self.assertGreaterEqual(fufu_count, 1)
        self.assertLessEqual(fufu_count, 3)

    def test_case_8_edit_preference(self) -> None:
        """
        TEST 8 — Edit Preference:
        Initial: Fufu = Healthy for me
        Change to: Fufu = Not healthy for me
        Expected:
        - preference saved
        - signatures differ
        - plan reduces Fufu frequency appropriately
        """
        payload_healthy = {
            "weight": "75",
            "goal": "g3",
            "cuisine": "Ghanaian",
            "favorite_meals": ["Fufu"],
            "favorite_meals_preferences": {"Fufu": "healthy_for_me"},
        }
        payload_not_healthy = {
            "weight": "75",
            "goal": "g3",
            "cuisine": "Ghanaian",
            "favorite_meals": ["Fufu"],
            "favorite_meals_preferences": {"Fufu": "not_healthy_for_me"},
        }

        # Verify signature changes so cache does not return stale plan
        sig_healthy = build_nutrition_plan_signature(payload_healthy)
        sig_not_healthy = build_nutrition_plan_signature(payload_not_healthy)
        self.assertNotEqual(sig_healthy, sig_not_healthy)

        plan_healthy = _build_fallback_nutrition_plan(payload_healthy)
        plan_not_healthy = _build_fallback_nutrition_plan(payload_not_healthy)

        count_healthy = sum(
            1 for day in plan_healthy["days"]
            for slot in ("lunch", "dinner")
            if "fufu" in day[slot]["name"].lower()
        )
        count_not_healthy = sum(
            1 for day in plan_not_healthy["days"]
            for slot in ("lunch", "dinner")
            if "fufu" in day[slot]["name"].lower()
        )

        self.assertLessEqual(count_not_healthy, count_healthy)
        self.assertLessEqual(count_not_healthy, 3)


if __name__ == "__main__":
    unittest.main()
