from fastapi import APIRouter
from bson import ObjectId

from ...core.legacy import *
from ...conversion_service import assign_invite_variant
from ...models import InviteAcceptRequest

router = APIRouter()

@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: _InviteRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if invites_collection is None:
        return {"status": "noop"}
    copy_variant = str(payload.copy_variant or assign_invite_variant(user_id)).strip().lower() or "a"
    doc = {
        "user_id": user_id or None,
        "recipient_email": str(payload.recipient_email) if payload.recipient_email else None,
        "recipient_phone": payload.recipient_phone or None,
        "copy_variant": copy_variant,
        "accepted": False,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await invites_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"invites insert failed: {exc}")
    await _record_analytics_event("invite_sent", user_id=user_id or None, details={"variant": copy_variant})
    return {"id": str(result.inserted_id), "copyVariant": copy_variant}


@router.patch("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: str,
    payload: InviteAcceptRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, object]:
    if invites_collection is None:
        return {"updated": False}
    filters = {}
    if ObjectId.is_valid(invite_id):
        filters["_id"] = ObjectId(invite_id)
    else:
        filters["_id"] = invite_id
    invite = await invites_collection.find_one(filters)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    accepted = bool(payload.accepted)
    result = await invites_collection.update_one(
        filters,
        {
            "$set": {
                "accepted": accepted,
                "accepted_at": datetime.now(timezone.utc) if accepted else None,
                "accepted_by_user_id": str(user.get("_id") or ""),
            }
        },
    )
    if accepted:
        await _record_analytics_event(
            "invite_accepted",
            user_id=str(user.get("_id") or ""),
            market=str(user.get("country_code") or "") or None,
            details={"invite_id": invite_id, "variant": str(invite.get("copy_variant") or "a").lower()},
        )
    return {"updated": bool(result.modified_count), "accepted": accepted}
