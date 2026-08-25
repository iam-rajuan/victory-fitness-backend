from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from .database import (
    accountability_pairs_collection,
    coach_victor_threads_collection,
    meal_analysis_entries_collection,
    nutrition_plans_collection,
    users_collection,
    workout_logs_collection,
)
from .email_service import send_retention_email
from .push_service import notify_user

logger = logging.getLogger(__name__)

RETENTION_NOTIFICATION_WINDOW_DAYS = 14
DEFAULT_NOTIFICATION_HOUR = 18
WEEKLY_DIGEST_TARGET_HOUR = 8
ACCOUNTABILITY_NUDGE_HOUR = 20
RETENTION_STATE_PATH = "retention"
COMEBACK_DAYS = (3, 7, 14, 30)

COUNTRY_TIMEZONE_OFFSETS = {
    "DE": 2.0,
    "GH": 0.0,
    "IN": 5.5,
}


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _local_time_for_user(user: dict, moment: datetime) -> datetime:
    offset_hours = COUNTRY_TIMEZONE_OFFSETS.get(str(user.get("country_code") or "").upper(), 0.0)
    offset_minutes = int(offset_hours * 60)
    return moment.astimezone(timezone(timedelta(minutes=offset_minutes)))


def _retention_state(user: dict) -> dict[str, Any]:
    value = user.get(RETENTION_STATE_PATH)
    return dict(value) if isinstance(value, dict) else {}


def _notification_timing_state(user: dict) -> dict[str, Any]:
    return dict(_retention_state(user).get("notification_timing") or {})


def _comeback_state(user: dict) -> dict[str, Any]:
    return dict(_retention_state(user).get("comeback_flow") or {})


def _weekly_digest_state(user: dict) -> dict[str, Any]:
    return dict(_retention_state(user).get("weekly_digest") or {})


def _optimal_send_hour_from_history(history: list[dict[str, Any]]) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_NOTIFICATION_WINDOW_DAYS)
    counter: Counter[int] = Counter()
    for item in history:
        if not isinstance(item, dict):
            continue
        opened_at = _as_utc(item.get("opened_at"))
        if opened_at is None or opened_at < cutoff:
            continue
        try:
            hour = int(item.get("local_open_hour"))
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23:
            counter[hour] += 1
    if not counter:
        return DEFAULT_NOTIFICATION_HOUR
    return sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


async def record_notification_open(user: dict, notification_id: str, *, opened_at: datetime | None = None) -> None:
    opened_at = opened_at or datetime.now(timezone.utc)
    notifications = [item for item in (user.get("app_notifications") or []) if isinstance(item, dict)]
    target = next((item for item in notifications if str(item.get("id") or "") == notification_id), None)
    if target is None:
        return

    sent_at = _as_utc(target.get("created_at"))
    local_opened = _local_time_for_user(user, opened_at)
    entry = {
        "notification_id": notification_id,
        "notification_type": str(target.get("type") or ""),
        "opened_at": opened_at,
        "sent_at": sent_at,
        "local_open_hour": local_opened.hour,
        "response_minutes": (
            max(int((opened_at - sent_at).total_seconds() // 60), 0)
            if sent_at is not None
            else None
        ),
    }

    timing_state = _notification_timing_state(user)
    history = [item for item in timing_state.get("open_history") or [] if isinstance(item, dict)]
    history.append(entry)
    history = history[-100:]
    optimal_hour = _optimal_send_hour_from_history(history)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                f"{RETENTION_STATE_PATH}.notification_timing.open_history": history,
                f"{RETENTION_STATE_PATH}.notification_timing.optimal_send_hour": optimal_hour,
                f"{RETENTION_STATE_PATH}.notification_timing.last_opened_at": opened_at,
                "updated_at": opened_at,
            }
        },
    )


def _notification_target_hour(user: dict) -> int:
    timing_state = _notification_timing_state(user)
    try:
        hour = int(timing_state.get("optimal_send_hour"))
    except (TypeError, ValueError):
        hour = DEFAULT_NOTIFICATION_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_NOTIFICATION_HOUR


def _is_paid_user(user: dict) -> bool:
    tier = str(user.get("subscription_tier") or "").upper()
    status = str(user.get("subscription_status") or "").upper()
    return tier not in {"", "NONE"} and (bool(user.get("subscription_is_purchased")) or status in {"ACTIVE", "PAID"})


