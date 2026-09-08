from datetime import datetime, timedelta, timezone
from typing import Any
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core.legacy import (
    users_collection,
    dependency_require_access_user,
    _record_analytics_event,
    _resolve_subscription_access,
    _resolve_subscription_checkout_plan,
    _subscription_has_active_access_window,
)
from ...services.stripe_payments import (
    cancel_stripe_subscription_at_period_end,
    change_stripe_subscription_plan,
    pause_stripe_subscription_collection,
    resume_stripe_subscription_collection,
)

router = APIRouter()


class SubscriptionCancelResponse(BaseModel):
    success: bool = True
    status: str = "CANCELLED"
    tier: str
    cancelled_at: str
    period_end: str
    current_period_end: str
    message: str


class SubscriptionPauseRequest(BaseModel):
    pause_days: int = Field(default=30, ge=14, le=60)


class SubscriptionPauseResponse(BaseModel):
    success: bool = True
    status: str = "PAUSED"
    paused_at: str
    paused_until: str
    message: str


class SubscriptionChangePlanRequest(BaseModel):
    tier: str | None = None  # "SILVER", "GOLD", "PLATINUM"
    plan_id: str | None = None
    billing_cycle: str = "yearly"  # "monthly", "yearly"


class SubscriptionDetailResponse(BaseModel):
    tier: str
    role: str
    status: str  # "ACTIVE", "PAUSED", "CANCELLED", "TRIAL", "NONE"
    billing_cycle: str
    started_at: str | None = None
    expires_at: str | None = None
    period_end: str | None = None
    current_period_end: str | None = None
    cancelled_at: str | None = None
    paused_until: str | None = None
    is_purchased: bool = False
    can_cancel: bool = True
    can_pause: bool = True
    can_change_plan: bool = True
    subscription: dict[str, Any] = Field(default_factory=dict)
    upgrade_offer: dict[str, Any] | None = None


class ProfileUpgradeOfferResponse(BaseModel):
    eligible: bool
    title: str = ""
    message: str = ""
    current_tier: str = "NONE"
    target_tier: str = "GOLD"
    streak_count: int = 1
    discount_pct: int = 0
    source: str = "profile_upgrade"


def _derive_period_end(user: dict) -> datetime:
    sub = user.get("subscription") or {}
    now = datetime.now(timezone.utc)
    for key in ("subscription_expires_at", "current_period_end", "expires_at"):
        raw = user.get(key) if key.startswith("subscription_") else sub.get(key)
        if raw:
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    if user.get("subscription_confirmed_at"):
        try:
            base = datetime.fromisoformat(str(user["subscription_confirmed_at"]).replace("Z", "+00:00"))
            return base + timedelta(days=365 if user.get("subscription_billing_cycle") == "yearly" else 30)
        except Exception:
            pass
    return now + timedelta(days=30)


@router.get("/me/subscription", response_model=SubscriptionDetailResponse)
async def get_my_subscription(
    user: dict = Depends(dependency_require_access_user),
) -> SubscriptionDetailResponse:
    sub = user.get("subscription") or {}
    tier = str(user.get("subscription_tier") or sub.get("tier") or "NONE").upper()
    role = str(user.get("subscription_role") or sub.get("role") or tier).upper()
    status_val = str(user.get("subscription_status") or sub.get("status") or ("ACTIVE" if tier != "NONE" else "NONE")).upper()
    cycle = str(user.get("subscription_billing_cycle") or sub.get("billing_cycle") or "yearly")
    period_end = _derive_period_end(user)
    workouts_completed = int(user.get("workouts_completed") or user.get("streak_days") or 1)

    sub_dict = {
        "tier": tier,
        "status": status_val,
        "plan_id": tier.lower(),
        "plan_title": f"{tier.title()} Membership",
        "billing_cycle": cycle,
        "price": 19.99 if cycle == "monthly" else 149.99,
        "currency": "USD",
        "current_period_end": period_end.isoformat(),
        "is_cancelled": (status_val == "CANCELLED"),
        "paused_until": str(user.get("subscription_paused_until") or "") or None,
        "has_active_access": _subscription_has_active_access_window(user) or status_val == "TRIAL",
    }

    upgrade_offer = {
        "offer_id": "post_workout_streak",
        "title": "Keep this streak moving",
        "message": f"You just finished workout #{max(workouts_completed, 1)}. Unlock unlimited AI coaching to keep this going.",
        "target_tier": "GOLD" if tier in {"NONE", "SILVER"} else "PLATINUM",
    }

    return SubscriptionDetailResponse(
        tier=tier,
        role=role,
        status=status_val,
        billing_cycle=cycle,
        started_at=str(user.get("subscription_started_at") or sub.get("started_at") or ""),
        expires_at=period_end.isoformat(),
        period_end=period_end.isoformat(),
        current_period_end=period_end.isoformat(),
        cancelled_at=str(user.get("subscription_cancelled_at") or "") or None,
        paused_until=str(user.get("subscription_paused_until") or "") or None,
        is_purchased=bool(user.get("subscription_is_purchased") or sub.get("is_purchased")),
        can_cancel=(status_val == "ACTIVE" and tier != "NONE"),
        can_pause=(status_val == "ACTIVE" and tier != "NONE"),
        can_change_plan=(tier != "NONE"),
        subscription=sub_dict,
        upgrade_offer=upgrade_offer,
    )


