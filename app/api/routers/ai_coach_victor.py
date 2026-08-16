from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

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

    existing_messages = full_thread_messages[-12:]

    chat_history = [

        {"role": item["role"], "content": item["content"]}

        for item in existing_messages[-12:]

    ]

    chat_history.append({"role": "user", "content": payload.message})

    try:

        result = generate_coach_victor_reply(chat_history)

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
