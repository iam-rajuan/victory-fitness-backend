import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...core.legacy import *
from ...coach_victor import (
    build_coach_victor_system_prompt,
    generate_coach_victor_reply,
    generate_coach_victor_stream,
)

logger = logging.getLogger(__name__)

router = APIRouter()

PAIN_KEYWORDS = {
    "knee": ["knee", "knees", "patella", "meniscus"],
    "shoulder": ["shoulder", "rotator cuff", "deltoid"],
    "lower_back": ["lower back", "back pain", "lumbar", "spine", "sciatica"],
    "elbow": ["elbow", "tennis elbow"],
    "wrist": ["wrist"],
    "hip": ["hip", "hips", "groin"],
    "ankle": ["ankle", "achilles"],
}


def detect_pain_flags(message: str) -> list[str]:
    lowered = (message or "").strip().lower()
    pain_indicators = [
        "hurt", "hurts", "hurting", "pain", "painful", "injury", "injured",
        "sore", "soreness", "tweak", "strain", "strained", "ache", "aching"
    ]
    if not any(ind in lowered for ind in pain_indicators):
        return []
    flagged = []
    for joint, terms in PAIN_KEYWORDS.items():
        if any(term in lowered for term in terms):
            flagged.append(joint)
    return flagged


async def handle_pain_signals_if_any(user: dict, user_id: str, message: str) -> list[str]:
    flags = detect_pain_flags(message)
    if not flags:
        return []

    logger.info("pain_signal_detected user_id=%s flags=%s", user_id, flags)
    # 1. Persist to user record
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"injury_flags": {"$each": flags}}}
    )

    # 2. Modify upcoming workout plan if active
    latest_workout_plan = await strength_workout_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1), ("created_at", -1)],
    )
    if latest_workout_plan and isinstance(latest_workout_plan.get("plan"), dict):
        plan_data = dict(latest_workout_plan["plan"])
        days = plan_data.get("days") or []
        modified = False
        for day in days:
            exs = []
            for ex in day.get("exercises") or []:
                ex_name = str(ex.get("name") or "").lower()
                if "knee" in flags and any(k in ex_name for k in ["squat", "lunge", "leg press", "leg extension"]):
                    ex_copy = dict(ex)
                    ex_copy["name"] = "Romanian Deadlift" if ("squat" in ex_name or "press" in ex_name) else "Hamstring Curl"
                    exs.append(ex_copy)
                    modified = True
                elif "shoulder" in flags and any(k in ex_name for k in ["overhead press", "military press", "incline press"]):
                    ex_copy = dict(ex)
                    ex_copy["name"] = "Cable Face Pull"
                    exs.append(ex_copy)
                    modified = True
                else:
                    exs.append(ex)
            day["exercises"] = exs

        if modified:
            await strength_workout_plans_collection.update_one(
                {"_id": latest_workout_plan["_id"]},
                {"$set": {"plan": plan_data, "updated_at": datetime.now(timezone.utc)}}
            )
            logger.info("adjusted_workout_for_pain user_id=%s flags=%s", user_id, flags)

    return flags


async def _latest_nutrition_profile(user_id: str, user: dict | None = None) -> dict[str, Any]:
    record = await nutrition_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )
    plan = dict((record or {}).get("plan") or {})
    profile = dict(plan.get("profile") or {})

    fav_meals = []
    if user:
        if isinstance(user.get("favorite_meals"), list):
            fav_meals.extend(user["favorite_meals"])
        elif user.get("favorite_meals"):
            fav_meals.append(str(user["favorite_meals"]))
        if isinstance(user.get("favorite_meals_json"), list):
            fav_meals.extend(user["favorite_meals_json"])

    if isinstance(profile.get("favorite_meals"), list):
        fav_meals.extend(profile["favorite_meals"])
    if isinstance(profile.get("favorite_meals_json"), list):
        fav_meals.extend(profile["favorite_meals_json"])
    if profile.get("favorite_meal"):
        fav_meals.append(str(profile["favorite_meal"]))

    deduped_meals = []
    for m in fav_meals:
        s = str(m or "").strip()
        if s and s not in deduped_meals:
            deduped_meals.append(s)

    protein_target = profile.get("protein_target_g") or profile.get("daily_protein") or (user or {}).get("daily_protein_target") or 124

    return {
        **profile,
        "favorite_meals_json": deduped_meals,
        "favorite_meals": deduped_meals,
        "protein_target_g": protein_target,
    }


