from __future__ import annotations

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


def _serialize_notification_template_items(templates: list[dict]) -> list[AdminNotificationTemplateItem]:
    return [
        AdminNotificationTemplateItem(
            id=str(item.get("id") or item.get("type") or ""),
            type=str(item.get("type") or "").strip(),
            title=str(item.get("title") or "").strip(),
            frequencyCapHours=max(int(item.get("frequencyCapHours") or 24), 1),
            variants=[
                NotificationTemplateVariantItem(
                    key=str(variant.get("key") or "a").strip().lower(),
                    title=str(variant.get("title") or "").strip(),
                    message=str(variant.get("message") or "").strip(),
                )
                for variant in (item.get("variants") or [])
                if isinstance(variant, dict)
            ],
        )
        for item in templates
    ]

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
    return AdminNotificationTemplateListResponse(items=_serialize_notification_template_items(templates))


@router.put("/admin/notification-templates", response_model=AdminNotificationTemplateListResponse)
async def admin_replace_notification_templates(
    payload: list[AdminNotificationTemplateRequest],
    _: dict = Depends(_require_admin_user),
) -> AdminNotificationTemplateListResponse:
    normalized_items = []
    for item in payload:
        normalized_items.append(
            {
                "id": item.id.strip(),
                "type": item.type.strip(),
                "title": item.title.strip(),
                "frequencyCapHours": max(int(item.frequencyCapHours or 24), 1),
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
    return AdminNotificationTemplateListResponse(items=_serialize_notification_template_items(normalized_items))
