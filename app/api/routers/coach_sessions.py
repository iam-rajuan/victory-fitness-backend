from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...core.legacy import *

router = APIRouter()


class CoachSessionNotesRequest(BaseModel):
    notes: str = Field(default="", max_length=3000)


def _utc_date(value) -> str | None:
    moment = value
    if isinstance(moment, str):
        try:
            moment = datetime.fromisoformat(moment.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(moment, datetime):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date().isoformat()


async def _habit_consistency_weeks(user: dict, *, weeks_count: int = 4) -> list[dict]:
    user_id = str(user.get("_id") or "")
    trigger_context = str(user.get("training_trigger_context") or "").strip()
    trigger_action = str(user.get("training_trigger_action") or "").strip()
    has_trigger = bool(trigger_context and trigger_action)
    today = datetime.now(timezone.utc).date()
    weeks: list[dict] = []

    for index in range(weeks_count - 1, -1, -1):
        week_end_date = today - timedelta(days=index * 7)
        week_start_date = week_end_date - timedelta(days=6)
        start_dt = datetime.combine(week_start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(week_end_date, datetime.max.time(), tzinfo=timezone.utc)
        logs = await workout_logs_collection.find(
            {
                "user_id": user_id,
                "status": "completed",
                "$or": [
                    {"completed_at": {"$gte": start_dt, "$lte": end_dt}},
                    {"started_at": {"$gte": start_dt, "$lte": end_dt}},
                    {"created_at": {"$gte": start_dt, "$lte": end_dt}},
                ],
            }
        ).to_list(length=200)
        trained_dates = {date_key for date_key in (_utc_date(log.get("completed_at") or log.get("started_at") or log.get("created_at")) for log in logs) if date_key}
        trigger_days = 7 if has_trigger else 0
        trained_trigger_days = len(trained_dates) if has_trigger else 0
        weeks.append(
            {
                "label": f"{week_start_date.strftime('%b %d')} - {week_end_date.strftime('%b %d')}",
                "week_start": week_start_date.isoformat(),
                "week_end": week_end_date.isoformat(),
                "trigger_days": trigger_days,
                "trained_trigger_days": trained_trigger_days,
                "score": round((trained_trigger_days / trigger_days) * 100, 1) if trigger_days else 0,
            }
        )
    return weeks


async def _load_target_user(user_id: str) -> dict:
    try:
        object_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc
    user = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/admin/users/{user_id}/coach-session-brief")
async def admin_get_coach_session_brief(
    user_id: str,
    _: dict = Depends(_require_admin_user),
) -> dict:
    user = await _load_target_user(user_id)
    tier = _normalize_subscription_tier(user.get("subscription_tier") or user.get("subscription_role") or user.get("tier"))
    if tier != "INNER_CIRCLE":
        raise HTTPException(status_code=403, detail="Coach session briefs are only available for Inner Circle users")
    weeks = await _habit_consistency_weeks(user)
    latest = weeks[-1] if weeks else {}
    return {
        "userId": str(user["_id"]),
        "fullName": str(user.get("name") or "Unknown"),
        "subscriptionTier": tier,
        "identityStatement": str(user.get("identity_statement") or ""),
        "workoutUnlockLabel": str(user.get("workout_unlock_label") or ""),
        "trainingTriggerContext": str(user.get("training_trigger_context") or ""),
        "trainingTriggerAction": str(user.get("training_trigger_action") or ""),
        "habitConsistencyScore": float(latest.get("score") or 0),
        "weeks": weeks,
        "coachSessionNotes": str(user.get("coach_session_notes") or ""),
        "coachSessionNotesUpdatedAt": user.get("coach_session_notes_updated_at"),
    }


@router.patch("/admin/users/{user_id}/coach-session-notes")
async def admin_update_coach_session_notes(
    user_id: str,
    payload: CoachSessionNotesRequest,
    admin: dict = Depends(_require_admin_user),
) -> dict:
    user = await _load_target_user(user_id)
    tier = _normalize_subscription_tier(user.get("subscription_tier") or user.get("subscription_role") or user.get("tier"))
    if tier != "INNER_CIRCLE":
        raise HTTPException(status_code=403, detail="Coach session notes are only available for Inner Circle users")
    now = datetime.now(timezone.utc)
    notes = payload.notes.strip()
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "coach_session_notes": notes,
                "coach_session_notes_updated_at": now,
                "coach_session_notes_updated_by": str(admin.get("_id") or ""),
                "updated_at": now,
            }
        },
    )
    return {"status": "success", "coachSessionNotes": notes, "updatedAt": now}
