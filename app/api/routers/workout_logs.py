import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from bson import ObjectId

from ...core.legacy import (
    dependency_require_access_user,
    workout_logs_collection,
    points_log_collection,
    users_collection,
    _record_analytics_event,
)

router = APIRouter()

STREAK_MILESTONE_POINTS = {
    3: 15,
    7: 25,
    14: 50,
    30: 100,
}


class WorkoutLogCreateRequest(BaseModel):
    workout_id: str = Field(min_length=1, max_length=120)
    title: Optional[str] = Field(default=None, max_length=200)
    duration_seconds: int = 0
    status: str = Field(default="started", pattern=r"^(started|completed|abandoned)$")
    market: Optional[str] = Field(default=None, min_length=2, max_length=2)


def _format_workout_title(title: str, workout_id: str) -> str:
    raw = (title or "").strip()
    if re.search(r'[0-9a-fA-F]{24}', raw):
        remainder = re.sub(r'[0-9a-fA-F]{24}', '', raw).strip(" -_")
        if remainder:
            return f"Strength Session - {remainder.title()}"
        return "Strength Workout Session"
    if not raw or raw.lower() == "workout session":
        clean_id = re.sub(r'^[0-9a-fA-F]{24}[-_]?', '', workout_id or '')
        clean_name = clean_id.replace("-", " ").replace("_", " ").strip().title()
        return clean_name if clean_name else "Strength Workout Session"
    return raw


def _serialize_workout_log(doc: dict[str, Any]) -> dict[str, Any]:
    started_at = doc.get("started_at")
    completed_at = doc.get("completed_at")
    raw_title = str(doc.get("title") or doc.get("workout_id") or "Workout Session")
    workout_id = str(doc.get("workout_id") or "")
    return {
        "id": str(doc.get("_id") or ""),
        "workout_id": workout_id,
        "title": _format_workout_title(raw_title, workout_id),
        "duration_seconds": int(doc.get("duration_seconds") or 0),
        "status": str(doc.get("status") or "completed"),
        "market": doc.get("market"),
        "started_at": started_at.isoformat() if isinstance(started_at, datetime) else str(started_at or ""),
        "completed_at": completed_at.isoformat() if isinstance(completed_at, datetime) else str(completed_at or ""),
    }


def _workout_log_completed_date(doc: dict[str, Any]) -> date | None:
    value = doc.get("completed_at") or doc.get("started_at")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


