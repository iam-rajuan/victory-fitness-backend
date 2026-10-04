from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...core.legacy import *
from ...conversion_service import list_notification_templates, mark_notification_event_actioned, mark_notification_event_opened
from ...dependencies import normalize_subscription_tier, user_has_active_gold_trial
from ...retention_service import record_notification_open

router = APIRouter()


class NotificationPreferenceTemplateState(BaseModel):
    type: str
    enabled: bool = True


class NotificationPreferencesUpdateRequest(BaseModel):
    pushEnabled: bool | None = None
    whatsappEnabled: bool | None = None
    emailEnabled: bool | None = None
    nudgeTime: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    templates: list[NotificationPreferenceTemplateState] | None = None


def _template_preference_map(user: dict) -> dict[str, dict]:
    raw = user.get("notification_template_preferences") or {}
    return raw if isinstance(raw, dict) else {}


def _channels_for_template(template: dict) -> list[str]:
    channels = [str(item).strip().lower() for item in (template.get("channels") or []) if str(item).strip()]
    return channels or ["push", "email"]


def _member_segments_for_template(template: dict) -> list[str]:
    segments = [
        str(item).strip()
        for item in (template.get("memberSegments") or template.get("member_segments") or [])
        if str(item).strip() in {"all", "silver", "gold", "platinum", "twenty_one_day_tester"}
    ]
    if not segments or "all" in segments:
        return ["all"]
    return list(dict.fromkeys(segments))


def _user_matches_member_segments(user: dict, segments: list[str]) -> bool:
    if not segments or "all" in segments:
        return True
    tier = normalize_subscription_tier(user.get("subscription_tier") or user.get("subscription_role") or user.get("tier"))
    return bool(
        ("silver" in segments and tier == "SILVER")
        or ("gold" in segments and tier == "GOLD")
        or ("platinum" in segments and tier == "PLATINUM")
        or (
            "twenty_one_day_tester" in segments
            and (
                user.get("isBetaTester")
                or user.get("is_beta_tester")
                or tier == "GOLD_BETA"
                or user_has_active_gold_trial(user)
            )
        )
    )

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


@router.get("/me/notification-preferences")
async def get_notification_preferences(user: dict = Depends(_require_access_user)) -> dict:
    templates = [
        template
        for template in await list_notification_templates()
        if str(template.get("audience") or "member").strip() == "member"
        and _user_matches_member_segments(user, _member_segments_for_template(template))
    ]
    template_prefs = _template_preference_map(user)
    return {
        "pushEnabled": bool(user.get("notification_push_enabled", True)),
        "whatsappEnabled": bool(user.get("notification_whatsapp_enabled", False)),
        "emailEnabled": bool(user.get("notification_email_enabled", False)),
        "nudgeTime": str(user.get("notification_nudge_time") or "20:30"),
        "templates": [
            {
                "id": str(template.get("id") or template.get("type") or ""),
                "type": str(template.get("type") or ""),
                "title": str(template.get("title") or ""),
                "channels": _channels_for_template(template),
                "approved": str(template.get("reviewStatus") or "approved") == "approved",
                "frequencyCapHours": max(int(template.get("frequencyCapHours") or 24), 1),
                "enabled": bool((template_prefs.get(str(template.get("type") or "")) or {}).get("enabled", True)),
            }
            for template in templates
        ],
    }


@router.patch("/me/notification-preferences")
async def update_notification_preferences(
    payload: NotificationPreferencesUpdateRequest,
    user: dict = Depends(_require_access_user),
) -> dict:
    update_doc: dict[str, object] = {}
    if payload.pushEnabled is not None:
        update_doc["notification_push_enabled"] = bool(payload.pushEnabled)
    if payload.whatsappEnabled is not None:
        update_doc["notification_whatsapp_enabled"] = bool(payload.whatsappEnabled)
    if payload.emailEnabled is not None:
        update_doc["notification_email_enabled"] = bool(payload.emailEnabled)
    if payload.nudgeTime is not None:
        update_doc["notification_nudge_time"] = payload.nudgeTime.strip() or "20:30"
    if payload.templates is not None:
        prefs = _template_preference_map(user)
        for item in payload.templates:
            notification_type = item.type.strip()
            if notification_type:
                prefs[notification_type] = {"enabled": bool(item.enabled)}
        update_doc["notification_template_preferences"] = prefs
    if update_doc:
        update_doc["updated_at"] = datetime.now(timezone.utc)
        await users_collection.update_one({"_id": user["_id"]}, {"$set": update_doc})
    updated_user = await users_collection.find_one({"_id": user["_id"]}) or {**user, **update_doc}
    return await get_notification_preferences(updated_user)

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
