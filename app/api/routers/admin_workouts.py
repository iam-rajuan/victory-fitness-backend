from fastapi import APIRouter

from ...core.legacy import *
from ...workout_categories import DEFAULT_WORKOUT_CATEGORY, WORKOUT_CATEGORY_OPTIONS, normalize_workout_categories, normalize_workout_category

router = APIRouter()

WORKOUT_LEVEL_OPTIONS = ("Beginner", "Intermediate", "Advanced")
WORKOUT_PURPOSE_OPTIONS = WORKOUT_CATEGORY_OPTIONS


def _normalize_workout_level_values(level: str | None = None, levels: list[str] | None = None) -> list[str]:
    candidates = list(levels or [])
    if level:
        candidates.append(level)
    normalized: list[str] = []
    for item in candidates:
        raw = str(item or "").strip()
        canonical = next((option for option in WORKOUT_LEVEL_OPTIONS if option.lower() == raw.lower()), "")
        if canonical and canonical not in normalized:
            normalized.append(canonical)
    return normalized


def _normalize_workout_purpose_values(tag: str | None = None, purposes: list[str] | None = None) -> list[str]:
    return normalize_workout_categories(tag, purposes)


def _build_vimeo_import_options(payload: AdminWorkoutSyncRequest | None) -> VimeoWorkoutImportOptions:
    return VimeoWorkoutImportOptions(
        folder_name=str(payload.folderName or "").strip() if payload else "",
        tag=normalize_workout_category(payload.tag if payload else DEFAULT_WORKOUT_CATEGORY),
        equipment=str(payload.equipment or "Dumbbells").strip() if payload else "Dumbbells",
        level=str(payload.level or "Intermediate").strip() if payload else "Intermediate",
        levels=_normalize_workout_level_values(payload.level, getattr(payload, "levels", None)) if payload else ["Intermediate"],
        use_vimeo_duration=bool(payload.useVimeoDuration) if payload else True,
        visibility=str(payload.visibility or "Draft").strip() if payload else "Draft",
        import_limit=int(payload.importLimit or 12) if payload else 12,
    )

@router.get("/admin/workouts", response_model=AdminWorkoutListResponse)

