from fastapi import APIRouter

from ...core.legacy import *
from ...coach_victor import generate_coach_victor_reply

router = APIRouter()


async def _latest_nutrition_profile(user_id: str) -> dict[str, Any]:
    record = await nutrition_plans_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )
    if not record:
        return {}
    plan = dict(record.get("plan") or {})
    profile = dict(plan.get("profile") or {})
    favorite_meal = str(profile.get("favorite_meal") or "").strip()
    favorite_meals_json = [favorite_meal] if favorite_meal else []
    return {
        **profile,
        "favorite_meals_json": favorite_meals_json,
        "protein_target_g": profile.get("protein_target_g") or profile.get("daily_protein"),
    }


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
    nutrition_profile = await _latest_nutrition_profile(user_id)
    longevity_profile = await _get_or_create_longevity_profile(user)
    habits = [dict(item) for item in longevity_profile.get("habits") or [] if isinstance(item, dict)]
    completed_habits = [str(item.get("title") or item.get("id") or "").strip() for item in habits if bool(item.get("done"))]
    pending_habits = [str(item.get("title") or item.get("id") or "").strip() for item in habits if not bool(item.get("done"))]
    application = await coaching_applications_collection.find_one(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )
    return {
        "country": str(user.get("country") or onboarding.get("country") or "").strip(),
        "country_code": str(user.get("country_code") or onboarding.get("countryCode") or "").upper(),
        "subscription_tier": str(user.get("subscription_tier") or "NONE"),
        "motivation_statement": str(user.get("motivation_statement") or onboarding.get("motivationStatement") or "").strip(),
        "onboarding": onboarding,
        "nutrition_profile": nutrition_profile,
        "habit_fields": {
            "identity_statement": user.get("identity_statement"),
            "workout_unlock_label": user.get("workout_unlock_label"),
            "training_trigger_context": user.get("training_trigger_context"),
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

    user: dict = Depends(_require_coach_victor_access_user),

) -> CoachVictorChatResponse:

    user_id = str(user["_id"])

    logger.info("coach_chat_attempt user_id=%s", user_id)

    thread = await coach_victor_threads_collection.find_one(

        {"user_id": user_id},

        sort=[("updated_at", -1)],

    )

    full_thread_messages = await _get_full_thread_messages(thread)

    existing_messages = full_thread_messages[-10:]

    chat_history = [

        {"role": item["role"], "content": item["content"]}

        for item in existing_messages[-10:]

    ]

    chat_history.append({"role": "user", "content": payload.message})
    user_context = await _coach_user_context(user, existing_messages)

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

        ]

    )