@router.post("/me/subscription/cancel", response_model=SubscriptionCancelResponse)
async def cancel_my_subscription(
    user: dict = Depends(dependency_require_access_user),
) -> SubscriptionCancelResponse:
    """Cancels user subscription. Subscription stays active until period_end."""
    user_id = str(user.get("_id") or user.get("id") or "")
    now = datetime.now(timezone.utc)
    period_end = _derive_period_end(user)
    tier = str(user.get("subscription_tier") or "GOLD").upper()

    await cancel_stripe_subscription_at_period_end(user)

    update_fields = {
        "subscription_status": "CANCELLED",
        "subscription_cancelled_at": now.isoformat(),
        "subscription_expires_at": period_end.isoformat(),
        "subscription.status": "CANCELLED",
        "subscription.cancelled_at": now.isoformat(),
        "updated_at": now,
    }

    await users_collection.update_one(
        {"_id": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id},
        {"$set": update_fields},
    )

    formatted_date = period_end.strftime("%B %d, %Y")
    await _record_analytics_event("subscription_cancelled", user_id=user_id, details={"tier": tier, "period_end": period_end.isoformat()})

    return SubscriptionCancelResponse(
        success=True,
        status="CANCELLED",
        tier=tier,
        cancelled_at=now.isoformat(),
        period_end=period_end.isoformat(),
        current_period_end=period_end.isoformat(),
        message=f"Subscription cancelled. Your {tier} benefits will stay fully active until {formatted_date}.",
    )


@router.post("/me/subscription/pause", response_model=SubscriptionPauseResponse)
async def pause_my_subscription(
    payload: SubscriptionPauseRequest,
    user: dict = Depends(dependency_require_access_user),
) -> SubscriptionPauseResponse:
    """Pauses subscription for specified number of days."""
    user_id = str(user.get("_id") or user.get("id") or "")
    now = datetime.now(timezone.utc)
    resume_date = now + timedelta(days=payload.pause_days)

    await pause_stripe_subscription_collection(user, resume_date)

    update_fields = {
        "subscription_status": "PAUSED",
        "subscription_paused_at": now.isoformat(),
        "subscription_paused_until": resume_date.isoformat(),
        "subscription.status": "PAUSED",
        "updated_at": now,
    }

    await users_collection.update_one(
        {"_id": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id},
        {"$set": update_fields},
    )

    formatted_date = resume_date.strftime("%B %d, %Y")
    await _record_analytics_event("subscription_paused", user_id=user_id, details={"days": payload.pause_days})

    return SubscriptionPauseResponse(
        success=True,
        status="PAUSED",
        paused_at=now.isoformat(),
        paused_until=resume_date.isoformat(),
        message=f"Subscription paused for {payload.pause_days} days. It will automatically resume on {formatted_date}.",
    )


