from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import Cookie, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import ensure_indexes, users_collection
from .email_service import send_verification_email
from .models import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, VerifyEmailRequest
from .security import (
    create_token,
    create_verification_code,
    decode_token,
    hash_password,
    verify_password,
)


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
async def validate_authorization(authorization: str | None = Header(default=None)) -> dict[str, str]:
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

    return {"status": "ok"}


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
