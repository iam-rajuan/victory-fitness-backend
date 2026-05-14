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
nutrition_plan_jobs_collection = db["nutrition_plan_jobs"]
nutrition_progressive_plans_collection = db["nutrition_progressive_plans"]
nutrition_progressive_plan_jobs_collection = db["nutrition_progressive_plan_jobs"]
meal_analysis_entries_collection = db["meal_analysis_entries"]
strength_workout_plans_collection = db["strength_workout_plans"]
app_content_collection = db["app_content"]
coaching_applications_collection = db["coaching_applications"]
support_messages_collection = db["support_messages"]
longevity_os_profiles_collection = db["longevity_os_profiles"]
coach_victor_threads_collection = db["coach_victor_threads"]
coach_victor_archives_collection = db["coach_victor_archives"]
journal_entries_collection = db["journal_entries"]
workouts_collection = db["workouts"]
challenges_collection = db["challenges"]
challenge_memberships_collection = db["challenge_memberships"]
challenge_chat_messages_collection = db["challenge_chat_messages"]
challenge_message_reactions_collection = db["challenge_message_reactions"]
community_posts_collection = db["community_posts"]
community_comments_collection = db["community_comments"]
community_reactions_collection = db["community_reactions"]


async def ensure_indexes() -> None:
    await client.admin.command("ping")
    await users_collection.create_index("email", unique=True)
    await users_collection.create_index([("is_admin", 1), ("created_at", -1)])
    await nutrition_plans_collection.create_index([("user_id", 1), ("created_at", -1)])
    await nutrition_plans_collection.create_index([("user_id", 1), ("profile_hash", 1), ("created_at", -1)])
    await nutrition_plan_jobs_collection.create_index([("user_id", 1), ("created_at", -1)])
    await nutrition_plan_jobs_collection.create_index([("user_id", 1), ("profile_hash", 1), ("created_at", -1)])
    await nutrition_plan_jobs_collection.create_index([("status", 1), ("updated_at", -1)])
    await nutrition_progressive_plans_collection.create_index([("user_id", 1), ("created_at", -1)])
    await nutrition_progressive_plans_collection.create_index([("user_id", 1), ("profile_hash", 1), ("created_at", -1)])
    await nutrition_progressive_plan_jobs_collection.create_index([("user_id", 1), ("created_at", -1)])
    await nutrition_progressive_plan_jobs_collection.create_index([("user_id", 1), ("profile_hash", 1), ("created_at", -1)])
    await nutrition_progressive_plan_jobs_collection.create_index([("status", 1), ("updated_at", -1)])
    await meal_analysis_entries_collection.create_index([("user_id", 1), ("created_at", -1)])
    await strength_workout_plans_collection.create_index([("user_id", 1), ("created_at", -1)])
    await app_content_collection.create_index("key", unique=True)
    await coaching_applications_collection.create_index([("user_id", 1), ("created_at", -1)])
    await coaching_applications_collection.create_index([("status", 1), ("created_at", -1)])
    await support_messages_collection.create_index([("user_id", 1), ("created_at", -1)])
    await support_messages_collection.create_index([("status", 1), ("created_at", -1)])
    await longevity_os_profiles_collection.create_index("user_id", unique=True)
    await coach_victor_threads_collection.create_index([("user_id", 1), ("updated_at", -1)])
    await coach_victor_archives_collection.create_index([("thread_id", 1), ("created_at", 1)])
    await coach_victor_archives_collection.create_index([("user_id", 1), ("created_at", -1)])
    await journal_entries_collection.create_index([("user_id", 1), ("created_at", -1)])
    await workouts_collection.create_index([("created_at", -1)])
    await workouts_collection.create_index("vimeo_id", unique=True)
    await challenges_collection.create_index([("status", 1), ("created_at", -1)])
    await challenges_collection.create_index([("category", 1), ("created_at", -1)])
    await challenge_memberships_collection.create_index([("user_id", 1), ("status", 1), ("joined_at", -1)])
    await challenge_memberships_collection.create_index([("challenge_id", 1), ("status", 1)])
    await challenge_memberships_collection.create_index([("user_id", 1), ("challenge_id", 1)], unique=True)
    await challenge_chat_messages_collection.create_index([("challenge_id", 1), ("created_at", -1)])
    await challenge_message_reactions_collection.create_index([("message_id", 1), ("created_at", -1)])
    await challenge_message_reactions_collection.create_index([("message_id", 1), ("emoji", 1)])
    await challenge_message_reactions_collection.create_index([("message_id", 1), ("user_id", 1), ("emoji", 1)], unique=True)
    await community_posts_collection.create_index([("created_at", -1)])
    await community_posts_collection.create_index([("audience", 1), ("created_at", -1)])
    await community_comments_collection.create_index([("post_id", 1), ("created_at", 1)])
    await community_comments_collection.create_index([("author_id", 1), ("created_at", -1)])
    await community_reactions_collection.create_index([("post_id", 1), ("created_at", -1)])
    await community_reactions_collection.create_index([("post_id", 1), ("user_id", 1)], unique=True)
