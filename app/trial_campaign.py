import asyncio
import logging
from datetime import datetime, timedelta, timezone
from bson import ObjectId

from .email_service import send_trial_campaign_email
from .push_service import notify_user
from .challenge_milestone import generate_challenge_reminder_message

logger = logging.getLogger(__name__)

GOLD_TRIAL_CONFIG_KEY = "gold_trial_config"
TRIAL_DURATION_DAYS = 5

CAMPAIGN = {
    0: ("Welcome to Victory Gold", "Hi {name}, your Gold trial is active. Ask Coach Victor one question right now to get your first win."),
    1: ("Have you set up your meal plan?", "Have you set up your meal plan yet? Takes 2 minutes."),
    2: ("See what Gold can do", "Watch your mid-trial Victory Fitness video and choose one Gold feature to try today."),
    3: ("Keep your momentum going", "{engagement_message}"),
    4: ("Your trial ends tomorrow", "Tomorrow your trial ends. Here is what you have used so far: {usage_summary}"),
    5: ("Your Gold trial is complete", "Your Gold trial has ended. Compare Silver and Gold using what you actually tried, then choose your plan."),
}

WINBACK_CAMPAIGN = {
    7: ("Still thinking about Gold?", "Your Victory Fitness trial has ended. Come back and keep building your routine."),
    14: ("Your next step is waiting", "Return to Victory Fitness and choose the Gold plan when you are ready to continue."),
}


def _as_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _trial_started_at(user: dict) -> datetime | None:
    return _as_utc(user.get("trial_start_at") or user.get("subscription_started_at"))


def _trial_ended_at(user: dict, started_at: datetime) -> datetime:
    return _as_utc(user.get("trial_end_at")) or (started_at + timedelta(days=TRIAL_DURATION_DAYS))


def _is_paid(user: dict) -> bool:
    tier = str(user.get("subscription_tier") or "").upper()
    status = str(user.get("subscription_status") or "").upper()
    return tier not in {"", "NONE"} and (bool(user.get("subscription_is_purchased")) or status in {"ACTIVE", "PAID"})


def _trial_outcome_for_user(user: dict, now: datetime) -> str | None:
    tier = str(user.get("subscription_tier") or "").upper()
    if tier in {"GOLD", "PLATINUM", "INNER_CIRCLE"} and _is_paid(user):
        return "converted_gold"
    if tier == "SILVER" and _is_paid(user):
        return "downgraded_silver"
    started_at = _trial_started_at(user)
    if started_at and now >= _trial_ended_at(user, started_at):
        return "lapsed"
    return None


async def _load_campaign_config(app_content_collection=None) -> dict:
    config = {"messages": {}, "tierLabel": "Try Gold free for 5 days"}
    if app_content_collection is None:
        return config
    try:
        record = await app_content_collection.find_one({"key": GOLD_TRIAL_CONFIG_KEY})
    except Exception:
        return config
    messages = {}
    for item in (record or {}).get("messages") or []:
        if not isinstance(item, dict):
            continue
        try:
            day = int(item.get("day"))
        except (TypeError, ValueError):
            continue
        messages[day] = item
    config["messages"] = messages
    if record and record.get("tierLabel"):
        config["tierLabel"] = str(record.get("tierLabel"))
    return config


async def _notify_admin_fallback(app_content_collection, title: str, message: str, data: dict | None = None) -> None:
    if app_content_collection is None:
        logger.warning("trial_campaign_admin_fallback title=%s message=%s", title, message)
        return
    now = datetime.now(timezone.utc)
    item = {
        "id": str(ObjectId()),
        "title": title,
        "message": message,
        "read": False,
        "createdAt": now,
        "data": data or {},
    }
    try:
        await app_content_collection.update_one(
            {"key": "dashboard_notifications"},
            {
                "$setOnInsert": {"key": "dashboard_notifications", "created_at": now},
                "$set": {"updated_at": now},
                "$push": {"items": {"$each": [item], "$slice": -100}},
            },
            upsert=True,
        )
    except Exception:
        logger.exception("trial_campaign_admin_fallback_failed")