async def _trial_usage_snapshot(user: dict, start: datetime, end: datetime) -> dict[str, int]:
    user_id = str(user.get("_id") or "")
    if not user_id:
        return {"workouts": 0, "coach_messages": 0, "nutrition_actions": 0}

    workouts = await workout_logs_collection.count_documents(
        {"user_id": user_id, "started_at": {"$gte": start, "$lte": end}, "status": "completed"}
    )
    nutrition_actions = await nutrition_plans_collection.count_documents(
        {"user_id": user_id, "created_at": {"$gte": start, "$lte": end}}
    )
    nutrition_actions += await meal_analysis_entries_collection.count_documents(
        {"user_id": user_id, "created_at": {"$gte": start, "$lte": end}}
    )
    coach_messages = 0
    threads = await coach_victor_threads_collection.find({"user_id": user_id}, {"recent_messages": 1, "messages": 1}).to_list(length=None)
    for thread in threads:
        messages = thread.get("recent_messages") if isinstance(thread.get("recent_messages"), list) else thread.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict) or str(message.get("role") or "").lower() != "user":
                continue
            created_at = _as_utc(message.get("created_at"))
            if created_at is None or not (start <= created_at <= end):
                continue
            coach_messages += 1
    return {"workouts": workouts, "coach_messages": coach_messages, "nutrition_actions": nutrition_actions}


def _build_digest_message(user: dict, usage: dict[str, int], start: datetime, end: datetime) -> tuple[str, str]:
    name = str(user.get("name") or "there").strip() or "there"
    motivation_statement = str(user.get("motivation_statement") or "").strip()
    workout_count = int(usage.get("workouts") or 0)
    coach_count = int(usage.get("coach_messages") or 0)
    nutrition_count = int(usage.get("nutrition_actions") or 0)
    streak = int(user.get("streak_days") or 0)
    summary_parts = []
    if workout_count:
        summary_parts.append(f"{workout_count} completed workout{'s' if workout_count != 1 else ''}")
    if coach_count:
        summary_parts.append(f"{coach_count} AI coach check-in{'s' if coach_count != 1 else ''}")
    if nutrition_count:
        summary_parts.append(f"{nutrition_count} nutrition action{'s' if nutrition_count != 1 else ''}")
    if not summary_parts:
        summary_parts.append("a quiet week inside the app")
    summary_text = ", ".join(summary_parts)
    subject = "Victory Fitness — Your weekly AI coaching digest"
    body = (
        f"{name}, here is your coaching digest for the last 7 days.\n\n"
        f"{f'You said you want to {motivation_statement}. Keep using that as your anchor this week.\\n\\n' if motivation_statement else ''}"
        f"You logged {summary_text} between {start.strftime('%B %d, %Y')} and {end.strftime('%B %d, %Y')}.\n"
        f"Your current streak is {streak} day{'s' if streak != 1 else ''}.\n\n"
        "Next best move:\n"
        + (
            "Keep your current momentum and schedule your next session today."
            if workout_count >= 3 or coach_count >= 2
            else "Book one workout, open the coach once, and lock in one nutrition action this week."
        )
    )
    return subject, body


async def _send_weekly_digest(now: datetime) -> int:
    processed = 0
    users = await users_collection.find(
        {
            "$or": [
                {"subscription_status": "ACTIVE"},
                {"trial_tier_granted": "gold", "trial_outcome": {"$in": [None, ""]}},
                {"subscription_purchase_source": "beta_trial"},
            ]
        }
    ).to_list(length=None)
    for user in users:
        local_now = _local_time_for_user(user, now)
        if local_now.weekday() != 0 or local_now.hour < WEEKLY_DIGEST_TARGET_HOUR:
            continue
        week_key = f"{local_now.isocalendar().year}-W{local_now.isocalendar().week:02d}"
        digest_state = _weekly_digest_state(user)
        if str(digest_state.get("last_sent_week") or "") == week_key:
            continue
        end = now
        start = now - timedelta(days=7)
        usage = await _trial_usage_snapshot(user, start, end)
        subject, body = _build_digest_message(user, usage, start, end)
        await notify_user(
            users_collection,
            user,
            subject.replace("Victory Fitness — ", ""),
            body,
            "weekly_ai_digest",
            {"route": "/notifications", "weekKey": week_key, "usage": usage},
        )
        if bool(user.get("marketing_consent")) and str(user.get("email") or "").strip():
            try:
                await asyncio.to_thread(
                    send_retention_email,
                    to_email=str(user.get("email") or ""),
                    name=str(user.get("name") or "there"),
                    subject=subject,
                    body=body,
                    flow="weekly_ai_digest",
                )
            except Exception:
                logger.exception("weekly_digest_email_failed user_id=%s", user.get("_id"))
        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    f"{RETENTION_STATE_PATH}.weekly_digest.last_sent_week": week_key,
                    f"{RETENTION_STATE_PATH}.weekly_digest.last_sent_at": now,
                    "updated_at": now,
                }
            },
        )
        processed += 1
    return processed


def _build_comeback_message(day: int, usage: dict[str, int]) -> tuple[str, str]:
    if day == 3:
        return ("Your routine is easier to restart today", "Come back today for one simple win. Open your next workout and rebuild momentum before the week slips away.")
    if day == 7:
        return (
            "Your AI coach is ready when you are",
            f"You previously used the AI coach {usage.get('coach_messages', 0)} time(s). Open Victory Fitness, ask one direct question, and let the coach restart your week with a concrete next step.",
        )
    if day == 14:
        return ("Two weeks away is enough", "Your structure is waiting inside Victory Fitness. Reopen your plan, pick one action, and let the habit restart with less friction.")
    return ("Final comeback offer", "This is your final reminder to return and keep building your Victory routine before your momentum goes cold.")


