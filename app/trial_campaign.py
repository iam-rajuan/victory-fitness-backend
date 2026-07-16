import asyncio
import logging
from datetime import datetime, timedelta, timezone
from bson import ObjectId

from .email_service import send_trial_campaign_email
from .push_service import notify_user

logger = logging.getLogger(__name__)

CAMPAIGN = {
    0: ("Welcome to Victory Gold", "Hi {name}, your Gold trial is active. Ask Coach Victor one question right now to get your first win."),
    1: ("Have you set up your meal plan?", "Your personalized Nutrition Planner takes about two minutes to set up."),
    2: ("See what Gold can do", "Watch your mid-trial Victory Fitness video and choose one feature to try today."),
    3: ("Keep your momentum going", "{engagement_message}"),
    4: ("Your trial ends tomorrow", "Review what you have used so far and get ready to choose your Gold plan."),
    5: ("Your Gold trial is complete", "Your trial has ended. Keep your coaching, nutrition, and workout tools by choosing a plan."),
}

WINBACK_CAMPAIGN = {
    7: ("Still thinking about Gold?", "Your Victory Fitness trial has ended. Come back and keep building your routine."),
    14: ("Your next step is waiting", "Return to Victory Fitness and choose the Gold plan when you are ready to continue."),
}


async def _engagement_message(user: dict, coach_threads_collection=None, nutrition_plans_collection=None) -> str:
    user_id = str(user.get("_id") or "")
    coach_messages = 0
    has_nutrition_plan = False

    if coach_threads_collection is not None and user_id:
        threads = await coach_threads_collection.find({"user_id": user_id}, {"messages": 1}).to_list(length=None)
        for thread in threads:
            messages = thread.get("messages") if isinstance(thread, dict) else None
            if isinstance(messages, list):
                coach_messages += sum(1 for message in messages if isinstance(message, dict) and str(message.get("role") or "").lower() == "user")

    if nutrition_plans_collection is not None and user_id:
        has_nutrition_plan = bool(await nutrition_plans_collection.find_one({"user_id": user_id}, {"_id": 1}))

    if coach_messages and has_nutrition_plan:
        return f"You have sent {coach_messages} message{'s' if coach_messages != 1 else ''} to Coach Victor and set up your nutrition plan. Keep going today."
    if coach_messages:
        return f"You have already sent {coach_messages} message{'s' if coach_messages != 1 else ''} to Coach Victor. Keep going and set up your Nutrition Planner today."
    if has_nutrition_plan:
        return "You have started your Nutrition Planner. Open Coach Victor today to keep your progress moving."
    return "You have not tried Coach Victor or the Nutrition Planner yet. Open one today before your trial gets away from you."


async def process_trial_campaign(
    users_collection,
    challenge_memberships_collection=None,
    challenges_collection=None,
    coach_threads_collection=None,
    nutrition_plans_collection=None,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    processed = skipped = 0
    users = await users_collection.find({"marketing_consent": True, "subscription_started_at": {"$ne": None}}).to_list(length=None)
    for user in users:
        if bool(user.get("subscription_is_purchased")) or str(user.get("subscription_status") or "").upper() in {"ACTIVE", "PAID"}:
            skipped += 1
            continue
        started = user.get("subscription_started_at")
        if not isinstance(started, datetime):
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        current_day = int((now - started).total_seconds() // 86400)
        if current_day < 0:
            skipped += 1
            continue
        sent_days = {int(day) for day in (user.get("trial_campaign_sent_days") or []) if str(day).lstrip("-").isdigit()}
        due_days = sorted(day for day in (set(CAMPAIGN) | set(WINBACK_CAMPAIGN)) if day <= current_day and day not in sent_days)
        if not due_days:
            skipped += 1
            continue
        for day in due_days:
            if day in CAMPAIGN:
                title, message_template = CAMPAIGN[day]
                engagement_message = await _engagement_message(user, coach_threads_collection, nutrition_plans_collection) if day == 3 else ""
                message = message_template.format(name=str(user.get("name") or "there"), engagement_message=engagement_message)
                notification_type = f"trial_day_{day}"
                data = {"route": "/notifications", "trialDay": day, "fallback": "in_app"}
                if day in {2, 5}:
                    data.update({"contentType": "video", "videoRoute": "/workoutplan/video-plan", "videoFallback": "Open the workout plan from your notification inbox."})
                if day == 5:
                    data["channels"] = ["push", "email", "video"]
            else:
                title, message = WINBACK_CAMPAIGN[day]
                notification_type = f"trial_winback_day_{day}"
                data = {"route": "/notifications", "trialDay": day, "winback": True, "fallback": "in_app"}
            # notify_user always writes the in-app inbox first. Only mark the
            # day sent after that succeeds, so a transient failure is retried.
            await notify_user(users_collection, user, title, message, notification_type, data)
            await users_collection.update_one(
                {"_id": user["_id"], "marketing_consent": True},
                {"$addToSet": {"trial_campaign_sent_days": day}},
            )
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
