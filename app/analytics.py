"""Admin Intelligence & Marketing Analytics endpoints (Section 18).

All endpoints follow the same query-param contract:
    preset: today | this_week | this_year | custom   (default: this_week)
    from / to: only used when preset=custom
    market:  all | ghana | germany | india | other    (default: all)

All endpoints gracefully return zero data if the underlying collections are
missing (so the dashboard renders empty state, never crashes).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from .database import (
    accountability_pairs_collection,
    analytics_events_collection,
    challenges_collection,
    challenge_memberships_collection,
    coach_victor_threads_collection,
    completion_cards_collection,
    invites_collection,
    meal_analysis_entries_collection,
    nutrition_plan_jobs_collection,
    payment_events_collection,
    points_log_collection,
    users_collection,
    workout_logs_collection,
    workouts_collection,
)
from .dependencies import require_admin_user
from .models import (
    AnalyticsRangeResponse,
    AccountabilityStatsResponse,
    ChallengeStatsResponse,
    DailyWinEvent,
    DailyWinsFeedResponse,
    FunnelStep,
    HabitAdoptionResponse,
    InviteAbVariant,
    MarketBreakdownResponse,
    MarketBreakdownRow,
    MarketFoodItem,
    MarketRevenue,
    MarketShareSplit,
    MrrTrendPoint,
    NutritionStatsResponse,
    PopularChallengeItem,
    RetentionCohortResponse,
    RetentionCohortRow,
    RetentionComparison,
    RevenueStatsResponse,
    RevenueTierItem,
    SparklinePoint,
    TopUserItem,
    TopWorkoutItem,
    TrialFunnelResponse,
    UserStatsResponse,
    UserTierBreakdown,
    ViralCoefficientWidgetResponse,
    WhatsAppTrackerWidgetResponse,
    WorkoutStatsResponse,
)
from .utils.analytics import (
    build_currency_breakdown,
    color_band,
    market_filter,
    normalize_market,
    parse_time_range,
    pct_change,
    safe_ratio,
    sparkline_series,
    trend_arrow,
    viral_coefficient,
)
from .utils.country import PRIMARY_MARKETS, market_bucket

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _safe_count(coll, query: dict | None = None) -> int:
    """count_documents with full try/except so missing collections return 0."""
    if coll is None:
        return 0
    try:
        return await coll.count_documents(query or {})
    except Exception:
        return 0


async def _safe_find(
    coll,
    query: dict | None = None,
    *,
    projection: dict | None = None,
    sort: list[tuple[str, int]] | None = None,
    limit: int | None = None,
):
    if coll is None:
        return []
    try:
        cursor = coll.find(query or {}, projection)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
    except Exception:
        return []


def _and(*filters: dict | None) -> dict:
    clauses = [item for item in filters if item]
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


async def _market_user_filter(market: str, field: str = "user_id") -> dict:
    """Scope an activity collection through users.country_code."""
    m_filter = market_filter(market)
    if not m_filter:
        return {}
    users = await _safe_find(users_collection, m_filter, projection={"_id": 1})
    ids: list[Any] = []
    for user in users:
        user_id = user.get("_id")
        if user_id is not None:
            ids.extend((user_id, str(user_id)))
    return {field: {"$in": ids}}


async def _find_by_id(collection, value: str) -> dict | None:
    candidates: list[Any] = [value]
    try:
        candidates.insert(0, ObjectId(value))
    except Exception:
        pass
    try:
        return await collection.find_one({"_id": {"$in": candidates}})
    except Exception:
        return None


def _as_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _trial_started_at(user: dict) -> datetime | None:
    return _as_utc_datetime(user.get("trial_start_at") or user.get("subscription_started_at"))


def _trial_end_at(user: dict, started_at: datetime) -> datetime:
    return _as_utc_datetime(user.get("trial_end_at")) or (started_at + timedelta(days=5))


def _is_phase_one_beta_user(user: dict) -> bool:
    return str(user.get("subscription_purchase_source") or "").strip() == "beta_trial"


def _is_paid_subscription(user: dict) -> bool:
    if _is_phase_one_beta_user(user):
        return False
    return bool(user.get("subscription_is_purchased")) or str(user.get("subscription_status") or "").upper() in {"ACTIVE", "PAID"}


def _trial_user_outcome(user: dict, now: datetime) -> str | None:
    explicit = str(user.get("trial_outcome") or "").strip()
    if explicit:
        return explicit
    tier = str(user.get("subscription_tier") or "").upper()
    paid = _is_paid_subscription(user)
    if paid and tier in {"GOLD", "PLATINUM", "INNER_CIRCLE"}:
        return "converted_gold"
    if paid and tier == "SILVER":
        return "downgraded_silver"
    started_at = _trial_started_at(user)
    if started_at and now >= _trial_end_at(user, started_at):
        return "lapsed"
    return None


async def _active_user_ids(start: datetime, end: datetime, market: str) -> set[str]:
    user_scope = await _market_user_filter(market)
    sources = (
        (workout_logs_collection, "started_at", None),
        (meal_analysis_entries_collection, "created_at", None),
        (coach_victor_threads_collection, "created_at", None),
        (analytics_events_collection, "created_at", {"event_type": "ai_coach_used"}),
    )
    active: set[str] = set()
    for collection, date_field, extra in sources:
        query = _and(
            {date_field: {"$gte": start, "$lte": end}},
            user_scope,
            extra,
        )
        rows = await _safe_find(collection, query, projection={"user_id": 1})
        active.update(str(row["user_id"]) for row in rows if row.get("user_id"))
    return active


async def _active_ids_for_users(
    user_ids: list[Any],
    start: datetime,
    end: datetime,
) -> set[str]:
    if not user_ids:
        return set()
    scope = {"user_id": {"$in": user_ids}}
    sources = (
        (workout_logs_collection, "started_at"),
        (meal_analysis_entries_collection, "created_at"),
        (coach_victor_threads_collection, "created_at"),
        (analytics_events_collection, "created_at"),
    )
    active: set[str] = set()
    for collection, date_field in sources:
        rows = await _safe_find(
            collection,
            _and(scope, {date_field: {"$gte": start, "$lt": end}}),
            projection={"user_id": 1},
        )
        active.update(str(row["user_id"]) for row in rows if row.get("user_id"))
    return active


async def _latest_market_day7_retention(market: str, anchor: datetime) -> float:
    current_week_start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=timezone.utc)
    current_week_start -= timedelta(days=current_week_start.weekday())
    cohort_end = current_week_start - timedelta(days=7)
    cohort_start = cohort_end - timedelta(days=7)
    cohort_users = await _safe_find(
        users_collection,
        _and(
            market_filter(market),
            {"is_admin": {"$ne": True}},
            {"created_at": {"$gte": cohort_start, "$lt": cohort_end}},
        ),
        projection={"_id": 1},
    )
    if not cohort_users:
        return 0.0
    ids: list[Any] = []
    for user in cohort_users:
        ids.extend((user.get("_id"), str(user.get("_id"))))
    active = await _active_ids_for_users(ids, cohort_end, current_week_start)
    return round(safe_ratio(len(active), len(cohort_users)), 1)


def _range_dict(preset: str, market: str, start: datetime, end: datetime, prev_start: datetime, prev_end: datetime) -> dict:
    return {
        "preset": preset,
        "market": market,
        "fromDate": start,
        "toDate": end,
        "prevFromDate": prev_start,
        "prevToDate": prev_end,
    }


def _common_filter(
    preset: str,
    custom_from: date | None,
    custom_to: date | None,
    market: str,
    date_field: str = "created_at",
) -> tuple[dict, dict, dict, datetime, datetime, datetime, datetime]:
    """Returns (range_filter, prev_range_filter, combined, start, end, prev_start, prev_end)."""
    start, end, prev_start, prev_end = parse_time_range(preset, custom_from, custom_to)
    m_filter = market_filter(market)
    rng = {date_field: {"$gte": start, "$lte": end}}
    prev_rng = {date_field: {"$gte": prev_start, "$lte": prev_end}}
    combined = {"$and": [m_filter or {}, rng]}
    return rng, prev_rng, combined, start, end, prev_start, prev_end


# ---------------------------------------------------------------------------
# 18.1 Range helper
# ---------------------------------------------------------------------------

@router.get("/range", response_model=AnalyticsRangeResponse)
async def analytics_range(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> AnalyticsRangeResponse:
    start, end, prev_start, prev_end = parse_time_range(preset, from_date, to_date)
    return AnalyticsRangeResponse(
        preset=preset,
        market=normalize_market(market),
        fromDate=start,
        toDate=end,
        prevFromDate=prev_start,
        prevToDate=prev_end,
    )


# ---------------------------------------------------------------------------
# 18.2 User Statistics
# ---------------------------------------------------------------------------

TIER_COLORS = {
    "NONE": "#94a3b8",
    "SILVER": "#cbd5e1",
    "GOLD": "#fbbf24",
    "PLATINUM": "#818cf8",
    "INNER_CIRCLE": "#34d399",
}


@router.get("/user-stats", response_model=UserStatsResponse)
async def user_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> UserStatsResponse:
    rng, prev_rng, combined, start, end, prev_start, prev_end = _common_filter(
        preset, from_date, to_date, market, "created_at"
    )
    m_filter = market_filter(market)
    users_filter = _and({"is_admin": {"$ne": True}}, m_filter)
    total = await _safe_count(users_collection, users_filter)
    new_users = await _safe_count(users_collection, _and(users_filter, rng))
    prev_new_users = await _safe_count(users_collection, _and(users_filter, prev_rng))

    active_user_ids = await _active_user_ids(start, end, market)
    prev_active = await _active_user_ids(prev_start, prev_end, market)

    # A trial is decided five days after it starts. Conversion belongs to the
    # period in which that decision date falls, not the registration period.
    trial_users = await _safe_find(
        users_collection,
        _and(users_filter, {"$or": [{"trial_start_at": {"$ne": None}}, {"subscription_started_at": {"$ne": None}}]}),
        projection={
            "trial_start_at": 1,
            "trial_end_at": 1,
            "trial_outcome": 1,
            "subscription_started_at": 1,
            "subscription_is_purchased": 1,
            "subscription_status": 1,
            "subscription_tier": 1,
            "subscription_purchase_source": 1,
        },
    )
    completed_trial = converted_trial = 0
    prev_completed_trial = prev_converted_trial = 0
    for trial_user in trial_users:
        trial_started = _trial_started_at(trial_user)
        if not trial_started:
            continue
        decided_at = _trial_end_at(trial_user, trial_started)
        converted = _trial_user_outcome(trial_user, end) == "converted_gold"
        if start <= decided_at <= end:
            completed_trial += 1
            converted_trial += int(converted)
        elif prev_start <= decided_at <= prev_end:
            prev_completed_trial += 1
            prev_converted_trial += int(converted)
    conversion = safe_ratio(converted_trial, completed_trial)

    activity_market = await _market_user_filter(market)
    churn_event = {"type": {"$in": ["subscription_cancelled", "subscription_expired"]}}
    churned = await _safe_count(payment_events_collection, _and(rng, activity_market, churn_event))
    prev_churned = await _safe_count(payment_events_collection, _and(prev_rng, activity_market, churn_event))

    # Users by tier
    tier_counts: Counter[str] = Counter()
    all_users = await _safe_find(users_collection, users_filter, projection={"subscription_tier": 1})
    for u in all_users:
        tier = u.get("subscription_tier") or "NONE"
        tier_counts[tier] += 1
    users_by_tier = [
        UserTierBreakdown(tier=t, count=c, color=TIER_COLORS.get(t))
        for t, c in tier_counts.most_common()
    ]

    # Top 10 users by points
    top = await _safe_find(
        points_log_collection,
        _and(rng, activity_market),
        sort=[("created_at", -1)],
        limit=500,
        projection={"user_id": 1, "points": 1},
    )
    points_by_user: dict[str, int] = defaultdict(int)
    for row in top:
        uid = str(row.get("user_id") or "")
        points_by_user[uid] += int(row.get("points") or 0)
    top_sorted = sorted(points_by_user.items(), key=lambda kv: kv[1], reverse=True)[:10]
    top_users: list[TopUserItem] = []
    for idx, (uid, points) in enumerate(top_sorted, start=1):
        profile = await _find_by_id(users_collection, uid)
        name = str((profile or {}).get("name") or (profile or {}).get("full_name") or uid[:8])
        tier = str((profile or {}).get("subscription_tier") or "NONE")
        workouts = await _safe_count(
            workout_logs_collection,
            _and(
                {"started_at": {"$gte": start, "$lte": end}},
                {"user_id": {"$in": [uid, (profile or {}).get("_id")] }},
                {"completed_at": {"$ne": None}},
            ),
        )
        top_users.append(
            TopUserItem(
                rank=idx,
                userId=uid,
                name=name,
                tier=tier,
                points=points,
                workouts=workouts,
            )
        )

    return UserStatsResponse(
        totalRegistered=total,
        totalRegisteredChangePct=round(pct_change(total, max(total - new_users, 0)), 1),
        newUsers=new_users,
        newUsersChangePct=round(pct_change(new_users, prev_new_users), 1),
        activeUsers=len(active_user_ids),
        activeUsersChangePct=round(pct_change(len(active_user_ids), len(prev_active)), 1),
        trialConversionRate=round(conversion, 1),
        trialConversionColor=color_band(conversion, 30.0, 15.0),
        churnedUsers=churned,
        churnedChangePct=round(pct_change(churned, prev_churned), 1),
        usersByTier=users_by_tier,
        top10Users=top_users,
    )


# ---------------------------------------------------------------------------
# 18.3 Workout Statistics
# ---------------------------------------------------------------------------

@router.get("/workout-stats", response_model=WorkoutStatsResponse)
async def workout_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> WorkoutStatsResponse:
    rng, prev_rng, _, start, end, _, _ = _common_filter(
        preset, from_date, to_date, market, "started_at"
    )
    activity_market = await _market_user_filter(market)
    completed_q = _and(rng, activity_market, {"completed_at": {"$ne": None}})
    completed = await _safe_count(workout_logs_collection, completed_q)
    prev_completed = await _safe_count(
        workout_logs_collection,
        _and(prev_rng, activity_market, {"completed_at": {"$ne": None}}),
    )
    started = await _safe_count(workout_logs_collection, _and(rng, activity_market))
    rate = safe_ratio(completed, max(started, 1))

    # Top workout
    rows = await _safe_find(workout_logs_collection, completed_q, limit=2000, projection={"workout_id": 1, "duration_seconds": 1})
    counts: Counter[str] = Counter()
    duration_by_workout: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        wid = str(r.get("workout_id") or "unknown")
        counts[wid] += 1
        duration_by_workout[wid].append(int(r.get("duration_seconds") or 0))
    top_workout: TopWorkoutItem | None = None
    if counts:
        top_wid, top_count = counts.most_common(1)[0]
        title = top_wid
        try:
            w = await _find_by_id(workouts_collection, top_wid)
            if w:
                title = str(w.get("title") or top_wid)
        except Exception:
            pass
        durs = duration_by_workout.get(top_wid, [])
        avg = sum(durs) // len(durs) if durs else 0
        top_workout = TopWorkoutItem(workoutId=top_wid, title=title, count=top_count, avgDurationSeconds=avg)

    ai_generated = await _safe_count(
        workouts_collection,
        _and(
            {"source": "ai"},
            {"created_at": {"$gte": start, "$lte": end}},
            activity_market,
        ),
    )

    return WorkoutStatsResponse(
        totalCompleted=completed,
        totalCompletedChangePct=round(pct_change(completed, prev_completed), 1),
        completionRate=round(rate, 1),
        completionRateColor=color_band(rate, 70.0, 50.0),
        topWorkout=top_workout,
        aiGeneratedWorkouts=ai_generated,
    )


# ---------------------------------------------------------------------------
# 18.4 Challenge Statistics
# ---------------------------------------------------------------------------

@router.get("/challenge-stats", response_model=ChallengeStatsResponse)
async def challenge_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> ChallengeStatsResponse:
    rng, prev_rng, _, start, end, prev_start, prev_end = _common_filter(
        preset, from_date, to_date, market, "joined_at"
    )
    activity_market = await _market_user_filter(market)
    membership_filter = _and(rng, activity_market)

    # Most popular challenge in range (by member count)
    pipeline = []
    if challenge_memberships_collection is not None:
        try:
            pipeline = [
                {"$match": membership_filter},
                {"$group": {"_id": "$challenge_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 1},
            ]
            top_rows = await challenge_memberships_collection.aggregate(pipeline).to_list(length=1)
        except Exception:
            top_rows = []
    else:
        top_rows = []

    most_popular: PopularChallengeItem | None = None
    if top_rows:
        top = top_rows[0]
        challenge_id = top.get("_id")
        title = str(challenge_id or "—")
        category = None
        completion_rate = 0.0
        if challenges_collection is not None:
            try:
                ch = await challenges_collection.find_one({"_id": challenge_id})
                if ch:
                    title = str(ch.get("title") or title)
                    category = ch.get("category")
            except Exception:
                pass
        try:
            members = await challenge_memberships_collection.count_documents(
                _and(membership_filter, {"challenge_id": challenge_id}, {"status": "completed"})
            )
            completion_rate = safe_ratio(members, max(top.get("count", 0), 1))
        except Exception:
            pass
        most_popular = PopularChallengeItem(
            challengeId=str(challenge_id) if challenge_id else None,
            title=title,
            category=category,
            participants=top.get("count", 0),
            completionRate=round(completion_rate, 1),
        )

    invite_rng = {"created_at": {"$gte": start, "$lte": end}}
    prev_invite_rng = {"created_at": {"$gte": prev_start, "$lte": prev_end}}
    invites_sent = await _safe_count(invites_collection, _and(invite_rng, activity_market))
    prev_invites_sent = await _safe_count(invites_collection, _and(prev_invite_rng, activity_market))
    accepted = await _safe_count(
        invites_collection,
        _and(invite_rng, activity_market, {"accepted": True}),
    )
    invite_conversion = safe_ratio(accepted, max(invites_sent, 1))

    # A/B variant test
    variant_counts: Counter[str] = Counter()
    variant_accepted: Counter[str] = Counter()
    rows = await _safe_find(
        invites_collection,
        _and(invite_rng, activity_market),
        projection={"copy_variant": 1, "accepted": 1},
    )
    for r in rows:
        v = str(r.get("copy_variant") or "a").lower()
        variant_counts[v] += 1
        if r.get("accepted"):
            variant_accepted[v] += 1
    ab_results = [
        InviteAbVariant(variant=v, acceptances=variant_accepted[v], total=variant_counts[v])
        for v in sorted(variant_counts.keys())
    ]

    return ChallengeStatsResponse(
        mostPopular=most_popular,
        invitesSent=invites_sent,
        invitesSentChangePct=round(pct_change(invites_sent, prev_invites_sent), 1),
        inviteConversionRate=round(invite_conversion, 1),
        abTestResult=ab_results,
    )


# ---------------------------------------------------------------------------
# 18.5 Nutrition Statistics
# ---------------------------------------------------------------------------

@router.get("/nutrition-stats", response_model=NutritionStatsResponse)
async def nutrition_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> NutritionStatsResponse:
    rng, prev_rng, _, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    activity_market = await _market_user_filter(market)
    meal_plan_job = {
        "$or": [
            {"job_type": "meal_plan"},
            {"generation_mode": {"$exists": True}},
        ]
    }
    ai_plans = await _safe_count(
        nutrition_plan_jobs_collection,
        _and(rng, activity_market, meal_plan_job, {"status": "completed"}),
    )
    prev_ai_plans = await _safe_count(
        nutrition_plan_jobs_collection,
        _and(prev_rng, activity_market, meal_plan_job, {"status": "completed"}),
    )
    entries = await _safe_find(
        meal_analysis_entries_collection,
        _and(rng, activity_market),
        projection={"user_id": 1, "created_at": 1, "analysis.estimated_protein": 1},
    )
    protein_by_user_day: dict[tuple[str, str], float] = defaultdict(float)
    for entry in entries:
        created_at = _as_utc_datetime(entry.get("created_at"))
        user_id = str(entry.get("user_id") or "")
        if not created_at or not user_id:
            continue
        protein_by_user_day[(user_id, created_at.strftime("%Y-%m-%d"))] += float(
            (entry.get("analysis") or {}).get("estimated_protein") or 0
        )
    protein_hit = 0
    for (user_id, _day), protein_total in protein_by_user_day.items():
        profile = await _find_by_id(users_collection, user_id)
        target = float(
            (profile or {}).get("protein_target_g")
            or (profile or {}).get("daily_protein")
            or 0
        )
        if target > 0 and protein_total >= target:
            protein_hit += 1
    protein_rate = safe_ratio(protein_hit, len(protein_by_user_day))

    # Most logged food by market — group meal entries by market via user.country_code
    most_logged: dict[str, MarketFoodItem | None] = {"Ghana": None, "Germany": None, "India": None}
    if meal_analysis_entries_collection is not None and users_collection is not None:
        try:
            pipeline = [
                {"$match": _and(rng, activity_market)},
                {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}},
                {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": False}},
                {
                    "$group": {
                        "_id": {
                            "market": "$user.country_code",
                            "food_id": "$analysis.meal_name_guess",
                            "food_name": "$analysis.meal_name_guess",
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": 30},
            ]
            grouped = await meal_analysis_entries_collection.aggregate(pipeline).to_list(length=30)
            market_to_food: dict[str, tuple[MarketFoodItem, int]] = {}
            for g in grouped:
                bucket = market_bucket(g["_id"].get("market"))
                if bucket not in most_logged:
                    continue
                existing = market_to_food.get(bucket)
                count = g.get("count", 0)
                if existing is None or count > existing[1]:
                    market_to_food[bucket] = (
                        MarketFoodItem(
                            foodId=str(g["_id"].get("food_id")) if g["_id"].get("food_id") else None,
                            foodName=str(g["_id"].get("food_name") or "Unknown"),
                            count=count,
                        ),
                        count,
                    )
            for bucket, (item, _) in market_to_food.items():
                most_logged[bucket] = item
        except Exception:
            pass

    return NutritionStatsResponse(
        aiMealPlans=ai_plans,
        aiMealPlansChangePct=round(pct_change(ai_plans, prev_ai_plans), 1),
        proteinTargetHitRate=round(protein_rate, 1),
        mostLoggedByMarket=most_logged,
    )


# ---------------------------------------------------------------------------
# 18.6 Revenue Statistics
# ---------------------------------------------------------------------------

@router.get("/revenue", response_model=RevenueStatsResponse)
async def revenue_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    trend_granularity: str = Query("daily", alias="granularity"),
    _: dict = Depends(require_admin_user),
) -> RevenueStatsResponse:
    rng, _, _, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    activity_market = await _market_user_filter(market)
    payment_filter = _and(
        activity_market,
        {"status": "success"},
        {"type": "subscription_renewed"},
    )
    payments = await _safe_find(
        payment_events_collection,
        _and(rng, payment_filter),
        projection={"amount": 1, "currency": 1, "tier": 1, "market": 1, "created_at": 1},
        limit=5000,
    )
    by_country: dict[str, float] = defaultdict(float)
    by_tier: dict[str, float] = defaultdict(float)
    daily: dict[str, float] = defaultdict(float)
    for p in payments:
        amount = float(p.get("amount") or 0)
        currency = str(p.get("currency") or "EUR")
        market_code = str(p.get("market") or "OTHER")
        tier = str(p.get("tier") or "NONE")
        by_country[market_code] += amount
        by_tier[tier] += amount
        ts = _as_utc_datetime(p.get("created_at"))
        if isinstance(ts, datetime):
            granularity = trend_granularity.lower()
            if granularity == "monthly":
                bucket = ts.strftime("%Y-%m")
            elif granularity == "weekly":
                bucket = f"{ts.isocalendar().year}-W{ts.isocalendar().week:02d}"
            else:
                granularity = "daily"
                bucket = ts.strftime("%Y-%m-%d")
            daily[bucket] += amount

    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    mrr_payments = await _safe_find(
        payment_events_collection,
        _and({"created_at": {"$gte": month_start, "$lte": now}}, payment_filter),
        projection={"amount": 1, "market": 1},
        limit=5000,
    )
    mrr_by_country: dict[str, float] = defaultdict(float)
    for payment in mrr_payments:
        mrr_by_country[str(payment.get("market") or "OTHER")] += float(payment.get("amount") or 0)
    mrr = build_currency_breakdown(mrr_by_country)
    active_subs = await _safe_count(
        users_collection,
        _and(
            market_filter(market),
            {"subscription_status": {"$in": ["ACTIVE", "PAID", "active", "paid"]}},
            {"subscription_purchase_source": {"$ne": "beta_trial"}},
        ),
    )
    arpu = round(sum(mrr_by_country.values()) / active_subs, 2) if active_subs else 0.0

    revenue_by_tier = [
        RevenueTierItem(tier=t, amount=round(amt, 2))
        for t, amt in sorted(by_tier.items(), key=lambda kv: kv[1], reverse=True)
    ]

    currency_for_market = {"GH": "GHS", "DE": "EUR", "IN": "INR"}
    revenue_by_market = [
        MarketRevenue(market=m, currency=currency_for_market.get(m, "EUR"), amount=round(amt, 2))
        for m, amt in by_country.items()
        if amt > 0
    ]

    trend = [MrrTrendPoint(date=k, value=round(v, 2)) for k, v in sorted(daily.items())]
    granularity = trend_granularity.lower()
    if granularity not in {"daily", "weekly", "monthly"}:
        granularity = "daily"

    return RevenueStatsResponse(
        mrr=mrr,
        revenueByTier=revenue_by_tier,
        revenueByMarket=revenue_by_market,
        arpu=arpu,
        mrrTrend=trend,
        trendGranularity=granularity,
    )


# ---------------------------------------------------------------------------
# 18.7 Accountability Adoption
# ---------------------------------------------------------------------------

@router.get("/accountability-stats", response_model=AccountabilityStatsResponse)
async def accountability_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> AccountabilityStatsResponse:
    rng, prev_rng, _, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    pair_scope = await _market_user_filter(market, field="user_ids")
    pairs = await _safe_count(accountability_pairs_collection, _and(rng, pair_scope, {"status": "active"}))
    prev_pairs = await _safe_count(accountability_pairs_collection, _and(prev_rng, pair_scope, {"status": "active"}))

    return AccountabilityStatsResponse(
        newAccountabilityPairs=pairs,
        newPairsChangePct=round(pct_change(pairs, prev_pairs), 1),
    )


# ---------------------------------------------------------------------------
# 18.8 Habit Adoption
# ---------------------------------------------------------------------------

@router.get("/habit-adoption", response_model=HabitAdoptionResponse)
async def habit_adoption_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> HabitAdoptionResponse:
    m_filter = market_filter(market)
    base = _and(
        m_filter,
        {"subscription_tier": {"$in": ["GOLD", "PLATINUM", "INNER_CIRCLE"]}},
    )
    eligible_users = await _safe_find(
        users_collection,
        base,
        projection={
            "_id": 1,
            "identity_statement": 1,
            "workout_unlock_label": 1,
            "training_trigger_context": 1,
            "subscription_confirmed_at": 1,
            "subscription_started_at": 1,
        },
    )
    eligible = len(eligible_users)

    def is_set(value: Any) -> bool:
        return bool(str(value or "").strip())

    identity_set = sum(is_set(user.get("identity_statement")) for user in eligible_users)
    unlock_set = sum(is_set(user.get("workout_unlock_label")) for user in eligible_users)
    trigger_set = sum(is_set(user.get("training_trigger_context")) for user in eligible_users)

    mature_habit = mature_non_habit = habit_retained = non_habit_retained = 0
    now = datetime.now(timezone.utc)
    for user in eligible_users:
        gold_started = _as_utc_datetime(
            user.get("subscription_confirmed_at") or user.get("subscription_started_at")
        )
        if not gold_started or gold_started + timedelta(days=30) > now:
            continue
        has_habit = any(
            is_set(user.get(field))
            for field in (
                "identity_statement",
                "workout_unlock_label",
                "training_trigger_context",
            )
        )
        active = bool(
            await _active_ids_for_users(
                [user.get("_id"), str(user.get("_id"))],
                gold_started,
                gold_started + timedelta(days=30),
            )
        )
        if has_habit:
            mature_habit += 1
            habit_retained += int(active)
        else:
            mature_non_habit += 1
            non_habit_retained += int(active)

    return HabitAdoptionResponse(
        identityStatementSet=identity_set,
        identityStatementPct=round(safe_ratio(identity_set, eligible), 1),
        workoutUnlockSet=unlock_set,
        workoutUnlockPct=round(safe_ratio(unlock_set, eligible), 1),
        ifThenTriggerSet=trigger_set,
        ifThenTriggerPct=round(safe_ratio(trigger_set, eligible), 1),
        retentionComparison=RetentionComparison(
            habitRetainedPct=round(safe_ratio(habit_retained, mature_habit), 1),
            nonHabitRetainedPct=round(safe_ratio(non_habit_retained, mature_non_habit), 1),
        ),
    )


# ---------------------------------------------------------------------------
# 18.9 Widgets
# ---------------------------------------------------------------------------

@router.get("/trial-funnel", response_model=TrialFunnelResponse)
async def trial_funnel_widget(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> TrialFunnelResponse:
    rng, _, _, start, end, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    trial_rng, _, _, *_ = _common_filter(preset, from_date, to_date, market, "trial_start_at")
    m_filter = market_filter(market)
    activity_market = await _market_user_filter(market)

    started = await _safe_count(users_collection, {"$and": [m_filter, trial_rng, {"trial_tier_granted": "gold"}]})
    opened_msg = await _safe_count(analytics_events_collection, _and(activity_market, rng, {"event_type": "day1_message_opened"}))
    used_coach = await _safe_count(analytics_events_collection, _and(activity_market, rng, {"event_type": "ai_coach_used"}))
    used_nutrition = await _safe_count(nutrition_plan_jobs_collection, _and(activity_market, rng))
    warmup = await _safe_count(analytics_events_collection, _and(activity_market, rng, {"event_type": "day4_warmup_seen"}))
    converted = await _safe_count(users_collection, {"$and": [m_filter, {"trial_outcome": "converted_gold"}, {"trial_outcome_at": {"$gte": start, "$lte": end}}]})

    raw = [
        ("Trial Started", started),
        ("Day-1 Message Opened", opened_msg),
        ("AI Coach Used", used_coach),
        ("Nutrition Planner Used", used_nutrition),
        ("Day-4 Warm-Up Seen", warmup),
        ("Converted", converted),
    ]
    steps: list[FunnelStep] = []
    prev_count = None
    largest_drop_label: str | None = None
    largest_drop_pct = 0.0
    for label, count in raw:
        drop_pct = 0.0
        if prev_count and prev_count > 0:
            drop_pct = round(max(0, (prev_count - count) / prev_count * 100), 1)
        steps.append(FunnelStep(label=label, count=count, dropOffPct=drop_pct))
        if drop_pct > largest_drop_pct:
            largest_drop_pct = drop_pct
            largest_drop_label = label
        prev_count = count

    return TrialFunnelResponse(steps=steps, largestDropOff=largest_drop_label)


@router.get("/viral-coefficient", response_model=ViralCoefficientWidgetResponse)
async def viral_coefficient_widget(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> ViralCoefficientWidgetResponse:
    # Use a rolling 30-day window regardless of preset
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    activity_market = await _market_user_filter(market)
    user_market = market_filter(market)
    weekly_points = []
    sparkline: list[SparklinePoint] = []
    for week_offset in range(12):
        week_end = end - timedelta(weeks=week_offset)
        week_start = week_end - timedelta(weeks=1)
        invites_q = _and(
            {"created_at": {"$gte": week_start, "$lte": week_end}},
            activity_market,
            {"accepted": True},
        )
        new_q = _and(
            {"created_at": {"$gte": week_start, "$lte": week_end}},
            user_market,
        )
        accepted = await _safe_count(invites_collection, invites_q)
        new_users = await _safe_count(users_collection, new_q)
        ratio = viral_coefficient(accepted, new_users)
        weekly_points.append(SparklinePoint(date=week_start.strftime("%Y-%m-%d"), value=round(ratio, 2)))
    weekly_points.reverse()
    sparkline = weekly_points

    invites_q = _and(
        {"created_at": {"$gte": start, "$lte": end}},
        activity_market,
        {"accepted": True},
    )
    accepted = await _safe_count(invites_collection, invites_q)
    new_users = await _safe_count(
        users_collection,
        _and({"created_at": {"$gte": start, "$lte": end}}, user_market),
    )
    current = round(viral_coefficient(accepted, new_users), 2)
    sublabel = f"For every 10 new users, {current:g} came from an invite"

    return ViralCoefficientWidgetResponse(
        current=current,
        color=color_band(current, 1.0, 0.5),
        sublabel=sublabel,
        sparkline=sparkline,
    )


@router.get("/whatsapp-tracker", response_model=WhatsAppTrackerWidgetResponse)
async def whatsapp_tracker_widget(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> WhatsAppTrackerWidgetResponse:
    _, _, _, _start, end, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    activity_market = await _market_user_filter(market)
    today_start = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=today_start.weekday())
    prev_week_start = week_start - timedelta(days=7)
    share_filter = _and(activity_market, {"shared_to_whatsapp": True})
    today_count = await _safe_count(
        completion_cards_collection,
        _and({"created_at": {"$gte": today_start, "$lte": end}}, share_filter),
    )
    week_count = await _safe_count(
        completion_cards_collection,
        _and({"created_at": {"$gte": week_start, "$lte": end}}, share_filter),
    )
    prev_week = await _safe_count(
        completion_cards_collection,
        _and({"created_at": {"$gte": prev_week_start, "$lt": week_start}}, share_filter),
    )

    # 30-day daily series
    daily_series: list[SparklinePoint] = []
    for day_offset in range(29, -1, -1):
        day = end - timedelta(days=day_offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        c = await _safe_count(
            completion_cards_collection,
            _and(
                {"created_at": {"$gte": day_start, "$lt": day_end}},
                share_filter,
            ),
        )
        daily_series.append(SparklinePoint(date=day_start.strftime("%Y-%m-%d"), value=float(c)))

    # Market split (look up user.country_code for each card via lookup)
    market_split = MarketShareSplit()
    if completion_cards_collection is not None and users_collection is not None:
        try:
            pipeline = [
                {"$match": _and(
                    {"created_at": {"$gte": week_start, "$lte": end}},
                    share_filter,
                )},
                {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}},
                {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": False}},
                {"$group": {"_id": "$user.country_code", "count": {"$sum": 1}}},
            ]
            rows = await completion_cards_collection.aggregate(pipeline).to_list(length=10)
            for r in rows:
                bucket = market_bucket(r.get("_id"))
                if bucket == "Ghana":
                    market_split.ghana = r.get("count", 0)
                elif bucket == "Germany":
                    market_split.germany = r.get("count", 0)
                elif bucket == "India":
                    market_split.india = r.get("count", 0)
        except Exception:
            pass

    return WhatsAppTrackerWidgetResponse(
        todayCount=today_count,
        thisWeekCount=week_count,
        thisWeekChangePct=round(pct_change(week_count, prev_week), 1),
        dailySeries=daily_series,
        marketSplit=market_split,
    )


@router.get("/daily-wins", response_model=DailyWinsFeedResponse)
async def daily_wins_widget(
    _: dict = Depends(require_admin_user),
) -> DailyWinsFeedResponse:
    from datetime import timedelta
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    rng = {"created_at": {"$gte": start, "$lte": end}}
    events: list[DailyWinEvent] = []

    if completion_cards_collection is not None:
        try:
            pipeline = [
                {"$match": {"$and": [rng, {"shared_to_whatsapp": True}]}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%dT%H", "date": "$created_at"}}, "count": {"$sum": 1}}},
                {"$sort": {"_id": -1}},
                {"$limit": 5},
            ]
            for r in await completion_cards_collection.aggregate(pipeline).to_list(length=5):
                events.append(DailyWinEvent(
                    type="whatsapp_share",
                    label=f"{r['count']} workout card{'s' if r['count'] != 1 else ''} shared",
                    count=r["count"],
                    createdAt=end,
                ))
        except Exception:
            pass

    if accountability_pairs_collection is not None:
        try:
            n = await accountability_pairs_collection.count_documents(rng)
            if n:
                events.append(DailyWinEvent(type="pair_created", label=f"{n} new accountability pair{'s' if n != 1 else ''}", count=n, createdAt=end))
        except Exception:
            pass

    if challenge_memberships_collection is not None:
        try:
            n = await challenge_memberships_collection.count_documents({"$and": [rng, {"status": "completed"}]})
            if n:
                events.append(DailyWinEvent(type="challenge_completed", label=f"{n} challenge{'s' if n != 1 else ''} completed", count=n, createdAt=end))
        except Exception:
            pass

    new_subs = await _safe_count(
        payment_events_collection,
        _and(
            rng,
            {"type": "subscription_started"},
            {"tier": {"$in": ["GOLD", "PLATINUM", "INNER_CIRCLE"]}},
        ),
    )
    if new_subs:
        events.append(DailyWinEvent(type="new_subscriber", label=f"{new_subs} new Gold subscriber{'s' if new_subs != 1 else ''}", count=new_subs, createdAt=end))

    streaks = await _safe_count(analytics_events_collection, {"$and": [rng, {"event_type": "streak_7_day"}]})
    if streaks:
        events.append(DailyWinEvent(type="streak", label=f"{streaks} 7-day streak{'s' if streaks != 1 else ''} achieved", count=streaks, createdAt=end))

    return DailyWinsFeedResponse(events=events[:10], lastUpdated=end)


# ---------------------------------------------------------------------------
# 18.10 Retention Cohort
# ---------------------------------------------------------------------------

@router.get("/retention-cohort", response_model=RetentionCohortResponse)
async def retention_cohort(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> RetentionCohortResponse:
    rows: list[RetentionCohortRow] = []
    selected_start, selected_end, _, _ = parse_time_range(preset, from_date, to_date)
    span_weeks = max(8, min(52, int((selected_end - selected_start).days / 7) + 1))
    anchor = datetime(selected_end.year, selected_end.month, selected_end.day, tzinfo=timezone.utc)
    anchor -= timedelta(days=anchor.weekday())
    now = datetime.now(timezone.utc)
    for week_offset in range(span_weeks - 1, -1, -1):
        week_start = anchor - timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=7)
        cohort_users = await _safe_find(
            users_collection,
            _and(
                market_filter(market),
                {"is_admin": {"$ne": True}},
                {"created_at": {"$gte": week_start, "$lt": week_end}},
            ),
            projection={
                "_id": 1,
                "subscription_confirmed_at": 1,
                "subscription_started_at": 1,
                "subscription_status": 1,
                "subscription_is_purchased": 1,
                "subscription_purchase_source": 1,
            },
        )
        if not cohort_users:
            continue
        new_users = len(cohort_users)
        cohort_ids: list[Any] = []
        for user in cohort_users:
            cohort_ids.extend((user.get("_id"), str(user.get("_id"))))

        async def retention_for_window(window_start: datetime, window_end: datetime) -> float | None:
            if now < window_end:
                return None
            active = await _active_ids_for_users(cohort_ids, window_start, window_end)
            return round(safe_ratio(len(active), new_users), 1)

        day7 = await retention_for_window(week_end, week_end + timedelta(days=7))
        day14 = await retention_for_window(week_end + timedelta(days=7), week_end + timedelta(days=14))
        day30_end = week_end + timedelta(days=30)
        day30 = await retention_for_window(week_end + timedelta(days=23), day30_end)
        paid_day30 = None
        if now >= day30_end:
            paid = 0
            for user in cohort_users:
                confirmed_at = _as_utc_datetime(user.get("subscription_confirmed_at"))
                purchased = _is_paid_subscription(user)
                if purchased and (confirmed_at is None or confirmed_at <= day30_end):
                    paid += 1
            paid_day30 = round(safe_ratio(paid, new_users), 1)
        rows.append(RetentionCohortRow(
            weekStart=week_start.strftime("%Y-%m-%d"),
            newUsers=new_users,
            day7Pct=day7,
            day14Pct=day14,
            day30Pct=day30,
            paidDay30Pct=paid_day30,
        ))
    return RetentionCohortResponse(cohorts=rows)


# ---------------------------------------------------------------------------
# 18.11 Market Breakdown
# ---------------------------------------------------------------------------

@router.get("/market-breakdown", response_model=MarketBreakdownResponse)
async def market_breakdown(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    country: str | None = Query(default=None),
    _: dict = Depends(require_admin_user),
) -> MarketBreakdownResponse:
    default_map = {"Ghana": "GH", "Germany": "DE", "India": "IN"}
    markets = ["Ghana", "Germany", "India"]
    if country:
        from .utils.country import COUNTRY_NAME_TO_CODE, CODE_TO_COUNTRY_NAME
        norm_country = country.strip()
        if len(norm_country) == 2:
            norm_name = CODE_TO_COUNTRY_NAME.get(norm_country.upper(), norm_country.upper())
        else:
            norm_name = norm_country.title()
        if norm_name and norm_name not in markets:
            markets.append(norm_name)

    out: list[MarketBreakdownRow] = []
    start, end, _, _ = parse_time_range(preset, from_date, to_date)
    rng_q = {"created_at": {"$gte": start, "$lte": end}}
    shares_rng = {"$and": [rng_q, {"shared_to_whatsapp": True}]}
    for market_name in markets:
        if market_name in default_map:
            market_code = default_map[market_name]
            regex_str = {"Ghana": "ghana", "Germany": "germany|german", "India": "india|indian"}[market_name]
            m_filter = {"$or": [{"country_code": market_code}, {"country_code": {"$exists": False}, "country": {"$regex": regex_str, "$options": "i"}}]}
        else:
            from .utils.country import COUNTRY_NAME_TO_CODE
            market_code = COUNTRY_NAME_TO_CODE.get(market_name, market_name[:2].upper())
            m_filter = {"$or": [{"country_code": market_code}, {"country_code": {"$exists": False}, "country": {"$regex": f"^{market_name}$", "$options": "i"}}]}

        activity_market = await _market_user_filter(market_name.lower())
        active = len(await _active_user_ids(start, end, market_name.lower()))
        new_users = await _safe_count(users_collection, {"$and": [m_filter, rng_q]})
        converted = await _safe_count(users_collection, {"$and": [m_filter, {"trial_outcome": "converted_gold"}, {"trial_outcome_at": {"$gte": start, "$lte": end}}]})
        trial_conversion = safe_ratio(converted, max(new_users, 1))
        revenue_local = 0.0
        if payment_events_collection is not None:
            try:
                pipeline = [
                    {"$match": {"$and": [rng_q, {"status": "success"}, {"market": market_code}]}},
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
                ]
                rows = await payment_events_collection.aggregate(pipeline).to_list(length=1)
                if rows:
                    revenue_local = round(float(rows[0].get("total") or 0), 2)
            except Exception:
                pass
        shares = await _safe_count(
            completion_cards_collection,
            _and(shares_rng, activity_market),
        )
        viral = 0.0
        if invites_collection is not None:
            try:
                accepted = await _safe_count(
                    invites_collection,
                    _and(rng_q, activity_market, {"accepted": True}),
                )
                viral = round(viral_coefficient(accepted, new_users), 2)
            except Exception:
                pass
        out.append(MarketBreakdownRow(
            name=market_name,
            activeUsers=active,
            newUsersThisWeek=new_users,
            trialConversionRate=round(trial_conversion, 1),
            revenueLocal=revenue_local,
            whatsappShares=shares,
            day7RetentionPct=await _latest_market_day7_retention(market_name.lower(), end),
            viralCoefficient=viral,
        ))
    return MarketBreakdownResponse(markets=out)
