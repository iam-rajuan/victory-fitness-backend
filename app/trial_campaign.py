import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .email_service import send_trial_campaign_email
from .push_service import _send_expo_push

logger = logging.getLogger(__name__)

CAMPAIGN = {
    0: ("Welcome to Victory Gold", "Your trial is active. Ask Coach Victor one question right now to get your first win."),
    1: ("Have you set up your meal plan?", "Your personalized Nutrition Planner takes about two minutes to set up."),
    2: ("See what Gold can do", "Watch your mid-trial Victory Fitness video and choose one feature to try today."),
    3: ("Keep your momentum going", "Check in with Coach Victor or your Nutrition Planner today to keep your progress moving."),
    4: ("Your trial ends tomorrow", "Review what you have used so far and get ready to choose your Gold plan."),
    5: ("Your Gold trial is complete", "Your trial has ended. Keep your coaching, nutrition, and workout tools by choosing a plan."),
}


async def process_trial_campaign(users_collection) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    processed = skipped = 0
    users = await users_collection.find({"marketing_consent": True, "subscription_started_at": {"$ne": None}}).to_list(length=None)
    for user in users:
        started = user.get("subscription_started_at")
        if not isinstance(started, datetime):
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        day = int((now - started).total_seconds() // 86400)
        if day < 0 or day > 5 or day in set(user.get("trial_campaign_sent_days") or []):
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
    return {"processed": processed, "skipped": skipped}