def _personalize_comeback_message(user: dict, title: str, body: str) -> tuple[str, str]:
    motivation_statement = str(user.get("motivation_statement") or "").strip()
    if not motivation_statement:
        return title, body
    return title, f"{body} You told us you want to {motivation_statement}, so start with one small action that still fits that direction."


async def _send_comeback_flow(now: datetime) -> int:
    processed = 0
    users = await users_collection.find(
        {
            "marketing_consent": True,
            "trial_outcome": "lapsed",
            "trial_end_at": {"$ne": None},
            "subscription_is_purchased": {"$ne": True},
            "subscription_purchase_source": {"$ne": "beta_trial"},
        }
    ).to_list(length=None)
    for user in users:
        if _is_paid_user(user):
            continue
        local_now = _local_time_for_user(user, now)
        if local_now.hour < _notification_target_hour(user):
            continue
        end_at = _as_utc(user.get("trial_end_at"))
        if end_at is None:
            continue
        elapsed_days = max((now - end_at).days, 0)
        if elapsed_days <= 0:
            continue
        state = _comeback_state(user)
        sent_days = {int(day) for day in (state.get("sent_days") or []) if str(day).isdigit()}
        usage = await _trial_usage_snapshot(user, end_at - timedelta(days=5), end_at)
        due_days = [day for day in COMEBACK_DAYS if day <= elapsed_days and day not in sent_days]
        for day in due_days:
            title, body = _build_comeback_message(day, usage)
            title, body = _personalize_comeback_message(user, title, body)
            route = "/plan" if day in {14, 30} else "/(tabs)"
            await notify_user(
                users_collection,
                user,
                title,
                body,
                f"comeback_day_{day}",
                {"route": route, "day": day, "usage": usage},
            )
            if day in {14, 30}:
                try:
                    await asyncio.to_thread(
                        send_retention_email,
                        to_email=str(user.get("email") or ""),
                        name=str(user.get("name") or "there"),
                        subject=f"Victory Fitness — {title}",
                        body=body,
                        flow="comeback_flow",
                    )
                except Exception:
                    logger.exception("comeback_email_failed user_id=%s day=%s", user.get("_id"), day)
            sent_days.add(day)
            processed += 1
        if due_days:
            await users_collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        f"{RETENTION_STATE_PATH}.comeback_flow.sent_days": sorted(sent_days),
                        f"{RETENTION_STATE_PATH}.comeback_flow.last_processed_at": now,
                        "updated_at": now,
                    }
                },
            )
    return processed


def _pair_day_key(user: dict, now: datetime) -> str:
    local_now = _local_time_for_user(user, now)
    return local_now.date().isoformat()


async def _send_accountability_nudges(now: datetime) -> int:
    processed = 0
    pairs = await accountability_pairs_collection.find({"status": "active"}).to_list(length=None)
    for pair in pairs:
        user_ids = [str(item) for item in (pair.get("user_ids") or []) if str(item).strip()]
        if len(user_ids) != 2:
            continue
        users = await users_collection.find({"_id": {"$in": [ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)]}}).to_list(length=2)
        users_by_id = {str(item.get("_id")): item for item in users}
        day_key = None
        pending_users: list[dict] = []
        pair_status = dict(pair.get("daily_status") or {})
        for user_id in user_ids:
            user = users_by_id.get(user_id)
            if not user:
                continue
            local_now = _local_time_for_user(user, now)
            if local_now.hour < ACCOUNTABILITY_NUDGE_HOUR:
                continue
            day_key = local_now.date().isoformat()
            status_for_day = dict(pair_status.get(day_key) or {})
            if not bool(status_for_day.get(user_id)):
                pending_users.append(user)
        if not pending_users or not day_key:
            continue
        if str(pair.get("last_nudged_on") or "") == day_key:
            continue
        for pending_user in pending_users:
            await notify_user(
                users_collection,
                pending_user,
                "Accountability check-in reminder",
                "Your accountability partner is waiting for today's green tick. Check in before the day ends.",
                "accountability_nudge",
                {"route": "/notifications", "pairId": str(pair.get("_id") or ""), "day": day_key},
            )
            processed += 1
        await accountability_pairs_collection.update_one(
            {"_id": pair["_id"]},
            {"$set": {"last_nudged_on": day_key, "updated_at": now}},
        )
    return processed


async def process_retention_jobs() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    comeback = await _send_comeback_flow(now)
    digest = await _send_weekly_digest(now)
    nudges = await _send_accountability_nudges(now)
    return {
        "comebackMessages": comeback,
        "weeklyDigests": digest,
        "accountabilityNudges": nudges,
    }
