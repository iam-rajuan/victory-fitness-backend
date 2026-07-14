import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from bson import ObjectId

from .email_service import send_trial_campaign_email
from .push_service import _send_expo_push
from .push_service import notify_user

logger = logging.getLogger(__name__)

CAMPAIGN = {
    0: ("Welcome to Victory Gold", "Your trial is active. Ask Coach Victor one question right now to get your first win."),
    1: ("Have you set up your meal plan?", "Your personalized Nutrition Planner takes about two minutes to set up."),
    2: ("See what Gold can do", "Watch your mid-trial Victory Fitness video and choose one feature to try today."),
    3: ("Keep your momentum going", "Check in with Coach Victor or your Nutrition Planner today to keep your progress moving."),
    4: ("Your trial ends tomorrow", "Review what you have used so far and get ready to choose your Gold plan."),
    5: ("Your Gold trial is complete", "Your trial has ended. Keep your coaching, nutrition, and workout tools by choosing a plan."),
}


async def process_trial_campaign(users_collection, challenge_memberships_collection=None, challenges_collection=None) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    processed = skipped = 0
    users = await users_collection.find({"marketing_consent": True, "subscription_started_at": {"$ne": None}}).to_list(length=None)
    for user in users:
        if bool(user.get("subscription_is_purchased")) or str(user.get("subscription_status") or "").upper() in {"ACTIVE", "PAID", "CANCELLED"}:
            skipped += 1
            continue
        started = user.get("subscription_started_at")
        if not isinstance(started, datetime):
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        day = int((now - started).total_seconds() // 86400)
        if day < 0 or day > 5 or day in set(user.get("trial_campaign_sent_days") or []):
            skipped += 1
            continue
        due_at = started + timedelta(days=day)
        if now < due_at:
            skipped += 1
            continue
        title, message = CAMPAIGN[day]
        item = {"id": str(uuid4()), "type": f"trial_day_{day}", "title": title, "message": message, "data": {"route": "/notifications", "trialDay": day}, "created_at": now, "read": False}
        await users_collection.update_one(
            {"_id": user["_id"], "marketing_consent": True},
            {"$push": {"app_notifications": {"$each": [item], "$slice": -50}, "trial_campaign_sent_days": day}},
        )
        tokens = [str(token.get("token")) for token in (user.get("push_tokens") or []) if isinstance(token, dict) and str(token.get("platform") or "").lower() != "web" and str(token.get("token") or "").startswith("ExponentPushToken[")]
        if tokens:
            await asyncio.to_thread(_send_expo_push, list(dict.fromkeys(tokens)), title, message, item["data"])
        try:
            await asyncio.to_thread(send_trial_campaign_email, str(user.get("email") or ""), str(user.get("name") or "there"), day, title, message)
        except Exception:
            logger.exception("trial_campaign_email_failed user_id=%s day=%s", user.get("_id"), day)
        processed += 1
    challenge_reminders = 0
    if challenge_memberships_collection is not None and challenges_collection is not None:
        memberships = await challenge_memberships_collection.find({"status": "ACTIVE"}).to_list(length=None)
        today_key = now.date().isoformat()
        for membership in memberships:
            user_id = str(membership.get("user_id") or "")
            challenge_id = str(membership.get("challenge_id") or "")
            if not ObjectId.is_valid(user_id) or not challenge_id:
                continue
            progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}
            started_at = membership.get("started_at")
            current_day = 1
            if isinstance(started_at, datetime):
                current_day = max((now.date() - started_at.date()).days + 1, 1)
            if bool((progress.get(str(current_day)) or {}).get("completed")):
                continue
            user = await users_collection.find_one({"_id": ObjectId(user_id), "is_admin": {"$ne": True}})
            challenge = await challenges_collection.find_one({"_id": ObjectId(challenge_id)}) if ObjectId.is_valid(challenge_id) else None
            if not user or not challenge:
                continue
            total_days = max(int(challenge.get("duration_days") or 0), 1)
            if current_day > total_days:
                await challenge_memberships_collection.update_one(
                    {"_id": membership.get("_id")},
                    {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}},
                )
                continue
            reminder_key = f"{challenge_id}:{today_key}"
            marked = await users_collection.update_one({"_id": user["_id"], "challenge_reminder_dates": {"$ne": reminder_key}}, {"$addToSet": {"challenge_reminder_dates": reminder_key}})
            if marked.modified_count:
                await notify_user(users_collection, user, "Finish today’s challenge", f"Complete day {current_day} of {str(challenge.get('title') or 'your challenge')} today or risk losing your points.", "challenge_reminder", {"type": "challenge", "challengeId": challenge_id, "day": current_day})
                challenge_reminders += 1
    return {"processed": processed, "skipped": skipped, "challenge_reminders": challenge_reminders}
