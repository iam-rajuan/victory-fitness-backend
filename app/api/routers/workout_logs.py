from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

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
    await _record_analytics_event(
        f"workout_{payload.status}",
        user_id=user_id,
        market=payload.market,
        details={"workout_id": payload.workout_id},
    )
    return {"id": str(result.inserted_id), "status": payload.status}