async def _trial_usage_counts(user: dict, started_at: datetime, now: datetime, coach_threads_collection=None, nutrition_plans_collection=None, nutrition_logs_collection=None) -> dict:
    user_id = str(user.get("_id") or "")
    coach_messages = 0
    meals_logged = 0
    nutrition_plans = 0

    if coach_threads_collection is not None and user_id:
        threads = await coach_threads_collection.find({"user_id": user_id}, {"messages": 1}).to_list(length=None)
        for thread in threads:
            messages = thread.get("messages") if isinstance(thread, dict) else None
            if isinstance(messages, list):
                for message in messages:
                    if not isinstance(message, dict) or str(message.get("role") or "").lower() != "user":
                        continue
                    created_at = _as_utc(message.get("created_at"))
                    if created_at is None or started_at <= created_at <= now:
                        coach_messages += 1

    if nutrition_plans_collection is not None and user_id:
        nutrition_plans = await nutrition_plans_collection.count_documents({"user_id": user_id, "created_at": {"$gte": started_at, "$lte": now}})

    if nutrition_logs_collection is not None and user_id:
        meals_logged = await nutrition_logs_collection.count_documents({"user_id": user_id, "created_at": {"$gte": started_at, "$lte": now}})

    tracked = user.get("trial_engagement") if isinstance(user.get("trial_engagement"), dict) else {}
    coach_messages = max(coach_messages, int(tracked.get("coach_messages") or 0))
    if tracked.get("nutrition_plan_created_at"):
        nutrition_plans = max(nutrition_plans, 1)
    return {"ai_message_count": coach_messages, "nutrition_plan_count": nutrition_plans, "meal_logged_count": meals_logged}


async def _engagement_message(user: dict, started_at: datetime, now: datetime, coach_threads_collection=None, nutrition_plans_collection=None, nutrition_logs_collection=None) -> str:
    usage = await _trial_usage_counts(user, started_at, now, coach_threads_collection, nutrition_plans_collection, nutrition_logs_collection)
    coach_messages = int(usage["ai_message_count"])
    meals_or_plans = int(usage["meal_logged_count"]) + int(usage["nutrition_plan_count"])
    if coach_messages:
        return f"You have already sent {coach_messages} message{'s' if coach_messages != 1 else ''} to your coach - keep going."
    if meals_or_plans:
        return "You have started Nutrition Planner. Ask your AI Coach one question today to connect the plan to your training."
    return "You have 2 days left to try your AI Coach - ask it one question right now."


def _usage_summary_text(usage: dict) -> str:
    return (
        f"{int(usage.get('ai_message_count') or 0)} coach messages, "
        f"{int(usage.get('nutrition_plan_count') or 0)} nutrition plans, "
        f"{int(usage.get('meal_logged_count') or 0)} meals logged."
    )


