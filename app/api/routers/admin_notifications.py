from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from ...core.legacy import *
from ...conversion_service import list_notification_templates, replace_notification_templates
from ...models import (
    AdminNotificationTemplateItem,
    AdminNotificationTemplateListResponse,
    AdminNotificationTemplateRequest,
    NotificationTemplateVariantItem,
)

router = APIRouter()


def _channels_for_template(template: dict) -> list[str]:
    channels = [str(item).strip().lower() for item in (template.get("channels") or []) if str(item).strip()]
    return channels or ["push", "email"]


def _user_enabled_channels(user: dict) -> set[str]:
    enabled_channels: set[str] = set()
    if user.get("notification_push_enabled", True):
        enabled_channels.add("push")
    if user.get("notification_whatsapp_enabled"):
        enabled_channels.add("whatsapp")
    if user.get("notification_email_enabled"):
        enabled_channels.add("email")
    return enabled_channels


async def _notification_template_stats(notification_type: str, audience: str, channels: list[str]) -> tuple[int, int, int]:
    if audience != "member":
        sent = await notification_events_collection.count_documents({"type": notification_type, "status": {"$in": ["sent", "queued", "inbox_only", "partial"]}})
        return 0, 0, sent

    users = await users_collection.find({"is_admin": {"$ne": True}}).to_list(length=None)
    enabled = 0
    disabled = 0
    offered_channels = set(channels or ["push"])
    for user in users:
        has_channel = bool(_user_enabled_channels(user) & offered_channels)
        template_prefs = user.get("notification_template_preferences") if isinstance(user.get("notification_template_preferences"), dict) else {}
        template_enabled = bool((template_prefs.get(notification_type) or {}).get("enabled", True))
        if has_channel and template_enabled:
            enabled += 1
        else:
            disabled += 1
    sent = await notification_events_collection.count_documents({"type": notification_type, "status": {"$in": ["sent", "queued", "inbox_only", "partial"]}})
    return enabled, disabled, sent


async def _serialize_notification_template_items(templates: list[dict]) -> list[AdminNotificationTemplateItem]:
    now = datetime.now(timezone.utc)
    items: list[AdminNotificationTemplateItem] = []
    for item in templates:
        notification_type = str(item.get("type") or "").strip()
        audience = str(item.get("audience") or "member").strip() or "member"
        channels = _channels_for_template(item)
        enabled, disabled, sent = await _notification_template_stats(notification_type, audience, channels)
        items.append(AdminNotificationTemplateItem(
            id=str(item.get("id") or item.get("type") or ""),
            type=notification_type,
            title=str(item.get("title") or "").strip(),
            channels=channels,
            audience=audience,
            frequencyCapHours=max(int(item.get("frequencyCapHours") or 24), 1),
            requiresContentReview=bool(item.get("requiresContentReview")),
            reviewStatus=str(item.get("reviewStatus") or ("pending_review" if item.get("requiresContentReview") else "approved")),
            enabledMembers=enabled,
            disabledMembers=disabled,
            sentCount=sent,
            variants=[
                NotificationTemplateVariantItem(
                    key=str(variant.get("key") or "a").strip().lower(),
                    title=str(variant.get("title") or "").strip(),
                    message=str(variant.get("message") or "").strip(),
                )
                for variant in (item.get("variants") or [])
                if isinstance(variant, dict)
            ],
            updatedAt=item.get("updated_at") or item.get("updatedAt") or now,
        ))
    return items

@router.get("/admin/notifications", response_model=AdminNotificationListResponse)

async def admin_list_notifications(

    _: dict = Depends(_require_admin_user),

) -> AdminNotificationListResponse:

    items = [_serialize_admin_notification_item(item) for item in await _get_dashboard_notification_items()]

    items.sort(key=lambda item: item["createdAt"], reverse=True)

    return AdminNotificationListResponse(items=[AdminNotificationItem(**item) for item in items])

@router.post("/admin/notifications/test")
async def admin_send_test_notification(
    payload: AdminTestNotificationRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> dict[str, object]:
    email = payload.email.strip().lower()
    user = await users_collection.find_one({"email": email, "is_admin": {"$ne": True}})
    if not user:
        raise HTTPException(status_code=404, detail="App user not found for that email")
    tokens = [item for item in (user.get("push_tokens") or []) if isinstance(item, dict) and str(item.get("token") or "").strip()]
    delivery = await notify_user(
        users_collection,
        user,
        "Victory Fitness test notification",
        "Push notifications are connected successfully.",
        "test_notification",
        {"type": "test_notification", "route": "/notifications"},
    )
    return {"status": delivery.get("status", "sent"), "email": email, "registeredDevices": len(tokens), "delivery": delivery}

@router.patch("/admin/notifications/{notification_id}", response_model=AdminNotificationItem)
async def admin_update_notification(

    notification_id: str,

    payload: AdminNotificationUpdateRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminNotificationItem:

    items = [_serialize_admin_notification_item(item) for item in await _get_dashboard_notification_items()]

    updated_item: dict | None = None

    for item in items:

        if item["id"] == notification_id:

            item["read"] = payload.read

            updated_item = item

            break

    if not updated_item:

        raise HTTPException(status_code=404, detail="Notification not found")

    await _replace_items_record(DASHBOARD_NOTIFICATIONS_KEY, items)

    return AdminNotificationItem(**updated_item)

@router.patch("/admin/notifications/actions/read-all", response_model=AdminNotificationListResponse)

async def admin_mark_all_notifications_read(

    _: dict = Depends(_require_admin_user),

) -> AdminNotificationListResponse:

    items = [_serialize_admin_notification_item(item) for item in await _get_dashboard_notification_items()]

    for item in items:

        item["read"] = True

    await _replace_items_record(DASHBOARD_NOTIFICATIONS_KEY, items)

    return AdminNotificationListResponse(items=[AdminNotificationItem(**item) for item in items])


@router.get("/admin/notification-templates", response_model=AdminNotificationTemplateListResponse)
async def admin_list_notification_templates(
    _: dict = Depends(_require_admin_user),
) -> AdminNotificationTemplateListResponse:
    templates = await list_notification_templates()
    return AdminNotificationTemplateListResponse(items=await _serialize_notification_template_items(templates))


@router.put("/admin/notification-templates", response_model=AdminNotificationTemplateListResponse)
async def admin_replace_notification_templates(
    payload: list[AdminNotificationTemplateRequest],
    _: dict = Depends(_require_admin_user),
) -> AdminNotificationTemplateListResponse:
    normalized_items = []
    for item in payload:
        normalized_items.append(
            {
                "id": (item.id or item.type).strip(),
                "type": item.type.strip(),
                "title": item.title.strip(),
                "channels": [str(channel).strip().lower() for channel in item.channels if str(channel).strip()],
                "audience": item.audience,
                "frequencyCapHours": max(int(item.frequencyCapHours or 24), 1),
                "requiresContentReview": bool(item.requiresContentReview),
                "reviewStatus": item.reviewStatus,
                "variants": [
                    {
                        "key": variant.key.strip().lower(),
                        "title": variant.title.strip(),
                        "message": variant.message.strip(),
                    }
                    for variant in item.variants
                ],
            }
        )
    await replace_notification_templates(normalized_items)
    return AdminNotificationTemplateListResponse(items=await _serialize_notification_template_items(normalized_items))
