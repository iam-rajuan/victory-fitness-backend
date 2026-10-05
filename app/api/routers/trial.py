from fastapi import APIRouter

from ...core.legacy import *
from ...database import beta_feedback_collection
from ...models import BetaFeedbackCreateRequest, BetaFeedbackResponse

router = APIRouter()

_BETA_FEEDBACK_THEMES = {
    "nutrition_logging",
    "coach_context",
    "video_playback",
    "workout_plan",
    "gold_value",
    "other",
}


def _normalize_beta_feedback_theme(value: object) -> str:
    theme = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return theme if theme in _BETA_FEEDBACK_THEMES else "other"


async def _resolve_me_payload(record: dict) -> dict:
    payload = _serialize_me_record(record)
    while inspect.isawaitable(payload):
        payload = await payload
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="Unable to serialize user profile")
    return payload

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

@router.post("/me/trial/phase-one-beta/start", response_model=MeResponse)
async def start_me_phase_one_beta(user: dict = Depends(_require_access_user)) -> MeResponse:
    if not _is_phase_one_beta_enabled():
        raise HTTPException(status_code=403, detail="The 21-day Phase 1 beta is not enabled")

    if _is_phase_one_beta_user(user):
        return MeResponse(**(await _resolve_me_payload(user)))

    await _claim_phase_one_beta_slot(str(user["_id"]))
    updated_user = await _activate_phase_one_beta_subscription(user)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    await notify_user(
        users_collection,
        updated_user,
        "21-Day Gold Beta activated",
        f"Hi {updated_user.get('name') or 'there'}, your 21-day Gold beta access is now active. Open your profile and start using your Gold features.",
        "phase_one_beta_started",
        {"route": "/profile", "trialDay": 0, "tier": "gold", "trialType": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE},
    )
    await _record_analytics_event(
        "phase_one_beta_started",
        user_id=str(user["_id"]),
        market=str(updated_user.get("country_code") or user.get("country_code") or "") or None,
    )
    return MeResponse(**(await _resolve_me_payload(updated_user)))


@router.post("/me/beta-feedback", response_model=BetaFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_me_beta_feedback(
    payload: BetaFeedbackCreateRequest,
    user: dict = Depends(_require_access_user),
) -> BetaFeedbackResponse:
    now = datetime.now(timezone.utc)
    theme = _normalize_beta_feedback_theme(payload.theme)
    message = payload.message.strip()
    if len(message) < 4:
        raise HTTPException(status_code=422, detail="Feedback message is too short")

    document = {
        "_id": ObjectId(),
        "user_id": str(user.get("_id") or ""),
        "user_name": str(user.get("name") or "").strip(),
        "user_email": str(user.get("email") or "").strip(),
        "country": str(user.get("country") or "").strip(),
        "country_code": str(user.get("country_code") or "").strip().upper(),
        "subscription_tier": str(user.get("subscription_tier") or "").strip(),
        "subscription_purchase_source": str(user.get("subscription_purchase_source") or "").strip(),
        "trial_type": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE if _is_phase_one_beta_user(user) else "",
        "rating": int(payload.rating),
        "theme": theme,
        "message": message,
        "would_pay": payload.would_pay,
        "status": "OPEN",
        "created_at": now,
        "updated_at": now,
    }
    await beta_feedback_collection.insert_one(document)
    await _record_analytics_event(
        "beta_feedback_submitted",
        user_id=str(user.get("_id") or ""),
        market=document["country_code"] or None,
        details={"rating": document["rating"], "theme": theme, "would_pay": payload.would_pay},
    )
    return BetaFeedbackResponse(
        id=str(document["_id"]),
        rating=document["rating"],
        theme=theme,
        message=message,
        wouldPay=payload.would_pay,
        status=document["status"],
        createdAt=now,
    )

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
