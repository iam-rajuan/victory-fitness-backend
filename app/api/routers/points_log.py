from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/points-log", status_code=status.HTTP_201_CREATED)
async def create_points_entry(
    payload: _PointsLogRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, str]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if points_log_collection is None:
        return {"status": "noop"}
    try:
        await points_log_collection.insert_one({
            "user_id": user_id,
            "points": payload.points,
            "reason": payload.reason,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"points_log insert failed: {exc}")
    return {"status": "ok"}
