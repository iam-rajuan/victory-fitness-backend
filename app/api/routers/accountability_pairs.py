import secrets
from datetime import datetime, timezone
from typing import Any
from bson import ObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ...core.legacy import (
    accountability_pairs_collection,
    users_collection,
    workout_logs_collection,
    dependency_require_access_user,
    _record_analytics_event,
)
from ...models import (
    AccountabilityPairCheckInRequest,
    AccountabilityPairItemResponse,
    AccountabilityPairListResponse,
)
from ...retention_service import _pair_day_key
from ...config import settings

router = APIRouter()


class AccountabilityInviteRequest(BaseModel):
    partner_email: str | None = None


class AccountabilityAcceptRequest(BaseModel):
    invite_code: str | None = None
    pair_id: str | None = None


class AccountabilityPartnerDetailResponse(BaseModel):
    paired: bool
    pair_id: str | None = None
    status: str = "none"  # "none", "pending", "active"
    is_inviter: bool = False
    invite_code: str | None = None
    partner_user_id: str | None = None
    partner_name: str | None = None
    partner_email: str | None = None
    partner_profile_image: str | None = None
    your_checked_in_today: bool = False
    partner_checked_in_today: bool = False  # Green tick if True, grey circle if False
    last_nudged_on: str | None = None
    can_nudge: bool = False
    partner: dict[str, Any] | None = None