@router.post("/me/subscription/resume")
async def resume_my_subscription(
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Resumes paused subscription."""
    user_id = str(user.get("_id") or user.get("id") or "")
    now = datetime.now(timezone.utc)

    await resume_stripe_subscription_collection(user)

    await users_collection.update_one(
        {"_id": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id},
        {
            "$set": {
                "subscription_status": "ACTIVE",
                "subscription.status": "ACTIVE",
                "subscription_paused_until": None,
                "updated_at": now,
            }
        },
    )
    return {"success": True, "status": "ACTIVE", "message": "Subscription resumed."}


@router.post("/me/subscription/change-plan")
async def change_subscription_plan(
    payload: SubscriptionChangePlanRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Switches subscription plan tier and billing cycle."""
    user_id = str(user.get("_id") or user.get("id") or "")
    now = datetime.now(timezone.utc)
    raw_tier = payload.tier or payload.plan_id or "GOLD"
    target_tier = raw_tier.strip().upper()
    if target_tier not in {"SILVER", "GOLD", "PLATINUM", "NONE"}:
        raise HTTPException(status_code=400, detail="Invalid tier")
    cycle = (payload.billing_cycle or "yearly").strip().lower()
    if cycle not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="Invalid billing cycle")
    period_days = 365 if cycle == "yearly" else 30
    new_period_end = now + timedelta(days=period_days)
    checkout_plan = await _resolve_subscription_checkout_plan(target_tier, cycle, payload.plan_id)
    feature_access = checkout_plan["feature_access"] if checkout_plan else _resolve_subscription_access(target_tier)
    if checkout_plan and checkout_plan.get("price") is not None:
        await change_stripe_subscription_plan(
            user,
            title=str(checkout_plan.get("title") or f"Victory {target_tier.title()}"),
            tier=target_tier,
            billing_cycle=cycle,
            plan_id=str(checkout_plan.get("plan_id") or payload.plan_id or target_tier.lower()),
            amount=float(checkout_plan["price"]),
        )

    update_fields = {
        "subscription_tier": target_tier,
        "subscription_role": target_tier,
        "subscription_status": "ACTIVE",
        "subscription_billing_cycle": cycle,
        "subscription_confirmed_at": now.isoformat(),
        "subscription_expires_at": new_period_end.isoformat(),
        "subscription.tier": target_tier,
        "subscription.role": target_tier,
        "subscription.status": "ACTIVE",
        "subscription.billing_cycle": cycle,
        "subscription.access": feature_access,
        "subscription_access": feature_access,
        "updated_at": now,
    }

    await users_collection.update_one(
        {"_id": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id},
        {"$set": update_fields},
    )

    await _record_analytics_event("subscription_plan_changed", user_id=user_id, details={"new_tier": target_tier, "cycle": cycle})
    return {
        "success": True,
        "status": "ACTIVE",
        "tier": target_tier,
        "plan_id": target_tier.lower(),
        "billing_cycle": cycle,
        "period_end": new_period_end.isoformat(),
        "current_period_end": new_period_end.isoformat(),
        "message": f"Successfully updated to {target_tier} plan ({cycle}).",
    }


@router.get("/me/subscription/upgrade-offer", response_model=ProfileUpgradeOfferResponse)
async def get_profile_upgrade_offer(
    user: dict = Depends(dependency_require_access_user),
) -> ProfileUpgradeOfferResponse:
    """Section 17.1: Post-workout upgrade offer also triggerable from Profile upgrade button."""
    user_id = str(user.get("_id") or user.get("id") or "")
    tier = str(user.get("subscription_tier") or "SILVER").upper()
    workouts_completed = int(user.get("workouts_completed") or user.get("streak_days") or 1)
    streak_count = max(workouts_completed, 1)

    eligible = tier in {"NONE", "SILVER", "GOLD"}
    target_tier = "GOLD" if tier in {"NONE", "SILVER"} else "PLATINUM"

    title = "Keep this streak moving"
    message = f"You just finished workout #{streak_count}. Unlock unlimited AI coaching to keep this going."

    if eligible:
        # Reuses: upgrade_screen_viewed analytics event with source: 'profile_upgrade'
        await _record_analytics_event(
            "upgrade_screen_viewed",
            user_id=user_id,
            details={"source": "profile_upgrade", "tier": tier, "streak_count": streak_count},
        )

    return ProfileUpgradeOfferResponse(
        eligible=eligible,
        title=title,
        message=message,
        current_tier=tier,
        target_tier=target_tier,
        streak_count=streak_count,
        discount_pct=20 if streak_count >= 3 else 0,
        source="profile_upgrade",
    )
