from fastapi import APIRouter

from ...core.legacy import *
from ...models import (
    AccountabilityPairCheckInRequest,
    AccountabilityPairItemResponse,
    AccountabilityPairListResponse,
)
from ...retention_service import _pair_day_key

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
        "daily_status": {},
        "last_nudged_on": None,
    }
    try:
        await accountability_pairs_collection.insert_one(doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"accountability_pairs insert failed: {exc}")
    await _record_analytics_event("accountability_pair_created", user_id=user_id, details={"partner": payload.partner_user_id})
    return {"status": "ok"}


@router.get("/me/accountability-pairs", response_model=AccountabilityPairListResponse)
async def list_accountability_pairs(
    user: dict = Depends(dependency_require_access_user),
) -> AccountabilityPairListResponse:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    now = datetime.now(timezone.utc)
    day_key = _pair_day_key(user, now)
    rows = await accountability_pairs_collection.find(
        {"user_ids": user_id, "status": "active"},
        sort=[("created_at", -1)],
    ).to_list(length=20)
    items: list[AccountabilityPairItemResponse] = []
    for row in rows:
        user_ids = [str(item) for item in (row.get("user_ids") or []) if str(item).strip()]
        partner_user_id = next((item for item in user_ids if item != user_id), "")
        today_status = dict((row.get("daily_status") or {}).get(day_key) or {})
        items.append(
            AccountabilityPairItemResponse(
                pair_id=str(row.get("_id") or ""),
                partner_user_id=partner_user_id,
                status=str(row.get("status") or "active"),
                created_at=row.get("created_at"),
                your_checked_in_today=bool(today_status.get(user_id)),
                partner_checked_in_today=bool(today_status.get(partner_user_id)),
                last_nudged_on=str(row.get("last_nudged_on") or "") or None,
            )
        )
    return AccountabilityPairListResponse(items=items)


@router.patch("/accountability-pairs/{pair_id}/check-in", response_model=AccountabilityPairItemResponse)
async def check_in_accountability_pair(
    pair_id: str,
    payload: AccountabilityPairCheckInRequest,
    user: dict = Depends(dependency_require_access_user),
) -> AccountabilityPairItemResponse:
    if not ObjectId.is_valid(pair_id):
        raise HTTPException(status_code=404, detail="Accountability pair not found")
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    record = await accountability_pairs_collection.find_one({"_id": ObjectId(pair_id), "user_ids": user_id, "status": "active"})
    if not record:
        raise HTTPException(status_code=404, detail="Accountability pair not found")
    now = datetime.now(timezone.utc)
    day_key = _pair_day_key(user, now)
    await accountability_pairs_collection.update_one(
        {"_id": record["_id"]},
        {
            "$set": {
                f"daily_status.{day_key}.{user_id}": bool(payload.completed),
                "updated_at": now,
            }
        },
    )
    updated = await accountability_pairs_collection.find_one({"_id": record["_id"]})
    today_status = dict((updated.get("daily_status") or {}).get(day_key) or {})
    partner_user_id = next((item for item in [str(value) for value in (updated.get("user_ids") or [])] if item != user_id), "")
    return AccountabilityPairItemResponse(
        pair_id=str(updated.get("_id") or ""),
        partner_user_id=partner_user_id,
        status=str(updated.get("status") or "active"),
        created_at=updated.get("created_at"),
        your_checked_in_today=bool(today_status.get(user_id)),
        partner_checked_in_today=bool(today_status.get(partner_user_id)),
        last_nudged_on=str(updated.get("last_nudged_on") or "") or None,
    )
