import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jose import jwt

from .config import settings
from .conversion_service import get_notification_template, is_notification_template_approved, log_notification_event, resolve_notification_variant
from .email_service import send_notification_email

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
FIREBASE_TOKEN_URL = "https://oauth2.googleapis.com/token"
FIREBASE_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_firebase_access_token: str | None = None
_firebase_access_token_expires_at = 0.0
logger = logging.getLogger(__name__)
_notification_event_listeners = set()


def _has_firebase_web_push_credentials() -> bool:
    return bool(
        str(settings.firebase_project_id or "").strip()
        and str(settings.firebase_client_email or "").strip()
        and str(settings.firebase_private_key or "").strip()
    )


def subscribe_notification_events(listener):
    _notification_event_listeners.add(listener)

    def unsubscribe() -> None:
        _notification_event_listeners.discard(listener)

    return unsubscribe


def _serialize_notification_for_event(notification: dict) -> dict:
    created_at = notification.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "id": str(notification.get("id") or ""),
        "type": str(notification.get("type") or ""),
        "title": str(notification.get("title") or ""),
        "message": str(notification.get("message") or ""),
        "data": notification.get("data") if isinstance(notification.get("data"), dict) else {},
        "created_at": created_at,
        "read": bool(notification.get("read")),
    }


async def _emit_notification_event(user_id: str, notification: dict) -> None:
    if not _notification_event_listeners:
        return

    payload = {
        "type": "notification_created",
        "notification": _serialize_notification_for_event(notification),
    }
    results = await asyncio.gather(
        *(listener(user_id, payload) for listener in list(_notification_event_listeners)),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Notification event listener failed: %s", result, exc_info=result)


async def notify_user(users_collection, user: dict, title: str, message: str, notification_type: str, data: dict) -> dict:
    notification_id = str(uuid4())
    if not await is_notification_template_approved(notification_type):
        await log_notification_event(str(user["_id"]), notification_id, notification_type, "blocked", "blocked_unapproved")
        return {"status": "blocked_unapproved", "providers": [], "failedProviders": [], "updatedAt": datetime.now(timezone.utc)}
    template = await get_notification_template(notification_type)
    template_channels = [str(channel).strip().lower() for channel in ((template or {}).get("channels") or []) if str(channel).strip()]
    template_channels = template_channels or ["push"]
    if template and str(template.get("audience") or "member") == "member":
        template_prefs = user.get("notification_template_preferences") if isinstance(user.get("notification_template_preferences"), dict) else {}
        if not bool((template_prefs.get(notification_type) or {}).get("enabled", True)):
            await log_notification_event(str(user["_id"]), notification_id, notification_type, "blocked", "blocked_user_disabled")
            return {"status": "blocked_user_disabled", "providers": [], "failedProviders": [], "updatedAt": datetime.now(timezone.utc)}
        user_enabled_channels = set()
        if user.get("notification_push_enabled", True):
            user_enabled_channels.add("push")
        if user.get("notification_whatsapp_enabled"):
            user_enabled_channels.add("whatsapp")
        if user.get("notification_email_enabled"):
            user_enabled_channels.add("email")
        if not bool(user_enabled_channels & set(template_channels)):
            await log_notification_event(str(user["_id"]), notification_id, notification_type, "blocked", "blocked_user_muted")
            return {"status": "blocked_user_muted", "providers": [], "failedProviders": [], "updatedAt": datetime.now(timezone.utc)}
    resolved_title, resolved_message, copy_variant = await resolve_notification_variant(user, notification_type, title, message)
    notification_data = {**data, "notificationId": notification_id, "copyVariant": copy_variant}
    notification = {"id": notification_id, "type": notification_type, "title": resolved_title, "message": resolved_message, "data": notification_data, "copy_variant": copy_variant, "created_at": datetime.now(timezone.utc), "read": False, "delivery": {"status": "queued", "providers": []}}
    await users_collection.update_one({"_id": user["_id"]}, {"$push": {"app_notifications": {"$each": [notification], "$slice": -50}}})
    await _emit_notification_event(str(user["_id"]), notification)
    await log_notification_event(str(user["_id"]), notification_id, notification_type, copy_variant, "queued")
    push_enabled = bool(user.get("notification_push_enabled", True))
    expo_tokens = [str(item.get("token")) for item in (user.get("push_tokens") or []) if push_enabled and isinstance(item, dict) and str(item.get("platform") or "").lower() != "web" and str(item.get("token") or "").startswith("ExponentPushToken[")]
    web_tokens = [str(item.get("token")) for item in (user.get("push_tokens") or []) if push_enabled and isinstance(item, dict) and str(item.get("platform") or "").lower() == "web" and str(item.get("token") or "").strip()]
    tasks = []
    providers = []
    if "push" in template_channels and expo_tokens:
        providers.append("expo")
        tasks.append(asyncio.to_thread(_send_expo_push, list(dict.fromkeys(expo_tokens)), resolved_title, resolved_message, notification_data))
    if "push" in template_channels and web_tokens and _has_firebase_web_push_credentials():
        providers.append("firebase")
        tasks.append(asyncio.to_thread(_send_firebase_web_push, list(dict.fromkeys(web_tokens)), resolved_title, resolved_message, notification_data))
    elif "push" in template_channels and web_tokens:
        logger.info("Skipping Firebase web push delivery because service-account credentials are not configured")
    email = str(user.get("email") or "").strip()
    if "email" in template_channels and user.get("notification_email_enabled") and email:
        providers.append("email")
        tasks.append(asyncio.to_thread(
            send_notification_email,
            to_email=email,
            name=str(user.get("name") or user.get("full_name") or "there"),
            subject=resolved_title,
            body=resolved_message,
            flow=f"notification_{notification_type}",
        ))
    delivery_status = "inbox_only" if not tasks else "sent"
    failed_providers = []
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for provider, result in zip(providers, results):
            if isinstance(result, Exception):
                # The notification is already stored in the app inbox. A provider
                # failure must not turn the admin action into a 500.
                logger.error("Push provider delivery failed: %s", result, exc_info=result)
                failed_providers.append(provider)
        if failed_providers and len(failed_providers) == len(providers):
            delivery_status = "failed"
        elif failed_providers:
            delivery_status = "partial"
    delivery = {"status": delivery_status, "providers": providers, "failedProviders": failed_providers, "updatedAt": datetime.now(timezone.utc)}
    await users_collection.update_one(
        {"_id": user["_id"], "app_notifications.id": notification["id"]},
        {"$set": {"app_notifications.$.delivery": delivery}},
    )
    await log_notification_event(str(user["_id"]), notification_id, notification_type, copy_variant, delivery_status)
    return delivery


def _send_expo_push(tokens: list[str], title: str, body: str, data: dict) -> None:
    if not tokens:
        return
    messages = [{"to": token, "sound": "default", "title": title, "body": body, "data": data} for token in tokens]
    request = Request(EXPO_PUSH_URL, data=json.dumps(messages).encode("utf-8"), headers={"Accept": "application/json", "Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=15) as response:
        response.read()


def _get_firebase_access_token() -> str:
    global _firebase_access_token, _firebase_access_token_expires_at
    now = datetime.now(timezone.utc).timestamp()
    if _firebase_access_token and now < _firebase_access_token_expires_at - 60:
        return _firebase_access_token

    client_email = str(settings.firebase_client_email or "").strip()
    private_key = str(settings.firebase_private_key or "").replace("\\n", "\n").strip()
    if not client_email or not private_key or not settings.firebase_project_id:
        raise RuntimeError("Firebase web push service-account credentials are not configured")

    issued_at = int(now)
    assertion = jwt.encode(
        {
            "iss": client_email,
            "scope": FIREBASE_SCOPE,
            "aud": FIREBASE_TOKEN_URL,
            "iat": issued_at,
            "exp": issued_at + 3600,
        },
        private_key,
        algorithm="RS256",
    )
    request = Request(
        FIREBASE_TOKEN_URL,
        data=(f"grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion={assertion}").encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Firebase token exchange failed ({error.code}): {details}") from error
    _firebase_access_token = str(token_data["access_token"])
    _firebase_access_token_expires_at = now + int(token_data.get("expires_in") or 3600)
    return _firebase_access_token


def _send_firebase_web_push(tokens: list[str], title: str, body: str, data: dict) -> None:
    if not tokens:
        return

    access_token = _get_firebase_access_token()
    endpoint = f"https://fcm.googleapis.com/v1/projects/{settings.firebase_project_id}/messages:send"
    failures: list[str] = []
    for token in tokens:
        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": {key: str(value) for key, value in data.items()},
                "webpush": {"fcm_options": {"link": "/notifications"}},
            }
        }
        request = Request(
            endpoint,
            data=json.dumps(message).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                response.read()
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:500]
            failures.append(f"{token[:12]}… ({error.code}): {details}")
        except Exception as error:
            failures.append(f"{token[:12]}…: {error}")

    if failures:
        raise RuntimeError(f"Firebase web push failed for {len(failures)} token(s): {'; '.join(failures[:3])}")


async def notify_users_of_published_workout(users_collection, workout: dict) -> None:
    records = await users_collection.find({"is_admin": {"$ne": True}}).to_list(length=None)
    title = "New workout available"
    message = f"{str(workout.get('title') or 'A new workout')} is now available in Victory Fitness."
    data = {"type": "workout", "workoutId": str(workout.get("_id") or ""), "route": "/workout"}
    concurrency = max(int(getattr(settings, "push_notification_concurrency", 50) or 50), 1)
    semaphore = asyncio.Semaphore(concurrency)

    async def _send(user: dict) -> None:
        async with semaphore:
            await notify_user(users_collection, user, title, message, "workout_published", data)

    await asyncio.gather(*(_send(user) for user in records), return_exceptions=True)
