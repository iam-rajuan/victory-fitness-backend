from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/me/trial/status", response_model=GoldTrialSummaryResponse)
async def get_me_gold_trial_status(user: dict = Depends(_require_access_user)) -> GoldTrialSummaryResponse:
    return GoldTrialSummaryResponse(**_trial_summary(user))

@router.post("/me/trial/gold/start", response_model=GoldTrialStartResponse)
async def start_me_gold_trial(user: dict = Depends(_require_access_user)) -> GoldTrialStartResponse:
    if _is_phase_one_beta_enabled():
        raise HTTPException(
            status_code=403,
            detail="The commercial 5-day Gold trial is disabled during the Phase 1 beta campaign",
        )
    tier = _normalize_subscription_tier(user.get("subscription_tier"))
    if tier != "NONE":
        raise HTTPException(status_code=409, detail="Users who already selected a tier are not eligible for the undecided Gold trial")
    existing_started = _trial_started_at(user)
    if existing_started:
        return GoldTrialStartResponse(trial=GoldTrialSummaryResponse(**_trial_summary(user)))

    now = datetime.now(timezone.utc)
    end_at = now + timedelta(days=GOLD_TRIAL_DURATION_DAYS)
    update_doc = {
        "trial_tier_granted": GOLD_TRIAL_TIER,
        "trial_start_at": now,
        "trial_end_at": end_at,
        "trial_outcome": None,
        "trial_outcome_at": None,
        "trial_campaign_sent_days": [0],
        "trial_engagement": {"days": [0], "coach_messages": 0},
        "updated_at": now,
    }
    await users_collection.update_one({"_id": user["_id"]}, {"$set": update_doc})
    updated_user = await users_collection.find_one({"_id": user["_id"]})
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    await notify_user(
        users_collection,
        updated_user,
        "Welcome to Victory Gold",
        f"Hi {updated_user.get('name') or 'there'}, your Gold trial is active. Ask Coach Victor one question right now to get your first win.",
        "trial_day_0",
        {"route": "/ai-coach", "trialDay": 0, "tier": "gold"},
    )
    await _record_analytics_event("gold_trial_started", user_id=str(user["_id"]), market=str(user.get("country_code") or "") or None)
    return GoldTrialStartResponse(trial=GoldTrialSummaryResponse(**_trial_summary(updated_user)))

@router.get("/me/trial/decision", response_model=GoldTrialDecisionResponse)
async def get_me_gold_trial_decision(user: dict = Depends(_require_access_user)) -> GoldTrialDecisionResponse:
    trial = GoldTrialSummaryResponse(**_trial_summary(user))
    if not trial.start_at:
        raise HTTPException(status_code=404, detail="Gold trial has not started")
    return GoldTrialDecisionResponse(
        trial=trial,
        usage=trial.usage,
        options=await _gold_trial_decision_options(user),
    )
