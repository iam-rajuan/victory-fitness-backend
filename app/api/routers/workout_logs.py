import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId

from ...core.legacy import (
    _WorkoutLogRequest,
    dependency_require_access_user,
    workout_logs_collection,
    points_log_collection,
    users_collection,
    _record_analytics_event,
)

router = APIRouter()


def _serialize_workout_log(doc: dict[str, Any]) -> dict[str, Any]:
    started_at = doc.get("started_at")
    completed_at = doc.get("completed_at")
    return {
        "id": str(doc.get("_id") or ""),
        "workout_id": str(doc.get("workout_id") or ""),
        "title": str(doc.get("title") or doc.get("workout_id") or "Workout Session"),
        "duration_seconds": int(doc.get("duration_seconds") or 0),
        "status": str(doc.get("status") or "completed"),
        "market": doc.get("market"),
        "started_at": started_at.isoformat() if isinstance(started_at, datetime) else str(started_at or ""),
        "completed_at": completed_at.isoformat() if isinstance(completed_at, datetime) else str(completed_at or ""),
    }


@router.post("/workout-logs", status_code=status.HTTP_201_CREATED)
async def create_workout_log(
    payload: _WorkoutLogRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    now = datetime.now(timezone.utc)
    if workout_logs_collection is None:
        return {"status": "noop"}
    doc = {
        "user_id": user_id,
        "workout_id": payload.workout_id,
        "title": payload.workout_id.replace("-", " ").title(),
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
