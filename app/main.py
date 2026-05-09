from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .coach_victor import generate_coach_victor_reply
from .config import settings
from .database import DatabaseNotConfiguredError, ensure_indexes, users_collection
from .email_service import send_verification_email
from .models import (
    CoachVictorChatRequest,
    CoachVictorChatResponse,
    CoachVictorHistoryResponse,
    LoginRequest,
    NutritionAdviceRequest,
    NutritionAdviceResponse,
    NutritionPlanRequest,
    NutritionPlanResponse,
    NutritionPlanSaveResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from .database import coach_victor_threads_collection, nutrition_plans_collection
from .nutrition_ai import (
    NutritionPlanRefusalError,
    generate_nutrition_advice,
    generate_nutrition_plan,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(
    _request: Request,
    exc: DatabaseNotConfiguredError,
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


async def _require_access_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await _get_verified_user(f"Bearer {token}")


@app.on_event("startup")
async def startup() -> None:
    await ensure_indexes()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "success",
        "message": "Victory Fitness API is running",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", status_code=status.HTTP_202_ACCEPTED)
async def register(payload: RegisterRequest) -> dict[str, str]:
    email = payload.email.lower()
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

    return {"message": "Verification code sent", "email": email}


@app.post("/auth/verify-email", response_model=TokenResponse)
async def verify_email(payload: VerifyEmailRequest, response: Response) -> TokenResponse:
    email = payload.email.lower()
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
    return await _issue_tokens(user, response)


@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response) -> TokenResponse:
    user = await users_collection.find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_verified"):
        raise HTTPException(status_code=403, detail="Email is not verified")
    return await _issue_tokens(user, response)


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    payload: RefreshRequest | None = None,
    session_token: str | None = Cookie(default=None),
) -> TokenResponse:
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
    return await _issue_tokens(user, response)


@app.get("/auth/validate")
async def validate_authorization(user: dict = Depends(_require_access_user)) -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ai/coach-victor/chat", response_model=CoachVictorChatResponse)
async def coach_victor_chat(
    payload: CoachVictorChatRequest,
    user: dict = Depends(_require_access_user),
) -> CoachVictorChatResponse:
    user_id = str(user["_id"])
    thread = await coach_victor_threads_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1)],
    )

    existing_messages = thread.get("messages", []) if thread else []
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

    if thread:
        await coach_victor_threads_collection.update_one(
            {"_id": thread["_id"]},
            {
                "$push": {"messages": {"$each": [user_message, assistant_message]}},
                "$set": {"updated_at": now},
            },
        )
        thread_id = str(thread["_id"])
    else:
        insert_result = await coach_victor_threads_collection.insert_one(
            {
                "user_id": user_id,
                "messages": [user_message, assistant_message],
                "created_at": now,
                "updated_at": now,
            }
        )
        thread_id = str(insert_result.inserted_id)

    return CoachVictorChatResponse(reply=result.reply, thread_id=thread_id)


@app.get("/ai/coach-victor/history", response_model=CoachVictorHistoryResponse)
async def coach_victor_history(
    user: dict = Depends(_require_access_user),
) -> CoachVictorHistoryResponse:
    user_id = str(user["_id"])
    thread = await coach_victor_threads_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1)],
    )
    stored_messages = thread.get("messages", []) if thread else []

    return CoachVictorHistoryResponse(
        thread_id=str(thread["_id"]) if thread else None,
        messages=[
            {
                "id": item["id"],
                "role": item["role"],
                "content": item["content"],
                "created_at": item["created_at"],
            }
            for item in stored_messages
        ]
    )


@app.post("/ai/nutrition/plan", response_model=NutritionPlanSaveResponse)
async def nutrition_plan(
    payload: NutritionPlanRequest,
    user: dict = Depends(_require_access_user),
) -> NutritionPlanSaveResponse:
    try:
        result = generate_nutrition_plan(payload.model_dump())
    except NutritionPlanRefusalError as exc:
        raise HTTPException(status_code=422, detail=f"Nutrition plan refused: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Nutrition plan unavailable: {exc}") from exc

    plan = NutritionPlanResponse(**result.data, profile=payload.model_dump())
    created_at = datetime.now(timezone.utc)
    insert_result = await nutrition_plans_collection.insert_one(
        {
            "user_id": str(user["_id"]),
            "plan": plan.model_dump(),
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    plan.plan_id = str(insert_result.inserted_id)

    return NutritionPlanSaveResponse(plan=plan)


@app.get("/ai/nutrition/plan/latest", response_model=NutritionPlanResponse)
async def nutrition_latest_plan(
    user: dict = Depends(_require_access_user),
) -> NutritionPlanResponse:
    record = await nutrition_plans_collection.find_one(
        {"user_id": str(user["_id"])},
        sort=[("created_at", -1)],
    )
    if not record or not record.get("plan"):
        raise HTTPException(status_code=404, detail="Nutrition plan not found")

    return NutritionPlanResponse(
        **record["plan"],
        plan_id=str(record["_id"]),
    )


@app.post("/ai/nutrition/advice", response_model=NutritionAdviceResponse)
async def nutrition_advice(
    payload: NutritionAdviceRequest,
    user: dict = Depends(_require_access_user),
) -> NutritionAdviceResponse:
    try:
        result = generate_nutrition_advice(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return NutritionAdviceResponse(reply=result.reply)


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
            samesite="lax",
        )
        response.set_cookie(
            "session_token",
            session_token,
            max_age=settings.session_token_expire_days * 24 * 60 * 60,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
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
        },
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