async def _get_today_daily_protein(user_id: str, user: dict, nutrition_profile: dict) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    today_key = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now_utc.weekday()]

    record = await nutrition_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )
    plan_completions = dict((record or {}).get("plan", {}).get("meal_completions", {}).get(today_key, {}))
    plan_days = list((record or {}).get("plan", {}).get("days", []))
    today_plan_day = next((d for d in plan_days if isinstance(d, dict) and d.get("day") == today_key), {})

    consumed_protein = 0
    for meal_key, completed in plan_completions.items():
        if completed:
            meal_data = today_plan_day.get(meal_key, {})
            if isinstance(meal_data, dict):
                consumed_protein += int(meal_data.get("p") or 0)

    start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    today_analyses = await meal_analysis_entries_collection.find(
        {"user_id": user_id, "created_at": {"$gte": start_of_day}}
    ).to_list(length=20)
    for entry in today_analyses:
        consumed_protein += int(entry.get("protein_g") or entry.get("protein") or 0)

    target_protein = int(nutrition_profile.get("protein_target_g") or user.get("daily_protein_target") or 124)
    return {"consumed_g": consumed_protein, "target_g": target_protein}


async def _coach_progress_context(user: dict, user_id: str) -> dict[str, Any]:
    fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=14)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_completed_workouts = await workout_logs_collection.count_documents(
        {"user_id": user_id, "status": "completed", "started_at": {"$gte": fourteen_days_ago}}
    )
    recent_nutrition_actions = await meal_analysis_entries_collection.count_documents(
        {"user_id": user_id, "created_at": {"$gte": seven_days_ago}}
    )
    latest_workout_plan = await strength_workout_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1), ("created_at", -1)],
    )
    latest_feedback = {}
    raw_feedback = (latest_workout_plan or {}).get("session_feedback") or []
    if isinstance(raw_feedback, list) and raw_feedback:
        latest_feedback = dict(raw_feedback[-1] or {})
    latest_nutrition_plan = await nutrition_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1), ("created_at", -1)],
    )
    latest_nutrition_summary = str(((latest_nutrition_plan or {}).get("plan") or {}).get("summary") or "").strip()
    longevity_profile = await _get_or_create_longevity_profile(user)
    weekly_plan = dict(longevity_profile.get("weekly_plan") or {})
    return {
        "streak_days": int(user.get("streak_days") or 0),
        "workouts_completed": int(user.get("workouts_completed") or 0),
        "recent_completed_workouts": recent_completed_workouts,
        "recent_nutrition_actions": recent_nutrition_actions,
        "latest_workout_feedback_summary": (
            f"Day {latest_feedback.get('day')}: {latest_feedback.get('next_volume_direction')} {latest_feedback.get('adjustment_pct')}%"
            if latest_feedback
            else ""
        ),
        "latest_nutrition_summary": latest_nutrition_summary,
        "weekly_plan_focus": str(weekly_plan.get("focus") or weekly_plan.get("headline") or "").strip(),
    }


