from fastapi import APIRouter

from ...core.legacy import *
from ...utils.country import derive_country_code

router = APIRouter()


def _validate_minimum_supported_age(age_value: str | None) -> None:
    normalized = str(age_value or "").strip()
    if not normalized:
        return
    try:
        age = int(float(normalized))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Age must be a valid number") from exc
    if age < 16:
        raise HTTPException(status_code=400, detail="You must be at least 16 years old to use Victory Fitness")

@router.get("/me", response_model=MeResponse)

async def get_me(user: dict = Depends(_require_access_user)) -> MeResponse:

    return MeResponse(**(await _serialize_me_record(user)))

@router.get("/me/onboarding", response_model=OnboardingStateResponse)
async def get_me_onboarding(user: dict = Depends(_require_access_user)) -> OnboardingStateResponse:
    return OnboardingStateResponse(**_serialize_onboarding_state(user))

@router.patch("/me", response_model=MeResponse)

async def update_me(

    payload: UpdateMeRequest,

    user: dict = Depends(_require_access_user),

) -> MeResponse:

    user_id = user["_id"]

    update_doc: dict = {}

    if payload.name is not None:

        update_doc["name"] = payload.name.strip()

    if payload.email is not None:

        new_email = payload.email.lower().strip()

        existing_user = await users_collection.find_one({"email": new_email, "_id": {"$ne": user_id}})

        if existing_user:

            raise HTTPException(status_code=409, detail="Email already exists")

        update_doc["email"] = new_email

    if payload.country is not None:

        update_doc["country"] = payload.country.strip()

        if payload.country_code is None:

            derived_country_code = derive_country_code(payload.country)

            update_doc["country_code"] = derived_country_code.upper() if derived_country_code else None

    if payload.country_code is not None:

        normalized_country_code = payload.country_code.strip().upper()

        update_doc["country_code"] = normalized_country_code or None

    if payload.motivation_statement is not None:

        motivation_statement = payload.motivation_statement.strip()

        update_doc["motivation_statement"] = motivation_statement or None
        update_doc["onboarding_state.motivationStatement"] = motivation_statement

    if payload.identity_statement is not None:
        identity_statement = payload.identity_statement.strip()
        update_doc["identity_statement"] = identity_statement or None

    if payload.workout_unlock_label is not None:
        workout_unlock_label = payload.workout_unlock_label.strip()
        update_doc["workout_unlock_label"] = workout_unlock_label or None

    if payload.training_trigger_context is not None:
        training_trigger_context = payload.training_trigger_context.strip()
        update_doc["training_trigger_context"] = training_trigger_context or None

    if payload.training_trigger_action is not None:
        training_trigger_action = payload.training_trigger_action.strip()
        update_doc["training_trigger_action"] = training_trigger_action or None

    if payload.profileImage is not None:

        update_doc["profile_image"] = payload.profileImage.strip()

    if payload.onboarding_completed is not None:

        update_doc["onboarding_completed"] = payload.onboarding_completed

    if not update_doc:

        return MeResponse(**(await _serialize_me_record(user)))

    update_doc["updated_at"] = datetime.now(timezone.utc)

    await users_collection.update_one({"_id": user_id}, {"$set": update_doc})

    updated_user = await users_collection.find_one({"_id": user_id})

    if not updated_user:

        raise HTTPException(status_code=404, detail="User not found")

    await _sync_community_author_profile(updated_user)

    return MeResponse(**(await _serialize_me_record(updated_user)))

@router.patch("/me/onboarding", response_model=OnboardingStateResponse)
async def update_me_onboarding(
    payload: UpdateOnboardingStateRequest,
    user: dict = Depends(_require_access_user),
) -> OnboardingStateResponse:
    user_id = user["_id"]
    next_state = _serialize_onboarding_state(user)
    update_doc: dict[str, Any] = {}
    next_metrics = dict(user.get("body_metrics") or {})

    if payload.currentStep is not None:
        next_state["currentStep"] = payload.currentStep

    if payload.language is not None:
        next_state["language"] = payload.language.strip()

    if payload.country is not None:
        next_state["country"] = payload.country.strip()
        update_doc["country"] = payload.country.strip()

        if payload.countryCode is None:
            derived_country_code = derive_country_code(payload.country)
            normalized_country_code = derived_country_code.upper() if derived_country_code else None
            next_state["countryCode"] = normalized_country_code
            update_doc["country_code"] = normalized_country_code

    if payload.countryCode is not None:
        normalized_country_code = payload.countryCode.strip().upper() or None
        next_state["countryCode"] = normalized_country_code
        update_doc["country_code"] = normalized_country_code

    if payload.motivationStatement is not None:
        motivation_statement = payload.motivationStatement.strip()
        next_state["motivationStatement"] = motivation_statement
        update_doc["motivation_statement"] = motivation_statement or None

    if payload.personalProfile is not None:
        personal_profile_update = payload.personalProfile.model_dump()
        _validate_minimum_supported_age(personal_profile_update.get("age"))
        next_state["personalProfile"] = {
            **dict(next_state.get("personalProfile") or {}),
            **personal_profile_update,
        }
        for field_name in ("age", "gender", "height", "weight"):
            field_value = personal_profile_update.get(field_name)
            if field_value is not None:
                next_metrics[field_name] = str(field_value).strip()

    if payload.anamnese is not None:
        next_state["anamnese"] = payload.anamnese.model_dump()

    if payload.suggestion is not None:
        next_state["suggestion"] = payload.suggestion.model_dump()

    if payload.completed is not None:
        update_doc["onboarding_completed"] = payload.completed
        next_state["completed"] = payload.completed

    next_state["updatedAt"] = datetime.now(timezone.utc)
    update_doc["onboarding_state"] = {
        "userId": next_state["userId"],
        "currentStep": next_state["currentStep"],
        "language": next_state["language"],
        "country": str(next_state.get("country") or "").strip(),
        "countryCode": (str(next_state.get("countryCode") or "").upper() or None),
        "motivationStatement": str(next_state.get("motivationStatement") or "").strip(),
        "personalProfile": next_state["personalProfile"],
        "anamnese": next_state["anamnese"],
        "suggestion": next_state["suggestion"],
        "updatedAt": next_state["updatedAt"],
    }
    update_doc["body_metrics"] = next_metrics

    await users_collection.update_one({"_id": user_id}, {"$set": update_doc})
    updated_user = await users_collection.find_one({"_id": user_id})
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return OnboardingStateResponse(**_serialize_onboarding_state(updated_user))

