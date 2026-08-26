from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/ai/nutrition/plan", response_model=NutritionPlanSaveResponse)

async def nutrition_plan(

    payload: NutritionPlanRequest,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanSaveResponse:

    logger.info("nutrition_plan_attempt user_id=%s", str(user["_id"]))

    payload_data = payload.model_dump()

    profile_hash = build_nutrition_plan_signature(payload_data)

    cached_record = await nutrition_plans_collection.find_one(

        _standard_nutrition_filter(str(user["_id"]), profile_hash),

        sort=[("created_at", -1)],

    )

    if cached_record and cached_record.get("plan"):

        plan_data = dict(cached_record["plan"])

        plan_data["plan_id"] = str(cached_record["_id"])
        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "nutrition_onboarding_profile": payload.model_dump(),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        logger.info(

            "nutrition_plan_cache_hit user_id=%s plan_id=%s",

            str(user["_id"]),

            plan_data["plan_id"],

        )

        await _record_trial_engagement(user, "nutrition_plan")
        return NutritionPlanSaveResponse(plan=NutritionPlanResponse(**plan_data))

    await _enforce_nutrition_generation_limit(user)

    try:

        result = await asyncio.to_thread(generate_nutrition_plan, payload_data)

    except NutritionPlanRefusalError as exc:

        raise HTTPException(status_code=422, detail=f"Nutrition plan refused: {exc}") from exc

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Nutrition plan unavailable: {exc}") from exc

    plan = NutritionPlanResponse(**result.data, profile=payload.model_dump())
    created_at = datetime.now(timezone.utc)
    insert_result = await nutrition_plans_collection.insert_one(
        {
            "user_id": str(user["_id"]),
            "profile_hash": profile_hash,
            "generation_mode": STANDARD_NUTRITION_PLAN_MODE,
            "plan": plan.model_dump(),
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    plan.plan_id = str(insert_result.inserted_id)

    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "nutrition_onboarding_profile": payload.model_dump(),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    logger.info(

        "nutrition_plan_generated user_id=%s plan_id=%s days=%s",

        str(user["_id"]),

        plan.plan_id,

        len(plan.days),

    )

    await _record_trial_engagement(user, "nutrition_plan")
    return NutritionPlanSaveResponse(plan=plan)

@router.post("/ai/nutrition/plan/jobs", response_model=NutritionPlanJobResponse, status_code=status.HTTP_202_ACCEPTED)

async def nutrition_plan_job(

    payload: NutritionPlanRequest,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanJobResponse:

    logger.info("nutrition_plan_job_attempt user_id=%s", str(user["_id"]))

    payload_data = payload.model_dump()

    profile_hash = build_nutrition_plan_signature(payload_data)

    cached_record = await nutrition_plans_collection.find_one(

        _standard_nutrition_filter(str(user["_id"]), profile_hash),

        sort=[("created_at", -1)],

    )

    if cached_record and cached_record.get("plan"):

        plan_data = dict(cached_record["plan"])

        plan_data["plan_id"] = str(cached_record["_id"])

        job_id = f"cached-{cached_record['_id']}"

        now = datetime.now(timezone.utc)

        logger.info("nutrition_plan_job_cache_hit user_id=%s plan_id=%s", str(user["_id"]), plan_data["plan_id"])

        return NutritionPlanJobResponse(

            job_id=job_id,

            status="completed",

            plan_id=plan_data["plan_id"],

            plan=NutritionPlanResponse(**plan_data),

            created_at=now,

            updated_at=now,

        )

    await _enforce_nutrition_generation_limit(user)

    created_at = datetime.now(timezone.utc)

    job_id = str(uuid4())

    await nutrition_plan_jobs_collection.insert_one(

        {

            "_id": job_id,

            "user_id": str(user["_id"]),

            "profile_hash": profile_hash,

            "generation_mode": STANDARD_NUTRITION_PLAN_MODE,

            "status": "queued",

            "plan_id": None,

            "plan": None,

            "error": None,

            "payload": payload_data,

            "created_at": created_at,

            "updated_at": created_at,

        }

    )

    logger.info("nutrition_plan_job_queued user_id=%s job_id=%s", str(user["_id"]), job_id)

    return NutritionPlanJobResponse(

        job_id=job_id,

        status="queued",

        created_at=created_at,

        updated_at=created_at,

    )

@router.get("/ai/nutrition/plan/jobs/{job_id}", response_model=NutritionPlanJobResponse)

async def nutrition_plan_job_status(

    job_id: str,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanJobResponse:

    logger.info("nutrition_plan_job_status_attempt user_id=%s job_id=%s", str(user["_id"]), job_id)

    record = await nutrition_plan_jobs_collection.find_one(

        {

            "_id": job_id,

            "user_id": str(user["_id"]),

        }

    )

    if not record:

        raise HTTPException(status_code=404, detail="Nutrition plan job not found")

    return _serialize_nutrition_plan_job(record)

@router.get("/ai/nutrition/plan/latest", response_model=NutritionPlanResponse | None)

async def nutrition_latest_plan(

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanResponse | None:

    logger.info("nutrition_latest_attempt user_id=%s", str(user["_id"]))

    record = await nutrition_plans_collection.find_one(

        _standard_nutrition_filter(str(user["_id"])),

        sort=[("created_at", -1)],

    )

    if not record or not record.get("plan"):
        return None

    plan_data = dict(record["plan"])

    plan_data["plan_id"] = str(record["_id"])

    logger.info("nutrition_latest_success user_id=%s plan_id=%s", str(user["_id"]), plan_data["plan_id"])

    return NutritionPlanResponse(**plan_data)

@router.patch("/ai/nutrition/plan/latest/completions", response_model=NutritionPlanResponse)

async def nutrition_latest_plan_completion(

    payload: NutritionMealCompletionUpdateRequest,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanResponse:

    logger.info(

        "nutrition_plan_completion_update_attempt user_id=%s day=%s meal_key=%s completed=%s",

        str(user["_id"]),

        payload.day,

        payload.meal_key,

        payload.completed,

    )

    record = await nutrition_plans_collection.find_one(

        _standard_nutrition_filter(str(user["_id"])),

        sort=[("created_at", -1)],

    )

    if not record or not record.get("plan"):

        raise HTTPException(status_code=404, detail="Nutrition plan not found")

    plan_data = dict(record["plan"])

    meal_completions = dict(plan_data.get("meal_completions") or {})

    day_completions = dict(meal_completions.get(payload.day) or {})

    day_completions[payload.meal_key] = payload.completed

    meal_completions[payload.day] = day_completions

    plan_data["meal_completions"] = meal_completions

    plan_data["plan_id"] = str(record["_id"])

    await nutrition_plans_collection.update_one(

        {"_id": record["_id"]},

        {

            "$set": {

                "plan": plan_data,

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )

    logger.info(

        "nutrition_plan_completion_update_success user_id=%s plan_id=%s",

        str(user["_id"]),

        plan_data["plan_id"],

    )

    return NutritionPlanResponse(**plan_data)

@router.post("/ai/nutrition/advice", response_model=NutritionAdviceResponse)

async def nutrition_advice(

    payload: NutritionAdviceRequest,

    user: dict = Depends(_require_nutrition_tracker_access_user),

) -> NutritionAdviceResponse:

    logger.info("nutrition_advice_attempt user_id=%s", str(user["_id"]))

    try:

        result = generate_nutrition_advice(payload.model_dump())

    except RuntimeError as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("nutrition_advice_success user_id=%s", str(user["_id"]))

    return NutritionAdviceResponse(reply=result.reply)

@router.post("/ai/nutrition/plan/progressive/jobs", response_model=NutritionPlanJobResponse, status_code=status.HTTP_202_ACCEPTED)

async def progressive_nutrition_plan_job(

    payload: NutritionPlanRequest,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanJobResponse:

    logger.info("progressive_nutrition_plan_job_attempt user_id=%s", str(user["_id"]))

    payload_data = payload.model_dump()

    profile_hash = build_nutrition_plan_signature(payload_data)

    user_id = str(user["_id"])

    cached_record = await nutrition_progressive_plans_collection.find_one(

        {

            "user_id": user_id,

            "profile_hash": profile_hash,

            "is_complete": True,

            "generation_mode": PROGRESSIVE_NUTRITION_PLAN_MODE,

        },

        sort=[("created_at", -1)],

    )

    if cached_record and cached_record.get("plan"):

        plan_data = dict(cached_record["plan"])

        plan_data["plan_id"] = str(cached_record["_id"])

        now = datetime.now(timezone.utc)

        return NutritionPlanJobResponse(

            job_id=f"cached-progressive-{cached_record['_id']}",

            status="completed",

            plan_id=plan_data["plan_id"],

            plan=NutritionPlanResponse(**plan_data),

            created_at=now,

            updated_at=now,

        )

    await _enforce_nutrition_generation_limit(user)

    created_at = datetime.now(timezone.utc)

    job_id = str(uuid4())

    await nutrition_progressive_plan_jobs_collection.insert_one(

        {

            "_id": job_id,

            "user_id": user_id,

            "profile_hash": profile_hash,

            "generation_mode": PROGRESSIVE_NUTRITION_PLAN_MODE,

            "status": "queued",

            "plan_id": None,

            "plan": None,

            "error": None,

            "payload": payload_data,

            "created_at": created_at,

            "updated_at": created_at,

        }

    )

    return NutritionPlanJobResponse(

        job_id=job_id,

        status="queued",

        created_at=created_at,

        updated_at=created_at,

    )

@router.get("/ai/nutrition/plan/progressive/jobs/{job_id}", response_model=NutritionPlanJobResponse)

async def progressive_nutrition_plan_job_status(

    job_id: str,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanJobResponse:

    record = await nutrition_progressive_plan_jobs_collection.find_one(

        {

            "_id": job_id,

            "user_id": str(user["_id"]),

            "generation_mode": PROGRESSIVE_NUTRITION_PLAN_MODE,

        }

    )

    if not record:

        raise HTTPException(status_code=404, detail="Progressive nutrition plan job not found")

    return _serialize_nutrition_plan_job(record)

@router.get("/ai/nutrition/plan/progressive/latest", response_model=NutritionPlanResponse)

async def progressive_nutrition_latest_plan(

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanResponse:

    record = await nutrition_progressive_plans_collection.find_one(

        {

            "user_id": str(user["_id"]),

            "generation_mode": PROGRESSIVE_NUTRITION_PLAN_MODE,

        },

        sort=[("created_at", -1)],

    )

    if not record or not record.get("plan"):

        raise HTTPException(status_code=404, detail="Progressive nutrition plan not found")

    plan_data = dict(record["plan"])

    plan_data["plan_id"] = str(record["_id"])

    return NutritionPlanResponse(**plan_data)

@router.patch("/ai/nutrition/plan/progressive/latest/completions", response_model=NutritionPlanResponse)

async def progressive_nutrition_latest_plan_completion(

    payload: NutritionMealCompletionUpdateRequest,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanResponse:

    record = await nutrition_progressive_plans_collection.find_one(

        {

            "user_id": str(user["_id"]),

            "generation_mode": PROGRESSIVE_NUTRITION_PLAN_MODE,

        },

        sort=[("created_at", -1)],

    )

    if not record or not record.get("plan"):

        raise HTTPException(status_code=404, detail="Progressive nutrition plan not found")

    plan_data = dict(record["plan"])

    meal_completions = dict(plan_data.get("meal_completions") or {})

    day_completions = dict(meal_completions.get(payload.day) or {})

    day_completions[payload.meal_key] = payload.completed

    meal_completions[payload.day] = day_completions

    plan_data["meal_completions"] = meal_completions

    plan_data["plan_id"] = str(record["_id"])

    await nutrition_progressive_plans_collection.update_one(

        {"_id": record["_id"]},

        {

            "$set": {

                "plan": plan_data,

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )

    return NutritionPlanResponse(**plan_data)
