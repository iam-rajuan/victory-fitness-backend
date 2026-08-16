from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/challenges", response_model=AdminChallengeListResponse)

async def admin_list_challenges(

    query: str | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminChallengeListResponse:

    filter_doc = {}

    search = (query or "").strip()

    if search:

        escaped = re.escape(search)

        filter_doc["$or"] = [

            {"title": {"$regex": escaped, "$options": "i"}},

            {"category": {"$regex": escaped, "$options": "i"}},

            {"difficulty": {"$regex": escaped, "$options": "i"}},

            {"status": {"$regex": escaped, "$options": "i"}},

        ]

    records = await challenges_collection.find(

        filter_doc,

        sort=[("duration_days", 1), ("created_at", -1), ("_id", -1)],

    ).to_list(length=None)

    stats = await _load_challenge_stats_map([str(record["_id"]) for record in records])

    return AdminChallengeListResponse(

        total=len(records),

        challenges=[AdminChallengeItem(**_serialize_admin_challenge_record(record, stats)) for record in records],

    )

@router.post("/admin/challenges/generate-plan", response_model=AdminChallengePlanGenerateResponse)

async def admin_generate_challenge_plan(

    payload: AdminChallengePlanGenerateRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminChallengePlanGenerateResponse:

    generated = generate_challenge_plan(

        ChallengePlanGenerationInput(

            title=payload.title.strip(),

            description=payload.description.strip(),

            category=payload.category.strip(),

            difficulty=payload.difficulty.strip(),

            duration_days=payload.durationDays,

        )

    )

    plan_days = _normalize_challenge_plan_days(generated.get("plan_days") if isinstance(generated, dict) else [])

    if not plan_days:

        raise HTTPException(status_code=500, detail="Failed to generate challenge plan")

    plan_text = _build_challenge_plan_text(plan_days)

    duration_days = max(_extract_plan_day_numbers(plan_days), default=payload.durationDays)

    return AdminChallengePlanGenerateResponse(

        title=payload.title.strip(),

        description=str(generated.get("summary") or payload.description).strip(),

        planText=plan_text,

        planDays=[ChallengePlanDay(**day) for day in plan_days],

        durationDays=duration_days,

    )

@router.post("/admin/challenges", response_model=AdminChallengeItem, status_code=status.HTTP_201_CREATED)
async def admin_create_challenge(

    payload: AdminChallengeRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminChallengeItem:

    now = datetime.now(timezone.utc)

    plan_days = _normalize_challenge_plan_days(payload.planDays)

    derived_duration_days = max(_extract_plan_day_numbers(plan_days), default=payload.durationDays)

    plan_text = _build_challenge_plan_text(plan_days) if plan_days else str(payload.planText or "").strip()

    thumbnail = _normalize_challenge_thumbnail(payload.thumbnail)

    if payload.image_base64:

        try:

            thumbnail = _upload_challenge_thumbnail_to_s3(

                str(admin_user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge thumbnail upload failed: {exc}") from exc

    document = {

        "title": payload.title.strip(),

        "description": payload.description.strip(),

        "why_it_matters": str(payload.whyItMatters or "").strip(),

        "plan_text": plan_text,

        "plan_days": plan_days,

        "category": payload.category.strip(),

        "duration_days": derived_duration_days,

        "points": payload.points,

        "difficulty": payload.difficulty,

        "status": payload.status,

        "thumbnail": thumbnail,

        "created_at": now,

        "updated_at": now,

    }

    insert_result = await challenges_collection.insert_one(document)

    document["_id"] = insert_result.inserted_id

    await _sync_workout_library_from_challenge_plan(plan_days, payload.category)
    if str(payload.status or "").upper() in {"ACTIVE", "UPCOMING"}:
        await _notify_users_of_new_challenge(document)

    return AdminChallengeItem(**_serialize_admin_challenge_record(document))

@router.patch("/admin/challenges/{challenge_id}", response_model=AdminChallengeItem)

async def admin_update_challenge(

    challenge_id: str,

    payload: AdminChallengeRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminChallengeItem:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc

    existing = await challenges_collection.find_one({"_id": object_id})

    if not existing:

        raise HTTPException(status_code=404, detail="Challenge not found")

    previous_thumbnail = _normalize_challenge_thumbnail(existing.get("thumbnail"))

    thumbnail = _normalize_challenge_thumbnail(payload.thumbnail)

    if payload.image_base64:

        try:

            thumbnail = _upload_challenge_thumbnail_to_s3(

                str(admin_user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge thumbnail upload failed: {exc}") from exc

    if previous_thumbnail and previous_thumbnail != thumbnail:

        _delete_image_from_s3(previous_thumbnail)

    plan_days = _normalize_challenge_plan_days(payload.planDays)

    derived_duration_days = max(_extract_plan_day_numbers(plan_days), default=payload.durationDays)

    plan_text = _build_challenge_plan_text(plan_days) if plan_days else str(payload.planText or "").strip()

    update_doc = {

        "title": payload.title.strip(),

        "description": payload.description.strip(),

        "why_it_matters": str(payload.whyItMatters or "").strip(),

        "plan_text": plan_text,

        "plan_days": plan_days,

        "category": payload.category.strip(),

        "duration_days": derived_duration_days,

        "points": payload.points,

        "difficulty": payload.difficulty,

        "status": payload.status,

        "thumbnail": thumbnail,

        "updated_at": datetime.now(timezone.utc),

    }

    await challenges_collection.update_one({"_id": object_id}, {"$set": update_doc})

    await _sync_workout_library_from_challenge_plan(plan_days, payload.category)

    updated = await challenges_collection.find_one({"_id": object_id})

    if not updated:

        raise HTTPException(status_code=404, detail="Challenge not found")

    was_available = str(existing.get("status") or "").upper() in {"ACTIVE", "UPCOMING"}
    is_available = str(updated.get("status") or "").upper() in {"ACTIVE", "UPCOMING"}
    if is_available and not was_available:
        await _notify_users_of_new_challenge(updated)

    stats = await _load_challenge_stats_map([challenge_id])

    return AdminChallengeItem(**_serialize_admin_challenge_record(updated, stats))

@router.delete("/admin/challenges/{challenge_id}")

async def admin_delete_challenge(

    challenge_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc

    existing = await challenges_collection.find_one({"_id": object_id})

    if not existing:

        raise HTTPException(status_code=404, detail="Challenge not found")

    _delete_image_from_s3(_normalize_challenge_thumbnail(existing.get("thumbnail")))

    delete_result = await challenges_collection.delete_one({"_id": object_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Challenge not found")

    await challenge_memberships_collection.delete_many({"challenge_id": challenge_id})

    await challenge_chat_messages_collection.delete_many({"challenge_id": challenge_id})

    return {"status": "success", "message": "Challenge deleted"}

@router.get("/admin/challenges/{challenge_id}/chat", response_model=ChallengeChatThreadResponse)

async def admin_get_challenge_chat_thread(

    challenge_id: str,

    _: dict = Depends(_require_admin_user),

) -> ChallengeChatThreadResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    messages = await _load_challenge_chat_messages(challenge_id, None, limit=200)

    participants = await _load_challenge_participants(challenge_id)

    participant_count = await challenge_memberships_collection.count_documents(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    )

    return ChallengeChatThreadResponse(

        challenge_id=challenge_id,

        title=str(challenge.get("title") or ""),

        description=str(challenge.get("description") or ""),

        plan_text=str(challenge.get("plan_text") or ""),

        plan_days=[ChallengePlanDay(**day) for day in _normalize_challenge_plan_days(challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [])],

        category=str(challenge.get("category") or "Challenge"),

        duration_days=max(int(challenge.get("duration_days") or 0), 0),

        points=max(int(challenge.get("points") or 0), 0),

        difficulty=str(challenge.get("difficulty") or "BEGINNER"),

        status=str(challenge.get("status") or "ACTIVE"),

        thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

        participant_count=participant_count,

        participants=participants,

        viewer_membership_status="ADMIN",

        viewer_progress_days_completed=0,

        viewer_plan_progress=[],

        unread_count=0,

        messages=[ChallengeChatMessageResponse(**message) for message in messages],

    )

@router.delete("/admin/challenges/{challenge_id}/chat/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)

async def admin_delete_challenge_chat_message(

    challenge_id: str,

    message_id: str,

    _: dict = Depends(_require_admin_user),

) -> Response:

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    now = datetime.now(timezone.utc)

    await challenge_chat_messages_collection.update_one(

        {"_id": message_record["_id"]},

        {

            "$set": {

                "content": "",

                "image_url": "",

                "updated_at": now,

                "deleted_at": now,

                "deleted_by_admin": True,

            }

        },

    )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if updated:

        await _broadcast_challenge_chat_event("message_deleted", challenge_id, updated, message_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
