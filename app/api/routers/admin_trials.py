from fastapi import APIRouter

from ...core.legacy import *
from ...services.beta_analytics import build_phase_one_beta_analytics

router = APIRouter()

@router.get("/admin/trials/config", response_model=GoldTrialConfigResponse)
async def admin_get_gold_trial_config(_: dict = Depends(_require_admin_user)) -> GoldTrialConfigResponse:
    record = await _get_gold_trial_config_record()
    return GoldTrialConfigResponse(**_serialize_gold_trial_config(record))

@router.patch("/admin/trials/config", response_model=GoldTrialConfigResponse)
async def admin_update_gold_trial_config(
    payload: GoldTrialConfigUpdateRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> GoldTrialConfigResponse:
    current = _serialize_gold_trial_config(await _get_gold_trial_config_record())
    next_record = {
        "tierLabel": payload.tierLabel.strip() if payload.tierLabel is not None else current["tierLabel"],
        "messages": [item.model_dump() for item in payload.messages] if payload.messages is not None else current["messages"],
        "trialTierGranted": GOLD_TRIAL_TIER,
        "durationDays": GOLD_TRIAL_DURATION_DAYS,
        "fallbackRule": "skip_to_next_channel_and_notify_admin",
        "updated_at": datetime.now(timezone.utc),
    }
    await app_content_collection.update_one(
        {"key": GOLD_TRIAL_CONFIG_KEY},
        {"$set": next_record, "$setOnInsert": {"key": GOLD_TRIAL_CONFIG_KEY, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    await _record_admin_audit(admin_user, "gold_trial_config_updated", "gold_trial_config", GOLD_TRIAL_CONFIG_KEY)
    updated = await _get_gold_trial_config_record()
    return GoldTrialConfigResponse(**_serialize_gold_trial_config(updated))

@router.get("/admin/trials/outcomes", response_model=GoldTrialOutcomeBreakdownResponse)
async def admin_gold_trial_outcomes(_: dict = Depends(_require_admin_user)) -> GoldTrialOutcomeBreakdownResponse:
    now = datetime.now(timezone.utc)
    users = await users_collection.find(
        {
            "is_admin": {"$ne": True},
            "trial_tier_granted": GOLD_TRIAL_TIER,
            "subscription_purchase_source": {"$ne": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE},
        }
    ).to_list(length=None)
    total = active = converted = downgraded = lapsed = pending = 0
    for user in users:
        total += 1
        summary = _trial_summary(user, now)
        outcome = summary["outcome"]
        if summary["active"]:
            active += 1
        if outcome == "converted_gold":
            converted += 1
        elif outcome == "downgraded_silver":
            downgraded += 1
        elif outcome == "lapsed":
            lapsed += 1
        else:
            pending += 1
    decided = converted + downgraded + lapsed
    return GoldTrialOutcomeBreakdownResponse(
        totalTrials=total,
        activeTrials=active,
        convertedGold=converted,
        downgradedSilver=downgraded,
        lapsed=lapsed,
        pendingDecision=pending,
        conversionRate=round((converted / decided) * 100, 2) if decided else 0,
        downgradeRate=round((downgraded / decided) * 100, 2) if decided else 0,
        lapsedRate=round((lapsed / decided) * 100, 2) if decided else 0,
    )

@router.get("/admin/trials/cohorts", response_model=AdminTrialCohortResponse)
async def admin_trial_cohorts(_: dict = Depends(_require_admin_user)) -> AdminTrialCohortResponse:
    now = datetime.now(timezone.utc)
    users = await users_collection.find({
        "is_admin": {"$ne": True},
        "subscription_purchase_source": {"$ne": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE},
        "$or": [
            {"trial_start_at": {"$ne": None}},
            {"subscription_started_at": {"$ne": None}},
        ],
    }).to_list(length=None)
    grouped: dict[tuple[str, str], dict] = {}
    for user in users:
        started_at = _trial_started_at(user)
        if not started_at:
            continue
        key = (_trial_cohort_key(started_at), str(user.get("signup_source") or "organic").strip() or "organic")
        bucket = grouped.setdefault(key, {"total": 0, "converted": 0, "dropouts": 0, "engaged": {str(day): 0 for day in range(6)}})
        bucket["total"] += 1
        if _trial_user_converted(user):
            bucket["converted"] += 1
        elif now >= started_at + timedelta(days=5):
            bucket["dropouts"] += 1
        engagement_days = (user.get("trial_engagement") or {}).get("days") or []
        for day in engagement_days:
            if str(day) in bucket["engaged"]:
                bucket["engaged"][str(day)] += 1
    cohorts = []
    for (cohort, signup_source), bucket in sorted(grouped.items(), reverse=True):
        total = bucket["total"]
        cohorts.append(AdminTrialCohortItem(
            cohort=cohort,
            signupSource=signup_source,
            totalUsers=total,
            convertedUsers=bucket["converted"],
            dropoutUsers=bucket["dropouts"],
            conversionRate=round((bucket["converted"] / total) * 100, 2) if total else 0,
            engagedUsersByDay=bucket["engaged"],
        ))
    return AdminTrialCohortResponse(cohorts=cohorts)

@router.get("/admin/trials/dropouts", response_model=AdminTrialDropoutResponse)
async def admin_trial_dropouts(
    limit: int = 100,
    _: dict = Depends(_require_admin_user),
) -> AdminTrialDropoutResponse:
    now = datetime.now(timezone.utc)
    records = await users_collection.find({
        "is_admin": {"$ne": True},
        "marketing_consent": True,
        "subscription_purchase_source": {"$ne": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE},
        "$or": [
            {"trial_start_at": {"$ne": None}},
            {"subscription_started_at": {"$ne": None}},
        ],
    }, sort=[("trial_start_at", -1)]).to_list(length=min(max(limit, 1), 500))
    dropouts = []
    for user in records:
        started_at = _trial_started_at(user)
        if not started_at or _trial_user_converted(user) or now < started_at + timedelta(days=5):
            continue
        engagement = user.get("trial_engagement") or {}
        engagement_days = [int(day) for day in (engagement.get("days") or []) if str(day).isdigit()]
        dropouts.append(AdminTrialDropoutItem(
            id=str(user["_id"]),
            fullName=str(user.get("name") or "Unknown"),
            email=str(user.get("email") or ""),
            signupSource=str(user.get("signup_source") or "organic"),
            cohort=_trial_cohort_key(started_at),
            trialStartedAt=started_at,
            marketingConsent=True,
            lastEngagedDay=max(engagement_days) if engagement_days else None,
            coachMessages=max(int(engagement.get("coach_messages") or 0), 0),
            nutritionPlanCreated=bool(engagement.get("nutrition_plan_created_at")),
            campaignDaysSent=sorted({int(day) for day in (user.get("trial_campaign_sent_days") or []) if str(day).isdigit()}),
        ))
    return AdminTrialDropoutResponse(total=len(dropouts), users=dropouts)


@router.get("/admin/trials/phase-one-beta", response_model=PhaseOneBetaSummaryResponse)
async def admin_phase_one_beta_summary(
    limit: int = 300,
    _: dict = Depends(_require_admin_user),
) -> PhaseOneBetaSummaryResponse:
    return await build_phase_one_beta_analytics(limit=limit)
