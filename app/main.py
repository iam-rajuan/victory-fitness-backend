import asyncio
import base64
import logging
import re
from uuid import uuid4
from calendar import month_abbr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from bson import ObjectId
from dotenv import dotenv_values
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from .coach_archive import (
    build_archive_record,
    hydrate_archive_messages,
    load_thread_snapshot,
    s3_archive_enabled,
    store_thread_snapshot,
)
from .coach_victor import generate_coach_victor_reply
from .config import settings
from .database import DatabaseNotConfiguredError, ensure_indexes, users_collection
from .email_service import send_verification_email
from .journal_ai import generate_journal_analysis
from .models import (
    CoachVictorChatRequest,
    CoachVictorChatResponse,
    CoachVictorHistoryResponse,
    DashboardOverviewChartPoint,
    AdminUserChartPoint,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserManagementOverviewResponse,
    AdminUserSummaryResponse,
    AdminUserUpdateRequest,
    AdminWorkoutItem,
    AdminWorkoutListResponse,
    AdminWorkoutRequest,
    AdminWorkoutSyncResponse,
    DashboardOverviewRecentUser,
    DashboardOverviewResponse,
    JournalAnalysisRequest,
    JournalAnalysisResponse,
    JournalEntryCreateRequest,
    JournalEntryListResponse,
    JournalEntryResponse,
    MealImageAnalysisRequest,
    MealImageAnalysisResponse,
    LoginRequest,
    MeResponse,
    NutritionAdviceRequest,
    NutritionAdviceResponse,
    ProfileImageUploadRequest,
    ProfileImageUploadResponse,
    NutritionMealCompletionUpdateRequest,
    NutritionPlanJobResponse,
    NutritionPlanRequest,
    NutritionPlanResponse,
    NutritionPlanSaveResponse,
    RefreshRequest,
    RegisterRequest,
    UpdateMeRequest,
    TokenResponse,
    VerifyEmailRequest,
    WorkoutLibraryCategory,
    WorkoutLibraryItem,
    WorkoutLibraryResponse,
)
from .database import (
    coach_victor_archives_collection,
    coach_victor_threads_collection,
    nutrition_progressive_plan_jobs_collection,
    nutrition_progressive_plans_collection,
    journal_entries_collection,
    nutrition_plans_collection,
    nutrition_plan_jobs_collection,
    workouts_collection,
)
from .nutrition_ai import (
    NutritionPlanRefusalError,
    build_nutrition_plan_signature,
    generate_meal_image_analysis,
    generate_nutrition_advice,
    generate_nutrition_plan,
    generate_progressive_nutrition_plan_day,
)
from .security import (
    create_token,
    create_verification_code,
    decode_token,
    hash_password,
    verify_password,
)