@router.post("/accountability-pairs/invite", status_code=status.HTTP_201_CREATED)
async def invite_accountability_partner(
    payload: AccountabilityInviteRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Creates a pending accountability partnership with a shareable 6-character invite code."""
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if accountability_pairs_collection is None:
        return {"status": "noop"}

    # Cancel any previous pending invites created by this user
    await accountability_pairs_collection.delete_many(
        {"inviter_user_id": user_id, "status": "pending"}
    )

    code = secrets.token_hex(3).upper()
    now = datetime.now(timezone.utc)
    partner_email = payload.partner_email.strip().lower() if payload.partner_email else None

    # Check if partner email maps to an existing user
    partner_user = None
    if partner_email:
        partner_user = await users_collection.find_one({"email": partner_email})
        if partner_user and str(partner_user["_id"]) == user_id:
            raise HTTPException(status_code=400, detail="You cannot pair with yourself")

    doc = {
        "inviter_user_id": user_id,
        "invite_code": code,
        "partner_email": partner_email,
        "user_ids": [user_id, str(partner_user["_id"])] if partner_user else [user_id],
        "status": "pending",
        "created_at": now,
        "daily_status": {},
        "last_nudged_on": None,
    }
    insert_res = await accountability_pairs_collection.insert_one(doc)

    if partner_user:
        # Notify the invited partner in-app
        inviter_name = str(user.get("name") or "A friend")
        await users_collection.update_one(
            {"_id": partner_user["_id"]},
            {
                "$push": {
                    "app_notifications": {
                        "id": str(ObjectId()),
                        "type": "accountability_invite",
                        "title": "Accountability Partner Request",
                        "message": f"{inviter_name} invited you to be their Accountability Partner (Code: {code}).",
                        "data": {"pair_id": str(insert_res.inserted_id), "invite_code": code},
                        "created_at": now,
                        "read": False,
                    }
                }
            },
        )

    await _record_analytics_event("accountability_invite_created", user_id=user_id, details={"code": code})
    return {
        "status": "pending",
        "pair_id": str(insert_res.inserted_id),
        "invite_code": code,
        "message": f"Share code {code} with your partner to accept.",
    }


@router.post("/accountability-pairs/accept")
async def accept_accountability_partner(
    payload: AccountabilityAcceptRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Mutual accept: partner enters invite code or accepts pair request to activate partnership."""
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if accountability_pairs_collection is None:
        return {"status": "noop"}

    query: dict[str, Any] = {"status": "pending"}
    if payload.invite_code:
        query["invite_code"] = payload.invite_code.strip().upper()
    elif payload.pair_id and ObjectId.is_valid(payload.pair_id):
        query["_id"] = ObjectId(payload.pair_id)
    else:
        raise HTTPException(status_code=400, detail="Either invite_code or valid pair_id required")

    pair = await accountability_pairs_collection.find_one(query)
    if not pair:
        raise HTTPException(status_code=404, detail="Invalid or expired invite code")

    if pair.get("inviter_user_id") == user_id:
        raise HTTPException(status_code=400, detail="You cannot accept your own invite")

    now = datetime.now(timezone.utc)
    inviter_id = pair["inviter_user_id"]

    await accountability_pairs_collection.update_one(
        {"_id": pair["_id"]},
        {
            "$set": {
                "status": "active",
                "user_ids": [inviter_id, user_id],
                "accepted_at": now,
                "partner_user_id": user_id,
            }
        },
    )

    # Send notification to inviter that partner accepted
    user_name = str(user.get("name") or "Your partner")
    await users_collection.update_one(
        {"_id": ObjectId(inviter_id) if ObjectId.is_valid(inviter_id) else inviter_id},
        {
            "$push": {
                "app_notifications": {
                    "id": str(ObjectId()),
                    "type": "accountability_accepted",
                    "title": "Partner Paired! 🤝",
                    "message": f"{user_name} accepted your invite! You are now accountability partners.",
                    "data": {"pair_id": str(pair["_id"])},
                    "created_at": now,
                    "read": False,
                }
            }
        },
    )

    await _record_analytics_event("accountability_pair_accepted", user_id=user_id, details={"pair_id": str(pair["_id"])})
    return {"success": True, "status": "active", "pair_id": str(pair["_id"]), "message": "Accountability partnership active!"}


@router.delete("/accountability-pairs/{pair_id}")
async def unpair_accountability_partner(
    pair_id: str,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, bool]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not ObjectId.is_valid(pair_id):
        raise HTTPException(status_code=404, detail="Invalid pair ID")

    res = await accountability_pairs_collection.delete_one(
        {"_id": ObjectId(pair_id), "user_ids": user_id}
    )
    return {"unpaired": bool(res.deleted_count)}


@router.get("/me/accountability-partner", response_model=AccountabilityPartnerDetailResponse)
async def get_my_accountability_partner(
    user: dict = Depends(dependency_require_access_user),
) -> AccountabilityPartnerDetailResponse:
    """Returns the current user's accountability partner status with daily Green Tick / Grey Circle indicator."""
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if accountability_pairs_collection is None:
        return AccountabilityPartnerDetailResponse(paired=False)

    now = datetime.now(timezone.utc)
    day_key = _pair_day_key(user, now)

    # 1. Check for active partnership
    active_pair = await accountability_pairs_collection.find_one(
        {"user_ids": user_id, "status": "active"},
        sort=[("created_at", -1)],
    )

    if active_pair:
        user_ids = [str(x) for x in (active_pair.get("user_ids") or []) if str(x).strip()]
        partner_id = next((x for x in user_ids if x != user_id), None)
        partner_user = None
        if partner_id:
            partner_user = await users_collection.find_one(
                {"_id": ObjectId(partner_id) if ObjectId.is_valid(partner_id) else partner_id}
            )

        daily_status = dict((active_pair.get("daily_status") or {}).get(day_key) or {})
        your_checked_in = bool(daily_status.get(user_id))
        partner_checked_in = bool(daily_status.get(partner_id))

        # Check today's workout completion from workout_logs_collection as real-time indicator
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        workout_day_filter = {
            "$or": [
                {"completed_at": {"$gte": start_of_day}},
                {"started_at": {"$gte": start_of_day}},
                {"created_at": {"$gte": start_of_day}},
            ]
        }
        if not partner_checked_in and partner_id and workout_logs_collection is not None:
            log = await workout_logs_collection.find_one(
                {"user_id": partner_id, **workout_day_filter}
            )
            if log:
                partner_checked_in = True

        if not your_checked_in and workout_logs_collection is not None:
            my_log = await workout_logs_collection.find_one(
                {"user_id": user_id, **workout_day_filter}
            )
            if my_log:
                your_checked_in = True

        last_nudged = active_pair.get("last_nudged_on")
        can_nudge = not partner_checked_in
        if last_nudged:
            try:
                dt = datetime.fromisoformat(str(last_nudged)) if isinstance(last_nudged, str) else last_nudged
                if (now - dt).total_seconds() < 14400:  # Nudge cooldown: 4 hours
                    can_nudge = False
            except Exception:
                pass

        return AccountabilityPartnerDetailResponse(
            paired=True,
            pair_id=str(active_pair["_id"]),
            status="active",
            is_inviter=(active_pair.get("inviter_user_id") == user_id),
            partner_user_id=partner_id,
            partner_name=str((partner_user or {}).get("name") or "Partner"),
            partner_email=str((partner_user or {}).get("email") or ""),
            partner_profile_image=(partner_user or {}).get("profile_image"),
            your_checked_in_today=your_checked_in,
            partner_checked_in_today=partner_checked_in,
            last_nudged_on=str(last_nudged) if last_nudged else None,
            can_nudge=can_nudge,
            partner={
                "id": partner_id,
                "name": str((partner_user or {}).get("name") or "Partner"),
                "email": str((partner_user or {}).get("email") or ""),
                "profileImage": (partner_user or {}).get("profile_image"),
                "streak_days": int((partner_user or {}).get("streak_days") or 0),
                "points": int((partner_user or {}).get("points") or 0),
                "trained_today": partner_checked_in,
                "last_trained_at": None,
            } if partner_id else None,
        )

    # 2. Check for pending invite
    pending_pair = await accountability_pairs_collection.find_one(
        {"user_ids": user_id, "status": "pending"},
        sort=[("created_at", -1)],
    )
    if pending_pair:
        is_inv = (pending_pair.get("inviter_user_id") == user_id)
        return AccountabilityPartnerDetailResponse(
            paired=False,
            pair_id=str(pending_pair["_id"]),
            status="pending",
            is_inviter=is_inv,
            invite_code=pending_pair.get("invite_code"),
            partner_email=pending_pair.get("partner_email"),
        )

    return AccountabilityPartnerDetailResponse(paired=False, status="none")


@router.post("/accountability-pairs/{pair_id}/nudge")
async def nudge_accountability_partner(
    pair_id: str,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Sends an 8pm or manual nudge notification to the accountability partner if they haven't trained today."""
    user_id = str(user.get("_id") or user.get("id") or "")
    if not ObjectId.is_valid(pair_id):
        raise HTTPException(status_code=404, detail="Invalid pair ID")

    pair = await accountability_pairs_collection.find_one(
        {"_id": ObjectId(pair_id), "user_ids": user_id, "status": "active"}
    )
    if not pair:
        raise HTTPException(status_code=404, detail="Active accountability pair not found")

    user_ids = [str(x) for x in (pair.get("user_ids") or []) if str(x).strip()]
    partner_id = next((x for x in user_ids if x != user_id), None)
    if not partner_id:
        raise HTTPException(status_code=404, detail="Partner not found")

    now = datetime.now(timezone.utc)
    sender_name = str(user.get("name") or "Your partner")

    # Insert nudge in partner's notifications
    partner_obj_id = ObjectId(partner_id) if ObjectId.is_valid(partner_id) else partner_id
    await users_collection.update_one(
        {"_id": partner_obj_id},
        {
            "$push": {
                "app_notifications": {
                    "id": str(ObjectId()),
                    "type": "accountability_nudge",
                    "title": "Accountability Nudge ⚡",
                    "message": f"{sender_name} completed training today! Don't let your partner down—get your session in!",
                    "data": {"pair_id": pair_id, "nudge_type": "8pm_daily"},
                    "created_at": now,
                    "read": False,
                }
            }
        },
    )

    await accountability_pairs_collection.update_one(
        {"_id": pair["_id"]},
        {"$set": {"last_nudged_on": now.isoformat(), "updated_at": now}},
    )

    await _record_analytics_event("accountability_nudge_sent", user_id=user_id, details={"partner_id": partner_id})
    return {"success": True, "status": "ok", "message": "Nudge notification sent to your partner!"}


@router.post("/accountability-pairs/run-8pm-nudges")
async def run_8pm_accountability_nudges(
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Automated job: scans active pairs and sends 8pm nudges to any partner who hasn't trained today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    active_pairs = await accountability_pairs_collection.find({"status": "active"}).to_list(length=500)
    nudges_sent = 0

    for pair in active_pairs:
        user_ids = pair.get("user_ids") or []
        if len(user_ids) < 2:
            continue
        pair_status = dict(pair.get("daily_status") or {})
        last_nudged = str(pair.get("last_nudged_on") or "")
        for pending_id in [str(item) for item in user_ids]:
            pending_user = await users_collection.find_one({"_id": ObjectId(pending_id) if ObjectId.is_valid(pending_id) else pending_id})
            day_key = _pair_day_key(pending_user or {}, now)
            if last_nudged == day_key:
                continue
            daily = dict(pair_status.get(day_key) or {})
            if bool(daily.get(pending_id)):
                continue
            workout_day_filter = {
                "$or": [
                    {"completed_at": {"$gte": start_of_day}},
                    {"started_at": {"$gte": start_of_day}},
                    {"created_at": {"$gte": start_of_day}},
                ]
            }
            logged = await workout_logs_collection.find_one({"user_id": pending_id, **workout_day_filter})
            if logged:
                continue
            partner_id = next((str(item) for item in user_ids if str(item) != pending_id), "")
            partner_user = await users_collection.find_one({"_id": ObjectId(partner_id) if ObjectId.is_valid(partner_id) else partner_id})
            partner_name = str((partner_user or {}).get("name") or "Your partner")
            await users_collection.update_one(
                {"_id": ObjectId(pending_id) if ObjectId.is_valid(pending_id) else pending_id},
                {
                    "$push": {
                        "app_notifications": {
                            "id": str(ObjectId()),
                            "type": "accountability_nudge",
                            "title": "8PM Accountability Nudge",
                            "message": f"{partner_name} is waiting for today's green tick. Check in before the day ends.",
                            "data": {"pair_id": str(pair["_id"]), "day": day_key},
                            "created_at": now,
                            "read": False,
                        }
                    }
                },
            )
            await accountability_pairs_collection.update_one(
                {"_id": pair["_id"]},
                {"$set": {"last_nudged_on": day_key, "updated_at": now}},
            )
            nudges_sent += 1

    return {"status": "ok", "nudges_sent": nudges_sent}
