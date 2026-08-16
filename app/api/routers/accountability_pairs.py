from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/accountability-pairs", status_code=status.HTTP_201_CREATED)
async def create_accountability_pair(
    payload: _AccountabilityPairRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, str]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if accountability_pairs_collection is None:
        return {"status": "noop"}
    doc = {
        "user_ids": [user_id, payload.partner_user_id],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await accountability_pairs_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"accountability_pairs insert failed: {exc}")
    await _record_analytics_event("accountability_pair_created", user_id=user_id, details={"partner": payload.partner_user_id})
    return {"status": "ok"}