app = FastAPI(title=settings.app_name)
bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger("victory_fitness.api")
STANDARD_NUTRITION_PLAN_MODE = "standard_v1"
PROGRESSIVE_NUTRITION_PLAN_MODE = "progressive_v2"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = perf_counter()
    logger.info("request_started method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%s",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "request_completed method=%s path=%s status_code=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(
    request: Request,
    exc: DatabaseNotConfiguredError,
) -> JSONResponse:
    logger.error("database_not_configured path=%s detail=%s", request.url.path, str(exc))
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    logger.warning(
        "http_exception method=%s path=%s status_code=%s detail=%s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    detail = str(exc).strip() or "Internal server error"
    logger.exception(
        "unhandled_exception method=%s path=%s detail=%s",
        request.method,
        request.url.path,
        detail,
    )
    return JSONResponse(status_code=500, content={"detail": detail})


async def _require_access_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await _get_verified_user(f"Bearer {token}")


async def _require_admin_user(user: dict = Depends(_require_access_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.on_event("startup")
async def startup() -> None:
    logger.info("startup_begin")
    await ensure_indexes()
    await _seed_admin_user()
    logger.info("startup_complete")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "success",
        "message": "Victory Fitness API is running",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/workouts/library", response_model=WorkoutLibraryResponse)
async def workout_library(query: str | None = None) -> WorkoutLibraryResponse:
    filter_doc: dict = {"visibility": "Published"}
    search = (query or "").strip()
    if search:
        escaped = re.escape(search)
        filter_doc["$or"] = [
            {"title": {"$regex": escaped, "$options": "i"}},
            {"tag": {"$regex": escaped, "$options": "i"}},
        ]

    records = await workouts_collection.find(
        filter_doc,
        sort=[("created_at", -1), ("_id", -1)],
    ).to_list(length=None)

    workouts = [WorkoutLibraryItem(**_serialize_public_workout_record(record)) for record in records]

    category_map: dict[str, dict[str, object]] = {}
    for workout in workouts:
        key = workout.tag.strip() or "Workout"
        if key not in category_map:
            category_map[key] = {
                "id": key.lower().replace(" ", "-"),
                "name": key,
                "count": 0,
                "image": workout.thumbnail,
            }
        category_map[key]["count"] = int(category_map[key]["count"]) + 1

    categories = [
        WorkoutLibraryCategory(
            id=str(item["id"]),
            name=str(item["name"]),
            count=int(item["count"]),
            image=str(item["image"] or ""),
        )
        for item in sorted(category_map.values(), key=lambda item: (-int(item["count"]), str(item["name"])))
    ]

    return WorkoutLibraryResponse(
        featuredWorkout=workouts[0] if workouts else None,
        workouts=workouts,
        categories=categories,
    )


@app.post("/auth/register", status_code=status.HTTP_202_ACCEPTED)
async def register(payload: RegisterRequest) -> dict[str, str]:
    email = payload.email.lower()
    logger.info("auth_register_attempt email=%s", email)
    existing_user = await users_collection.find_one({"email": email})
    if existing_user and existing_user.get("is_verified"):
        raise HTTPException(status_code=409, detail="Email is already registered")

    code = create_verification_code()
    now = datetime.now(timezone.utc)
    update_doc = {
        "$set": {
            "name": payload.name.strip(),
            "email": email,
            "password_hash": hash_password(payload.password),
            "is_verified": False,
            "role": "user",
            "is_admin": False,
            "verification_code_hash": hash_password(code),
            "verification_code_expires_at": now + timedelta(minutes=10),
            "updated_at": now,
        },
        "$setOnInsert": {"created_at": now},
    }
    await users_collection.update_one({"email": email}, update_doc, upsert=True)

    try:
        send_verification_email(email, code)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("auth_register_code_sent email=%s", email)
    return {"message": "Verification code sent", "email": email}


@app.post("/auth/verify-email", response_model=TokenResponse)
async def verify_email(payload: VerifyEmailRequest, response: Response) -> TokenResponse:
    email = payload.email.lower()
    logger.info("auth_verify_attempt email=%s", email)
    user = await users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("is_verified"):
        return await _issue_tokens(user, response)

    expires_at = user.get("verification_code_expires_at")
    if not expires_at or _as_utc(expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired")
    if not verify_password(payload.code, user["verification_code_hash"]):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"is_verified": True, "updated_at": datetime.now(timezone.utc)},
            "$unset": {"verification_code_hash": "", "verification_code_expires_at": ""},
        },
    )
    user["is_verified"] = True
    logger.info("auth_verify_success email=%s", email)
    return await _issue_tokens(user, response)


@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response) -> TokenResponse:
    logger.info("auth_login_attempt email=%s", payload.email.lower())
    user = await users_collection.find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_verified"):
        raise HTTPException(status_code=403, detail="Email is not verified")
    logger.info("auth_login_success email=%s", payload.email.lower())
    return await _issue_tokens(user, response)


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    payload: RefreshRequest | None = None,
    session_token: str | None = Cookie(default=None),
) -> TokenResponse:
    logger.info("auth_refresh_attempt")
    token = session_token or (payload.session_token if payload else None)
    if not token:
        raise HTTPException(status_code=401, detail="Missing session token")

    try:
        data = decode_token(token, "session")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid session token") from exc

    try:
        user_id = ObjectId(data["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session token") from exc

    user = await users_collection.find_one({"_id": user_id, "is_verified": True})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    logger.info("auth_refresh_success user_id=%s", str(user["_id"]))
    return await _issue_tokens(user, response)


@app.get("/auth/validate")
async def validate_authorization(user: dict = Depends(_require_access_user)) -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me", response_model=MeResponse)
async def get_me(user: dict = Depends(_require_access_user)) -> MeResponse:
    return MeResponse(**_serialize_me_record(user))


@app.patch("/me", response_model=MeResponse)
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

    if payload.profileImage is not None:
        update_doc["profile_image"] = payload.profileImage.strip()

    if not update_doc:
        return MeResponse(**_serialize_me_record(user))

    update_doc["updated_at"] = datetime.now(timezone.utc)
    await users_collection.update_one({"_id": user_id}, {"$set": update_doc})

    updated_user = await users_collection.find_one({"_id": user_id})
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    return MeResponse(**_serialize_me_record(updated_user))


@app.post("/me/profile-image", response_model=ProfileImageUploadResponse)
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

    logger.info("profile_image_upload_success user_id=%s", user_id)
    return ProfileImageUploadResponse(image_url=image_url)


@app.get("/admin/dashboard/overview", response_model=DashboardOverviewResponse)
async def admin_dashboard_overview(
    year: int | None = None,
    _: dict = Depends(_require_admin_user),
) -> DashboardOverviewResponse:
    selected_year = year or datetime.now(timezone.utc).year
    year_start = datetime(selected_year, 1, 1, tzinfo=timezone.utc)
    next_year_start = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)
    non_admin_filter = {"is_admin": {"$ne": True}}

    total_users = await users_collection.count_documents(non_admin_filter)
    recent_user_records = await users_collection.find(
        non_admin_filter,
        sort=[("created_at", -1)],
        limit=5,
    ).to_list(length=5)

    monthly_records = await users_collection.aggregate(
        [
            {
                "$match": {
                    **non_admin_filter,
                    "created_at": {
                        "$gte": year_start,
                        "$lt": next_year_start,
                    }
                }
            },
            {
                "$group": {
                    "_id": {"$month": "$created_at"},
                    "userCount": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    ).to_list(length=12)

    monthly_map = {int(item["_id"]): int(item.get("userCount", 0)) for item in monthly_records}
    user_chart = [
        DashboardOverviewChartPoint(
            month=month_abbr[month_number],
            userCount=monthly_map.get(month_number, 0),
            agentCount=0,
        )
        for month_number in range(1, 13)
    ]

    recent_users = [
        DashboardOverviewRecentUser(
            id=str(record["_id"]),
            fullName=str(record.get("name") or "Unknown"),
            email=record["email"],
            status="ACTIVE" if record.get("is_verified") else "PENDING",
            createdAt=_as_utc(record["created_at"]),
            profileImage=str(record.get("profile_image") or ""),
        )
        for record in recent_user_records
    ]

    return DashboardOverviewResponse(
        totalUsers=total_users,
        workoutsThisWeek=0,
        challengeCompletions=0,
        vimeoApiStatus=_get_vimeo_status(),
        userChart=user_chart,
        recentUsers=recent_users,
    )


@app.get("/admin/users/summary", response_model=AdminUserSummaryResponse)
async def admin_user_summary(
    year: int | None = None,
    _: dict = Depends(_require_admin_user),
) -> AdminUserSummaryResponse:
    return await _build_admin_user_summary_response(year)


@app.get("/admin/users", response_model=AdminUserListResponse)
async def admin_list_users(
    page: int = 1,
    limit: int = 10,
    query: str | None = None,
    _: dict = Depends(_require_admin_user),
) -> AdminUserListResponse:
    return await _build_admin_user_list_response(page=page, limit=limit, query=query)


@app.get("/admin/user-management", response_model=AdminUserManagementOverviewResponse)
async def admin_user_management_overview(
    page: int = 1,
    limit: int = 10,
    query: str | None = None,
    year: int | None = None,
    _: dict = Depends(_require_admin_user),
) -> AdminUserManagementOverviewResponse:
    summary, table = await asyncio.gather(
        _build_admin_user_summary_response(year),
        _build_admin_user_list_response(page=page, limit=limit, query=query),
    )
    return AdminUserManagementOverviewResponse(summary=summary, table=table)


@app.get("/admin/users/{user_id}", response_model=AdminUserDetailResponse)
async def admin_get_user(
    user_id: str,
    _: dict = Depends(_require_admin_user),
) -> AdminUserDetailResponse:
    try:
        object_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    record = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})
    if not record:
        raise HTTPException(status_code=404, detail="User not found")

    return AdminUserDetailResponse(**_serialize_admin_user_record(record))


@app.patch("/admin/users/{user_id}", response_model=AdminUserDetailResponse)
async def admin_update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> AdminUserDetailResponse:
    try:
        object_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    record = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})
    if not record:
        raise HTTPException(status_code=404, detail="User not found")

    update_doc: dict = {}

    if payload.fullName is not None:
        update_doc["name"] = payload.fullName.strip()
    if payload.email is not None:
        new_email = payload.email.lower()
        existing_user = await users_collection.find_one({"email": new_email, "_id": {"$ne": object_id}})
        if existing_user:
            raise HTTPException(status_code=409, detail="Email already exists")
        update_doc["email"] = new_email
    if payload.contactNumber is not None:
        update_doc["contact_number"] = payload.contactNumber.strip()
    if payload.country is not None:
        update_doc["country"] = payload.country.strip()
    if payload.profileImage is not None:
        update_doc["profile_image"] = payload.profileImage.strip()
    if payload.role is not None:
        normalized_role = payload.role.strip().lower()
        if normalized_role not in {"user", "trainer", "moderator", "admin"}:
            raise HTTPException(status_code=400, detail="Invalid role")
        if record["_id"] == admin_user["_id"] and normalized_role != "admin":
            raise HTTPException(status_code=400, detail="You cannot remove your own admin access")
        update_doc["role"] = normalized_role
        update_doc["is_admin"] = normalized_role == "admin"
    if payload.status is not None:
        normalized_status = payload.status.upper()
        update_doc["status"] = normalized_status
        update_doc["is_verified"] = normalized_status == "ACTIVE"
    if payload.isVerified is not None:
        update_doc["is_verified"] = payload.isVerified
        update_doc["status"] = "ACTIVE" if payload.isVerified else "PENDING"

    if not update_doc:
        return AdminUserDetailResponse(**_serialize_admin_user_record(record))

    update_doc["updated_at"] = datetime.now(timezone.utc)
    await users_collection.update_one({"_id": object_id}, {"$set": update_doc})

    updated_record = await users_collection.find_one({"_id": object_id})
    if not updated_record:
        raise HTTPException(status_code=404, detail="User not found")

    return AdminUserDetailResponse(**_serialize_admin_user_record(updated_record))


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    admin_user: dict = Depends(_require_admin_user),
) -> dict[str, str]:
    try:
        object_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    record = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})
    if not record:
        raise HTTPException(status_code=404, detail="User not found")
    if record["_id"] == admin_user["_id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    delete_result = await users_collection.delete_one({"_id": object_id, "is_admin": {"$ne": True}})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "success", "message": "User deleted"}


@app.get("/admin/workouts", response_model=AdminWorkoutListResponse)
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
            {"vimeo_id": {"$regex": escaped, "$options": "i"}},
            {"visibility": {"$regex": escaped, "$options": "i"}},
        ]

    records = await workouts_collection.find(
        filter_doc,
        sort=[("created_at", -1), ("_id", -1)],
    ).to_list(length=None)

    return AdminWorkoutListResponse(
        total=len(records),
        workouts=[AdminWorkoutItem(**_serialize_admin_workout_record(record)) for record in records],
    )


