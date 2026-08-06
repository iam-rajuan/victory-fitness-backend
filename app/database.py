from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings


MONGODB_NOT_CONFIGURED_MESSAGE = (
    "MongoDB Atlas is not configured. Set MONGODB_URI in victory-fitness-backend/.env "
    "to your MongoDB Atlas connection string."
)


class DatabaseNotConfiguredError(RuntimeError):
    pass


class _UnconfiguredCollection:
    def __getattr__(self, name: str):
        raise DatabaseNotConfiguredError(MONGODB_NOT_CONFIGURED_MESSAGE)

    def __bool__(self) -> bool:
        return False


def _require_database_configured() -> None:
    if not settings.mongodb_configured:
        raise DatabaseNotConfiguredError(MONGODB_NOT_CONFIGURED_MESSAGE)


if settings.mongodb_configured:
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
    admin_audit_logs_collection = db["admin_audit_logs"]
    # ------------------------------------------------------------------
    # Admin Intelligence & Marketing Analytics (Section 18)
    # ------------------------------------------------------------------
    analytics_events_collection = db["analytics_events"]
    workout_logs_collection = db["workout_logs"]
    payment_events_collection = db["payment_events"]
    completion_cards_collection = db["completion_cards"]
    accountability_pairs_collection = db["accountability_pairs"]
    points_log_collection = db["points_log"]
    invites_collection = db["invites"]
    wearable_connections_collection = user_provider_connections_collection
    health_metric_history_collection = health_samples_collection
    health_metrics_collection = health_metric_current_collection
else:
    client = None
    db = None
    users_collection = _UnconfiguredCollection()
    nutrition_plans_collection = _UnconfiguredCollection()
    nutrition_plan_jobs_collection = _UnconfiguredCollection()
    nutrition_progressive_plans_collection = _UnconfiguredCollection()
    nutrition_progressive_plan_jobs_collection = _UnconfiguredCollection()
    meal_analysis_entries_collection = _UnconfiguredCollection()
    strength_workout_plans_collection = _UnconfiguredCollection()
    app_content_collection = _UnconfiguredCollection()
    coaching_applications_collection = _UnconfiguredCollection()
    support_messages_collection = _UnconfiguredCollection()
    longevity_os_profiles_collection = _UnconfiguredCollection()
    coach_victor_threads_collection = _UnconfiguredCollection()
    coach_victor_archives_collection = _UnconfiguredCollection()
    journal_entries_collection = _UnconfiguredCollection()
    workouts_collection = _UnconfiguredCollection()
    challenges_collection = _UnconfiguredCollection()
    challenge_memberships_collection = _UnconfiguredCollection()
    challenge_chat_messages_collection = _UnconfiguredCollection()
    challenge_message_reactions_collection = _UnconfiguredCollection()
    community_posts_collection = _UnconfiguredCollection()
    community_comments_collection = _UnconfiguredCollection()
    community_reactions_collection = _UnconfiguredCollection()
    user_provider_connections_collection = _UnconfiguredCollection()
    provider_tokens_collection = _UnconfiguredCollection()
    health_metric_current_collection = _UnconfiguredCollection()
    health_samples_collection = _UnconfiguredCollection()
    sync_jobs_collection = _UnconfiguredCollection()
    sync_errors_collection = _UnconfiguredCollection()
    integration_audit_logs_collection = _UnconfiguredCollection()
    admin_audit_logs_collection = _UnconfiguredCollection()
    analytics_events_collection = _UnconfiguredCollection()
    workout_logs_collection = _UnconfiguredCollection()
    payment_events_collection = _UnconfiguredCollection()
    completion_cards_collection = _UnconfiguredCollection()
    accountability_pairs_collection = _UnconfiguredCollection()
    points_log_collection = _UnconfiguredCollection()
    invites_collection = _UnconfiguredCollection()
    wearable_connections_collection = user_provider_connections_collection
    health_metric_history_collection = health_samples_collection
    health_metrics_collection = health_metric_current_collection


