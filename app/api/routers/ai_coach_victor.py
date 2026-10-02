import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...core.legacy import *
from ...models import CoachWorkoutPlanActionApplyRequest, StrengthWorkoutPlanResponse
from ...coach_victor import (
    build_coach_victor_system_prompt,
    generate_coach_victor_reply,
    generate_coach_victor_stream,
    postprocess_coach_victor_reply,
)
from .ai_workout_plan import _hydrate_strength_plan_input
from ...workout_plan_ai import sanitize_workout_plan_for_injuries

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

DAY_ALIASES = [
    ("monday", "Mon"), ("mon", "Mon"),
    ("tuesday", "Tue"), ("tue", "Tue"),
    ("wednesday", "Wed"), ("wed", "Wed"),
    ("thursday", "Thu"), ("thu", "Thu"),
    ("friday", "Fri"), ("fri", "Fri"),
    ("saturday", "Sat"), ("sat", "Sat"),
    ("sunday", "Sun"), ("sun", "Sun"),
]

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day_sort_key(day: str) -> int:
    try:
        return DAY_ORDER.index(day)
    except ValueError:
        return 99


def _extract_target_days(message: str) -> list[str]:
    lowered = str(message or "").lower()
    days: list[str] = []
    for needle, day in DAY_ALIASES:
        if re.search(rf"\b{re.escape(needle)}\b", lowered) and day not in days:
            days.append(day)
    return sorted(days, key=_day_sort_key)


def _extract_target_minutes(message: str) -> int | None:
    lowered = str(message or "").lower()
    match = re.search(r"(\d{1,3})\s*(?:min|mins|minute|minutes)\b", lowered)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    return max(1, min(value, 180))


