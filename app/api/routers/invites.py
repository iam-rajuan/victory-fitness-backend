from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: _InviteRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if invites_collection is None:
        return {"status": "noop"}
    doc = {
        "user_id": user_id or None,
        "recipient_email": str(payload.recipient_email) if payload.recipient_email else None,
        "recipient_phone": payload.recipient_phone or None,
        "copy_variant": payload.copy_variant,
        "accepted": False,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await invites_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"invites insert failed: {exc}")
    await _record_analytics_event("invite_sent", user_id=user_id or None, details={"variant": payload.copy_variant})
    return {"id": str(result.inserted_id)}