def _parse_health_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _health_record_identity_key(record: dict[str, Any]) -> str:
    for field in ("dedupe_key", "current_key", "external_id", "_id", "id"):
        value = record.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def _extract_health_record_items(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = document.get("records")
    if isinstance(records, list):
        return [record for record in records if isinstance(record, dict)]
    return [document]


def _health_record_sort_value(record: dict[str, Any]) -> datetime:
    for field in ("synced_at", "end_time", "start_time", "created_at", "updated_at"):
        value = _parse_health_datetime(record.get(field))
        if value is not None:
            return value
    return datetime.min.replace(tzinfo=timezone.utc)


def _merge_health_record_items(existing_items: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in [*existing_items, *new_items]:
        key = _health_record_identity_key(record) or f"record:{len(merged)}"
        current = merged.get(key)
        if current is None or _health_record_sort_value(record) >= _health_record_sort_value(current):
            merged[key] = record
    return sorted(merged.values(), key=_health_record_sort_value, reverse=True)


async def _collapse_health_snapshot_collection(collection, *, preserve_existing: bool = True) -> int:
    documents = await collection.find({}).to_list(length=100000)
    if not documents:
        return 0

    records_by_user: dict[str, list[dict[str, Any]]] = {}
    metadata_by_user: dict[str, dict[str, Any]] = {}
    for document in documents:
        user_id = str(document.get("user_id") or "").strip()
        if not user_id:
            continue
        metadata_by_user.setdefault(user_id, document)
        records_by_user.setdefault(user_id, []).extend(_extract_health_record_items(document))

    if not records_by_user:
        return 0

    processed = 0
    for user_id, records in records_by_user.items():
        existing = metadata_by_user.get(user_id) if preserve_existing else {}
        merged_records = _merge_health_record_items([], records)
        snapshot = {
            "user_id": user_id,
            "records": merged_records,
            "record_count": len(merged_records),
            "latest_synced_at": merged_records[0].get("synced_at") if merged_records else None,
            "latest_end_time": merged_records[0].get("end_time") if merged_records else None,
            "created_at": existing.get("created_at") if existing and existing.get("created_at") else (merged_records[-1].get("created_at") if merged_records else None),
            "updated_at": datetime.now(timezone.utc),
        }
        if merged_records:
            snapshot["provider"] = merged_records[0].get("provider") or ""
            snapshot["metric_type"] = merged_records[0].get("metric_type") or ""
            snapshot["source_device"] = merged_records[0].get("source_device") or ""
        if existing and existing.get("_id") is not None:
            snapshot["_id"] = existing.get("_id")

        await collection.delete_many({"user_id": user_id})
        await collection.insert_one(snapshot)
        processed += 1

    return processed


async def ensure_indexes() -> None:
    _require_database_configured()
    await users_collection.create_index("email", unique=True, sparse=True)
    await users_collection.create_index([("created_at", -1)])
    await users_collection.create_index([("subscription_tier", 1), ("created_at", -1)])
    await users_collection.create_index([("marketing_consent", 1), ("subscription_started_at", -1)])
    await client.admin.command("ping")
    await _collapse_health_snapshot_collection(health_metric_current_collection)
    await _collapse_health_snapshot_collection(health_samples_collection)
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
    await workouts_collection.update_many({"vimeo_id": ""}, {"$unset": {"vimeo_id": ""}})
    existing_workout_indexes = await workouts_collection.index_information()
    if "vimeo_id_1" in existing_workout_indexes:
        await workouts_collection.drop_index("vimeo_id_1")
    await workouts_collection.create_index(
        "vimeo_id",
        unique=True,
        sparse=True,
    )
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
    await community_posts_collection.create_index([("flagged", 1), ("updated_at", -1)])
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
    await health_metric_current_collection.create_index("user_id", unique=True)
    await health_metric_current_collection.create_index([("updated_at", -1)])
    await health_samples_collection.create_index("user_id", unique=True)
    await health_samples_collection.create_index([("updated_at", -1)])
    await sync_jobs_collection.create_index([("user_id", 1), ("provider", 1), ("created_at", -1)])
    await sync_jobs_collection.create_index([("status", 1), ("updated_at", -1)])
    await sync_errors_collection.create_index([("user_id", 1), ("provider", 1), ("created_at", -1)])
    await sync_errors_collection.create_index([("job_id", 1), ("created_at", -1)])
    await integration_audit_logs_collection.create_index([("user_id", 1), ("provider", 1), ("created_at", -1)])
    await admin_audit_logs_collection.create_index([("created_at", -1)])
    await admin_audit_logs_collection.create_index([("resource", 1), ("resource_id", 1), ("created_at", -1)])
    # ------------------------------------------------------------------
    # Admin Intelligence & Marketing Analytics (Section 18) indexes
    # ------------------------------------------------------------------
    await analytics_events_collection.create_index([("event_type", 1), ("created_at", -1)])
    await analytics_events_collection.create_index([("user_id", 1), ("created_at", -1)])
    await analytics_events_collection.create_index([("market", 1), ("created_at", -1)])
    await workout_logs_collection.create_index([("user_id", 1), ("started_at", -1)])
    await workout_logs_collection.create_index([("workout_id", 1), ("started_at", -1)])
    await workout_logs_collection.create_index([("status", 1), ("started_at", -1)])
    await payment_events_collection.create_index([("user_id", 1), ("created_at", -1)])
    await payment_events_collection.create_index([("status", 1), ("type", 1), ("created_at", -1)])
    await payment_events_collection.create_index([("market", 1), ("created_at", -1)])
    await completion_cards_collection.create_index([("shared_to_whatsapp", 1), ("created_at", -1)])
    await completion_cards_collection.create_index([("user_id", 1), ("created_at", -1)])
    await accountability_pairs_collection.create_index([("status", 1), ("created_at", -1)])
    await accountability_pairs_collection.create_index([("user_ids", 1), ("created_at", -1)])
    await points_log_collection.create_index([("user_id", 1), ("created_at", -1)])
    await points_log_collection.create_index([("created_at", -1)])
    await invites_collection.create_index([("created_at", -1)])
    await invites_collection.create_index([("copy_variant", 1), ("created_at", -1)])
    await invites_collection.create_index([("user_id", 1), ("created_at", -1)])


async def close_database_connection() -> None:
    if client is not None:
        client.close()
