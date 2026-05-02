from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings


client = AsyncIOMotorClient(settings.mongodb_uri)
db = client[settings.mongodb_db]
users_collection = db["users"]


async def ensure_indexes() -> None:
    await users_collection.create_index("email", unique=True)