@router.post("/me/profile-image", response_model=ProfileImageUploadResponse)

async def upload_profile_image(

    payload: ProfileImageUploadRequest,

    user: dict = Depends(_require_access_user),

) -> ProfileImageUploadResponse:

    user_id = str(user["_id"])

    logger.info("profile_image_upload_attempt user_id=%s", user_id)

    try:

        image_url = await asyncio.to_thread(

            _upload_profile_image_to_s3,

            user_id,

            payload.image_base64,

            payload.mime_type,

            payload.file_name,

        )

    except RuntimeError as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await users_collection.update_one(

        {"_id": user["_id"]},

        {

            "$set": {

                "profile_image": image_url,

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )

    updated_user = await users_collection.find_one({"_id": user["_id"]})

    if updated_user:

        await _sync_community_author_profile(updated_user)

    logger.info("profile_image_upload_success user_id=%s", user_id)

    return ProfileImageUploadResponse(image_url=image_url)

@router.patch("/me/subscription", response_model=MeResponse)

async def update_subscription(

    payload: UpdateSubscriptionRequest,

    user: dict = Depends(_require_access_user),

) -> MeResponse:

    if _normalize_subscription_tier(payload.subscription_tier) != "NONE":

        raise HTTPException(status_code=400, detail="Use Stripe Checkout to start or change a paid subscription")

    now = datetime.now(timezone.utc)

    update_doc = await _build_subscription_update_doc(user, payload, now)

    await users_collection.update_one({"_id": user["_id"]}, {"$set": update_doc})

    updated_user = await users_collection.find_one({"_id": user["_id"]})

    if not updated_user:

        raise HTTPException(status_code=404, detail="User not found")

    previous_tier = _normalize_subscription_tier(user.get("subscription_tier"))
    updated_tier = _normalize_subscription_tier(updated_user.get("subscription_tier"))
    previous_status = _normalize_subscription_status(user.get("subscription_status"), previous_tier)
    updated_status = _normalize_subscription_status(updated_user.get("subscription_status"), updated_tier)
    if (previous_tier, previous_status) != (updated_tier, updated_status) and updated_status == "ACTIVE":
        await notify_user(
            users_collection,
            updated_user,
            f"{updated_tier.title().replace('_', ' ')} plan activated",
            "Your Victory Fitness plan is active and your included features are ready.",
            "subscription_activated",
            {"type": "subscription", "tier": updated_tier, "route": "/profile"},
        )

    return MeResponse(**(await _serialize_me_record(updated_user)))

@router.get("/me/body-metrics", response_model=BodyMetricsResponse)

async def get_body_metrics(user: dict = Depends(_require_access_user)) -> BodyMetricsResponse:

    metrics = dict(user.get("body_metrics") or {})

    return BodyMetricsResponse(

        age=str(metrics.get("age") or ""),

        height=str(metrics.get("height") or ""),

        weight=str(metrics.get("weight") or ""),

        gender=str(metrics.get("gender") or ""),

    )

@router.patch("/me/body-metrics", response_model=BodyMetricsResponse)

async def update_body_metrics(

    payload: UpdateBodyMetricsRequest,

    user: dict = Depends(_require_access_user),

) -> BodyMetricsResponse:

    next_metrics = dict(user.get("body_metrics") or {})

    if payload.age is not None:
        _validate_minimum_supported_age(payload.age)

        next_metrics["age"] = payload.age.strip()

    if payload.height is not None:

        next_metrics["height"] = payload.height.strip()

    if payload.weight is not None:

        next_metrics["weight"] = payload.weight.strip()

    if payload.gender is not None:

        next_metrics["gender"] = payload.gender.strip()

    await users_collection.update_one(

        {"_id": user["_id"]},

        {

            "$set": {

                "body_metrics": next_metrics,

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )

    return BodyMetricsResponse(

        age=str(next_metrics.get("age") or ""),

        height=str(next_metrics.get("height") or ""),

        weight=str(next_metrics.get("weight") or ""),

        gender=str(next_metrics.get("gender") or ""),

    )
