from fastapi import APIRouter

from ...core.legacy import *
from ...country_food_data import get_country_food_dataset
from ...nutrition_ai import _build_fallback_nutrition_plan, _normalize_nutrition_plan

router = APIRouter()


def _today_log_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _serialize_nutrition_meal_log(record: dict) -> NutritionMealLogResponse:
    return NutritionMealLogResponse(
        id=str(record.get("_id") or ""),
        name=str(record.get("name") or "Logged meal"),
        protein=max(0, int(record.get("protein") or 0)),
        carbs=max(0, int(record.get("carbs") or 0)),
        fat=max(0, int(record.get("fat") or 0)),
        calories=max(0, int(record.get("calories") or 0)),
        source=str(record.get("source") or "manual"),
        source_analysis_id=str(record.get("source_analysis_id") or ""),
        logged_date=str(record.get("logged_date") or _today_log_date()),
        completed=bool(record["completed"]) if "completed" in record else True,
        created_at=record.get("created_at") or datetime.now(timezone.utc),
    )


def _nutrition_payload_with_user_country(payload_data: dict, user: dict) -> dict:
    enriched = dict(payload_data)
    country = str(enriched.get("country") or user.get("country") or "").strip()
    country_code = str(enriched.get("country_code") or enriched.get("countryCode") or user.get("country_code") or "").strip().upper()
    if country:
        enriched["country"] = country
    if country_code:
        enriched["country_code"] = country_code
    return enriched