async def _coach_user_context(user: dict, recent_messages: list[dict[str, Any]]) -> dict[str, Any]:
    user_id = str(user["_id"])
    onboarding = _serialize_onboarding_state(user)
    nutrition_profile = await _latest_nutrition_profile(user_id, user=user)
    longevity_profile = await _get_or_create_longevity_profile(user)
    habits = [dict(item) for item in longevity_profile.get("habits") or [] if isinstance(item, dict)]
    completed_habits = [str(item.get("title") or item.get("id") or "").strip() for item in habits if bool(item.get("done"))]
    pending_habits = [str(item.get("title") or item.get("id") or "").strip() for item in habits if not bool(item.get("done"))]
    application = await coaching_applications_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )

    daily_protein = await _get_today_daily_protein(user_id, user, nutrition_profile)
    country_code = str(user.get("country_code") or onboarding.get("countryCode") or "").upper()
    preferred_lang = str(
        user.get("preferred_language")
        or user.get("language")
        or (onboarding.get("personalProfile") or {}).get("language")
        or ("de" if country_code == "DE" else "hi" if country_code == "IN" else "en")
    ).strip().lower()
    user_name = str(user.get("name") or (onboarding.get("personalProfile") or {}).get("name") or "").strip()

    return {
        "name": user_name,
        "country": str(user.get("country") or onboarding.get("country") or "").strip(),
        "country_code": country_code,
        "preferred_language": preferred_lang,
        "subscription_tier": str(user.get("subscription_tier") or "NONE"),
        "motivation_statement": str(user.get("motivation_statement") or onboarding.get("motivationStatement") or "").strip(),
        "onboarding": onboarding,
        "nutrition_profile": nutrition_profile,
        "daily_protein": daily_protein,
        "habit_fields": {
            "identity_statement": user.get("identity_statement"),
            "workout_unlock_label": user.get("workout_unlock_label"),
            "training_trigger_context": user.get("training_trigger_context"),
            "training_trigger_action": user.get("training_trigger_action"),
        },
        "longevity": {
            "completed_habits": [item for item in completed_habits if item],
            "pending_habits": [item for item in pending_habits if item],
        },
        "progress": await _coach_progress_context(user, user_id),
        "medical": {
            "health_notes": str((onboarding.get("anamnese") or {}).get("healthNotes") or "").strip(),
            "injury": str((application or {}).get("injury") or "").strip(),
        },
        "recent_messages": [
            {"role": str(item.get("role") or ""), "content": str(item.get("content") or "")}
            for item in recent_messages[-10:]
            if str(item.get("content") or "").strip()
        ],
    }


