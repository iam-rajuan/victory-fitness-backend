from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import (
    app_content_collection,
    completion_cards_collection,
    notification_events_collection,
    users_collection,
)

NOTIFICATION_TEMPLATES_KEY = "notification_templates"
DEFAULT_NOTIFICATION_TEMPLATES = [
    {
        "id": "workout_reminder",
        "type": "workout_reminder",
        "title": "Workout reminder",
        "frequencyCapHours": 24,
        "variants": [
            {"key": "a", "title": "Your next workout is waiting", "message": "Keep your rhythm going with one focused session today."},
            {"key": "b", "title": "Momentum fades when today goes quiet", "message": "A short workout today protects the progress you already earned."},
            {"key": "c", "title": "Others are staying on track today", "message": "Open Victory Fitness and keep pace with the people building consistency."},
        ],
    },
    {
        "id": "protein_nudge",
        "type": "protein_nudge",
        "title": "Protein nudge",
        "frequencyCapHours": 24,
        "variants": [
            {"key": "a", "title": "Protein target check", "message": "A protein-focused meal now makes the rest of your day easier."},
            {"key": "b", "title": "Don’t leave recovery to chance", "message": "Missing protein today makes tomorrow’s recovery harder than it needs to be."},
            {"key": "c", "title": "Most consistent members do this early", "message": "Lock in one protein-rich meal and keep your recovery standard high."},
        ],
    },
]


def _bucket(*parts: str, modulo: int) -> int:
    seed = ":".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def assign_invite_variant(inviter_user_id: str) -> str:
    return "a" if _bucket(inviter_user_id, modulo=2) == 0 else "b"


def assign_notification_variant(user_id: str, notification_type: str, variant_count: int) -> int:
    return _bucket(user_id, notification_type, modulo=max(variant_count, 1))


async def should_show_post_workout_upsell(user: dict) -> tuple[bool, str]:
    tier = str(user.get("subscription_tier") or "").upper()
    if tier not in {"SILVER", "GOLD"}:
        return False, "tier_not_eligible"
    workout_count = int(user.get("workouts_completed") or 0)
    if workout_count <= 1:
        return False, "first_workout"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    last_prompt = await completion_cards_collection.find_one(
        {
            "user_id": str(user.get("_id") or ""),
            "upsell_shown": True,
            "created_at": {"$gte": cutoff},
        },
        sort=[("created_at", -1)],
    )
    if last_prompt:
        return False, "cooldown"
    return True, "eligible"


def build_post_workout_upsell_message(user: dict) -> tuple[str, str]:
    streak = max(int(user.get("streak_days") or 0), 0)
    title = "Keep this streak moving"
    message = f"You just finished a workout with a {streak}-day streak. Unlock unlimited AI coaching to keep this going."
    return title, message


async def ensure_notification_templates() -> list[dict[str, Any]]:
    if not app_content_collection:
        return [dict(item) for item in DEFAULT_NOTIFICATION_TEMPLATES]
    now = datetime.now(timezone.utc)
    await app_content_collection.update_one(
        {"key": NOTIFICATION_TEMPLATES_KEY},
        {
            "$setOnInsert": {
                "key": NOTIFICATION_TEMPLATES_KEY,
                "items": DEFAULT_NOTIFICATION_TEMPLATES,
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    record = await app_content_collection.find_one({"key": NOTIFICATION_TEMPLATES_KEY})
    return [dict(item) for item in (record or {}).get("items") or [] if isinstance(item, dict)]


async def list_notification_templates() -> list[dict[str, Any]]:
    return await ensure_notification_templates()


async def replace_notification_templates(items: list[dict[str, Any]]) -> None:
    if not app_content_collection:
        return
    now = datetime.now(timezone.utc)
    await app_content_collection.update_one(
        {"key": NOTIFICATION_TEMPLATES_KEY},
        {"$set": {"key": NOTIFICATION_TEMPLATES_KEY, "items": [dict(item) for item in items], "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


async def resolve_notification_variant(user: dict, notification_type: str, fallback_title: str, fallback_message: str) -> tuple[str, str, str]:
    templates = await list_notification_templates()
    template = next((item for item in templates if str(item.get("type") or "").strip() == notification_type), None)
    if not template:
        return fallback_title, fallback_message, "a"
    variants = [dict(item) for item in template.get("variants") or [] if isinstance(item, dict)]
    if not variants:
        return fallback_title, fallback_message, "a"
    index = assign_notification_variant(str(user.get("_id") or ""), notification_type, len(variants))
    chosen = variants[index]
    return (
        str(chosen.get("title") or fallback_title).strip() or fallback_title,
        str(chosen.get("message") or fallback_message).strip() or fallback_message,
        str(chosen.get("key") or "a").strip() or "a",
    )


async def log_notification_event(user_id: str, notification_id: str, notification_type: str, copy_variant: str, status: str, *, action_taken: bool = False) -> None:
    if not notification_events_collection:
        return
    await notification_events_collection.insert_one(
        {
            "user_id": user_id,
            "notification_id": notification_id,
            "type": notification_type,
            "copy_variant": copy_variant,
            "status": status,
            "action_taken": bool(action_taken),
            "created_at": datetime.now(timezone.utc),
        }
    )


async def mark_notification_event_opened(user_id: str, notification_id: str) -> None:
    if not notification_events_collection:
        return
    await notification_events_collection.update_one(
        {"user_id": user_id, "notification_id": notification_id},
        {"$set": {"status": "opened", "opened_at": datetime.now(timezone.utc)}},
    )


async def mark_notification_event_actioned(user_id: str, notification_id: str) -> None:
    if not notification_events_collection:
        return
    await notification_events_collection.update_one(
        {"user_id": user_id, "notification_id": notification_id},
        {"$set": {"action_taken": True, "action_at": datetime.now(timezone.utc)}},
    )