def _validate_nutrition_favorites_or_country_dataset(payload_data: dict) -> None:
    meals = [
        str(item).strip()
        for item in (payload_data.get("favorite_meals") or payload_data.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    if payload_data.get("favorite_meal") and str(payload_data.get("favorite_meal")).strip():
        meal = str(payload_data.get("favorite_meal")).strip()
        if meal.lower() not in {item.lower() for item in meals}:
            meals.insert(0, meal)
    cuisine = str(payload_data.get("cuisine") or "").strip()
    has_specific_cuisine = bool(cuisine) and cuisine.lower() not in {"balanced", "any", "mixed", "local"}
    if len(meals) >= 3 or get_country_food_dataset(payload_data) or has_specific_cuisine:
        return
    raise HTTPException(
        status_code=422,
        detail="Choose at least one cuisine or add at least 3 favourite meals to build your meal plan.",
    )


@router.get("/ai/nutrition/meal-logs", response_model=NutritionMealLogListResponse)
async def list_nutrition_meal_logs(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(_require_meal_plan_access_user),
) -> NutritionMealLogListResponse:
    logged_date = str(date or _today_log_date())
    records = await nutrition_logs_collection.find(
        {"user_id": str(user["_id"]), "logged_date": logged_date},
        sort=[("created_at", 1), ("_id", 1)],
    ).to_list(length=100)
    return NutritionMealLogListResponse(logs=[_serialize_nutrition_meal_log(record) for record in records])


@router.post("/ai/nutrition/meal-logs", response_model=NutritionMealLogResponse, status_code=status.HTTP_201_CREATED)
async def create_nutrition_meal_log(
    payload: NutritionMealLogCreateRequest,
    user: dict = Depends(_require_meal_plan_access_user),
) -> NutritionMealLogResponse:
    now = datetime.now(timezone.utc)
    document = {
        "_id": ObjectId(),
        "user_id": str(user["_id"]),
        "name": payload.name.strip(),
        "protein": payload.protein,
        "carbs": payload.carbs,
        "fat": payload.fat,
        "calories": payload.calories,
        "source": str(payload.source or "manual").strip() or "manual",
        "source_analysis_id": str(payload.source_analysis_id or "").strip(),
        "logged_date": payload.logged_date or now.date().isoformat(),
        "completed": payload.completed,
        "created_at": now,
        "updated_at": now,
    }
    await nutrition_logs_collection.insert_one(document)
    try:
        await _record_trial_engagement(user, "meal_logged")
    except Exception:
        pass
    return _serialize_nutrition_meal_log(document)


@router.patch("/ai/nutrition/meal-logs/{log_id}", response_model=NutritionMealLogResponse)
async def update_nutrition_meal_log(
    log_id: str,
    payload: NutritionMealLogUpdateRequest,
    user: dict = Depends(_require_meal_plan_access_user),
) -> NutritionMealLogResponse:
    if not ObjectId.is_valid(log_id):
        raise HTTPException(status_code=404, detail="Meal log not found")
    updated = await nutrition_logs_collection.find_one_and_update(
        {"_id": ObjectId(log_id), "user_id": str(user["_id"])},
        {"$set": {"completed": payload.completed, "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Meal log not found")
    return _serialize_nutrition_meal_log(updated)


@router.delete("/ai/nutrition/meal-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_nutrition_meal_log(
    log_id: str,
    user: dict = Depends(_require_meal_plan_access_user),
) -> Response:
    if not ObjectId.is_valid(log_id):
        raise HTTPException(status_code=404, detail="Meal log not found")
    result = await nutrition_logs_collection.delete_one({"_id": ObjectId(log_id), "user_id": str(user["_id"])})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Meal log not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/ai/nutrition/plan", response_model=NutritionPlanSaveResponse)

async def nutrition_plan(

    payload: NutritionPlanRequest,

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanSaveResponse:

    logger.info("nutrition_plan_attempt user_id=%s", str(user["_id"]))

    payload_data = _nutrition_payload_with_user_country(payload.model_dump(), user)
    _validate_nutrition_favorites_or_country_dataset(payload_data)

    profile_hash = build_nutrition_plan_signature(payload_data)

    cached_record = None
    if not payload.regenerate and not payload.force_refresh:
        cached_record = await nutrition_plans_collection.find_one(
            _standard_nutrition_filter(str(user["_id"]), profile_hash),
            sort=[("created_at", -1)],
        )

    # Only return cache if it already has pre_workout and post_workout meals
    has_pre_and_post = False
    if cached_record and cached_record.get("plan") and isinstance(cached_record["plan"].get("days"), list):
        days = cached_record["plan"]["days"]
        if days and isinstance(days[0], dict) and "pre_workout" in days[0] and "post_workout" in days[0]:
            has_pre_and_post = True

    if cached_record and cached_record.get("plan") and has_pre_and_post:
        plan_data = dict(cached_record["plan"])
        plan_data["plan_id"] = str(cached_record["_id"])
        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "nutrition_onboarding_profile": payload_data,
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

    plan = NutritionPlanResponse(**result.data, profile=payload_data)
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
                "nutrition_onboarding_profile": payload_data,
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

    payload_data = _nutrition_payload_with_user_country(payload.model_dump(), user)
    _validate_nutrition_favorites_or_country_dataset(payload_data)

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
        user_profile = dict(user.get("nutrition_onboarding_profile") or {})
        if not user_profile:
            user_profile = {
                "goal": user.get("goal") or "g1",
                "weight": float(user.get("weight") or 70.0),
                "diet": user.get("diet") or "d1",
                "cuisine": user.get("cuisine") or "balanced",
                "country": user.get("country") or "",
                "country_code": user.get("country_code") or "",
            }
        user_profile = _nutrition_payload_with_user_country(user_profile, user)
        base_plan = _build_fallback_nutrition_plan(user_profile)
        created_at = datetime.now(timezone.utc)
        insert_res = await nutrition_plans_collection.insert_one(
            {
                "user_id": str(user["_id"]),
                "profile_hash": "starter_baseline",
                "generation_mode": STANDARD_NUTRITION_PLAN_MODE,
                "plan": base_plan,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        record = {
            "_id": insert_res.inserted_id,
            "plan": base_plan,
        }

    plan_raw = dict(record["plan"])
    # Normalize plan to guarantee pre_workout and post_workout are populated even on legacy saved records
    plan_dict = _normalize_nutrition_plan(plan_raw)
    plan_data = dict(plan_dict)
    plan_data["plan_id"] = str(record["_id"])
    if plan_raw.get("profile"):
        plan_data["profile"] = plan_raw["profile"]

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
        user_profile = dict(user.get("nutrition_onboarding_profile") or {})
        if not user_profile:
            user_profile = {
                "goal": user.get("goal") or "g1",
                "weight": float(user.get("weight") or 70.0),
                "diet": user.get("diet") or "d1",
                "cuisine": user.get("cuisine") or "balanced",
                "country": user.get("country") or "",
                "country_code": user.get("country_code") or "",
            }
        user_profile = _nutrition_payload_with_user_country(user_profile, user)
        base_plan = _build_fallback_nutrition_plan(user_profile)
        created_at = datetime.now(timezone.utc)
        insert_res = await nutrition_plans_collection.insert_one(
            {
                "user_id": str(user["_id"]),
                "profile_hash": "starter_baseline",
                "generation_mode": STANDARD_NUTRITION_PLAN_MODE,
                "plan": base_plan,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        record = {
            "_id": insert_res.inserted_id,
            "plan": base_plan,
        }

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

    if payload.completed:
        try:
            await _record_trial_engagement(user, "meal_logged")
        except Exception:
            pass

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

    payload_data = _nutrition_payload_with_user_country(payload.model_dump(), user)
    _validate_nutrition_favorites_or_country_dataset(payload_data)

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
