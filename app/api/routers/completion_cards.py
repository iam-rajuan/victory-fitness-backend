from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/completion-cards", status_code=status.HTTP_201_CREATED)
async def create_completion_card(
    payload: _CompletionCardRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if completion_cards_collection is None:
        return {"status": "noop"}
    doc = {
        "user_id": user_id,
        "workout_id": payload.workout_id,
        "shared_to_whatsapp": bool(payload.shared_to_whatsapp),
        "image_url": payload.image_url or "",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await completion_cards_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"completion_cards insert failed: {exc}")
    if payload.shared_to_whatsapp:
        await _record_analytics_event(
            "completion_card_shared_whatsapp",
            user_id=user_id,
            details={"workout_id": payload.workout_id},
        )
    return {"id": str(result.inserted_id), "sharedToWhatsapp": payload.shared_to_whatsapp}
