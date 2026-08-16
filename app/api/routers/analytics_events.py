from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/analytics-events", status_code=status.HTTP_202_ACCEPTED)
async def create_analytics_event(
    payload: _AnalyticsEventRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, str]:
    if payload.event_type not in _CLIENT_ANALYTICS_EVENTS:
        raise HTTPException(status_code=400, detail="Unsupported analytics event")
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    await _record_analytics_event(
        payload.event_type,
        user_id=user_id,
        market=str(user.get("country_code") or "") or None,
        details=payload.details,
    )
    return {"status": "accepted"}
