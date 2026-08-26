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
        self.assertEqual(fake_plans.records[0]["plan"]["profile"]["diet"], "d2")
        self.assertEqual(
            fake_users.updated_payloads[-1]["update"]["$set"]["nutrition_onboarding_profile"]["activity_level"],
            "a3",
        )


class NutritionPlanFallbackTests(unittest.TestCase):
    def test_generate_nutrition_plan_returns_fallback_plan_when_model_json_is_unusable(self) -> None:
        payload = {
            "goal": "g2",
            "cuisine": "German",
            "favorite_meal": "Dinner",
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