def _is_full_plan_rebuild_request(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(term in lowered for term in ("rebuild", "new plan", "generate", "create", "build my plan", "replace my plan", "full plan", "whole plan"))


def _looks_like_home_plan_change_request(message: str) -> bool:
    lowered = str(message or "").lower()
    action_terms = ("change", "adjust", "update", "make", "replace", "rebuild", "generate", "create", "insert", "save", "apply", "switch", "remove", "add", "only have", "have")
    plan_terms = ("workout", "training", "routine", "plan", "session", "today", "tonight", "minutes", "no equipment", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "push", "pull", "squat", "legs")
    return any(term in lowered for term in action_terms) and any(term in lowered for term in plan_terms)


def _coach_plan_action_from_message(message: str, user_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not _looks_like_home_plan_change_request(message):
        return None
    target_days = _extract_target_days(message)
    target_minutes = _extract_target_minutes(message)
    lowered = str(message or "").lower()
    current_plan = dict(((user_context or {}).get("progress") or {}).get("current_home_workout_plan") or {})
    if not target_days and any(term in lowered for term in ("today", "tonight", "current session", "this session", "today's workout", "todays workout")):
        for session in current_plan.get("sessions") or []:
            if isinstance(session, dict) and not session.get("completed"):
                day_key = str(session.get("day") or "").strip()
                if day_key in DAY_ORDER:
                    target_days = [day_key]
                    break
    scope = "full_plan" if _is_full_plan_rebuild_request(message) or not target_days else "day"
    label = ", ".join(target_days) if target_days else "Home plan"
    summary_bits = []
    if scope == "day":
        summary_bits.append(f"Update {label}")
    else:
        summary_bits.append("Replace your Home workout plan")
    if target_minutes:
        summary_bits.append(f"{target_minutes} min")
    elif current_plan.get("summary") and scope == "full_plan":
        summary_bits.append("using your current profile")
    return {
        "type": "home_workout_plan_update",
        "source_prompt": str(message or "").strip(),
        "scope": scope,
        "target_days": target_days,
        "target_minutes": target_minutes,
        "summary": " · ".join(summary_bits),
        "button_label": "Apply to Home plan" if scope == "full_plan" else f"Update {label}",
    }


def _plan_input_document(input_data: Any, source: str, message: str) -> dict[str, Any]:
    return {
        "goal": input_data.goal,
        "level": input_data.level,
        "split": input_data.split,
        "muscle_group": input_data.muscle_group,
        "duration_minutes": input_data.duration_minutes,
        "height": input_data.height,
        "gender": input_data.gender,
        "bench": input_data.bench,
        "squat": input_data.squat,
        "deadlift": input_data.deadlift,
        "equipment": input_data.equipment,
        "frequency": input_data.frequency,
        "days": input_data.days,
        "age": input_data.age,
        "weight": input_data.weight,
        "source": source,
        "coach_message": str(message or "")[:2000],
    }


def _matching_generated_day(generated_days: list[dict[str, Any]], target_day: str, fallback_index: int = 0) -> dict[str, Any] | None:
    for day in generated_days:
        if str(day.get("day") or "").strip() == target_day:
            return dict(day)
    if 0 <= fallback_index < len(generated_days):
        return dict(generated_days[fallback_index])
    return dict(generated_days[0]) if generated_days else None


def _normalize_generated_day_for_target(day: dict[str, Any], target_day: str, minutes: int | None) -> dict[str, Any]:
    next_day = dict(day)
    next_day["day"] = target_day
    if minutes:
        next_day["est_time"] = f"{minutes} min"
    return next_day


async def _apply_coach_workout_plan_action(
    user: dict,
    *,
    source_prompt: str,
    scope: str,
    target_days: list[str] | None = None,
    target_minutes: int | None = None,
) -> dict:
    user_id = str(user["_id"])
    now = datetime.now(timezone.utc)
    clean_days = [day for day in (target_days or []) if day in DAY_ORDER]
    prompt_with_constraints = source_prompt
    if target_minutes:
        prompt_with_constraints = f"{prompt_with_constraints}\n\nHard constraint: every affected session must be around {target_minutes} minutes."
    if clean_days:
        prompt_with_constraints = f"{prompt_with_constraints}\n\nHard constraint: affected days are {', '.join(clean_days)}."

    payload = _coach_plan_payload_from_message(prompt_with_constraints)
    if clean_days:
        payload.days = clean_days
        payload.frequency = str(len(clean_days))
    if target_minutes:
        payload.duration_minutes = str(target_minutes)
    hydrated_input = _hydrate_strength_plan_input(payload, user)
    hydrated_input.custom_notes = prompt_with_constraints[:4000]
    generated_plan = generate_strength_workout_plan(hydrated_input)

    latest_record = await strength_workout_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )
    should_patch_days = scope == "day" and clean_days and latest_record and isinstance(latest_record.get("plan"), dict)
    if should_patch_days:
        base_plan = dict(latest_record.get("plan") or {})
        base_days = [dict(day) for day in base_plan.get("days") or [] if isinstance(day, dict)]
        generated_days = [dict(day) for day in generated_plan.get("days") or [] if isinstance(day, dict)]
        next_days: list[dict[str, Any]] = []
        for index, existing_day in enumerate(base_days):
            day_key = str(existing_day.get("day") or "").strip()
            if day_key in clean_days:
                replacement = _matching_generated_day(generated_days, day_key, clean_days.index(day_key))
                next_days.append(_normalize_generated_day_for_target(replacement or existing_day, day_key, target_minutes))
            else:
                next_days.append(existing_day)
        existing_keys = {str(day.get("day") or "") for day in next_days}
        for index, day_key in enumerate(clean_days):
            if day_key in existing_keys:
                continue
            replacement = _matching_generated_day(generated_days, day_key, index)
            if replacement:
                next_days.append(_normalize_generated_day_for_target(replacement, day_key, target_minutes))
        next_days.sort(key=lambda item: _day_sort_key(str(item.get("day") or "")))
        next_plan = {**base_plan, "days": next_days}
        next_plan["summary"] = str(generated_plan.get("summary") or base_plan.get("summary") or "").strip()
        insert_doc = {
            "user_id": user_id,
            "input": {
                **dict(latest_record.get("input") or {}),
                "source": "coach_adjustment",
                "coach_message": source_prompt[:2000],
                "days": sorted({*(dict(latest_record.get("input") or {}).get("days") or []), *clean_days}, key=_day_sort_key),
            },
            "plan": next_plan,
            "progress": [item for item in latest_record.get("progress") or [] if isinstance(item, dict)],
            "created_at": now,
            "updated_at": now,
        }
    else:
        insert_doc = {
            "user_id": user_id,
            "input": _plan_input_document(hydrated_input, "coach_adjustment", source_prompt),
            "plan": generated_plan,
            "progress": [],
            "created_at": now,
            "updated_at": now,
        }

    insert_result = await strength_workout_plans_collection.insert_one(insert_doc)
    return {**insert_doc, "_id": insert_result.inserted_id}


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
        plan_data, modified = sanitize_workout_plan_for_injuries(plan_data, flags)

        if modified:
            await strength_workout_plans_collection.update_one(
                {"_id": latest_workout_plan["_id"]},
                {"$set": {"plan": plan_data, "updated_at": datetime.now(timezone.utc)}}
            )
            logger.info("adjusted_workout_for_pain user_id=%s flags=%s", user_id, flags)

    return flags


def _coach_message_requests_plan_update(message: str) -> bool:
    text = str(message or "").lower()
    update_terms = ("apply", "update", "change", "adjust", "rebuild", "replace", "custom plan", "my plan")
    plan_terms = ("workout plan", "training plan", "plan card", "split", "push", "pull", "legs", "dumbbell", "bodyweight", "gym")
    return any(term in text for term in update_terms) and any(term in text for term in plan_terms)


def _coach_plan_payload_from_message(message: str) -> StrengthWorkoutPlanRequest:
    text = str(message or "")
    lowered = text.lower()

    if any(term in lowered for term in ("lose weight", "fat loss", "cut", "recomp")):
        goal = "Body Recomp"
    elif any(term in lowered for term in ("strength", "stronger", "heavy")):
        goal = "Pure Strength"
    elif any(term in lowered for term in ("speed", "power", "athletic", "endurance")):
        goal = "Power & Speed"
    else:
        goal = "Hypertrophy"

    if "push" in lowered and "pull" in lowered and "leg" in lowered:
        split = "Push Pull Legs"
    elif "upper" in lowered and "lower" in lowered:
        split = "Upper / Lower"
    else:
        split = "Full Body"

    if any(term in lowered for term in ("bodyweight", "no equipment", "nothing at all")):
        equipment = ["No equipment"]
    elif "dumbbell" in lowered:
        equipment = ["Dumbbells"]
    elif any(term in lowered for term in ("home gym", "bands", "pull-up", "pull up")):
        equipment = ["Dumbbells", "Bands"]
    elif "gym" in lowered or "barbell" in lowered:
        equipment = ["Gym", "Barbell", "Dumbbells", "Cables", "Machines"]
    else:
        equipment = []

    duration_match = re.search(r"(\d{2,3})\s*(?:min|minute)", lowered)
    duration_minutes = duration_match.group(1) if duration_match else None
    day_count_match = re.search(r"(\d)\s*(?:day|days)", lowered)
    frequency = day_count_match.group(1) if day_count_match else "7"

    day_aliases = [
        ("mon", "Mon"), ("monday", "Mon"),
        ("tue", "Tue"), ("tuesday", "Tue"),
        ("wed", "Wed"), ("wednesday", "Wed"),
        ("thu", "Thu"), ("thursday", "Thu"),
        ("fri", "Fri"), ("friday", "Fri"),
        ("sat", "Sat"), ("saturday", "Sat"),
        ("sun", "Sun"), ("sunday", "Sun"),
    ]
    days = []
    for needle, day in day_aliases:
        if needle in lowered and day not in days:
            days.append(day)
    if not days and frequency == "7":
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    return StrengthWorkoutPlanRequest(
        goal=goal,
        split=split,
        duration_minutes=duration_minutes,
        equipment=equipment,
        frequency=frequency,
        days=days,
        muscle_group="Full Body",
    )


async def _maybe_apply_coach_workout_plan_update(user: dict, user_id: str, message: str) -> bool:
    if not _coach_message_requests_plan_update(message):
        return False
    payload = _coach_plan_payload_from_message(message)
    hydrated_input = _hydrate_strength_plan_input(payload, user)
    hydrated_input.custom_notes = str(message or "").strip()[:4000]
    plan_data = generate_strength_workout_plan(hydrated_input)
    now = datetime.now(timezone.utc)
    await strength_workout_plans_collection.insert_one(
        {
            "user_id": user_id,
            "input": {
                "goal": hydrated_input.goal,
                "level": hydrated_input.level,
                "split": hydrated_input.split,
                "muscle_group": hydrated_input.muscle_group,
                "duration_minutes": hydrated_input.duration_minutes,
                "height": hydrated_input.height,
                "gender": hydrated_input.gender,
                "bench": hydrated_input.bench,
                "squat": hydrated_input.squat,
                "deadlift": hydrated_input.deadlift,
                "equipment": hydrated_input.equipment,
                "frequency": hydrated_input.frequency,
                "days": hydrated_input.days,
                "age": hydrated_input.age,
                "weight": hydrated_input.weight,
                "source": "coach_adjustment",
                "coach_message": str(message or "")[:2000],
            },
            "plan": plan_data,
            "progress": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    return True


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
    current_home_plan: dict[str, Any] = {}
    if latest_workout_plan and isinstance(latest_workout_plan.get("plan"), dict):
        plan = dict(latest_workout_plan.get("plan") or {})
        input_data = dict(latest_workout_plan.get("input") or {})
        progress_items = [item for item in latest_workout_plan.get("progress") or [] if isinstance(item, dict)]
        completed_days = {str(item.get("day") or "") for item in progress_items if item.get("completed")}
        day_summaries: list[dict[str, Any]] = []
        for day in [item for item in plan.get("days") or [] if isinstance(item, dict)][:7]:
            exercises = []
            for exercise in (day.get("exercises") or [])[:6]:
                if not isinstance(exercise, dict):
                    continue
                exercises.append(
                    {
                        "name": str(exercise.get("name") or "").strip(),
                        "sets": exercise.get("sets"),
                        "reps": exercise.get("reps"),
                        "rest": exercise.get("rest"),
                        "equipment": exercise.get("equipment") or exercise.get("weight"),
                        "type": exercise.get("type") or exercise.get("kind"),
                    }
                )
            day_summaries.append(
                {
                    "day": str(day.get("day") or "").strip(),
                    "title": str(day.get("title") or "").strip(),
                    "est_time": str(day.get("est_time") or "").strip(),
                    "intensity": str(day.get("intensity") or "").strip(),
                    "completed": str(day.get("day") or "").strip() in completed_days,
                    "exercises": exercises,
                }
            )
        current_home_plan = {
            "summary": str(plan.get("summary") or "").strip(),
            "goal": str(input_data.get("goal") or "").strip(),
            "split": str(input_data.get("split") or "").strip(),
            "frequency": input_data.get("frequency"),
            "days": input_data.get("days") or [],
            "equipment": input_data.get("equipment") or [],
            "completed_days": sorted(completed_days),
            "sessions": day_summaries,
        }
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
        "current_home_workout_plan": current_home_plan,
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
            "coach_session_notes": user.get("coach_session_notes"),
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
    if payload.language_override:
        user_context["preferred_language"] = str(payload.language_override).strip().lower()
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
    reply_text = result.reply

    assistant_message = {
        "id": str(ObjectId()),
        "role": "assistant",
        "content": reply_text,
        "created_at": now,
    }
    plan_action = _coach_plan_action_from_message(payload.message, user_context)
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
    return CoachVictorChatResponse(reply=reply_text, thread_id=thread_id, plan_action=plan_action)


@router.post("/ai/coach-victor/workout-plan-action/apply", response_model=StrengthWorkoutPlanResponse)
async def apply_coach_workout_plan_action(
    payload: CoachWorkoutPlanActionApplyRequest,
    user: dict = Depends(_require_coach_victor_access_user),
) -> StrengthWorkoutPlanResponse:
    record = await _apply_coach_workout_plan_action(
        user,
        source_prompt=payload.source_prompt,
        scope=payload.scope,
        target_days=payload.target_days,
        target_minutes=payload.target_minutes,
    )
    return _serialize_strength_workout_plan_record(record)


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
    if payload.language_override:
        user_context["preferred_language"] = str(payload.language_override).strip().lower()
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

        full_reply_text = postprocess_coach_victor_reply(
            "".join(accumulated_reply).strip(),
            user_context=user_context,
            last_user_message=payload.message,
        )
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

        plan_action = _coach_plan_action_from_message(payload.message, user_context)
        done_data = json.dumps({"type": "done", "reply": full_reply_text, "thread_id": final_thread_id, "plan_action": plan_action})
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


@router.delete("/ai/coach-victor/history")
async def clear_coach_victor_history(
    user: dict = Depends(_require_coach_victor_access_user),
) -> dict[str, bool]:
    user_id = str(user["_id"])
    logger.info("coach_history_clear_attempt user_id=%s", user_id)
    await coach_victor_threads_collection.delete_many({"user_id": user_id})
    logger.info("coach_history_clear_success user_id=%s", user_id)
    return {"cleared": True}
