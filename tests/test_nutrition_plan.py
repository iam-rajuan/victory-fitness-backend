from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


nutrition_router_module = importlib.import_module("app.api.routers.ai_nutrition")
nutrition_ai_module = importlib.import_module("app.nutrition_ai")


class _FakeNutritionPlansCollection:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def find_one(self, query, sort=None):
        user_id = query.get("user_id")
        profile_hash = query.get("profile_hash")
        matching = []
        for record in self.records:
            if record.get("user_id") != user_id:
                continue
            if isinstance(profile_hash, dict) and "$ne" in profile_hash:
                if record.get("profile_hash") == profile_hash["$ne"]:
                    continue
            elif profile_hash is not None and record.get("profile_hash") != profile_hash:
                continue
            matching.append(record)
        if not matching:
            return None
        return matching[-1]

    async def insert_one(self, document):
        record = dict(document)
        record["_id"] = f"plan-{len(self.records) + 1}"
        self.records.append(record)
        return SimpleNamespace(inserted_id=record["_id"])


class _FakeUsersCollection:
    def __init__(self) -> None:
        self.updated_payloads: list[dict] = []

    async def update_one(self, query, update):
        self.updated_payloads.append({"query": query, "update": update})
        return SimpleNamespace(modified_count=1)


class NutritionPlanPersistenceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(nutrition_router_module.router)
        app.dependency_overrides[nutrition_router_module._require_meal_plan_access_user] = lambda: {
            "_id": "nutrition-user-1",
            "subscription_tier": "GOLD",
            "subscription_status": "ACTIVE",
            "is_verified": True,
        }
        cls.client = TestClient(app)

    def test_generate_plan_persists_plan_and_user_onboarding_payload(self) -> None:
        fake_plans = _FakeNutritionPlansCollection()
        fake_users = _FakeUsersCollection()
        payload = {
            "goal": "g2",
            "cuisine": "Bangladeshi",
            "favorite_meal": "Lunch",
            "favorite_meals": ["Lunch", "Chicken curry", "Lentil soup"],
            "favorite_meals_json": ["Lunch", "Chicken curry", "Lentil soup"],
            "diet": "d2",
            "allergies": "peanut",
            "activity_level": "a3",
            "age": "25",
            "gender": "Male",
            "height": "180",
            "weight": "75",
            "health_conditions": ["h1"],
        }
        generated_data = {
            "summary": "A structured weekly meal plan.",
            "goal_label": "Muscle Building",
            "days": [
                {
                    "day": "Mon",
                    "breakfast": {
                        "name": "Egg oats",
                        "desc": "Protein breakfast",
                        "kcal": 420,
                        "p": 30,
                        "c": 35,
                        "f": 16,
                        "ingredients": ["Egg", "Oats"],
                        "instructions": ["Cook oats", "Add eggs"],
                    },
                    "lunch": {
                        "name": "Chicken rice",
                        "desc": "Balanced lunch",
                        "kcal": 620,
                        "p": 42,
                        "c": 60,
                        "f": 18,
                        "ingredients": ["Chicken", "Rice"],
                        "instructions": ["Cook rice", "Grill chicken"],
                    },
                    "dinner": {
                        "name": "Fish vegetables",
                        "desc": "Light dinner",
                        "kcal": 500,
                        "p": 36,
                        "c": 28,
                        "f": 20,
                        "ingredients": ["Fish", "Vegetables"],
                        "instructions": ["Bake fish", "Steam vegetables"],
                    },
                }
            ],
            "shopping_list": [{"category": "Protein", "items": [{"name": "Chicken", "qty": "1 kg"}]}],
            "meal_completions": {},
        }

        with patch.object(nutrition_router_module, "nutrition_plans_collection", fake_plans), patch.object(
            nutrition_router_module,
            "users_collection",
            fake_users,
        ), patch.object(
            nutrition_router_module,
            "_enforce_nutrition_generation_limit",
            AsyncMock(),
        ), patch.object(
            nutrition_router_module,
            "_record_trial_engagement",
            AsyncMock(),
        ), patch.object(
            nutrition_router_module,
            "generate_nutrition_plan",
            return_value=SimpleNamespace(data=generated_data),
        ), patch.object(
            nutrition_router_module,
            "build_nutrition_plan_signature",
            return_value="profile-hash-1",
        ):
            response = self.client.post("/ai/nutrition/plan", json=payload)
            latest_response = self.client.get("/ai/nutrition/plan/latest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(latest_response.status_code, 200)
        response_plan = response.json()["plan"]
        latest_plan = latest_response.json()

        self.assertEqual(response_plan["plan_id"], "plan-1")
        self.assertEqual(latest_plan["plan_id"], "plan-1")
        self.assertEqual(response_plan["profile"]["cuisine"], "Bangladeshi")
        self.assertEqual(latest_plan["profile"]["favorite_meal"], "Lunch")
        self.assertEqual(latest_plan["profile"]["favorite_meals"], ["Lunch", "Chicken curry", "Lentil soup"])
        self.assertEqual(latest_plan["profile"]["favorite_meals_json"], ["Lunch", "Chicken curry", "Lentil soup"])
        self.assertEqual(fake_plans.records[0]["plan"]["profile"]["diet"], "d2")
        self.assertEqual(
            fake_users.updated_payloads[-1]["update"]["$set"]["nutrition_onboarding_profile"]["activity_level"],
            "a3",
        )

    def test_generate_plan_enriches_payload_from_saved_user_country(self) -> None:
        fake_plans = _FakeNutritionPlansCollection()
        fake_users = _FakeUsersCollection()
        captured_payloads: list[dict] = []
        payload = {
            "goal": "g2",
            "cuisine": "balanced",
            "favorite_meals": ["Waakye", "Banku", "Fufu"],
            "diet": "balanced",
            "allergies": "",
            "activity_level": "a3",
            "weight": "75",
        }
        generated_data = nutrition_ai_module._build_fallback_nutrition_plan(
            {**payload, "country": "Ghana", "country_code": "GH"}
        )

        def _capture_generate(data):
            captured_payloads.append(dict(data))
            return SimpleNamespace(data=generated_data)

        app = self.client.app
        previous_override = app.dependency_overrides.get(nutrition_router_module._require_meal_plan_access_user)
        app.dependency_overrides[nutrition_router_module._require_meal_plan_access_user] = lambda: {
            "_id": "ghana-user-1",
            "subscription_tier": "GOLD",
            "subscription_status": "ACTIVE",
            "is_verified": True,
            "country": "Ghana",
            "country_code": "GH",
        }

        try:
            with patch.object(nutrition_router_module, "nutrition_plans_collection", fake_plans), patch.object(
                nutrition_router_module,
                "users_collection",
                fake_users,
            ), patch.object(
                nutrition_router_module,
                "_enforce_nutrition_generation_limit",
                AsyncMock(),
            ), patch.object(
                nutrition_router_module,
                "_record_trial_engagement",
                AsyncMock(),
            ), patch.object(
                nutrition_router_module,
                "generate_nutrition_plan",
                side_effect=_capture_generate,
            ), patch.object(
                nutrition_router_module,
                "build_nutrition_plan_signature",
                return_value="ghana-profile-hash",
            ):
                response = self.client.post("/ai/nutrition/plan", json=payload)
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(nutrition_router_module._require_meal_plan_access_user, None)
            else:
                app.dependency_overrides[nutrition_router_module._require_meal_plan_access_user] = previous_override
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_payloads[-1]["country"], "Ghana")
        self.assertEqual(captured_payloads[-1]["country_code"], "GH")
        self.assertEqual(fake_users.updated_payloads[-1]["update"]["$set"]["nutrition_onboarding_profile"]["country"], "Ghana")

    def test_generate_plan_allows_specific_cuisine_without_three_favorite_meals(self) -> None:
        fake_plans = _FakeNutritionPlansCollection()
        fake_users = _FakeUsersCollection()
        payload = {
            "goal": "g2",
            "cuisine": "Bangladeshi",
            "favorite_meal": "Lunch",
            "favorite_meals": ["Lunch", "Dinner"],
            "diet": "d2",
            "allergies": "",
            "activity_level": "a3",
            "age": "25",
            "gender": "Male",
            "height": "180",
            "weight": "75",
            "health_conditions": [],
        }
        generated_data = nutrition_ai_module._build_fallback_nutrition_plan(payload)

        with patch.object(nutrition_router_module, "nutrition_plans_collection", fake_plans), patch.object(
            nutrition_router_module,
            "users_collection",
            fake_users,
        ), patch.object(
            nutrition_router_module,
            "_enforce_nutrition_generation_limit",
            AsyncMock(),
        ), patch.object(
            nutrition_router_module,
            "_record_trial_engagement",
            AsyncMock(),
        ), patch.object(
            nutrition_router_module,
            "generate_nutrition_plan",
            return_value=SimpleNamespace(data=generated_data),
        ), patch.object(
            nutrition_router_module,
            "build_nutrition_plan_signature",
            return_value="specific-cuisine-hash",
        ):
            response = self.client.post("/ai/nutrition/plan", json=payload)

        self.assertEqual(response.status_code, 200)

    def test_generate_plan_allows_default_balanced_request_without_favorite_meals(self) -> None:
        fake_plans = _FakeNutritionPlansCollection()
        fake_users = _FakeUsersCollection()
        payload = {
            "goal": "g2",
            "cuisine": "balanced",
            "favorite_meal": None,
            "favorite_meals": [],
            "diet": "d2",
            "allergies": "",
            "activity_level": "a3",
            "age": "25",
            "gender": "Male",
            "height": "180",
            "weight": "75",
            "health_conditions": [],
        }
        generated_data = nutrition_ai_module._build_fallback_nutrition_plan(payload)

        with patch.object(nutrition_router_module, "nutrition_plans_collection", fake_plans), patch.object(
            nutrition_router_module,
            "users_collection",
            fake_users,
        ), patch.object(
            nutrition_router_module,
            "_enforce_nutrition_generation_limit",
            AsyncMock(),
        ), patch.object(
            nutrition_router_module,
            "_record_trial_engagement",
            AsyncMock(),
        ), patch.object(
            nutrition_router_module,
            "generate_nutrition_plan",
            return_value=SimpleNamespace(data=generated_data),
        ), patch.object(
            nutrition_router_module,
            "build_nutrition_plan_signature",
            return_value="default-balanced-hash",
        ):
            response = self.client.post("/ai/nutrition/plan", json=payload)

        self.assertEqual(response.status_code, 200)


