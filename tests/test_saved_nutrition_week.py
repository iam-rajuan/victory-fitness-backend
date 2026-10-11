import unittest
from unittest.mock import AsyncMock, patch

from app.api.routers import ai_nutrition as routes


class SavedNutritionWeekTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_read_does_not_generate_or_persist_a_starter(self):
        collection = AsyncMock()
        collection.find_one.return_value = None
        with patch.object(routes, 'nutrition_plans_collection', collection):
            result = await routes.nutrition_latest_plan(user={'_id': 'user-a'})
        self.assertIsNone(result)
        collection.insert_one.assert_not_awaited()

    async def test_clear_is_user_scoped_and_preserves_quota_records(self):
        collection = AsyncMock()
        with patch.object(routes, 'nutrition_plans_collection', collection):
            result = await routes.clear_saved_nutrition_plan(user={'_id': 'user-a'})
        self.assertEqual(result.status_code, 204)
        query, update = collection.update_many.call_args.args
        self.assertEqual(query['user_id'], 'user-a')
        self.assertTrue(update['$set']['cleared'])
        collection.delete_many.assert_not_awaited()

    def test_latest_filter_excludes_cleared_and_starter_plans(self):
        query = routes._standard_nutrition_filter('user-a')
        self.assertEqual(query['cleared'], {'$ne': True})
        self.assertEqual(query['profile_hash'], {'$ne': 'starter_baseline'})
        self.assertEqual(routes._standard_nutrition_filter('user-a', 'profile')['profile_hash'], 'profile')

    async def test_completion_without_plan_returns_not_found(self):
        collection = AsyncMock()
        collection.find_one.return_value = None
        payload = routes.NutritionMealCompletionUpdateRequest(day='Mon', meal_key='breakfast', completed=True)
        with patch.object(routes, 'nutrition_plans_collection', collection):
            with self.assertRaises(routes.HTTPException) as caught:
                await routes.nutrition_latest_plan_completion(payload, user={'_id': 'user-a'})
        self.assertEqual(caught.exception.status_code, 404)
        collection.insert_one.assert_not_awaited()