@router.post("/ai/coach-victor/chat", response_model=CoachVictorChatResponse)
async def coach_victor_chat(
    payload: CoachVictorChatRequest,
    request: Request,
    user: dict = Depends(_require_coach_victor_access_user),
) -> CoachVictorChatResponse:
    user_id = str(user["_id"])
    logger.info("coach_chat_attempt user_id=%s", user_id)

    # Pain flag detection & active adjustment
    await handle_pain_signals_if_any(user, user_id, payload.message)

    thread = await coach_victor_threads_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1)],
    )
    full_thread_messages = list(thread.get("messages", [])) if thread else []
    existing_messages = full_thread_messages[-10:]
    chat_history = [
        {"role": item["role"], "content": item["content"]}
        for item in existing_messages[-10:]
    ]
    chat_history.append({"role": "user", "content": payload.message})
    user_context = await _coach_user_context(user, existing_messages)
    req_lang = request.headers.get("accept-language", "").split(",")[0].split(";")[0].strip().lower()
    if req_lang and not user_context.get("preferred_language"):
        user_context["preferred_language"] = req_lang

    try:
        result = generate_coach_victor_reply(
            chat_history,
            user_context=user_context,
            recent_messages=user_context.get("recent_messages"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    user_message = {
        "id": str(ObjectId()),
        "role": "user",
        "content": payload.message,
        "created_at": now,
    }
    assistant_message = {
        "id": str(ObjectId()),
        "role": "assistant",
        "content": result.reply,
        "created_at": now,
    }
    next_full_messages = [*full_thread_messages, user_message, assistant_message]

    if thread:
        update_doc = await _build_thread_update_doc(
            thread_id=str(thread["_id"]),
            user_id=user_id,
            messages=next_full_messages,
            updated_at=now,
        )
        await coach_victor_threads_collection.update_one(
            {"_id": thread["_id"]},
            update_doc,
        )
        thread_id = str(thread["_id"])
    else:
        thread_doc = await _build_new_thread_doc(
            user_id=user_id,
            messages=next_full_messages,
            created_at=now,
        )
        insert_result = await coach_victor_threads_collection.insert_one(thread_doc)
        thread_id = str(insert_result.inserted_id)

    logger.info(
        "coach_chat_success user_id=%s thread_id=%s message_count=%s",
        user_id,
        thread_id,
        len(next_full_messages),
    )
    await _record_trial_engagement(user, "coach_message")
    return CoachVictorChatResponse(reply=result.reply, thread_id=thread_id)


@router.post("/ai/coach-victor/stream")
async def coach_victor_stream(
    payload: CoachVictorChatRequest,
    request: Request,
    user: dict = Depends(_require_coach_victor_access_user),
):
    """Server-Sent Events streaming endpoint for real-time coach victor responses."""
    user_id = str(user["_id"])
    logger.info("coach_stream_attempt user_id=%s", user_id)

    await handle_pain_signals_if_any(user, user_id, payload.message)

    thread = await coach_victor_threads_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1)],
    )
    full_thread_messages = list(thread.get("messages", [])) if thread else []
    existing_messages = full_thread_messages[-10:]
    chat_history = [
        {"role": item["role"], "content": item["content"]}
        for item in existing_messages[-10:]
    ]
    chat_history.append({"role": "user", "content": payload.message})
    user_context = await _coach_user_context(user, existing_messages)
    req_lang = request.headers.get("accept-language", "").split(",")[0].split(";")[0].strip().lower()
    if req_lang and not user_context.get("preferred_language"):
        user_context["preferred_language"] = req_lang

    async def event_generator():
        accumulated_reply = []
        try:
            async for token in generate_coach_victor_stream(
                chat_history,
                user_context=user_context,
                recent_messages=user_context.get("recent_messages"),
            ):
                accumulated_reply.append(token)
                event_data = json.dumps({"type": "token", "token": token})
                yield f"data: {event_data}\n\n"
        except Exception as exc:
            logger.error("stream_error: %s", exc)
            err_data = json.dumps({"type": "error", "error": str(exc)})
            yield f"data: {err_data}\n\n"

        full_reply_text = "".join(accumulated_reply).strip()
        now = datetime.now(timezone.utc)
        user_msg = {
            "id": str(ObjectId()),
            "role": "user",
            "content": payload.message,
            "created_at": now,
        }
        asst_msg = {
            "id": str(ObjectId()),
            "role": "assistant",
            "content": full_reply_text,
            "created_at": now,
        }
        next_messages = [*full_thread_messages, user_msg, asst_msg]

        if thread:
            update_doc = await _build_thread_update_doc(
                thread_id=str(thread["_id"]),
                user_id=user_id,
                messages=next_messages,
                updated_at=now,
            )
            await coach_victor_threads_collection.update_one(
                {"_id": thread["_id"]},
                update_doc,
            )
            final_thread_id = str(thread["_id"])
        else:
            thread_doc = await _build_new_thread_doc(
                user_id=user_id,
                messages=next_messages,
                created_at=now,
            )
            insert_res = await coach_victor_threads_collection.insert_one(thread_doc)
            final_thread_id = str(insert_res.inserted_id)

        done_data = json.dumps({"type": "done", "reply": full_reply_text, "thread_id": final_thread_id})
        yield f"data: {done_data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/ai/coach-victor/history", response_model=CoachVictorHistoryResponse)
async def coach_victor_history(
    user: dict = Depends(_require_coach_victor_access_user),
) -> CoachVictorHistoryResponse:
    user_id = str(user["_id"])
    logger.info("coach_history_attempt user_id=%s", user_id)
    thread = await coach_victor_threads_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1)],
    )
    all_messages = await _get_full_thread_messages(thread)
    logger.info(
        "coach_history_success user_id=%s thread_id=%s message_count=%s",
        user_id,
        str(thread["_id"]) if thread else None,
        len(all_messages),
    )
    return CoachVictorHistoryResponse(
        thread_id=str(thread["_id"]) if thread else None,
        messages=[
            {
                "id": item["id"],
                "role": item["role"],
                "content": item["content"],
                "created_at": item["created_at"],
            }
            for item in all_messages
        ],
    )
