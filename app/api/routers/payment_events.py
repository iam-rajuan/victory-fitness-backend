from fastapi import APIRouter

from ...core.legacy import *
from ...revenue_service import record_revenue_entry

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
    ledger_id = None
    if payload.type in {"subscription_started", "subscription_renewed"} and amount > 0:
        ledger_id = await record_revenue_entry(
            source="consumer_subscription",
            gross_amount=amount,
            net_amount=amount,
            currency=payload.currency.upper(),
            market=payload.market,
            user_id=user_id or None,
            subscription_tier=payload.tier,
            external_ref=f"payment_event:{result.inserted_id}",
            metadata={"legacy_type": payload.type},
        )
    await _record_analytics_event(
        f"payment_{payload.type}",
        user_id=user_id or None,
        market=payload.market,
        details={"amount": amount, "currency": payload.currency, "tier": payload.tier},
    )
    return {"id": str(result.inserted_id), "ledger_id": ledger_id}
