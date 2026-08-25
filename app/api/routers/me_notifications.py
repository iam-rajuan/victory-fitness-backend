from fastapi import APIRouter

from ...core.legacy import *
from ...conversion_service import mark_notification_event_actioned, mark_notification_event_opened
from ...retention_service import record_notification_open

router = APIRouter()

@router.post("/me/push-token")
async def register_push_token(
    payload: PushTokenRequest,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    token = payload.token.strip()
    platform = payload.platform.strip().lower() or "unknown"
    now = datetime.now(timezone.utc)
    existing_tokens = [item for item in (user.get("push_tokens") or []) if isinstance(item, dict)]
    updated_tokens = [item for item in existing_tokens if item.get("token") != token]
    updated_tokens.append({"token": token, "platform": platform, "updated_at": now})
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"push_tokens": updated_tokens[-10:]}},
    )
    return {"registered": True}

@router.get("/me/notifications", response_model=AppNotificationListResponse)
async def list_app_notifications(user: dict = Depends(_require_access_user)) -> AppNotificationListResponse:
    records = [item for item in (user.get("app_notifications") or []) if isinstance(item, dict)]
    records.sort(key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return AppNotificationListResponse(items=[AppNotificationItem(**item) for item in records[:50]])

@router.delete("/me/notifications/{notification_id}")
async def delete_app_notification(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    result = await users_collection.update_one(
        {"_id": user["_id"]},
        {"$pull": {"app_notifications": {"id": notification_id}}},
    )
    return {"deleted": bool(result.modified_count)}

@router.patch("/me/notifications/{notification_id}/read")
async def mark_app_notification_read(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    result = await users_collection.update_one(
        {"_id": user["_id"], "app_notifications.id": notification_id},
        {"$set": {"app_notifications.$.read": True}},
    )
    if result.modified_count:
        await record_notification_open(user, notification_id)
        await mark_notification_event_opened(str(user.get("_id") or ""), notification_id)
        await _record_analytics_event(
            "notification_opened",
            user_id=str(user.get("_id") or ""),
            market=str(user.get("country_code") or "") or None,
            details={"notification_id": notification_id},
        )
    return {"read": bool(result.modified_count)}


@router.patch("/me/notifications/{notification_id}/action")
async def mark_app_notification_actioned(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    await mark_notification_event_actioned(str(user.get("_id") or ""), notification_id)
    await _record_analytics_event(
        "notification_actioned",
        user_id=str(user.get("_id") or ""),
        market=str(user.get("country_code") or "") or None,
        details={"notification_id": notification_id},
    )
    return {"actioned": True}

@router.get("/me/activity-notifications/dismissed")
async def list_dismissed_activity_notifications(
    user: dict = Depends(_require_access_user),
) -> dict[str, list[str]]:
    return {
        "ids": [
            str(item)
            for item in (user.get("dismissed_activity_notification_ids") or [])
            if str(item).strip()
        ]
    }

@router.delete("/me/activity-notifications/{notification_id}")
async def delete_activity_notification(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    notification_id = notification_id.strip()
    if not notification_id:
        raise HTTPException(status_code=400, detail="Notification id is required")
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"dismissed_activity_notification_ids": notification_id}},
    )
    return {"deleted": True}

@router.delete("/me/push-token")
async def unregister_push_token(
    payload: PushTokenRequest,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    token = payload.token.strip()
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$pull": {"push_tokens": {"token": token}}},
    )
    return {"removed": True}
