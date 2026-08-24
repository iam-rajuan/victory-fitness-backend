from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..coach_archive import load_thread_snapshot
from ..core.legacy import (
    PHASE_ONE_BETA_SUBSCRIPTION_SOURCE,
    _build_subscription_summary,
    _phase_one_beta_max_users,
    _trial_summary,
)
from ..database import (
    challenge_memberships_collection,
    coach_victor_archives_collection,
    coach_victor_threads_collection,
    community_comments_collection,
    community_posts_collection,
    community_reactions_collection,
    meal_analysis_entries_collection,
    nutrition_plan_jobs_collection,
    support_messages_collection,
    users_collection,
    workout_logs_collection,
)
from ..models import (
    PhaseOneBetaCampaignHealthResponse,
    PhaseOneBetaCheckpointItem,
    PhaseOneBetaCountryItem,
    PhaseOneBetaCrossFeatureResponse,
    PhaseOneBetaFeatureAdoptionMetric,
    PhaseOneBetaFeatureAdoptionResponse,
    PhaseOneBetaParticipationResponse,
    PhaseOneBetaSummaryResponse,
    PhaseOneBetaSupportReferenceResponse,
    PhaseOneBetaUserActivity,
    PhaseOneBetaUserItem,
)

CHECKPOINT_DAYS = tuple(range(1, 22))
ENDING_SOON_DAYS = 2


def _as_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _normalize_user_id(value: Any) -> str:
    return str(value or "").strip()


def _normalize_country_label(value: Any) -> str:
    return str(value or "").strip() or "Unknown"


def _in_window(timestamp: datetime | None, start_at: datetime | None, end_at: datetime | None) -> bool:
    return bool(timestamp and start_at and end_at and start_at <= timestamp <= end_at)


def _window_end_for_user(user: dict, now: datetime) -> datetime | None:
    summary = _trial_summary(user, now)
    end_at = _as_utc_datetime(summary.get("end_at"))
    if end_at is None:
        return None
    return min(now, end_at)


def _checkpoint_cutoff(start_at: datetime, window_end: datetime, day: int) -> datetime | None:
    checkpoint = start_at + timedelta(days=day)
    if window_end < checkpoint:
        return None
    return min(window_end, checkpoint)


@dataclass
class _UserActivityAccumulator:
    ai_conversation_count: int = 0
    ai_message_count: int = 0
    nutrition_plan_count: int = 0
    nutrition_log_count: int = 0
    workout_started_count: int = 0
    workout_completed_count: int = 0
    challenge_joined_count: int = 0
    challenge_completed_count: int = 0
    community_post_count: int = 0
    community_comment_count: int = 0
    community_reaction_count: int = 0
    ai_timestamps: list[datetime] = field(default_factory=list)
    nutrition_timestamps: list[datetime] = field(default_factory=list)
    workout_timestamps: list[datetime] = field(default_factory=list)
    challenge_timestamps: list[datetime] = field(default_factory=list)
    community_timestamps: list[datetime] = field(default_factory=list)
    last_active_at: datetime | None = None

    def _touch(self, timestamp: datetime | None) -> None:
        if timestamp is None:
            return
        if self.last_active_at is None or timestamp > self.last_active_at:
            self.last_active_at = timestamp

    def add_ai_conversation(self, timestamp: datetime) -> None:
        self.ai_conversation_count += 1
        self.ai_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_ai_message(self, timestamp: datetime) -> None:
        self.ai_message_count += 1
        self.ai_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_nutrition_plan(self, timestamp: datetime) -> None:
        self.nutrition_plan_count += 1
        self.nutrition_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_nutrition_log(self, timestamp: datetime) -> None:
        self.nutrition_log_count += 1
        self.nutrition_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_workout_started(self, timestamp: datetime) -> None:
        self.workout_started_count += 1
        self.workout_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_workout_completed(self, timestamp: datetime) -> None:
        self.workout_completed_count += 1
        self.workout_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_challenge_joined(self, timestamp: datetime) -> None:
        self.challenge_joined_count += 1
        self.challenge_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_challenge_completed(self, timestamp: datetime) -> None:
        self.challenge_completed_count += 1
        self.challenge_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_community_post(self, timestamp: datetime) -> None:
        self.community_post_count += 1
        self.community_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_community_comment(self, timestamp: datetime) -> None:
        self.community_comment_count += 1
        self.community_timestamps.append(timestamp)
        self._touch(timestamp)

    def add_community_reaction(self, timestamp: datetime) -> None:
        self.community_reaction_count += 1
        self.community_timestamps.append(timestamp)
        self._touch(timestamp)

    def ai_used(self) -> bool:
        return self.ai_message_count > 0 or self.ai_conversation_count > 0

    def nutrition_used(self) -> bool:
        return self.nutrition_plan_count > 0 or self.nutrition_log_count > 0

    def workout_used(self) -> bool:
        return self.workout_started_count > 0 or self.workout_completed_count > 0

    def challenge_used(self) -> bool:
        return self.challenge_joined_count > 0 or self.challenge_completed_count > 0

    def community_used(self) -> bool:
        return self.community_post_count > 0 or self.community_comment_count > 0 or self.community_reaction_count > 0

    def any_used(self) -> bool:
        return self.ai_used() or self.nutrition_used() or self.workout_used() or self.challenge_used() or self.community_used()