class NutritionPlanFallbackTests(unittest.TestCase):
    def test_ghana_country_prompt_includes_approved_food_dataset(self) -> None:
        prompt = nutrition_ai_module._build_nutrition_plan_prompt(
            {
                "goal": "g2",
                "cuisine": "Ghanaian",
                "country": "Ghana",
                "country_code": "GH",
                "favorite_meals": ["Waakye", "Banku", "Fufu"],
                "weight": "75",
            }
        )

        self.assertIn("Active country dataset: Ghana", prompt)
        self.assertIn("Waakye -> with gari, shito, stew, talia, egg, wele, fried fish", prompt)
        self.assertIn("Fufu + Nkate nkwan -> with groundnut soup, chicken/goat", prompt)
        self.assertIn("Kpakpo shito", prompt)

    def test_non_ghana_prompt_does_not_include_ghana_dataset(self) -> None:
        prompt = nutrition_ai_module._build_nutrition_plan_prompt(
            {
                "goal": "g2",
                "cuisine": "Italian",
                "country": "Germany",
                "country_code": "DE",
                "favorite_meals": ["Pasta", "Pizza", "Risotto"],
                "weight": "75",
            }
        )

        self.assertNotIn("Active country dataset: Ghana", prompt)
        self.assertNotIn("Fufu + Nkate nkwan", prompt)

    def test_ghana_fallback_plan_prioritizes_approved_combinations(self) -> None:
        plan = nutrition_ai_module._build_fallback_nutrition_plan(
            {
                "goal": "g2",
                "cuisine": "Ghanaian",
                "country": "Ghana",
                "country_code": "GH",
                "diet": "balanced",
                "allergies": "",
                "weight": "75",
            }
        )

        meal_names = " | ".join(
            meal["name"]
            for day in plan["days"]
            for key, meal in day.items()
            if key != "day" and isinstance(meal, dict)
        )
        self.assertIn("Waakye with gari, shito, stew, talia, egg, wele, fried fish", meal_names)
        self.assertIn("Fufu + Nkate nkwan with groundnut soup, chicken/goat", meal_names)
        self.assertIn("approved Ghanaian food dataset", plan["summary"])

    def test_generate_nutrition_plan_returns_fallback_plan_when_model_json_is_unusable(self) -> None:
        payload = {
            "goal": "g2",
            "cuisine": "German",
            "favorite_meal": "Dinner",
            "favorite_meals": ["Dinner", "Tofu bowl", "Protein oats"],
            "diet": "d3",
            "allergies": "peanut",
            "activity_level": "a3",
            "age": "29",
            "gender": "Male",
            "height": "181",
            "weight": "79",
            "health_conditions": ["Inflammation"],
        }

        with patch.object(nutrition_ai_module, "_generate_nutrition_plan_json", return_value="not valid json"), patch.object(
            nutrition_ai_module,
            "_repair_nutrition_plan_json",
            return_value=None,
        ):
            result = nutrition_ai_module.generate_nutrition_plan(payload)

        self.assertEqual(result.data["goal_label"], "Muscle Building")
        self.assertEqual(len(result.data["days"]), 7)
        self.assertEqual(result.data["days"][0]["day"], "Mon")
        self.assertIn("Tofu and chickpeas", result.data["days"][0]["lunch"]["ingredients"])
        self.assertTrue(result.data["shopping_list"])

    def test_concise_nutrition_summary_across_goals_and_countries(self) -> None:
        """Validate dynamic concise structured summary with different goals, countries, and allergies."""
        build_summary = nutrition_ai_module.build_concise_nutrition_summary

        # 1. Ghanaian maintenance plan with nut allergy
        ghana_days = [
            {
                "day": "Mon",
                "breakfast": {"name": "Waakye", "kcal": 450, "p": 25},
                "lunch": {"name": "Red Red", "kcal": 700, "p": 40},
                "dinner": {"name": "Grilled Tilapia with Banku", "kcal": 650, "p": 35},
                "pre_workout": {"name": "Banana", "kcal": 150, "p": 2},
                "post_workout": {"name": "Protein Shake", "kcal": 150, "p": 10},
            }
        ]
        ghana_summary = build_summary(
            {
                "days": ghana_days,
                "goal_label": "Maintenance",
                "daily_protein_target": 112,
            },
            payload={
                "country": "Ghana",
                "cuisine": "Ghanaian",
                "goal": "g3",
                "allergies": "nut",
            },
        )
        self.assertIn("7-day Ghanaian maintenance plan", ghana_summary)
        self.assertIn("~2,100 kcal/day", ghana_summary)
        self.assertIn("112g protein/day", ghana_summary)
        self.assertIn("Nut allergy respected", ghana_summary)
        self.assertIn("Meals prioritize authentic Ghanaian options and your stated preferences", ghana_summary)
        self.assertNotIn("This tailored 7-day plan supports", ghana_summary)

        # 2. German muscle building plan
        german_days = [
            {
                "day": "Mon",
                "breakfast": {"name": "Quark with Berries", "kcal": 550, "p": 45},
                "lunch": {"name": "Chicken and Potatoes", "kcal": 850, "p": 55},
                "dinner": {"name": "Salmon and Vegetables", "kcal": 800, "p": 50},
                "pre_workout": {"name": "Oat Bar", "kcal": 200, "p": 5},
                "post_workout": {"name": "Whey Shake", "kcal": 200, "p": 25},
            }
        ]
        german_summary = build_summary(
            {
                "days": german_days,
                "goal_label": "Muscle Building",
                "daily_protein_target": 180,
            },
            payload={
                "country": "Germany",
                "cuisine": "German",
                "goal": "g2",
                "allergies": "",
            },
        )
        self.assertIn("7-day German muscle building plan", german_summary)
        self.assertIn("~2,600 kcal/day", german_summary)
        self.assertIn("180g protein/day", german_summary)
        self.assertIn("Meals prioritize authentic German options and your stated preferences", german_summary)

        # 3. Italian weight loss plan with lactose allergy
        italian_days = [
            {
                "day": "Mon",
                "breakfast": {"name": "Eggs and Fruit", "kcal": 380, "p": 30},
                "lunch": {"name": "Tuna Salad", "kcal": 550, "p": 45},
                "dinner": {"name": "Chicken Breast with Spinach", "kcal": 520, "p": 40},
                "pre_workout": {"name": "Apple", "kcal": 100, "p": 1},
                "post_workout": {"name": "Isolate Shake", "kcal": 150, "p": 24},
            }
        ]
        italian_summary = build_summary(
            {
                "days": italian_days,
                "goal_label": "Weight Loss",
                "daily_protein_target": 140,
            },
            payload={
                "country": "Italy",
                "cuisine": "Italian",
                "goal": "g1",
                "allergies": "lactose",
            },
        )
        self.assertIn("7-day Italian weight loss plan", italian_summary)
        self.assertIn("~1,700 kcal/day", italian_summary)
        self.assertIn("140g protein/day", italian_summary)
        self.assertIn("Lactose allergy respected", italian_summary)
        self.assertIn("Meals prioritize authentic Italian options and your stated preferences", italian_summary)

    def test_meal_entry_preparation_steps_sync_and_fallback(self) -> None:
        from app.models import NutritionMealEntry

        # 1. Existing instructions populates preparation_steps
        meal1 = NutritionMealEntry(
            name="Grilled Chicken",
            desc="Healthy chicken",
            kcal=400,
            p=40,
            c=10,
            f=8,
            ingredients=["200g chicken", "Olive oil"],
            instructions=["Season chicken", "Grill for 12 mins", "Rest and serve"],
        )
        self.assertEqual(meal1.preparation_steps, ["Season chicken", "Grill for 12 mins", "Rest and serve"])
        self.assertEqual(meal1.instructions, meal1.preparation_steps)

        # 2. Existing preparation_steps populates instructions
        meal2 = NutritionMealEntry(
            name="Oats Bowl",
            desc="Warm oats",
            kcal=350,
            p=25,
            c=45,
            f=6,
            ingredients=["Oats", "Whey"],
            preparation_steps=["Boil water", "Add oats", "Stir in whey"],
        )
        self.assertEqual(meal2.instructions, ["Boil water", "Add oats", "Stir in whey"])
        self.assertEqual(meal2.preparation_steps, meal2.instructions)

        # 3. Missing preparation steps generates structured 4-step meal-specific fallback
        meal3 = NutritionMealEntry(
            name="Jollof Rice with Chicken",
            desc="Spicy rice dish",
            kcal=650,
            p=45,
            c=70,
            f=15,
            ingredients=["Chicken breast", "Jasmine rice", "Tomatoes"],
        )
        self.assertEqual(len(meal3.preparation_steps), 4)
        self.assertEqual(meal3.instructions, meal3.preparation_steps)
        self.assertIn("Chicken breast, Jasmine rice, Tomatoes", meal3.preparation_steps[0])
        self.assertIn("Jollof Rice with Chicken", meal3.preparation_steps[1])
        self.assertIn("seasoning", meal3.preparation_steps[2].lower())
        self.assertIn("serve", meal3.preparation_steps[3].lower())
