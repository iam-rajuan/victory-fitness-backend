from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings


client = AsyncIOMotorClient(settings.mongodb_uri)
db = client[settings.mongodb_db]
users_collection = db["users"]
nutrition_plans_collection = db["nutrition_plans"]
coach_victor_threads_collection = db["coach_victor_threads"]


async def ensure_indexes() -> None:
    await users_collection.create_index("email", unique=True)
    await nutrition_plans_collection.create_index([("user_id", 1), ("created_at", -1)])
    await coach_victor_threads_collection.create_index([("user_id", 1), ("updated_at", -1)])