async def process_trial_campaign(
    users_collection,
    challenge_memberships_collection=None,
    challenges_collection=None,
    coach_threads_collection=None,
    nutrition_plans_collection=None,
    nutrition_logs_collection=None,
    app_content_collection=None,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    processed = skipped = outcomes_updated = admin_alerts = 0
    config = await _load_campaign_config(app_content_collection)
    users = await users_collection.find({
        "marketing_consent": True,
        "trial_tier_granted": "gold",
        "trial_start_at": {"$ne": None},
    }).to_list(length=None)
    for user in users:
        started = _trial_started_at(user)
        if not started:
            skipped += 1
            continue

        current_outcome = str(user.get("trial_outcome") or "").strip()
        next_outcome = _trial_outcome_for_user(user, now)
        if next_outcome and next_outcome != current_outcome:
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"trial_outcome": next_outcome, "trial_outcome_at": now, "updated_at": now}},
            )
            outcomes_updated += 1
            user["trial_outcome"] = next_outcome
        if next_outcome in {"converted_gold", "downgraded_silver"}:
            skipped += 1
            continue

        current_day = int((now - started).total_seconds() // 86400)
        if current_day < 0:
            skipped += 1
            continue
        sent_days = {int(day) for day in (user.get("trial_campaign_sent_days") or []) if str(day).lstrip("-").isdigit()}
        due_days = sorted(day for day in set(CAMPAIGN) if day <= current_day and day not in sent_days)
        if not due_days:
            skipped += 1
            continue
        for day in due_days:
            message_config = (config.get("messages") or {}).get(day) or {}
            if message_config and message_config.get("active") is False:
                continue
            title, message_template = CAMPAIGN[day]
            title = str(message_config.get("title") or title)
            message_template = str(message_config.get("body") or message_template)
            usage = await _trial_usage_counts(user, started, now, coach_threads_collection, nutrition_plans_collection, nutrition_logs_collection)
            engagement_message = await _engagement_message(user, started, now, coach_threads_collection, nutrition_plans_collection, nutrition_logs_collection) if day == 3 else ""
            message = message_template.format(
                name=str(user.get("name") or "there"),
                engagement_message=engagement_message,
                usage_summary=_usage_summary_text(usage),
                ai_message_count=int(usage.get("ai_message_count") or 0),
                meal_logged_count=int(usage.get("meal_logged_count") or 0),
                nutrition_plan_count=int(usage.get("nutrition_plan_count") or 0),
            )
            notification_type = f"trial_day_{day}"
            data = {"route": "/notifications", "trialDay": day, "fallback": "in_app", "usage": usage}
            if day in {2, 5}:
                video_url = str(message_config.get("video_url") or "").strip()
                if video_url:
                    data.update({"contentType": "video", "videoUrl": video_url, "videoFallback": "Open the workout plan from your notification inbox."})
                else:
                    await _notify_admin_fallback(app_content_collection, "Gold trial video missing", f"Day {day} trial video is not configured. Video channel was skipped.", {"trialDay": day})
                    admin_alerts += 1
            if day == 5:
                data["route"] = "/subscription/compare"
                data["channels"] = ["push", "email"] + (["video"] if data.get("videoUrl") else [])
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
                await _notify_admin_fallback(app_content_collection, "Gold trial email failed", f"Email delivery failed for {user.get('email')} on Day {day}. In-app notification was sent.", {"userId": str(user.get("_id")), "trialDay": day})
                admin_alerts += 1
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
            time_context = "evening" if now.hour >= 18 else "daytime"
            reminder_key = f"{challenge_id}:{today_key}:{time_context}"
            marked = await users_collection.update_one({"_id": user["_id"], "challenge_reminder_dates": {"$ne": reminder_key}}, {"$addToSet": {"challenge_reminder_dates": reminder_key}})
            if marked.modified_count:
                plan_days = challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else []
                current_plan_day = next((item for item in plan_days if isinstance(item, dict) and int(item.get("day_number") or 0) == current_day), {})
                task_names = []
                sections = current_plan_day.get("sections") if isinstance(current_plan_day, dict) and isinstance(current_plan_day.get("sections"), list) else []
                for section in sections:
                    if not isinstance(section, dict):
                        continue
                    section_title = str(section.get("title") or section.get("name") or "").strip()
                    if section_title:
                        task_names.append(section_title)
                    exercises = section.get("exercises") if isinstance(section.get("exercises"), list) else []
                    for exercise in exercises:
                        if isinstance(exercise, dict):
                            exercise_name = str(exercise.get("name") or exercise.get("title") or "").strip()
                            if exercise_name:
                                task_names.append(exercise_name)
                task_context = ", ".join(task_names[:5])
                reminder_message = await asyncio.to_thread(generate_challenge_reminder_message, str(user.get("name") or "there"), str(challenge.get("title") or "your challenge"), current_day, task_context, time_context)
                reminder_title = "You still have time today" if time_context == "evening" else "Your challenge task is waiting"
                await notify_user(users_collection, user, reminder_title, reminder_message, "challenge_reminder", {"type": "challenge", "challengeId": challenge_id, "day": current_day, "timeContext": time_context, "route": f"/challenges/progress/{challenge_id}", "taskContext": task_context})
                challenge_reminders += 1
    return {"processed": processed, "skipped": skipped, "outcomes_updated": outcomes_updated, "admin_alerts": admin_alerts, "challenge_reminders": challenge_reminders}
