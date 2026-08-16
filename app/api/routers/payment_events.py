from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/payment-events", status_code=status.HTTP_201_CREATED)
async def create_payment_event(
    payload: _PaymentEventRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if payment_events_collection is None:
        return {"status": "noop"}
    try:
        amount = float(payload.amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount must be a number")
    doc = {
        "user_id": user_id or None,
        "amount": amount,
        "currency": payload.currency.upper(),
        "type": payload.type,
        "tier": payload.tier,
        "market": (payload.market or "").upper() or None,
        "status": "success",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await payment_events_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"payment_events insert failed: {exc}")
    await _record_analytics_event(
        f"payment_{payload.type}",
        user_id=user_id or None,
        market=payload.market,
        details={"amount": amount, "currency": payload.currency, "tier": payload.tier},
    )
    return {"id": str(result.inserted_id)}