def _calculate_completed_workout_streak(logs: list[dict[str, Any]], *, now: datetime) -> int:
    completed_dates = {
        completed_date
        for completed_date in (_workout_log_completed_date(log) for log in logs)
        if completed_date is not None
    }
    if not completed_dates:
        return 0

    today = now.astimezone(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if today not in completed_dates and yesterday not in completed_dates:
        return 0

    cursor = today if today in completed_dates else yesterday
    streak = 0
    while cursor in completed_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def _award_streak_milestone_points(
    *,
    user_id: str,
    user: dict[str, Any],
    new_log_id: Any,
    now: datetime,
) -> None:
    if points_log_collection is None or users_collection is None:
        return

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    existing_today_count = await workout_logs_collection.count_documents(
        {
            "user_id": user_id,
            "status": "completed",
            "_id": {"$ne": new_log_id},
            "completed_at": {"$gte": today_start, "$lt": tomorrow_start},
        }
    )
    if existing_today_count > 0:
        return

    cursor = workout_logs_collection.find({"user_id": user_id, "status": "completed"}).sort("completed_at", -1)
    logs = await cursor.to_list(length=400)
    current_streak = _calculate_completed_workout_streak(logs, now=now)
    points = STREAK_MILESTONE_POINTS.get(current_streak)
    if not points:
        return

    existing_award_count = await points_log_collection.count_documents(
        {
            "user_id": user_id,
            "event_type": "streak_milestone",
            "streak_days": current_streak,
        }
    )
    if existing_award_count > 0:
        return

    await points_log_collection.insert_one(
        {
            "user_id": user_id,
            "points": points,
            "reason": f"{current_streak}-day workout streak milestone",
            "event_type": "streak_milestone",
            "streak_days": current_streak,
            "workout_log_id": str(new_log_id),
            "created_at": now,
        }
    )
    await users_collection.update_one(
        {"_id": user.get("_id")},
        {
            "$inc": {"points": points},
            "$set": {
                "streak_days": current_streak,
                "updated_at": now,
            },
        },
    )


@router.post("/workout-logs", status_code=status.HTTP_201_CREATED)
async def create_workout_log(
    payload: WorkoutLogCreateRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    now = datetime.now(timezone.utc)
    if workout_logs_collection is None:
        return {"status": "noop"}

    resolved_title = (payload.title or "").strip()
    if not resolved_title or re.search(r'[0-9a-fA-F]{24}', resolved_title):
        parts = payload.workout_id.split("-", 1)
        if len(parts) == 2 and ObjectId.is_valid(parts[0]):
            plan_id_str, day_suffix = parts
            try:
                from .ai_workout_plan import strength_workout_plans_collection
                if strength_workout_plans_collection is not None:
                    plan_doc = await strength_workout_plans_collection.find_one({"_id": ObjectId(plan_id_str)})
                    if plan_doc:
                        plan_data = plan_doc.get("plan", {})
                        days = plan_data.get("days", [])
                        matched_day = next((d for d in days if d.get("day", "").lower() == day_suffix.lower()), None)
                        day_name = matched_day.get("title") or matched_day.get("day") if matched_day else day_suffix.title()
                        summary = plan_data.get("summary", "")
                        if " using " in summary:
                            plan_name = summary.split(" using ")[0].replace(" plan", "").replace(" PLAN", "").strip().title()
                        elif " plan" in summary.lower():
                            plan_name = summary.lower().split(" plan")[0].strip().title()
                        else:
                            plan_name = summary.strip().title() if summary else "Strength Plan"
                        resolved_title = f"{plan_name} - {day_name}" if day_name else plan_name
            except Exception:
                pass
        if not resolved_title:
            clean_id = re.sub(r'^[0-9a-fA-F]{24}[-_]?', '', payload.workout_id)
            clean_name = clean_id.replace("-", " ").replace("_", " ").strip().title()
            resolved_title = clean_name if clean_name else "Strength Workout Session"

    doc = {
        "user_id": user_id,
        "workout_id": payload.workout_id,
        "title": resolved_title,
        "duration_seconds": payload.duration_seconds,
        "status": payload.status,
        "market": (payload.market or "").upper() or None,
        "started_at": now,
        "completed_at": now if payload.status == "completed" else None,
    }
    try:
        result = await workout_logs_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"workout_logs insert failed: {exc}")

    if payload.status == "completed":
        try:
            await _award_streak_milestone_points(
                user_id=user_id,
                user=user,
                new_log_id=result.inserted_id,
                now=now,
            )
            prev_completed = await workout_logs_collection.count_documents(
                {"user_id": user_id, "status": "completed", "_id": {"$ne": result.inserted_id}}
            )
            if prev_completed == 0:
                inviter_user_id = str(user.get("referred_by_user_id") or "").strip()
                if not inviter_user_id and isinstance(user.get("referral_program"), dict):
                    inviter_user_id = str((user.get("referral_program") or {}).get("referred_by_user_id") or "").strip()
                if inviter_user_id and not user.get("first_workout_reward_awarded"):
                    if points_log_collection is not None:
                        await points_log_collection.insert_one({
                            "user_id": inviter_user_id,
                            "points": 50,
                            "reason": "Referred friend completed first workout",
                            "referred_friend_id": user_id,
                            "created_at": now,
                        })
                    inviter_filter = {"_id": ObjectId(inviter_user_id)} if ObjectId.is_valid(inviter_user_id) else {"_id": inviter_user_id}
                    await users_collection.update_one(inviter_filter, {"$inc": {"points": 50}})
                    await users_collection.update_one({"_id": user.get("_id")}, {"$set": {"first_workout_reward_awarded": True}})
        except Exception:
            pass
    await _record_analytics_event(
        f"workout_{payload.status}",
        user_id=user_id,
        market=payload.market,
        details={"workout_id": payload.workout_id},
    )
    return {"id": str(result.inserted_id), "status": payload.status}


@router.get("/workout-logs")
async def list_workout_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (default 20)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (e.g. completed)"),
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if workout_logs_collection is None:
        return {"items": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}

    query: dict[str, Any] = {"user_id": user_id}
    if status_filter:
        query["status"] = status_filter

    total = await workout_logs_collection.count_documents(query)
    total_pages = math.ceil(total / limit) if total > 0 else 1

    cursor = (
        workout_logs_collection.find(query)
        .sort("started_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = [_serialize_workout_log(doc) async for doc in cursor]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
    }


@router.post("/workout-logs/seed-test-logs")
async def seed_test_workout_logs(
    count: int = Query(55, ge=1, le=100),
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    """Generates 50+ realistic workout logs for verifying the 20-items-per-page pagination requirement."""
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if workout_logs_collection is None:
        return {"inserted": 0}

    sample_workouts = [
        ("Push Hypertrophy", 2400, "Push Hypertrophy - Chest & Triceps"),
        ("Pull Power", 2700, "Pull Power - Heavy Deadlifts & Back"),
        ("Legs & Core Overload", 3000, "Legs & Core - Squats & Calves"),
        ("Upper Body Functional", 2100, "Upper Body Functional Strength"),
        ("HIIT Metabolic Burn", 1800, "HIIT Metabolic Burn & Conditioning"),
        ("Active Mobility & Core", 1500, "Active Mobility & Core Flow"),
        ("Full Body Compound", 2700, "Full Body Compound Builder"),
    ]

    now = datetime.now(timezone.utc)
    docs = []
    for i in range(count):
        workout_name, duration, title = sample_workouts[i % len(sample_workouts)]
        started_at = now - timedelta(days=i, hours=(i % 6) + 1, minutes=15)
        completed_at = started_at + timedelta(seconds=duration)
        docs.append(
            {
                "user_id": user_id,
                "workout_id": f"workout-{i+1}-{workout_name.lower().replace(' ', '-')}",
                "title": f"{title} #{i+1}",
                "duration_seconds": duration,
                "status": "completed",
                "market": "GB",
                "started_at": started_at,
                "completed_at": completed_at,
            }
        )

    if docs:
        await workout_logs_collection.insert_many(docs)

    return {
        "status": "success",
        "inserted": len(docs),
        "message": f"Successfully created {len(docs)} workout logs for pagination testing.",
    }
