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


client = AsyncIOMotorClient(
    settings.mongodb_uri,
    serverSelectionTimeoutMS=10000,
    maxPoolSize=settings.mongodb_max_pool_size,
    minPoolSize=settings.mongodb_min_pool_size,
)
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
user_provider_connections_collection = db["user_provider_connections"]
provider_tokens_collection = db["provider_tokens"]
health_metric_current_collection = db["health_metric_current"]
health_samples_collection = db["health_samples"]
sync_jobs_collection = db["sync_jobs"]
sync_errors_collection = db["sync_errors"]
integration_audit_logs_collection = db["integration_audit_logs"]
wearable_connections_collection = user_provider_connections_collection
health_metric_history_collection = health_samples_collection
health_metrics_collection = health_metric_current_collection


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
    await workouts_collection.create_index([("visibility", 1), ("created_at", -1)])
    await workouts_collection.create_index([("visibility", 1), ("tag", 1), ("created_at", -1)])
    await workouts_collection.create_index("vimeo_id", unique=True)
    await challenges_collection.create_index([("status", 1), ("created_at", -1)])
    await challenges_collection.create_index([("category", 1), ("created_at", -1)])
    await challenge_memberships_collection.create_index([("user_id", 1), ("joined_at", -1)])
    await challenge_memberships_collection.create_index([("user_id", 1), ("status", 1), ("joined_at", -1)])
    await challenge_memberships_collection.create_index([("challenge_id", 1), ("status", 1)])
    await challenge_memberships_collection.create_index([("user_id", 1), ("challenge_id", 1)], unique=True)
    await challenge_chat_messages_collection.create_index([("challenge_id", 1), ("created_at", -1)])
    await challenge_message_reactions_collection.create_index([("message_id", 1), ("created_at", -1)])
    await challenge_message_reactions_collection.create_index([("message_id", 1), ("emoji", 1)])
    await challenge_message_reactions_collection.create_index([("message_id", 1), ("user_id", 1), ("emoji", 1)], unique=True)
    await community_posts_collection.create_index([("created_at", -1)])
    await community_posts_collection.create_index([("author_id", 1), ("created_at", -1)])
    await community_posts_collection.create_index([("audience", 1), ("created_at", -1)])
    await community_comments_collection.create_index([("post_id", 1), ("created_at", 1)])
    await community_comments_collection.create_index([("author_id", 1), ("created_at", -1)])
    await community_reactions_collection.create_index([("post_id", 1), ("created_at", -1)])
    await community_reactions_collection.create_index([("post_id", 1), ("user_id", 1)], unique=True)
    await user_provider_connections_collection.create_index([("user_id", 1), ("provider", 1)], unique=True)
    await user_provider_connections_collection.create_index([("provider", 1), ("status", 1), ("updated_at", -1)])
    await user_provider_connections_collection.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
    await user_provider_connections_collection.create_index([("user_id", 1), ("platform", 1), ("status", 1)])
    await user_provider_connections_collection.create_index([("user_id", 1), ("source_device", 1)])
    await user_provider_connections_collection.create_index([("provider", 1), ("provider_user_id", 1)])
    await user_provider_connections_collection.create_index([("provider", 1), ("oauth_state", 1)])
    await provider_tokens_collection.create_index([("user_id", 1), ("provider", 1)], unique=True)
    await health_metric_current_collection.create_index([("user_id", 1), ("provider", 1), ("metric_type", 1), ("day", -1)])
    await health_metric_current_collection.create_index([("user_id", 1), ("provider", 1), ("source_device", 1), ("metric_type", 1), ("day", -1)])
    await health_metric_current_collection.create_index([("user_id", 1), ("metric_type", 1), ("end_time", -1)])
    await health_metric_current_collection.create_index([("user_id", 1), ("updated_at", -1)])
    await health_metric_current_collection.create_index("current_key", unique=True)
    await health_samples_collection.create_index([("user_id", 1), ("start_time", -1)])
    await health_samples_collection.create_index([("user_id", 1), ("provider", 1), ("metric_type", 1), ("start_time", -1)])
    await health_samples_collection.create_index([("user_id", 1), ("provider", 1), ("metric_type", 1), ("end_time", -1)])
    await health_samples_collection.create_index([("user_id", 1), ("metric_type", 1), ("end_time", -1)])
    await health_samples_collection.create_index("dedupe_key", unique=True)
    await health_samples_collection.create_index(
        [("user_id", 1), ("provider", 1), ("external_id", 1), ("type", 1), ("started_at", 1)],
        unique=True,
        sparse=True,
    )
    await sync_jobs_collection.create_index([("user_id", 1), ("provider", 1), ("created_at", -1)])
    await sync_jobs_collection.create_index([("status", 1), ("updated_at", -1)])
    await sync_errors_collection.create_index([("user_id", 1), ("provider", 1), ("created_at", -1)])
    await sync_errors_collection.create_index([("job_id", 1), ("created_at", -1)])
    await integration_audit_logs_collection.create_index([("user_id", 1), ("provider", 1), ("created_at", -1)])


async def close_database_connection() -> None:
    client.close()