async def admin_list_workouts(

    query: str | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminWorkoutListResponse:

    filter_doc = {}

    search = (query or "").strip()

    if search:

        escaped = re.escape(search)

        filter_doc["$or"] = [

            {"title": {"$regex": escaped, "$options": "i"}},

            {"tag": {"$regex": escaped, "$options": "i"}},
            {"purposes": {"$regex": escaped, "$options": "i"}},

            {"equipment": {"$regex": escaped, "$options": "i"}},

            {"level": {"$regex": escaped, "$options": "i"}},
            {"levels": {"$regex": escaped, "$options": "i"}},

            {"vimeo_id": {"$regex": escaped, "$options": "i"}},

            {"video_url": {"$regex": escaped, "$options": "i"}},

            {"video_source": {"$regex": escaped, "$options": "i"}},

            {"visibility": {"$regex": escaped, "$options": "i"}},

        ]

    records = await workouts_collection.find(

        filter_doc,

        sort=[("created_at", -1), ("_id", -1)],

    ).to_list(length=None)

    workout_ids = [str(record.get("_id") or "") for record in records if record.get("_id")]
    if workout_ids:
        start_rows = await workout_logs_collection.aggregate(
            [
                {"$match": {"workout_id": {"$in": workout_ids}}},
                {"$group": {"_id": "$workout_id", "starts": {"$sum": 1}}},
            ]
        ).to_list(length=None)
        starts_by_workout_id = {
            str(row.get("_id") or ""): int(row.get("starts") or 0)
            for row in start_rows
        }
        for record in records:
            record["starts_count"] = starts_by_workout_id.get(str(record.get("_id") or ""), 0)

    return AdminWorkoutListResponse(

        total=len(records),

        workouts=[AdminWorkoutItem(**_serialize_admin_workout_record(record)) for record in records],

    )

@router.post("/admin/workouts", response_model=AdminWorkoutItem, status_code=status.HTTP_201_CREATED)

async def admin_create_workout(

    payload: AdminWorkoutRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminWorkoutItem:

    now = datetime.now(timezone.utc)

    video_source = str(payload.videoSource or "VIMEO").strip().upper() or "VIMEO"

    try:

        video_url, vimeo_id = await _prepare_workout_video_payload(payload, f"workout-{uuid4().hex}", str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not video_url:

        raise HTTPException(status_code=400, detail="A workout video is required")

    existing_filter = {"video_url": video_url}

    if vimeo_id:

        existing_filter = {"$or": [{"video_url": video_url}, {"vimeo_id": vimeo_id}]}

    existing_workout = await workouts_collection.find_one(existing_filter)

    if existing_workout:

        raise HTTPException(status_code=409, detail="A workout with this video already exists")

    default_thumbnail = (payload.thumbnail or "").strip()
    custom_thumbnail = ""

    if payload.image_base64:

        try:

            custom_thumbnail = _upload_image_to_s3(

                "workout-thumbnails",

                f"workout-{uuid4().hex}",

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Workout thumbnail upload failed: {exc}") from exc

    levels = _normalize_workout_level_values(payload.level, payload.levels)
    purposes = _normalize_workout_purpose_values(payload.tag, payload.purposes)
    document = {

        "title": payload.title.strip(),

        "video_url": video_url,

        "video_source": video_source,

        "tag": purposes[0] if purposes else DEFAULT_WORKOUT_CATEGORY,
        "purposes": purposes,

        "equipment": payload.equipment.strip(),

        "level": levels[0] if levels else payload.level.strip(),
        "levels": levels,

        "duration_minutes": int(payload.durationMinutes or 0),

        "duration_seconds": int(payload.durationSeconds or 0),

        "visibility": payload.visibility,

        "thumbnail": default_thumbnail,
        "custom_thumbnail": custom_thumbnail,

        "movements": _normalize_workout_movements_for_storage(payload.movements),

        "created_at": now,

        "updated_at": now,

    }

    if vimeo_id:

        document["vimeo_id"] = vimeo_id

    insert_result = await workouts_collection.insert_one(document)

    document["_id"] = insert_result.inserted_id

    return AdminWorkoutItem(**_serialize_admin_workout_record(document))

@router.patch("/admin/workouts/{workout_id}", response_model=AdminWorkoutItem)

async def admin_update_workout(

    workout_id: str,

    payload: AdminWorkoutRequest,

    background_tasks: BackgroundTasks,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminWorkoutItem:

    try:

        object_id = ObjectId(workout_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid workout id") from exc

    existing_workout = await workouts_collection.find_one({"_id": object_id})

    if not existing_workout:

        raise HTTPException(status_code=404, detail="Workout not found")

    video_source = str(payload.videoSource or "VIMEO").strip().upper() or "VIMEO"

    try:

        video_url, vimeo_id = await _prepare_workout_video_payload(payload, f"workout-{object_id}", str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    duplicate_filter = {"video_url": video_url, "_id": {"$ne": object_id}}

    if vimeo_id:

        duplicate_filter = {"$or": [{"video_url": video_url, "_id": {"$ne": object_id}}, {"vimeo_id": vimeo_id, "_id": {"$ne": object_id}}]}

    duplicate_workout = await workouts_collection.find_one(duplicate_filter)

    if duplicate_workout:

        raise HTTPException(status_code=409, detail="A workout with this video already exists")

    previous_custom_thumbnail = str(existing_workout.get("custom_thumbnail") or "").strip()

    default_thumbnail = (payload.thumbnail or existing_workout.get("thumbnail") or existing_workout.get("thumbnail_url") or "").strip()
    custom_thumbnail = previous_custom_thumbnail
    unset_fields: dict[str, str] = {}

    if payload.image_base64:

        try:

            custom_thumbnail = _upload_image_to_s3(

                "workout-thumbnails",

                f"workout-{object_id}",

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Workout thumbnail upload failed: {exc}") from exc

    elif payload.removeThumbnail:

        custom_thumbnail = ""
        unset_fields["custom_thumbnail"] = ""

    if previous_custom_thumbnail and previous_custom_thumbnail != custom_thumbnail:

        _delete_image_from_s3(previous_custom_thumbnail)

    levels = _normalize_workout_level_values(payload.level, payload.levels)
    purposes = _normalize_workout_purpose_values(payload.tag, payload.purposes)
    update_doc = {

        "title": payload.title.strip(),

        "video_url": video_url,

        "video_source": video_source,

        "tag": purposes[0] if purposes else DEFAULT_WORKOUT_CATEGORY,
        "purposes": purposes,

        "equipment": payload.equipment.strip(),

        "level": levels[0] if levels else payload.level.strip(),
        "levels": levels,

        "duration_minutes": int(payload.durationMinutes or 0),

        "duration_seconds": int(payload.durationSeconds or 0),

        "visibility": payload.visibility,

        "thumbnail": default_thumbnail,

        "movements": _normalize_workout_movements_for_storage(payload.movements),

        "updated_at": datetime.now(timezone.utc),

    }

    if custom_thumbnail:

        update_doc["custom_thumbnail"] = custom_thumbnail

    update_operation: dict[str, Any] = {"$set": update_doc}

    if vimeo_id:

        update_doc["vimeo_id"] = vimeo_id

    else:

        unset_fields["vimeo_id"] = ""

    if unset_fields:

        update_operation["$unset"] = unset_fields

    await workouts_collection.update_one({"_id": object_id}, update_operation)

    updated_workout = await workouts_collection.find_one({"_id": object_id})

    if not updated_workout:

        raise HTTPException(status_code=404, detail="Workout not found")

    if str(existing_workout.get("visibility") or "Draft") != "Published" and payload.visibility == "Published":
        background_tasks.add_task(notify_users_of_published_workout, users_collection, updated_workout)

    return AdminWorkoutItem(**_serialize_admin_workout_record(updated_workout))

@router.delete("/admin/workouts/{workout_id}")

async def admin_delete_workout(

    workout_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    try:

        object_id = ObjectId(workout_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid workout id") from exc

    existing_workout = await workouts_collection.find_one({"_id": object_id})

    if not existing_workout:

        raise HTTPException(status_code=404, detail="Workout not found")

    delete_result = await workouts_collection.delete_one({"_id": object_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Workout not found")

    custom_thumbnail = str(existing_workout.get("custom_thumbnail") or "").strip()

    if custom_thumbnail:

        _delete_image_from_s3(custom_thumbnail)

    return {"status": "success", "message": "Workout deleted"}

@router.post("/admin/workouts/sync", response_model=AdminWorkoutSyncResponse)

async def admin_sync_workouts(

    payload: AdminWorkoutSyncRequest | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminWorkoutSyncResponse:

    try:

        summary = await sync_vimeo_workouts(_build_vimeo_import_options(payload))

    except VimeoSyncError as exc:

        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info(
        "admin_workout_sync_result synced_count=%s videos_discovered=%s modules_synced=%s synced_vimeo_ids=%s",
        summary.synced_count,
        summary.videos_discovered,
        summary.modules_synced,
        [str(item.get("vimeoId") or "").strip() for item in (summary.synced_videos or []) if isinstance(item, dict)],
    )

    return AdminWorkoutSyncResponse(

        message="Vimeo workout library synced successfully.",

        syncedCount=summary.synced_count,

        modulesSynced=summary.modules_synced,

        videosDiscovered=summary.videos_discovered,

        alreadyImportedCount=summary.already_imported_count,

        remainingToImport=max(summary.remaining_to_import - summary.synced_count, 0),

        syncedVideos=summary.synced_videos or [],

    )


@router.post("/admin/workouts/sync/preview", response_model=AdminWorkoutSyncPreviewResponse)
async def admin_preview_workout_sync(
    payload: AdminWorkoutSyncRequest | None = None,
    _: dict = Depends(_require_admin_user),
) -> AdminWorkoutSyncPreviewResponse:
    try:
        preview = await preview_vimeo_workout_import(_build_vimeo_import_options(payload))
    except VimeoSyncError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    library_total, untagged_count = await asyncio.gather(
        workouts_collection.count_documents({}),
        workouts_collection.count_documents(
            {
                "$or": [
                    {"tag": {"$exists": False}, "purposes": {"$exists": False}},
                    {"tag": "", "purposes": {"$in": [[], None]}},
                    {"equipment": {"$exists": False}},
                    {"equipment": ""},
                    {"level": {"$exists": False}, "levels": {"$exists": False}},
                    {"level": "", "levels": {"$in": [[], None]}},
                ]
            }
        ),
    )

    return AdminWorkoutSyncPreviewResponse(
        modulesSynced=preview.modules_synced,
        videosAvailable=preview.videos_available,
        alreadyImportedCount=preview.already_imported_count,
        remainingToImport=preview.remaining_to_import,
        libraryTotal=library_total,
        untaggedCount=untagged_count,
    )

@router.get("/admin/workouts/sync/debug", response_model=AdminWorkoutSyncDebugResponse)
async def admin_debug_synced_workouts(
    limit: int = 50,
    _: dict = Depends(_require_admin_user),
) -> AdminWorkoutSyncDebugResponse:
    capped_limit = max(1, min(int(limit or 50), 200))
    records = await workouts_collection.find(
        {
            "video_source": "VIMEO",
            "vimeo_id": {"$exists": True, "$ne": ""},
        },
        sort=[("vimeo_synced_at", -1), ("updated_at", -1), ("_id", -1)],
    ).to_list(length=capped_limit)

    workouts = [
        {
            "id": str(record["_id"]),
            "title": str(record.get("title") or ""),
            "vimeoId": str(record.get("vimeo_id") or ""),
            "tag": str(record.get("tag") or ""),
            "equipment": str(record.get("equipment") or ""),
            "level": str(record.get("level") or ""),
            "levels": normalize_workout_levels(record),
            "durationMinutes": int(record.get("duration_minutes") or 0),
            "visibility": str(record.get("visibility") or "Draft"),
            "providerVisibility": str(record.get("vimeo_provider_visibility") or "Draft"),
            "videoSource": str(record.get("video_source") or "VIMEO"),
            "vimeoSourceType": str(record.get("vimeo_source_type") or ""),
            "vimeoSourceUri": str(record.get("vimeo_source_uri") or ""),
            "vimeoSyncedAt": _as_utc(record.get("vimeo_synced_at")) if record.get("vimeo_synced_at") else None,
            "updatedAt": _as_utc(record.get("updated_at")) if record.get("updated_at") else None,
        }
        for record in records
    ]

    return AdminWorkoutSyncDebugResponse(total=len(workouts), workouts=workouts)
