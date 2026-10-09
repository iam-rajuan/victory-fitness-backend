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
        matching = [
            record
            for record in self.records
            if record.get("user_id") == user_id and (profile_hash is None or record.get("profile_hash") == profile_hash)
        ]
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

    def test_generate_plan_rejects_missing_cuisine_and_fewer_than_three_favorite_meals(self) -> None:
        payload = {
            "goal": "g2",
            "cuisine": "balanced",
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

        response = self.client.post("/ai/nutrition/plan", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertIn("Choose at least one cuisine", response.text)


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
