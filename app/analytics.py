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
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from .database import (
    accountability_pairs_collection,
    analytics_events_collection,
    challenges_collection,
    challenge_memberships_collection,
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
    ChallengeStatsResponse,
    CommunitySharingResponse,
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
    sort: list[tuple[str, int]] | None = None,
    limit: int | None = None,
):
    if coll is None:
        return []
    try:
        cursor = coll.find(query or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
    except Exception:
        return []


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
    total = await _safe_count(users_collection)
    new_users = await _safe_count(users_collection, {"$and": [m_filter, rng]})
    prev_new_users = await _safe_count(users_collection, {"$and": [m_filter, prev_rng]})

    # Active users: users with challenge membership in range OR workout log in range
    active_user_ids = set()
    memberships = await _safe_find(
        challenge_memberships_collection,
        rng,
        projection={"user_id": 1},
    )
    for m in memberships:
        uid = m.get("user_id")
        if uid:
            active_user_ids.add(str(uid))
    workout_logs = await _safe_find(
        workout_logs_collection,
        rng,
        projection={"user_id": 1},
    )
    for w in workout_logs:
        uid = w.get("user_id")
        if uid:
            active_user_ids.add(str(uid))

    prev_memberships = await _safe_find(
        challenge_memberships_collection,
        prev_rng,
        projection={"user_id": 1},
    )
    prev_active = set()
    for m in prev_memberships:
        uid = m.get("user_id")
        if uid:
            prev_active.add(str(uid))
    prev_workouts = await _safe_find(
        workout_logs_collection,
        prev_rng,
        projection={"user_id": 1},
    )
    for w in prev_workouts:
        uid = w.get("user_id")
        if uid:
            prev_active.add(str(uid))

    # Trial conversion: estimate as completed trial users / total trial users
    completed_trial_q = {"$and": [m_filter, {"subscription_tier": {"$ne": "NONE"}}, rng]}
    completed_trial = await _safe_count(users_collection, completed_trial_q)
    started_trial_q = {"$and": [m_filter, rng]}
    started_trial = await _safe_count(users_collection, started_trial_q)
    conversion = safe_ratio(completed_trial, max(started_trial, 1))

    # Churned users (subscription tier NONE within range OR has cancellation flag)
    churned = await _safe_count(
        users_collection,
        {"$and": [m_filter, {"subscription_tier": "NONE"}, {"created_at": {"$lt": start}}, rng]},
    )
    prev_churned = await _safe_count(
        users_collection,
        {"$and": [m_filter, {"subscription_tier": "NONE"}, {"created_at": {"$lt": prev_start}}, prev_rng]},
    )

    # Users by tier
    tier_counts: Counter[str] = Counter()
    all_users = await _safe_find(users_collection, m_filter or {}, projection={"subscription_tier": 1})
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
        rng,
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
        name = uid[:8]
        top_users.append(TopUserItem(rank=idx, userId=uid, name=name, points=points))

    return UserStatsResponse(
        totalRegistered=total,
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
    rng, prev_rng, _, start, end, prev_start, prev_end = _common_filter(
        preset, from_date, to_date, market, "started_at"
    )
    completed_q = {"$and": [rng, {"completed_at": {"$ne": None}}]}
    completed = await _safe_count(workout_logs_collection, completed_q)
    prev_completed = await _safe_count(workout_logs_collection, {"$and": [prev_rng, {"completed_at": {"$ne": None}}]})
    started = await _safe_count(workout_logs_collection, rng)
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
            w = await workouts_collection.find_one({"_id": top_wid}) if workouts_collection else None
            if w:
                title = str(w.get("title") or top_wid)
        except Exception:
            pass
        durs = duration_by_workout.get(top_wid, [])
        avg = sum(durs) // len(durs) if durs else 0
        top_workout = TopWorkoutItem(workoutId=top_wid, title=title, count=top_count, avgDurationSeconds=avg)

    ai_generated = await _safe_count(workouts_collection, {"source": "ai"})

    # WhatsApp shares
    shares_q = {"$and": [rng, {"shared_to_whatsapp": True}]}
    shares = await _safe_count(completion_cards_collection, shares_q)
    prev_shares = await _safe_count(completion_cards_collection, {"$and": [prev_rng, {"shared_to_whatsapp": True}]})

    return WorkoutStatsResponse(
        totalCompleted=completed,
        totalCompletedChangePct=round(pct_change(completed, prev_completed), 1),
        completionRate=round(rate, 1),
        completionRateColor=color_band(rate, 70.0, 50.0),
        topWorkout=top_workout,
        aiGeneratedWorkouts=ai_generated,
        whatsappShares=shares,
        whatsappSharesChangePct=round(pct_change(shares, prev_shares), 1),
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
    rng, prev_rng, _, *_ = _common_filter(preset, from_date, to_date, market, "joined_at")
    m_filter = market_filter(market)

    # Most popular challenge in range (by member count)
    pipeline = []
    if challenge_memberships_collection is not None:
        try:
            pipeline = [
                {"$match": {"$and": [rng, m_filter]}},
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
                {"$and": [rng, {"challenge_id": challenge_id}, {"status": "completed"}]}
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

    invites_sent = await _safe_count(invites_collection, rng)
    prev_invites_sent = await _safe_count(invites_collection, prev_rng)
    accepted = await _safe_count(invites_collection, {"$and": [rng, {"accepted": True}]})
    invite_conversion = safe_ratio(accepted, max(invites_sent, 1))

    # A/B variant test
    variant_counts: Counter[str] = Counter()
    variant_accepted: Counter[str] = Counter()
    rows = await _safe_find(invites_collection, rng, projection={"copy_variant": 1, "accepted": 1})
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
    ai_plans = await _safe_count(
        nutrition_plan_jobs_collection,
        {"$and": [rng, {"job_type": "meal_plan"}, {"status": "completed"}]},
    )
    prev_ai_plans = await _safe_count(
        nutrition_plan_jobs_collection,
        {"$and": [prev_rng, {"job_type": "meal_plan"}, {"status": "completed"}]},
    )
    protein_q = {"$and": [rng, {"protein_target_hit": True}]}
    protein_hit = await _safe_count(meal_analysis_entries_collection, protein_q)
    total_entries = await _safe_count(meal_analysis_entries_collection, rng)
    protein_rate = safe_ratio(protein_hit, max(total_entries, 1))

    # Most logged food by market — group meal entries by market via user.country_code
    most_logged: dict[str, MarketFoodItem | None] = {"Ghana": None, "Germany": None, "India": None}
    if meal_analysis_entries_collection is not None and users_collection is not None:
        try:
            pipeline = [
                {"$match": rng},
                {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}},
                {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": False}},
                {
                    "$group": {
                        "_id": {
                            "market": "$user.country_code",
                            "food_id": "$food_id",
                            "food_name": "$food_name",
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
    _: dict = Depends(require_admin_user),
) -> RevenueStatsResponse:
    rng, prev_rng, _, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    payments = await _safe_find(
        payment_events_collection,
        {"$and": [rng, {"status": "success"}, {"type": "subscription_renewed"}]},
        projection={"amount": 1, "currency": 1, "tier": 1, "market": 1, "created_at": 1},
        limit=5000,
    )
    by_country: dict[str, float] = defaultdict(float)
    by_tier: dict[str, float] = defaultdict(float)
    daily: dict[str, float] = defaultdict(float)
    total_revenue = 0.0
    for p in payments:
        amount = float(p.get("amount") or 0)
        currency = str(p.get("currency") or "EUR")
        market_code = str(p.get("market") or "OTHER")
        tier = str(p.get("tier") or "NONE")
        by_country[market_code] += amount
        by_tier[tier] += amount
        ts = p.get("created_at")
        if isinstance(ts, datetime):
            daily[ts.strftime("%Y-%m-%d")] += amount
        total_revenue += amount
    mrr = build_currency_breakdown(by_country)
    active_subs = max(await _safe_count(users_collection, {"subscription_status": "active"}), 1)
    arpu = round(total_revenue / active_subs, 2) if active_subs else 0.0

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
    granularity = "daily" if preset in ("today", "this_week", "custom") else "monthly"

    return RevenueStatsResponse(
        mrr=mrr,
        revenueByTier=revenue_by_tier,
        revenueByMarket=revenue_by_market,
        arpu=arpu,
        mrrTrend=trend,
        trendGranularity=granularity,
    )


# ---------------------------------------------------------------------------
# 18.7 Community & Sharing
# ---------------------------------------------------------------------------

@router.get("/community-sharing", response_model=CommunitySharingResponse)
async def community_sharing_stats(
    preset: str = Query("this_week"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    market: str = Query("all"),
    _: dict = Depends(require_admin_user),
) -> CommunitySharingResponse:
    rng, prev_rng, _, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    shares = await _safe_count(completion_cards_collection, {"$and": [rng, {"shared_to_whatsapp": True}]})
    prev_shares = await _safe_count(completion_cards_collection, {"$and": [prev_rng, {"shared_to_whatsapp": True}]})

    # Viral coefficient: new users via invite / total new users
    invites_q = {"$and": [rng, {"accepted": True}]}
    invite_accepts = await _safe_count(invites_collection, invites_q)
    new_users = await _safe_count(users_collection, rng)
    viral = round(safe_ratio(invite_accepts * 10, max(new_users, 1)), 2)

    pairs = await _safe_count(accountability_pairs_collection, {"$and": [rng, {"status": "active"}]})
    prev_pairs = await _safe_count(accountability_pairs_collection, {"$and": [prev_rng, {"status": "active"}]})

    return CommunitySharingResponse(
        whatsappShareCount=shares,
        whatsappShareChangePct=round(pct_change(shares, prev_shares), 1),
        viralCoefficient=viral,
        viralCoefficientColor=color_band(viral, 1.0, 0.5),
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
    base = {"$and": [m_filter, {"subscription_tier": {"$in": ["GOLD", "PLATINUM", "INNER_CIRCLE"]}}]}
    eligible = await _safe_count(users_collection, base) or 1

    identity_q = {"$and": [base, {"identity_statement": {"$ne": None}}]}
    unlock_q = {"$and": [base, {"workout_unlock_label": {"$ne": None}}]}
    trigger_q = {"$and": [base, {"training_trigger_context": {"$ne": None}}]}

    identity_set = await _safe_count(users_collection, identity_q)
    unlock_set = await _safe_count(users_collection, unlock_q)
    trigger_set = await _safe_count(users_collection, trigger_q)

    # Retention comparison: Gold users with habit vs without
    habit_users = await _safe_count(
        users_collection,
        {"$and": [base, {"$or": [identity_q["$and"][1], unlock_q["$and"][1], trigger_q["$and"][1]]}]},
    )
    non_habit_users = max(eligible - 1 - habit_users, 1)

    habit_retained_q = {"$and": [base, {"recent_activity": True}, {"$or": [identity_q["$and"][1], unlock_q["$and"][1], trigger_q["$and"][1]]}]}
    non_habit_retained_q = {"$and": [base, {"recent_activity": True}, {"$or": [{"identity_statement": None}, {"workout_unlock_label": None}, {"training_trigger_context": None}]}]}
    habit_retained = await _safe_count(users_collection, habit_retained_q)
    non_habit_retained = await _safe_count(users_collection, non_habit_retained_q)

    return HabitAdoptionResponse(
        identityStatementSet=identity_set,
        identityStatementPct=round(safe_ratio(identity_set, eligible), 1),
        workoutUnlockSet=unlock_set,
        workoutUnlockPct=round(safe_ratio(unlock_set, eligible), 1),
        ifThenTriggerSet=trigger_set,
        ifThenTriggerPct=round(safe_ratio(trigger_set, eligible), 1),
        retentionComparison=RetentionComparison(
            habitRetainedPct=round(safe_ratio(habit_retained, max(habit_users, 1)), 1),
            nonHabitRetainedPct=round(safe_ratio(non_habit_retained, non_habit_users), 1),
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
    m_filter = market_filter(market)

    started = await _safe_count(users_collection, {"$and": [m_filter, rng]})
    opened_msg = await _safe_count(analytics_events_collection, {"$and": [m_filter, rng, {"event_type": "day1_message_opened"}]})
    used_coach = await _safe_count(analytics_events_collection, {"$and": [m_filter, rng, {"event_type": "ai_coach_used"}]})
    used_nutrition = await _safe_count(nutrition_plan_jobs_collection, {"$and": [m_filter, rng]})
    warmup = await _safe_count(analytics_events_collection, {"$and": [m_filter, rng, {"event_type": "day4_warmup_seen"}]})
    converted = await _safe_count(users_collection, {"$and": [m_filter, rng, {"subscription_tier": {"$ne": "NONE"}}]})

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
            drop_pct = round(((prev_count - count) / prev_count) * 100, 1)
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
    from datetime import timedelta
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    weekly_points = []
    sparkline: list[SparklinePoint] = []
    for week_offset in range(12):
        week_end = end - timedelta(weeks=week_offset)
        week_start = week_end - timedelta(weeks=1)
        invites_q = {"created_at": {"$gte": week_start, "$lte": week_end}, "accepted": True}
        new_q = {"created_at": {"$gte": week_start, "$lte": week_end}}
        accepted = await _safe_count(invites_collection, invites_q)
        new_users = await _safe_count(users_collection, new_q)
        ratio = safe_ratio(accepted * 10, max(new_users, 1))
        weekly_points.append(SparklinePoint(date=week_start.strftime("%Y-%m-%d"), value=round(ratio, 2)))
    weekly_points.reverse()
    sparkline = weekly_points

    invites_q = {"created_at": {"$gte": start, "$lte": end}, "accepted": True}
    accepted = await _safe_count(invites_collection, invites_q)
    new_users = await _safe_count(users_collection, {"created_at": {"$gte": start, "$lte": end}})
    current = round(safe_ratio(accepted * 10, max(new_users, 1)), 2)
    sublabel = f"For every 10 new users, {int(current * 10)} came from an invite"

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
    rng, prev_rng, _, start, end, *_ = _common_filter(preset, from_date, to_date, market, "created_at")
    today_start = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    today_count = await _safe_count(completion_cards_collection, {"$and": [rng, {"shared_to_whatsapp": True}]})
    week_count = today_count
    prev_week = await _safe_count(completion_cards_collection, {"$and": [prev_rng, {"shared_to_whatsapp": True}]})

    # 30-day daily series
    daily_series: list[SparklinePoint] = []
    for day_offset in range(29, -1, -1):
        day = end - __import__("datetime").timedelta(days=day_offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + __import__("datetime").timedelta(days=1)
        c = await _safe_count(
            completion_cards_collection,
            {"created_at": {"$gte": day_start, "$lt": day_end}, "shared_to_whatsapp": True},
        )
        daily_series.append(SparklinePoint(date=day_start.strftime("%Y-%m-%d"), value=float(c)))

    # Market split (look up user.country_code for each card via lookup)
    market_split = MarketShareSplit()
    if completion_cards_collection is not None and users_collection is not None:
        try:
            pipeline = [
                {"$match": {"$and": [rng, {"shared_to_whatsapp": True}]}},
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
                ))
        except Exception:
            pass

    if accountability_pairs_collection is not None:
        try:
            n = await accountability_pairs_collection.count_documents(rng)
            if n:
                events.append(DailyWinEvent(type="pair_created", label=f"{n} new accountability pair{'s' if n != 1 else ''}", count=n))
        except Exception:
            pass

    if challenge_memberships_collection is not None:
        try:
            n = await challenge_memberships_collection.count_documents({"$and": [rng, {"status": "completed"}]})
            if n:
                events.append(DailyWinEvent(type="challenge_completed", label=f"{n} challenge{'s' if n != 1 else ''} completed", count=n))
        except Exception:
            pass

    new_subs = await _safe_count(payment_events_collection, {"$and": [rng, {"type": "subscription_started"}]})
    if new_subs:
        events.append(DailyWinEvent(type="new_subscriber", label=f"{new_subs} new Gold subscriber{'s' if new_subs != 1 else ''}", count=new_subs))

    streaks = await _safe_count(analytics_events_collection, {"$and": [rng, {"event_type": "streak_7_day"}]})
    if streaks:
        events.append(DailyWinEvent(type="streak", label=f"{streaks} 7-day streak{'s' if streaks != 1 else ''} achieved", count=streaks))

    return DailyWinsFeedResponse(events=events[:10], lastUpdated=end)


# ---------------------------------------------------------------------------
# 18.10 Retention Cohort
# ---------------------------------------------------------------------------

@router.get("/retention-cohort", response_model=RetentionCohortResponse)
async def retention_cohort(
    _: dict = Depends(require_admin_user),
) -> RetentionCohortResponse:
    rows: list[RetentionCohortRow] = []
    end = datetime.now(timezone.utc)
    # Last 8 weekly cohorts
    for week_offset in range(7, -1, -1):
        week_end = end - __import__("datetime").timedelta(weeks=week_offset)
        week_start = week_end - __import__("datetime").timedelta(days=7)
        new_users = await _safe_count(users_collection, {"created_at": {"$gte": week_start, "$lt": week_end}})
        if new_users == 0:
            continue
        # Day-7 retention: users with activity in the week after their cohort start
        d7_start = week_start
        d7_end = week_start + __import__("datetime").timedelta(days=7)
        d14_start = week_start
        d14_end = week_start + __import__("datetime").timedelta(days=14)
        d30_start = week_start
        d30_end = week_start + __import__("datetime").timedelta(days=30)
        d7 = await _safe_count(workout_logs_collection, {"started_at": {"$gte": d7_start, "$lt": d7_end}})
        d14 = await _safe_count(workout_logs_collection, {"started_at": {"$gte": d14_start, "$lt": d14_end}})
        d30 = await _safe_count(workout_logs_collection, {"started_at": {"$gte": d30_start, "$lt": d30_end}})
        paid = await _safe_count(users_collection, {"$and": [{"created_at": {"$gte": week_start, "$lt": week_end}}, {"subscription_tier": {"$ne": "NONE"}}]})
        rows.append(RetentionCohortRow(
            weekStart=week_start.strftime("%Y-%m-%d"),
            newUsers=new_users,
            day7Pct=round(safe_ratio(d7, max(new_users, 1)), 1),
            day14Pct=round(safe_ratio(d14, max(new_users, 1)), 1),
            day30Pct=round(safe_ratio(d30, max(new_users, 1)), 1),
            paidDay30Pct=round(safe_ratio(paid, max(new_users, 1)), 1),
        ))
    return RetentionCohortResponse(cohorts=rows)


# ---------------------------------------------------------------------------
# 18.11 Market Breakdown
# ---------------------------------------------------------------------------

@router.get("/market-breakdown", response_model=MarketBreakdownResponse)
async def market_breakdown(
    _: dict = Depends(require_admin_user),
) -> MarketBreakdownResponse:
    markets = ["Ghana", "Germany", "India"]
    out: list[MarketBreakdownRow] = []
    rng_q = {"created_at": {"$gte": datetime.now(timezone.utc) - __import__("datetime").timedelta(days=7)}}
    shares_rng = {"$and": [rng_q, {"shared_to_whatsapp": True}]}
    for market_name in markets:
        market_code = {"Ghana": "GH", "Germany": "DE", "India": "IN"}[market_name]
        m_filter = {"$or": [{"country_code": market_code}, {"country_code": {"$exists": False}, "country": {"$regex": {"Ghana": "ghana", "Germany": "germany|german", "India": "india|indian"}[market_name], "$options": "i"}}]}
        active = await _safe_count(users_collection, {"$and": [m_filter, {"recent_activity": True}]})
        new_users = await _safe_count(users_collection, {"$and": [m_filter, rng_q]})
        converted = await _safe_count(users_collection, {"$and": [m_filter, rng_q, {"subscription_tier": {"$ne": "NONE"}}]})
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
        shares = await _safe_count(completion_cards_collection, {"$and": [shares_rng, {"user_id": {"$in": []}}]})
        # Re-query shares via lookup if user collection has country_code
        if completion_cards_collection is not None and users_collection is not None:
            try:
                pipeline = [
                    {"$match": shares_rng},
                    {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}},
                    {"$unwind": "$user"},
                    {"$match": m_filter},
                    {"$count": "total"},
                ]
                rows = await completion_cards_collection.aggregate(pipeline).to_list(length=1)
                if rows:
                    shares = rows[0].get("total", 0)
            except Exception:
                pass
        viral = 0.0
        if invites_collection is not None:
            try:
                accepted = await _safe_count(invites_collection, {"$and": [rng_q, {"accepted": True}, {"market": market_code}]})
                viral = round(safe_ratio(accepted * 10, max(new_users, 1)), 2)
            except Exception:
                pass
        out.append(MarketBreakdownRow(
            name=market_name,
            activeUsers=active,
            newUsersThisWeek=new_users,
            trialConversionRate=round(trial_conversion, 1),
            revenueLocal=revenue_local,
            whatsappShares=shares,
            day7RetentionPct=0.0,
            viralCoefficient=viral,
        ))
    return MarketBreakdownResponse(markets=out)