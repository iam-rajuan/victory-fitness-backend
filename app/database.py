from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings


MONGODB_NOT_CONFIGURED_MESSAGE = (
    "MongoDB Atlas is not configured. Set MONGODB_URI in victory-fitness-backend/.env "
    "to your MongoDB Atlas connection string."
)


class DatabaseNotConfiguredError(RuntimeError):
    pass


if not settings.mongodb_configured:
    raise DatabaseNotConfiguredError(MONGODB_NOT_CONFIGURED_MESSAGE)


client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
db = client[settings.mongodb_db]
users_collection = db["users"]
nutrition_plans_collection = db["nutrition_plans"]
coach_victor_threads_collection = db["coach_victor_threads"]
coach_victor_archives_collection = db["coach_victor_archives"]


async def ensure_indexes() -> None:
    await client.admin.command("ping")
    await users_collection.create_index("email", unique=True)
    await nutrition_plans_collection.create_index([("user_id", 1), ("created_at", -1)])
    await coach_victor_threads_collection.create_index([("user_id", 1), ("updated_at", -1)])
    await coach_victor_archives_collection.create_index([("thread_id", 1), ("created_at", 1)])
    await coach_victor_archives_collection.create_index([("user_id", 1), ("created_at", -1)])