async def _load_records(collection, query: dict, *, projection: dict | None = None) -> list[dict]:
    if collection is None:
        return []
    try:
        return await collection.find(query, projection).to_list(length=None)
    except Exception:
        return []


async def _load_beta_thread_messages(user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    threads = await _load_records(
        coach_victor_threads_collection,
        {"user_id": {"$in": user_ids}},
        projection={
            "_id": 1,
            "user_id": 1,
            "recent_messages": 1,
            "messages": 1,
            "updated_at": 1,
            "created_at": 1,
            "latest_snapshot_s3_key": 1,
            "latest_snapshot_s3_bucket": 1,
        },
    )
    if not threads:
        return {}

    thread_ids = [str(thread.get("_id")) for thread in threads if thread.get("_id") is not None]
    archive_records = await _load_records(
        coach_victor_archives_collection,
        {"thread_id": {"$in": thread_ids}},
        projection={"thread_id": 1, "payload": 1, "storage_backend": 1, "s3_bucket": 1, "s3_key": 1},
    )
    archives_by_thread: dict[str, list[dict]] = defaultdict(list)
    for record in archive_records:
        archives_by_thread[str(record.get("thread_id") or "")].append(record)

    messages_by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for thread in threads:
        stored_messages = thread.get("messages")
        if not isinstance(stored_messages, list):
            stored_messages = thread.get("recent_messages")
        stored_messages = stored_messages if isinstance(stored_messages, list) else []
        messages: list[dict[str, Any]] = []
        snapshot_key = str(thread.get("latest_snapshot_s3_key") or "")
        snapshot_bucket = str(thread.get("latest_snapshot_s3_bucket") or "")
        if snapshot_key and snapshot_bucket:
            try:
                messages = load_thread_snapshot(snapshot_bucket, snapshot_key)
            except Exception:
                messages = []
        else:
            for record in sorted(archives_by_thread.get(str(thread.get("_id") or ""), []), key=lambda item: _as_utc_datetime(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)):
                if record.get("storage_backend") == "mongodb":
                    payload = record.get("payload")
                    if isinstance(payload, list):
                        messages.extend(payload)
            messages.extend(stored_messages)
        if messages:
            messages_by_user[str(thread.get("user_id") or "")].extend(messages)
    return messages_by_user


def _checkpoint_bool(timestamps: list[datetime], cutoff: datetime | None) -> bool:
    return bool(cutoff and any(timestamp <= cutoff for timestamp in timestamps))


async def build_phase_one_beta_analytics(limit: int = 300) -> PhaseOneBetaSummaryResponse:
    normalized_limit = min(max(int(limit or 300), 1), 500)
    now = datetime.now(timezone.utc)
    beta_users = await _load_records(
        users_collection,
        {
            "is_admin": {"$ne": True},
            "subscription_purchase_source": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE,
        },
    )

    if not beta_users:
        return PhaseOneBetaSummaryResponse(
            limit=_phase_one_beta_max_users(),
            remainingSlots=_phase_one_beta_max_users(),
        )

    beta_users.sort(key=lambda user: _as_utc_datetime(user.get("trial_start_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    beta_users = beta_users[:normalized_limit]
    user_ids = [_normalize_user_id(user.get("_id")) for user in beta_users]
    user_windows: dict[str, tuple[datetime | None, datetime | None]] = {}
    earliest_start: datetime | None = None
    latest_end: datetime | None = None
    for user in beta_users:
        user_id = _normalize_user_id(user.get("_id"))
        summary = _trial_summary(user, now)
        start_at = _as_utc_datetime(summary.get("start_at"))
        end_at = _window_end_for_user(user, now)
        user_windows[user_id] = (start_at, end_at)
        if start_at and (earliest_start is None or start_at < earliest_start):
            earliest_start = start_at
        if end_at and (latest_end is None or end_at > latest_end):
            latest_end = end_at

    if earliest_start is None or latest_end is None:
        latest_end = now
        earliest_start = now

    activity_by_user: dict[str, _UserActivityAccumulator] = {user_id: _UserActivityAccumulator() for user_id in user_ids}

    thread_messages_by_user = await _load_beta_thread_messages(user_ids)
    for user_id, messages in thread_messages_by_user.items():
        start_at, end_at = user_windows.get(user_id, (None, None))
        conversation_seen = False
        first_conversation_timestamp: datetime | None = None
        for message in messages:
            created_at = _as_utc_datetime(message.get("created_at"))
            if not _in_window(created_at, start_at, end_at):
                continue
            if str(message.get("role") or "").lower() != "user":
                continue
            activity_by_user[user_id].add_ai_message(created_at)
            if not conversation_seen:
                first_conversation_timestamp = created_at
                conversation_seen = True
        if conversation_seen and first_conversation_timestamp is not None:
            activity_by_user[user_id].add_ai_conversation(first_conversation_timestamp)

    nutrition_plan_jobs = await _load_records(
        nutrition_plan_jobs_collection,
        {
            "user_id": {"$in": user_ids},
            "status": "completed",
            "created_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"user_id": 1, "created_at": 1},
    )
    for record in nutrition_plan_jobs:
        user_id = _normalize_user_id(record.get("user_id"))
        created_at = _as_utc_datetime(record.get("created_at"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        if _in_window(created_at, start_at, end_at):
            activity_by_user[user_id].add_nutrition_plan(created_at)

    meal_entries = await _load_records(
        meal_analysis_entries_collection,
        {
            "user_id": {"$in": user_ids},
            "created_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"user_id": 1, "created_at": 1},
    )
    for record in meal_entries:
        user_id = _normalize_user_id(record.get("user_id"))
        created_at = _as_utc_datetime(record.get("created_at"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        if _in_window(created_at, start_at, end_at):
            activity_by_user[user_id].add_nutrition_log(created_at)

    workout_logs = await _load_records(
        workout_logs_collection,
        {
            "user_id": {"$in": user_ids},
            "started_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"user_id": 1, "started_at": 1, "completed_at": 1, "status": 1},
    )
    for record in workout_logs:
        user_id = _normalize_user_id(record.get("user_id"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        started_at = _as_utc_datetime(record.get("started_at"))
        completed_at = _as_utc_datetime(record.get("completed_at"))
        if _in_window(started_at, start_at, end_at):
            activity_by_user[user_id].add_workout_started(started_at)
        if _in_window(completed_at, start_at, end_at) and str(record.get("status") or "").lower() == "completed":
            activity_by_user[user_id].add_workout_completed(completed_at)

    challenge_memberships = await _load_records(
        challenge_memberships_collection,
        {
            "user_id": {"$in": user_ids},
        },
        projection={"user_id": 1, "joined_at": 1, "completed_at": 1, "status": 1},
    )
    for record in challenge_memberships:
        user_id = _normalize_user_id(record.get("user_id"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        joined_at = _as_utc_datetime(record.get("joined_at"))
        completed_at = _as_utc_datetime(record.get("completed_at"))
        if _in_window(joined_at, start_at, end_at):
            activity_by_user[user_id].add_challenge_joined(joined_at)
        if _in_window(completed_at, start_at, end_at) and str(record.get("status") or "").upper() == "COMPLETED":
            activity_by_user[user_id].add_challenge_completed(completed_at)

    community_posts = await _load_records(
        community_posts_collection,
        {
            "author_id": {"$in": user_ids},
            "created_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"author_id": 1, "created_at": 1},
    )
    for record in community_posts:
        user_id = _normalize_user_id(record.get("author_id"))
        created_at = _as_utc_datetime(record.get("created_at"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        if _in_window(created_at, start_at, end_at):
            activity_by_user[user_id].add_community_post(created_at)

    community_comments = await _load_records(
        community_comments_collection,
        {
            "author_id": {"$in": user_ids},
            "created_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"author_id": 1, "created_at": 1},
    )
    for record in community_comments:
        user_id = _normalize_user_id(record.get("author_id"))
        created_at = _as_utc_datetime(record.get("created_at"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        if _in_window(created_at, start_at, end_at):
            activity_by_user[user_id].add_community_comment(created_at)

    community_reactions = await _load_records(
        community_reactions_collection,
        {
            "user_id": {"$in": user_ids},
            "created_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"user_id": 1, "created_at": 1},
    )
    for record in community_reactions:
        user_id = _normalize_user_id(record.get("user_id"))
        created_at = _as_utc_datetime(record.get("created_at"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        if _in_window(created_at, start_at, end_at):
            activity_by_user[user_id].add_community_reaction(created_at)

    support_messages = await _load_records(
        support_messages_collection,
        {
            "user_id": {"$in": user_ids},
            "created_at": {"$gte": earliest_start, "$lte": latest_end},
        },
        projection={"user_id": 1, "created_at": 1},
    )
    support_counts: dict[str, int] = defaultdict(int)
    for message in support_messages:
        user_id = _normalize_user_id(message.get("user_id"))
        created_at = _as_utc_datetime(message.get("created_at"))
        start_at, end_at = user_windows.get(user_id, (None, None))
        if _in_window(created_at, start_at, end_at):
            support_counts[user_id] += 1

    active = expired = gold = 0
    days_remaining_total = 0
    countries: dict[tuple[str | None, str], dict[str, int]] = {}
    users: list[PhaseOneBetaUserItem] = []
    feature_counts = {
        "ai": 0,
        "nutrition": 0,
        "workout": 0,
        "challenge": 0,
        "community": 0,
    }
    totals = {
        "ai_conversations": 0,
        "ai_messages": 0,
        "nutrition_plans": 0,
        "nutrition_logs": 0,
        "workouts_started": 0,
        "workouts_completed": 0,
        "challenges_joined": 0,
        "challenges_completed": 0,
        "community_actions": 0,
    }
    cross_feature = PhaseOneBetaCrossFeatureResponse()
    checkpoints = {day: PhaseOneBetaCheckpointItem(day=day) for day in CHECKPOINT_DAYS}
    zero_activity_users = ending_soon_users = users_without_ai = users_without_nutrition = 0

    for user in beta_users:
        user_id = _normalize_user_id(user.get("_id"))
        summary = _trial_summary(user, now)
        subscription = _build_subscription_summary(user)
        country_label = _normalize_country_label(user.get("country"))
        country_code = str(user.get("country_code") or "").strip().upper() or None
        start_at = _as_utc_datetime(summary.get("start_at"))
        end_at = _as_utc_datetime(summary.get("end_at"))
        accumulator = activity_by_user[user_id]
        status = str(subscription["status"] or "NONE").upper()
        if status == "ACTIVE":
            active += 1
            days_remaining_total += max(int(summary.get("days_remaining") or 0), 0)
            if int(summary.get("days_remaining") or 0) <= ENDING_SOON_DAYS:
                ending_soon_users += 1
        else:
            expired += 1
        if subscription["tier"] == "GOLD":
            gold += 1

        used_ai = accumulator.ai_used()
        used_nutrition = accumulator.nutrition_used()
        used_workout = accumulator.workout_used()
        used_challenge = accumulator.challenge_used()
        used_community = accumulator.community_used()
        used_any = accumulator.any_used()
        if not used_any:
            zero_activity_users += 1
        if not used_ai:
            users_without_ai += 1
        if not used_nutrition:
            users_without_nutrition += 1

        feature_total = sum([used_ai, used_nutrition, used_workout, used_challenge, used_community])
        if used_ai:
            feature_counts["ai"] += 1
        if used_nutrition:
            feature_counts["nutrition"] += 1
        if used_workout:
            feature_counts["workout"] += 1
        if used_challenge:
            feature_counts["challenge"] += 1
        if used_community:
            feature_counts["community"] += 1
        if used_ai and not any([used_nutrition, used_workout, used_challenge, used_community]):
            cross_feature.aiOnly += 1
        if used_nutrition and not any([used_ai, used_workout, used_challenge, used_community]):
            cross_feature.nutritionOnly += 1
        if used_workout and not any([used_ai, used_nutrition, used_challenge, used_community]):
            cross_feature.workoutOnly += 1
        if used_ai and used_nutrition:
            cross_feature.aiAndNutrition += 1
        if used_ai and used_workout:
            cross_feature.aiAndWorkout += 1
        if used_nutrition and used_workout:
            cross_feature.nutritionAndWorkout += 1
        if feature_total >= 3:
            cross_feature.usedThreePlusFeatures += 1
        if feature_total == 0:
            cross_feature.usedNoTrackedFeature += 1

        totals["ai_conversations"] += accumulator.ai_conversation_count
        totals["ai_messages"] += accumulator.ai_message_count
        totals["nutrition_plans"] += accumulator.nutrition_plan_count
        totals["nutrition_logs"] += accumulator.nutrition_log_count
        totals["workouts_started"] += accumulator.workout_started_count
        totals["workouts_completed"] += accumulator.workout_completed_count
        totals["challenges_joined"] += accumulator.challenge_joined_count
        totals["challenges_completed"] += accumulator.challenge_completed_count
        totals["community_actions"] += accumulator.community_post_count + accumulator.community_comment_count + accumulator.community_reaction_count

        country_bucket = countries.setdefault((country_code, country_label), {"count": 0, "active": 0, "ai": 0, "nutrition": 0, "workout": 0})
        country_bucket["count"] += 1
        if status == "ACTIVE":
            country_bucket["active"] += 1
        if used_ai:
            country_bucket["ai"] += 1
        if used_nutrition:
            country_bucket["nutrition"] += 1
        if used_workout:
            country_bucket["workout"] += 1

        if start_at and end_at:
            window_end = min(now, end_at)
            for day, checkpoint in checkpoints.items():
                cutoff = _checkpoint_cutoff(start_at, window_end, day)
                if cutoff is None:
                    continue
                checkpoint.eligibleUsers += 1
                checkpoint.activeUsers += 1 if accumulator.any_used() and accumulator.last_active_at and accumulator.last_active_at <= cutoff else 0
                checkpoint.aiUsers += 1 if _checkpoint_bool(accumulator.ai_timestamps, cutoff) else 0
                checkpoint.nutritionUsers += 1 if _checkpoint_bool(accumulator.nutrition_timestamps, cutoff) else 0
                checkpoint.workoutUsers += 1 if _checkpoint_bool(accumulator.workout_timestamps, cutoff) else 0
                checkpoint.challengeUsers += 1 if _checkpoint_bool(accumulator.challenge_timestamps, cutoff) else 0
                checkpoint.communityUsers += 1 if _checkpoint_bool(accumulator.community_timestamps, cutoff) else 0
                checkpoint.anyFeatureUsers += 1 if any(
                    _checkpoint_bool(timestamps, cutoff)
                    for timestamps in (
                        accumulator.ai_timestamps,
                        accumulator.nutrition_timestamps,
                        accumulator.workout_timestamps,
                        accumulator.challenge_timestamps,
                        accumulator.community_timestamps,
                    )
                ) else 0

        users.append(
            PhaseOneBetaUserItem(
                id=user_id,
                fullName=str(user.get("name") or "Unknown"),
                email=str(user.get("email") or ""),
                country=country_label if country_label != "Unknown" else "",
                countryCode=country_code,
                plan=subscription["tier"],
                status=status,
                trialType=str(summary.get("trial_type") or PHASE_ONE_BETA_SUBSCRIPTION_SOURCE),
                isBetaTester=bool(summary.get("is_beta_tester")),
                trialStartedAt=start_at,
                trialExpiresAt=end_at,
                daysRemaining=int(summary.get("days_remaining") or 0),
                price=float(user.get("subscription_price_amount") or 0),
                currency=str(((user.get("subscription") or {}).get("currency") or "EUR")).upper(),
                paymentRequired=bool(((user.get("subscription") or {}).get("payment_required"))),
                activity=PhaseOneBetaUserActivity(
                    aiConversations=accumulator.ai_conversation_count,
                    aiMessages=accumulator.ai_message_count,
                    nutritionPlans=accumulator.nutrition_plan_count,
                    nutritionLogs=accumulator.nutrition_log_count,
                    workoutsStarted=accumulator.workout_started_count,
                    workoutsCompleted=accumulator.workout_completed_count,
                    challengesJoined=accumulator.challenge_joined_count,
                    challengesCompleted=accumulator.challenge_completed_count,
                    communityPosts=accumulator.community_post_count,
                    communityComments=accumulator.community_comment_count,
                    communityReactions=accumulator.community_reaction_count,
                    lastActiveAt=accumulator.last_active_at,
                    usedAiCoach=used_ai,
                    usedNutrition=used_nutrition,
                    usedWorkout=used_workout,
                    usedChallenge=used_challenge,
                    usedCommunity=used_community,
                    usedAnyTrackedFeature=used_any,
                ),
            )
        )

    total_beta_users = len(users)
    active_today = sum(1 for item in users if item.activity.lastActiveAt and item.activity.lastActiveAt >= now - timedelta(days=1))
    active_this_week = sum(1 for item in users if item.activity.lastActiveAt and item.activity.lastActiveAt >= now - timedelta(days=7))
    countries_represented = len(countries)

    def _feature_metric(user_total: int, total: int, population: int) -> PhaseOneBetaFeatureAdoptionMetric:
        return PhaseOneBetaFeatureAdoptionMetric(
            users=user_total,
            total=total,
            averagePerActiveUser=round(total / user_total, 1) if user_total else 0,
            neverUsedUsers=max(population - user_total, 0),
        )

    return PhaseOneBetaSummaryResponse(
        totalBetaUsers=total_beta_users,
        activeBetaUsers=active,
        expiredBetaUsers=expired,
        goldBetaUsers=gold,
        limit=_phase_one_beta_max_users(),
        remainingSlots=max(_phase_one_beta_max_users() - total_beta_users, 0),
        averageDaysRemaining=round(days_remaining_total / active, 1) if active else 0,
        countriesRepresented=countries_represented,
        participation=PhaseOneBetaParticipationResponse(
            enrollmentProgressPct=round((total_beta_users / _phase_one_beta_max_users()) * 100, 1) if _phase_one_beta_max_users() else 0,
            activeRatePct=round((active / total_beta_users) * 100, 1) if total_beta_users else 0,
            expiredRatePct=round((expired / total_beta_users) * 100, 1) if total_beta_users else 0,
            neverActiveUsers=zero_activity_users,
            usersActiveToday=active_today,
            usersActiveThisWeek=active_this_week,
        ),
        featureAdoption=PhaseOneBetaFeatureAdoptionResponse(
            aiCoach=_feature_metric(feature_counts["ai"], totals["ai_messages"], total_beta_users),
            nutrition=_feature_metric(feature_counts["nutrition"], totals["nutrition_plans"] + totals["nutrition_logs"], total_beta_users),
            workouts=_feature_metric(feature_counts["workout"], totals["workouts_completed"], total_beta_users),
            challenges=_feature_metric(feature_counts["challenge"], totals["challenges_joined"], total_beta_users),
            community=_feature_metric(feature_counts["community"], totals["community_actions"], total_beta_users),
        ),
        crossFeatureAdoption=cross_feature,
        checkpoints=[checkpoints[day] for day in CHECKPOINT_DAYS],
        campaignHealth=PhaseOneBetaCampaignHealthResponse(
            zeroActivityUsers=zero_activity_users,
            endingSoonUsers=ending_soon_users,
            usersWithoutAiCoach=users_without_ai,
            usersWithoutNutrition=users_without_nutrition,
        ),
        support=PhaseOneBetaSupportReferenceResponse(
            betaUsersWithMessages=sum(1 for count in support_counts.values() if count > 0),
            totalSupportMessages=sum(support_counts.values()),
        ),
        countries=[
            PhaseOneBetaCountryItem(
                code=code,
                label=label,
                count=bucket["count"],
                activeUsers=bucket["active"],
                aiUsers=bucket["ai"],
                nutritionUsers=bucket["nutrition"],
                workoutUsers=bucket["workout"],
            )
            for (code, label), bucket in sorted(countries.items(), key=lambda item: (-item[1]["count"], item[0][1].lower()))
        ],
        users=users,
    )
