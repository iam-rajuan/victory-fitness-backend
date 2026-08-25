from fastapi import APIRouter
from bson import ObjectId

from ...core.legacy import *
from ...conversion_service import build_post_workout_upsell_message, should_show_post_workout_upsell
from ...models import CompletionCardUpsellStateRequest

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
        "upsell_shown": bool(payload.upsell_shown),
        "upsell_clicked": bool(payload.upsell_clicked),
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
    should_show, reason = await should_show_post_workout_upsell(user)
    upsell = {
        "eligible": should_show,
        "reason": reason,
        "source": "completion_card",
    }
    if should_show:
        title, message = build_post_workout_upsell_message(user)
        upsell.update({"title": title, "message": message})
    return {"id": str(result.inserted_id), "sharedToWhatsapp": payload.shared_to_whatsapp, "upsell": upsell}


@router.patch("/completion-cards/{card_id}/upsell")
async def update_completion_card_upsell_state(
    card_id: str,
    payload: CompletionCardUpsellStateRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, object]:
    if completion_cards_collection is None:
        return {"updated": False}
    filters = {"user_id": str(user.get("_id") or user.get("id") or "")}
    if ObjectId.is_valid(card_id):
        filters["_id"] = ObjectId(card_id)
    else:
        filters["_id"] = card_id
    update_fields = {"updated_at": datetime.now(timezone.utc)}
    if payload.upsell_shown is not None:
        update_fields["upsell_shown"] = bool(payload.upsell_shown)
        if payload.upsell_shown:
            await _record_analytics_event(
                "upgrade_screen_viewed",
                user_id=str(user.get("_id") or ""),
                market=str(user.get("country_code") or "") or None,
                details={"source": "completion_card", "card_id": card_id},
            )
    if payload.upsell_clicked is not None:
        update_fields["upsell_clicked"] = bool(payload.upsell_clicked)
        if payload.upsell_clicked:
            await _record_analytics_event(
                "upgrade_prompt_clicked",
                user_id=str(user.get("_id") or ""),
                market=str(user.get("country_code") or "") or None,
                details={"source": "completion_card", "card_id": card_id},
            )
    result = await completion_cards_collection.update_one(filters, {"$set": update_fields})
    return {"updated": bool(result.modified_count)}