@app.post("/admin/workouts", response_model=AdminWorkoutItem, status_code=status.HTTP_201_CREATED)
async def admin_create_workout(
    payload: AdminWorkoutRequest,
    _: dict = Depends(_require_admin_user),
) -> AdminWorkoutItem:
    now = datetime.now(timezone.utc)
    vimeo_id = payload.vimeoId.strip()

    existing_workout = await workouts_collection.find_one({"vimeo_id": vimeo_id})
    if existing_workout:
        raise HTTPException(status_code=409, detail="A workout with this Vimeo ID already exists")

    document = {
        "title": payload.title.strip(),
        "vimeo_id": vimeo_id,
        "tag": payload.tag.strip(),
        "visibility": payload.visibility,
        "thumbnail": (payload.thumbnail or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    insert_result = await workouts_collection.insert_one(document)
    document["_id"] = insert_result.inserted_id
    return AdminWorkoutItem(**_serialize_admin_workout_record(document))


@app.patch("/admin/workouts/{workout_id}", response_model=AdminWorkoutItem)
async def admin_update_workout(
    workout_id: str,
    payload: AdminWorkoutRequest,
    _: dict = Depends(_require_admin_user),
) -> AdminWorkoutItem:
    try:
        object_id = ObjectId(workout_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid workout id") from exc

    existing_workout = await workouts_collection.find_one({"_id": object_id})
    if not existing_workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    vimeo_id = payload.vimeoId.strip()
    duplicate_workout = await workouts_collection.find_one({"vimeo_id": vimeo_id, "_id": {"$ne": object_id}})
    if duplicate_workout:
        raise HTTPException(status_code=409, detail="A workout with this Vimeo ID already exists")

    update_doc = {
        "title": payload.title.strip(),
        "vimeo_id": vimeo_id,
        "tag": payload.tag.strip(),
        "visibility": payload.visibility,
        "thumbnail": (payload.thumbnail or "").strip(),
        "updated_at": datetime.now(timezone.utc),
    }
    await workouts_collection.update_one({"_id": object_id}, {"$set": update_doc})

    updated_workout = await workouts_collection.find_one({"_id": object_id})
    if not updated_workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    return AdminWorkoutItem(**_serialize_admin_workout_record(updated_workout))


@app.delete("/admin/workouts/{workout_id}")
async def admin_delete_workout(
    workout_id: str,
    _: dict = Depends(_require_admin_user),
) -> dict[str, str]:
    try:
        object_id = ObjectId(workout_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid workout id") from exc

    delete_result = await workouts_collection.delete_one({"_id": object_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workout not found")

    return {"status": "success", "message": "Workout deleted"}


@app.post("/admin/workouts/sync", response_model=AdminWorkoutSyncResponse)
async def admin_sync_workouts(
    _: dict = Depends(_require_admin_user),
) -> AdminWorkoutSyncResponse:
    count = await workouts_collection.count_documents({})
    return AdminWorkoutSyncResponse(
        message="Workout sync is ready for Vimeo integration. Existing library has been refreshed.",
        syncedCount=count,
    )


@app.post("/journal/entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    payload: JournalEntryCreateRequest,
    user: dict = Depends(_require_access_user),
) -> JournalEntryResponse:
    user_id = str(user["_id"])
    logger.info("journal_create_attempt user_id=%s", user_id)
    now = datetime.now(timezone.utc)
    document = {
        "user_id": user_id,
        "mood": payload.mood.strip(),
        "content": payload.content.strip(),
        "created_at": now,
        "updated_at": now,
    }
    insert_result = await journal_entries_collection.insert_one(document)
    logger.info("journal_create_success user_id=%s entry_id=%s", user_id, str(insert_result.inserted_id))
    return JournalEntryResponse(
        id=str(insert_result.inserted_id),
        user_id=user_id,
        mood=document["mood"],
        content=document["content"],
        created_at=now,
        updated_at=now,
    )


@app.get("/journal/entries", response_model=JournalEntryListResponse)
async def list_journal_entries(
    user: dict = Depends(_require_access_user),
) -> JournalEntryListResponse:
    user_id = str(user["_id"])
    logger.info("journal_list_attempt user_id=%s", user_id)
    records = await journal_entries_collection.find(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    ).to_list(length=None)
    entries = [
        JournalEntryResponse(
            id=str(record["_id"]),
            user_id=record["user_id"],
            mood=record["mood"],
            content=record["content"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )
        for record in records
    ]
    logger.info("journal_list_success user_id=%s count=%s", user_id, len(entries))
    return JournalEntryListResponse(entries=entries)


@app.get("/journal/entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: str,
    user: dict = Depends(_require_access_user),
) -> JournalEntryResponse:
    user_id = str(user["_id"])
    logger.info("journal_get_attempt user_id=%s entry_id=%s", user_id, entry_id)
    try:
        object_id = ObjectId(entry_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid journal entry id") from exc

    record = await journal_entries_collection.find_one({"_id": object_id, "user_id": user_id})
    if not record:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    logger.info("journal_get_success user_id=%s entry_id=%s", user_id, entry_id)
    return JournalEntryResponse(
        id=str(record["_id"]),
        user_id=record["user_id"],
        mood=record["mood"],
        content=record["content"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@app.post("/journal/analyze", response_model=JournalAnalysisResponse)
async def analyze_journal_entry(
    payload: JournalAnalysisRequest,
    user: dict = Depends(_require_access_user),
) -> JournalAnalysisResponse:
    user_id = str(user["_id"])
    logger.info("journal_analyze_attempt user_id=%s", user_id)
    try:
        result = generate_journal_analysis(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Journal analysis unavailable: {exc}") from exc

    logger.info("journal_analyze_success user_id=%s", user_id)
    return JournalAnalysisResponse(analysis=result.analysis)


@app.post("/ai/meal-analysis", response_model=MealImageAnalysisResponse)
async def analyze_meal_image(
    payload: MealImageAnalysisRequest,
    user: dict = Depends(_require_access_user),
) -> MealImageAnalysisResponse:
    user_id = str(user["_id"])
    logger.info("meal_image_analyze_attempt user_id=%s file_name=%s", user_id, payload.file_name or "")
    try:
        result = generate_meal_image_analysis(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Meal image analysis unavailable: {exc}") from exc

    logger.info("meal_image_analyze_success user_id=%s", user_id)
    return MealImageAnalysisResponse(**result.data)


@app.post("/ai/coach-victor/chat", response_model=CoachVictorChatResponse)
async def coach_victor_chat(
    payload: CoachVictorChatRequest,
    user: dict = Depends(_require_access_user),
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
    return CoachVictorChatResponse(reply=result.reply, thread_id=thread_id)


@app.get("/ai/coach-victor/history", response_model=CoachVictorHistoryResponse)
async def coach_victor_history(
    user: dict = Depends(_require_access_user),
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


@app.post("/ai/nutrition/plan", response_model=NutritionPlanSaveResponse)
async def nutrition_plan(
    payload: NutritionPlanRequest,
    user: dict = Depends(_require_access_user),
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
        logger.info(
            "nutrition_plan_cache_hit user_id=%s plan_id=%s",
            str(user["_id"]),
            plan_data["plan_id"],
        )
        return NutritionPlanSaveResponse(plan=NutritionPlanResponse(**plan_data))

    try:
        result = generate_nutrition_plan(payload_data)
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
    logger.info(
        "nutrition_plan_saved user_id=%s plan_id=%s days=%s",
        str(user["_id"]),
        plan.plan_id,
        len(plan.days),
    )

    return NutritionPlanSaveResponse(plan=plan)


@app.post("/ai/nutrition/plan/jobs", response_model=NutritionPlanJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def nutrition_plan_job(
    payload: NutritionPlanRequest,
    user: dict = Depends(_require_access_user),
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

    asyncio.create_task(_process_nutrition_plan_job(job_id, str(user["_id"]), payload_data, profile_hash))

    logger.info("nutrition_plan_job_queued user_id=%s job_id=%s", str(user["_id"]), job_id)
    return NutritionPlanJobResponse(
        job_id=job_id,
        status="queued",
        created_at=created_at,
        updated_at=created_at,
    )


@app.get("/ai/nutrition/plan/jobs/{job_id}", response_model=NutritionPlanJobResponse)
async def nutrition_plan_job_status(
    job_id: str,
    user: dict = Depends(_require_access_user),
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


@app.get("/ai/nutrition/plan/latest", response_model=NutritionPlanResponse)
async def nutrition_latest_plan(
    user: dict = Depends(_require_access_user),
) -> NutritionPlanResponse:
    logger.info("nutrition_latest_attempt user_id=%s", str(user["_id"]))
    record = await nutrition_plans_collection.find_one(
        _standard_nutrition_filter(str(user["_id"])),
        sort=[("created_at", -1)],
    )
    if not record or not record.get("plan"):
        raise HTTPException(status_code=404, detail="Nutrition plan not found")

    plan_data = dict(record["plan"])
    plan_data["plan_id"] = str(record["_id"])
    logger.info("nutrition_latest_success user_id=%s plan_id=%s", str(user["_id"]), plan_data["plan_id"])
    return NutritionPlanResponse(**plan_data)


@app.patch("/ai/nutrition/plan/latest/completions", response_model=NutritionPlanResponse)
async def nutrition_latest_plan_completion(
    payload: NutritionMealCompletionUpdateRequest,
    user: dict = Depends(_require_access_user),
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


@app.post("/ai/nutrition/advice", response_model=NutritionAdviceResponse)
async def nutrition_advice(
    payload: NutritionAdviceRequest,
    user: dict = Depends(_require_access_user),
) -> NutritionAdviceResponse:
    logger.info("nutrition_advice_attempt user_id=%s", str(user["_id"]))
    try:
        result = generate_nutrition_advice(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("nutrition_advice_success user_id=%s", str(user["_id"]))
    return NutritionAdviceResponse(reply=result.reply)


async def _process_nutrition_plan_job(job_id: str, user_id: str, payload_data: dict, profile_hash: str) -> None:
    started_at = datetime.now(timezone.utc)
    await nutrition_plan_jobs_collection.update_one(
        {"_id": job_id, "user_id": user_id},
        {
            "$set": {
                "status": "processing",
                "updated_at": started_at,
            }
        },
    )

    try:
        cached_record = await nutrition_plans_collection.find_one(
            _standard_nutrition_filter(user_id, profile_hash),
            sort=[("created_at", -1)],
        )
        if cached_record and cached_record.get("plan"):
            plan_data = dict(cached_record["plan"])
            plan_data["plan_id"] = str(cached_record["_id"])
            await nutrition_plan_jobs_collection.update_one(
                {"_id": job_id, "user_id": user_id},
                {
                    "$set": {
                        "status": "completed",
                        "plan_id": plan_data["plan_id"],
                        "plan": plan_data,
                        "error": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            return

        result = await asyncio.to_thread(generate_nutrition_plan, payload_data)
        plan = NutritionPlanResponse(**result.data, profile=payload_data)
        created_at = datetime.now(timezone.utc)
        insert_result = await nutrition_plans_collection.insert_one(
            {
                "user_id": user_id,
                "profile_hash": profile_hash,
                "generation_mode": STANDARD_NUTRITION_PLAN_MODE,
                "plan": plan.model_dump(),
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        plan.plan_id = str(insert_result.inserted_id)
        await nutrition_plan_jobs_collection.update_one(
            {"_id": job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "completed",
                    "plan_id": plan.plan_id,
                    "plan": plan.model_dump(),
                    "error": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    except NutritionPlanRefusalError as exc:
        await nutrition_plan_jobs_collection.update_one(
            {"_id": job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "failed",
                    "error": f"Nutrition plan refused: {exc}",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    except Exception as exc:  # noqa: BLE001
        await nutrition_plan_jobs_collection.update_one(
            {"_id": job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "failed",
                    "error": f"Nutrition plan unavailable: {exc}",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )


@app.post("/ai/nutrition/plan/progressive/jobs", response_model=NutritionPlanJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def progressive_nutrition_plan_job(
    payload: NutritionPlanRequest,
    user: dict = Depends(_require_access_user),
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

    asyncio.create_task(_process_progressive_nutrition_plan_job(job_id, user_id, payload_data, profile_hash))

    return NutritionPlanJobResponse(
        job_id=job_id,
        status="queued",
        created_at=created_at,
        updated_at=created_at,
    )


@app.get("/ai/nutrition/plan/progressive/jobs/{job_id}", response_model=NutritionPlanJobResponse)
async def progressive_nutrition_plan_job_status(
    job_id: str,
    user: dict = Depends(_require_access_user),
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


@app.get("/ai/nutrition/plan/progressive/latest", response_model=NutritionPlanResponse)
async def progressive_nutrition_latest_plan(
    user: dict = Depends(_require_access_user),
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


@app.patch("/ai/nutrition/plan/progressive/latest/completions", response_model=NutritionPlanResponse)
async def progressive_nutrition_latest_plan_completion(
    payload: NutritionMealCompletionUpdateRequest,
    user: dict = Depends(_require_access_user),
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


async def _process_progressive_nutrition_plan_job(
    job_id: str,
    user_id: str,
    payload_data: dict,
    profile_hash: str,
) -> None:
    await nutrition_progressive_plan_jobs_collection.update_one(
        {"_id": job_id, "user_id": user_id},
        {
            "$set": {
                "status": "generating_monday",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    partial_plan_id: ObjectId | None = None
    partial_plan_data: dict | None = None
    generated_days: list[dict] = []
    summary_text = ""
    goal_label = ""

    try:
        for index, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            if index == 0:
                status_name = "generating_monday"
            else:
                status_name = f"generating_{day_name.lower()}"

            await nutrition_progressive_plan_jobs_collection.update_one(
                {"_id": job_id, "user_id": user_id},
                {
                    "$set": {
                        "status": status_name,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

            day_result = await asyncio.to_thread(
                generate_progressive_nutrition_plan_day,
                payload_data,
                day_name,
                generated_days,
            )
            day_plan = dict(day_result.data["days"][0])
            generated_days.append(day_plan)

            if not summary_text:
                summary_text = str(day_result.data.get("summary") or "").strip()
            if not goal_label:
                goal_label = str(day_result.data.get("goal_label") or "").strip()

            if partial_plan_id is None:
                created_at = datetime.now(timezone.utc)
                snapshot = _build_progressive_plan_snapshot(summary_text, goal_label, generated_days, payload_data)
                insert_result = await nutrition_progressive_plans_collection.insert_one(
                    {
                        "user_id": user_id,
                        "profile_hash": profile_hash,
                        "generation_mode": PROGRESSIVE_NUTRITION_PLAN_MODE,
                        "is_complete": False,
                        "plan": snapshot,
                        "created_at": created_at,
                        "updated_at": created_at,
                    }
                )
                partial_plan_id = insert_result.inserted_id
            else:
                snapshot = _build_progressive_plan_snapshot(summary_text, goal_label, generated_days, payload_data)
                await nutrition_progressive_plans_collection.update_one(
                    {"_id": partial_plan_id, "user_id": user_id},
                    {
                        "$set": {
                            "plan": snapshot,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )

            current_plan = NutritionPlanResponse(
                **snapshot,
                profile=payload_data,
            )
            current_plan.plan_id = str(partial_plan_id)
            partial_plan_data = current_plan.model_dump()

            await nutrition_progressive_plan_jobs_collection.update_one(
                {"_id": job_id, "user_id": user_id},
                {
                    "$set": {
                        "status": f"{day_name.lower()}_ready",
                        "plan_id": current_plan.plan_id,
                        "plan": partial_plan_data,
                        "error": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

        final_snapshot = _build_progressive_plan_snapshot(summary_text, goal_label, generated_days, payload_data)
        final_plan = NutritionPlanResponse(**final_snapshot, profile=payload_data)
        final_plan.plan_id = str(partial_plan_id)
        final_plan_data = final_plan.model_dump()

        await nutrition_progressive_plans_collection.update_one(
            {"_id": partial_plan_id, "user_id": user_id},
            {
                "$set": {
                    "plan": final_plan_data,
                    "is_complete": True,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        await nutrition_progressive_plan_jobs_collection.update_one(
            {"_id": job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "completed",
                    "plan_id": final_plan.plan_id,
                    "plan": final_plan_data,
                    "error": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    except NutritionPlanRefusalError as exc:
        await nutrition_progressive_plan_jobs_collection.update_one(
            {"_id": job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "failed",
                    "plan_id": str(partial_plan_id) if partial_plan_id else None,
                    "plan": partial_plan_data,
                    "error": f"Nutrition plan refused: {exc}",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    except Exception as exc:  # noqa: BLE001
        await nutrition_progressive_plan_jobs_collection.update_one(
            {"_id": job_id, "user_id": user_id},
            {
                "$set": {
                    "status": "failed",
                    "plan_id": str(partial_plan_id) if partial_plan_id else None,
                    "plan": partial_plan_data,
                    "error": f"Nutrition plan unavailable: {exc}",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )


def _serialize_nutrition_plan_job(record: dict) -> NutritionPlanJobResponse:
    plan_data = record.get("plan")
    plan = NutritionPlanResponse(**plan_data) if isinstance(plan_data, dict) else None
    return NutritionPlanJobResponse(
        job_id=str(record.get("_id")),
        status=str(record.get("status") or "queued"),
        plan_id=str(record["plan_id"]) if record.get("plan_id") else None,
        plan=plan,
        error=str(record["error"]) if record.get("error") else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


def _upload_profile_image_to_s3(
    user_id: str,
    image_base64: str,
    mime_type: str,
    file_name: str | None,
) -> str:
    if not s3_archive_enabled():
        raise RuntimeError("AWS S3 is not configured for profile image uploads")

    normalized_mime = str(mime_type or "image/jpeg").strip().lower()
    allowed_types = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    extension = allowed_types.get(normalized_mime)
    if extension is None:
        raise ValueError("Only JPEG, PNG, and WEBP profile images are supported")

    try:
        payload = base64.b64decode(image_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Profile image payload is not valid base64") from exc

    if len(payload) > 10 * 1024 * 1024:
        raise ValueError("Profile image must be 10MB or smaller")

    sanitized_file_name = re.sub(r"[^a-zA-Z0-9._-]", "-", str(file_name or "").strip()).strip("-")
    suffix = sanitized_file_name.rsplit(".", 1)[-1].lower() if "." in sanitized_file_name else ""
    if suffix and not extension.endswith(suffix):
        sanitized_file_name = ""

    object_name = sanitized_file_name or f"{uuid4().hex}{extension}"
    key_prefix = f"{settings.aws_s3_prefix}/profile-images/{user_id}".strip("/")
    object_key = f"{key_prefix}/{object_name}"

    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 profile image uploads") from exc

    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    client.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=object_key,
        Body=payload,
        ContentType=normalized_mime,
        CacheControl="public, max-age=31536000",
    )

    return f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{object_key}"


def _build_progressive_plan_snapshot(summary: str, goal_label: str, days: list[dict], payload_data: dict) -> dict:
    normalized_days = [dict(day) for day in days]
    shopping_list = _build_progressive_shopping_list(normalized_days)
    plan = {
        "summary": summary or "A practical weekly nutrition plan tailored to your profile.",
        "goal_label": goal_label or "Personalized Nutrition Plan",
        "days": normalized_days,
        "shopping_list": shopping_list,
        "meal_completions": {},
        "profile": payload_data,
    }
    return plan


def _build_progressive_shopping_list(days: list[dict]) -> list[dict]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for day in days:
        for meal_key in ("breakfast", "lunch", "dinner"):
            meal = day.get(meal_key, {})
            if not isinstance(meal, dict):
                continue
            for ingredient in meal.get("ingredients", []):
                label = str(ingredient).strip()
                lowered = label.lower()
                if label and lowered not in seen:
                    seen.add(lowered)
                    items.append({"name": label, "qty": "1 serving"})

    return [{"category": "Weekly Ingredients", "items": items[:60]}] if items else []


def _standard_nutrition_filter(user_id: str, profile_hash: str | None = None) -> dict:
    filter_doc: dict = {
        "user_id": user_id,
        "$or": [
            {"generation_mode": {"$exists": False}},
            {"generation_mode": STANDARD_NUTRITION_PLAN_MODE},
        ],
    }
    if profile_hash is not None:
        filter_doc["profile_hash"] = profile_hash
    return filter_doc


def _get_thread_recent_messages(thread: dict | None) -> list[dict]:
    if not thread:
        return []

    recent_messages = thread.get("recent_messages")
    if isinstance(recent_messages, list):
        return recent_messages

    legacy_messages = thread.get("messages")
    if isinstance(legacy_messages, list):
        return legacy_messages

    return []


async def _get_full_thread_messages(thread: dict | None) -> list[dict]:
    if not thread:
        return []

    snapshot_key = str(thread.get("latest_snapshot_s3_key") or "")
    snapshot_bucket = str(thread.get("latest_snapshot_s3_bucket") or "")
    if snapshot_key and snapshot_bucket:
        return load_thread_snapshot(snapshot_bucket, snapshot_key)

    stored_messages = _get_thread_recent_messages(thread)
    archived_messages: list[dict] = []
    archive_records = (
        await coach_victor_archives_collection.find(
            {"thread_id": str(thread["_id"])},
            sort=[("created_at", 1)],
        ).to_list(length=None)
    )
    for archive_record in archive_records:
        archived_messages.extend(hydrate_archive_messages(archive_record))

    return [*archived_messages, *stored_messages]


def _trim_recent_messages(messages: list[dict]) -> list[dict]:
    recent_limit = max(settings.coach_recent_message_limit, 2)
    return messages[-recent_limit:]


async def _build_thread_update_doc(
    thread_id: str,
    user_id: str,
    messages: list[dict],
    updated_at: datetime,
) -> dict:
    recent_messages = _trim_recent_messages(messages)
    update_doc: dict = {
        "$set": {
            "recent_messages": recent_messages,
            "recent_message_count": len(recent_messages),
            "updated_at": updated_at,
            "last_message_at": updated_at,
        },
        "$unset": {"messages": ""},
    }

    if s3_archive_enabled():
        snapshot = store_thread_snapshot(user_id, thread_id, messages)
        update_doc["$set"].update(
            {
                "latest_snapshot_s3_bucket": snapshot["s3_bucket"],
                "latest_snapshot_s3_key": snapshot["s3_key"],
                "snapshot_message_count": snapshot["message_count"],
                "last_snapshot_at": snapshot["created_at"],
                "storage_mode": "s3_snapshot",
            }
        )
        return update_doc

    archive_result = await _archive_thread_messages_if_needed(
        thread_id=thread_id,
        user_id=user_id,
        messages=messages,
    )
    update_doc["$set"]["recent_messages"] = archive_result["recent_messages"]
    update_doc["$set"]["recent_message_count"] = len(archive_result["recent_messages"])
    archive_count_increment = int(archive_result["archive_count_increment"])
    if archive_count_increment:
        update_doc["$inc"] = {"archive_count": archive_count_increment}
    if archive_result["last_archive_at"] is not None:
        update_doc["$set"]["last_archive_at"] = archive_result["last_archive_at"]
    update_doc["$set"]["storage_mode"] = "mongodb_archive"
    return update_doc


async def _build_new_thread_doc(
    user_id: str,
    messages: list[dict],
    created_at: datetime,
) -> dict:
    recent_messages = _trim_recent_messages(messages)
    thread_doc = {
        "user_id": user_id,
        "recent_messages": recent_messages,
        "recent_message_count": len(recent_messages),
        "archive_count": 0,
        "created_at": created_at,
        "updated_at": created_at,
        "last_message_at": created_at,
    }

    if s3_archive_enabled():
        thread_id = str(ObjectId())
        snapshot = store_thread_snapshot(user_id, thread_id, messages)
        thread_doc.update(
            {
                "_id": ObjectId(thread_id),
                "latest_snapshot_s3_bucket": snapshot["s3_bucket"],
                "latest_snapshot_s3_key": snapshot["s3_key"],
                "snapshot_message_count": snapshot["message_count"],
                "last_snapshot_at": snapshot["created_at"],
                "storage_mode": "s3_snapshot",
            }
        )
        return thread_doc

    thread_doc["storage_mode"] = "mongodb_archive"
    return thread_doc


async def _archive_thread_messages_if_needed(
    thread_id: str,
    user_id: str,
    messages: list[dict],
) -> dict[str, datetime | int | list[dict] | None]:
    recent_limit = max(settings.coach_recent_message_limit, 2)
    archive_batch_size = max(settings.coach_archive_batch_size, 2)

    if len(messages) <= recent_limit:
        return {
            "recent_messages": messages,
            "archive_count_increment": 0,
            "last_archive_at": None,
        }

    archive_count = len(messages) - recent_limit
    archive_count = max(archive_count, archive_batch_size)
    archive_count = min(archive_count, len(messages) - 2)
    if archive_count % 2 != 0:
        archive_count -= 1

    if archive_count <= 0:
        return {
            "recent_messages": messages,
            "archive_count_increment": 0,
            "last_archive_at": None,
        }

    archived_messages = messages[:archive_count]
    archive_record = build_archive_record(user_id, thread_id, archived_messages)
    await coach_victor_archives_collection.insert_one(archive_record)

    return {
        "recent_messages": messages[archive_count:],
        "archive_count_increment": 1,
        "last_archive_at": archive_record["created_at"],
    }


async def _issue_tokens(user: dict, response: Response | None) -> TokenResponse:
    user_id = str(user["_id"])
    access_token = create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    session_token = create_token(
        user_id,
        "session",
        timedelta(days=settings.session_token_expire_days),
    )

    if response:
        response.set_cookie(
            "access_token",
            access_token,
            max_age=settings.access_token_expire_minutes * 60,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
        response.set_cookie(
            "session_token",
            session_token,
            max_age=settings.session_token_expire_days * 24 * 60 * 60,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )

    return TokenResponse(
        access_token=access_token,
        session_token=session_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user={
            "id": user_id,
            "name": user["name"],
            "email": user["email"],
            "is_verified": bool(user.get("is_verified")),
            "role": str(user.get("role") or ("admin" if user.get("is_admin") else "user")),
            "is_admin": bool(user.get("is_admin")),
        },
    )


async def _seed_admin_user() -> None:
    if not settings.admin_seed_enabled:
        logger.info("admin_seed_skipped reason=disabled")
        return

    if not settings.admin_email or not settings.admin_password:
        logger.info("admin_seed_skipped reason=missing_credentials")
        return

    now = datetime.now(timezone.utc)
    existing_user = await users_collection.find_one({"email": settings.admin_email})
    if existing_user:
        await users_collection.update_one(
            {"_id": existing_user["_id"]},
            {
                "$set": {
                    "name": existing_user.get("name") or settings.admin_name,
                    "role": "admin",
                    "is_admin": True,
                    "is_verified": True,
                    "updated_at": now,
                },
                "$unset": {
                    "verification_code_hash": "",
                    "verification_code_expires_at": "",
                },
            },
        )
        logger.info("admin_seed_exists email=%s", settings.admin_email)
        return

    await users_collection.insert_one(
        {
            "name": settings.admin_name,
            "email": settings.admin_email,
            "password_hash": hash_password(settings.admin_password),
            "is_verified": True,
            "role": "admin",
            "is_admin": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    logger.info("admin_seed_created email=%s", settings.admin_email)


def _get_vimeo_status() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    env_values = dotenv_values(env_path)
    token = str(env_values.get("VIMEO_ACCESS_TOKEN") or "").strip()
    return "CONFIGURED" if token else "MISSING"


def _normalize_admin_user_status(record: dict) -> str:
    status = str(record.get("status") or "").strip().upper()
    if status in {"ACTIVE", "INACTIVE", "PENDING"}:
        return status
    return "ACTIVE" if record.get("is_verified") else "PENDING"


def _serialize_me_record(record: dict) -> dict:
    return {
        "id": str(record["_id"]),
        "name": str(record.get("name") or ""),
        "email": str(record.get("email") or ""),
        "is_verified": bool(record.get("is_verified")),
        "role": str(record.get("role") or ("admin" if record.get("is_admin") else "user")),
        "is_admin": bool(record.get("is_admin")),
        "country": str(record.get("country") or ""),
        "profileImage": str(record.get("profile_image") or ""),
    }


def _serialize_admin_user_record(record: dict) -> dict:
    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))
    updated_at = _as_utc(record.get("updated_at") or created_at)
    role = str(record.get("role") or ("admin" if record.get("is_admin") else "user"))

    return {
        "id": str(record["_id"]),
        "fullName": str(record.get("name") or "Unknown"),
        "email": str(record.get("email") or ""),
        "role": role,
        "status": _normalize_admin_user_status(record),
        "isVerified": bool(record.get("is_verified")),
        "contactNumber": str(record.get("contact_number") or ""),
        "country": str(record.get("country") or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
        "profileImage": str(record.get("profile_image") or ""),
    }


def _build_admin_user_query(query: str | None) -> dict:
    base_query: dict = {"is_admin": {"$ne": True}}
    search = (query or "").strip()
    if not search:
        return base_query

    escaped = re.escape(search)
    base_query["$or"] = [
        {"name": {"$regex": escaped, "$options": "i"}},
        {"email": {"$regex": escaped, "$options": "i"}},
        {"contact_number": {"$regex": escaped, "$options": "i"}},
        {"country": {"$regex": escaped, "$options": "i"}},
        {"role": {"$regex": escaped, "$options": "i"}},
    ]
    return base_query


def _serialize_admin_workout_record(record: dict) -> dict:
    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))
    updated_at = _as_utc(record.get("updated_at") or created_at)
    return {
        "id": str(record["_id"]),
        "title": str(record.get("title") or ""),
        "vimeoId": str(record.get("vimeo_id") or ""),
        "tag": str(record.get("tag") or ""),
        "visibility": str(record.get("visibility") or "Draft"),
        "thumbnail": str(record.get("thumbnail") or ""),
        "dateAdded": created_at,
        "updatedAt": updated_at,
    }


def _serialize_public_workout_record(record: dict) -> dict:
    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))
    return {
        "id": str(record["_id"]),
        "title": str(record.get("title") or ""),
        "vimeoId": str(record.get("vimeo_id") or ""),
        "tag": str(record.get("tag") or "Workout"),
        "thumbnail": str(record.get("thumbnail") or ""),
        "dateAdded": created_at,
    }


async def _build_admin_user_summary_response(year: int | None = None) -> AdminUserSummaryResponse:
    selected_year = year or datetime.now(timezone.utc).year
    year_start = datetime(selected_year, 1, 1, tzinfo=timezone.utc)
    next_year_start = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)
    non_admin_filter = {"is_admin": {"$ne": True}}

    total_users = await users_collection.count_documents(non_admin_filter)
    active_users = await users_collection.count_documents({**non_admin_filter, "is_verified": True})
    pending_users = max(total_users - active_users, 0)

    monthly_records = await users_collection.aggregate(
        [
            {
                "$match": {
                    **non_admin_filter,
                    "created_at": {
                        "$gte": year_start,
                        "$lt": next_year_start,
                    },
                }
            },
            {
                "$group": {
                    "_id": {"$month": "$created_at"},
                    "userCount": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    ).to_list(length=12)

    active_monthly_records = await users_collection.aggregate(
        [
            {
                "$match": {
                    **non_admin_filter,
                    "is_verified": True,
                    "created_at": {
                        "$gte": year_start,
                        "$lt": next_year_start,
                    },
                }
            },
            {
                "$group": {
                    "_id": {"$month": "$created_at"},
                    "userCount": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    ).to_list(length=12)

    monthly_map = {int(item["_id"]): int(item.get("userCount", 0)) for item in monthly_records}
    active_monthly_map = {int(item["_id"]): int(item.get("userCount", 0)) for item in active_monthly_records}
    user_chart = [
        AdminUserChartPoint(
            month=month_abbr[month_number],
            userCount=monthly_map.get(month_number, 0),
            activeUserCount=active_monthly_map.get(month_number, 0),
        )
        for month_number in range(1, 13)
    ]

    return AdminUserSummaryResponse(
        totalUsers=total_users,
        activeUsers=active_users,
        pendingUsers=pending_users,
        userChart=user_chart,
    )


async def _build_admin_user_list_response(
    page: int = 1,
    limit: int = 10,
    query: str | None = None,
) -> AdminUserListResponse:
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    skip = (page - 1) * limit
    filter_doc = _build_admin_user_query(query)

    total = await users_collection.count_documents(filter_doc)
    records = await users_collection.find(
        filter_doc,
        sort=[("created_at", -1), ("_id", -1)],
    ).skip(skip).limit(limit).to_list(length=limit)

    return AdminUserListResponse(
        total=total,
        page=page,
        limit=limit,
        users=[AdminUserListItem(**_serialize_admin_user_record(record)) for record in records],
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _get_verified_user(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing access token")

    token = authorization.split(" ", 1)[1].strip()

    try:
        data = decode_token(token, "access")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    try:
        user_id = ObjectId(data["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    user = await users_collection.find_one({"_id": user_id, "is_verified": True})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid access token")

    return user
