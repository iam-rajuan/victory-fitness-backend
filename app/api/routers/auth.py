from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()


def _verification_code_matches(payload_code: str, user: dict) -> bool:
    now = datetime.now(timezone.utc)
    for hash_field, expiry_field in (
        ("verification_code_hash", "verification_code_expires_at"),
        ("previous_verification_code_hash", "previous_verification_code_expires_at"),
    ):
        expires_at = user.get(expiry_field)
        code_hash = str(user.get(hash_field) or "").strip()
        if not expires_at or not code_hash or _as_utc(expires_at) < now:
            continue
        if verify_password(payload_code, code_hash):
            return True
    return False


def _remember_previous_verification_code(existing_user: dict | None, now: datetime) -> tuple[dict, dict]:
    if not existing_user or existing_user.get("is_verified"):
        return {}, {
            "previous_verification_code_hash": "",
            "previous_verification_code_expires_at": "",
        }

    current_hash = str(existing_user.get("verification_code_hash") or "").strip()
    current_expires_at = existing_user.get("verification_code_expires_at")
    if current_hash and current_expires_at and _as_utc(current_expires_at) >= now:
        return {
            "previous_verification_code_hash": current_hash,
            "previous_verification_code_expires_at": current_expires_at,
        }, {}

    return {}, {
        "previous_verification_code_hash": "",
        "previous_verification_code_expires_at": "",
    }


@router.post("/auth/register", status_code=status.HTTP_202_ACCEPTED)

async def register(payload: RegisterRequest) -> dict[str, str]:

    email = payload.email.lower()
    normalized_beta_access_code = str(payload.beta_access_code or "").strip().upper()
    if normalized_beta_access_code and _is_phase_one_beta_enabled() and not _is_phase_one_beta_code_valid(normalized_beta_access_code):
        raise HTTPException(status_code=400, detail="Invalid Phase 1 beta access code")

    logger.info("auth_register_attempt email=%s", email)

    existing_user = await users_collection.find_one({"email": email})

    if existing_user and existing_user.get("is_verified"):

        raise HTTPException(status_code=409, detail="Email is already registered")

    code = create_verification_code()
    first_name = payload.name.strip()
    last_name = payload.surname.strip()
    full_name = f"{first_name} {last_name}".strip()
    mobile = payload.mobile.strip()

    now = datetime.now(timezone.utc)
    previous_code_set, previous_code_unset = _remember_previous_verification_code(existing_user, now)

    update_doc = {

        "$set": {

            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,

            "email": email,
            "contact_number": mobile,
            "marketing_consent": payload.marketing_consent,
            "signup_source": payload.signup_source.strip() or "organic",
            "phase_one_beta_requested_code": normalized_beta_access_code or None,
            "marketing_consent_at": now if payload.marketing_consent else None,

            "password_hash": hash_password(payload.password),

            "is_verified": False,

            "role": "user",

            "is_admin": False,

            "subscription_tier": "NONE",

            "subscription_role": "NONE",

            "subscription_status": "NONE",

            "subscription_billing_cycle": "yearly",

            "subscription_is_purchased": False,

            "subscription_purchase_source": "",

            "onboarding_completed": False,

            "verification_code_hash": hash_password(code),

            "verification_code_expires_at": now + timedelta(minutes=10),

            "updated_at": now,

        },

        "$setOnInsert": {"created_at": now},

    }
    update_doc["$set"].update(previous_code_set)
    if previous_code_unset:
        update_doc["$unset"] = previous_code_unset

    await users_collection.update_one({"email": email}, update_doc, upsert=True)

    try:

        send_verification_email(email, code)

    except RuntimeError as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("auth_register_code_sent email=%s", email)

    return {"message": "Verification code sent", "email": email}

@router.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(payload: ResendVerificationRequest) -> dict[str, str]:
    email = payload.email.lower()
    user = await users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(status_code=404, detail="No pending registration found for this email")
    if user.get("is_verified"):
        raise HTTPException(status_code=409, detail="Email is already registered")

    code = create_verification_code()
    now = datetime.now(timezone.utc)
    previous_code_set, previous_code_unset = _remember_previous_verification_code(user, now)
    set_doc = {
        "verification_code_hash": hash_password(code),
        "verification_code_expires_at": now + timedelta(minutes=10),
        "updated_at": now,
    }
    set_doc.update(previous_code_set)
    update_doc = {"$set": set_doc}
    if previous_code_unset:
        update_doc["$unset"] = previous_code_unset

    await users_collection.update_one(
        {"_id": user["_id"]},
        update_doc,
    )

    try:
        send_verification_email(email, code)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("auth_register_code_resent email=%s", email)
    return {"message": "Verification code sent", "email": email}

@router.post("/auth/verify-email", response_model=TokenResponse)

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

    if not _verification_code_matches(payload.code, user):

        raise HTTPException(status_code=400, detail="Invalid verification code")

    await users_collection.update_one(

        {"_id": user["_id"]},

        {

            "$set": {"is_verified": True, "updated_at": datetime.now(timezone.utc)},

            "$unset": {
                "verification_code_hash": "",
                "verification_code_expires_at": "",
                "previous_verification_code_hash": "",
                "previous_verification_code_expires_at": "",
            },

        },

    )

    user["is_verified"] = True

    logger.info("auth_verify_success email=%s", email)

    user = await _maybe_activate_phase_one_beta_subscription(user)

    return await _issue_tokens(user, response)

@router.post("/auth/forgot-password")

async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, str]:

    email = payload.email.lower()

    logger.info("auth_forgot_password_attempt email=%s", email)

    user = await users_collection.find_one({"email": email, "is_verified": True})

    if not user:

        logger.info("auth_forgot_password_skipped email=%s reason=user_not_found", email)

        return {"message": "If that account exists, a reset code has been sent", "email": email}

    code = create_verification_code()

    now = datetime.now(timezone.utc)

    await users_collection.update_one(

        {"_id": user["_id"]},

        {

            "$set": {

                "reset_code_hash": hash_password(code),

                "reset_code_expires_at": now + timedelta(minutes=10),

                "updated_at": now,

            }

        },

    )

    try:

        send_password_reset_email(email, code)

    except RuntimeError as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("auth_forgot_password_code_sent email=%s", email)

    return {"message": "If that account exists, a reset code has been sent", "email": email}

@router.post("/auth/verify-reset-code")

async def verify_reset_code(payload: VerifyResetCodeRequest) -> dict[str, str]:

    email = payload.email.lower()

    logger.info("auth_verify_reset_attempt email=%s", email)

    user = await users_collection.find_one({"email": email, "is_verified": True})

    if not user:

        raise HTTPException(status_code=404, detail="User not found")

    expires_at = user.get("reset_code_expires_at")

    code_hash = str(user.get("reset_code_hash") or "")

    if not expires_at or _as_utc(expires_at) < datetime.now(timezone.utc):

        raise HTTPException(status_code=400, detail="Reset code expired")

    if not code_hash or not verify_password(payload.code, code_hash):

        raise HTTPException(status_code=400, detail="Invalid reset code")

    reset_token = create_token(

        str(user["_id"]),

        "password_reset",

        timedelta(minutes=15),

    )

    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_reset_token_hash": hash_password(reset_token)}},
    )
    logger.info("auth_verify_reset_success email=%s", email)

    return {"message": "Reset code verified", "reset_token": reset_token}

@router.post("/auth/reset-password")

async def reset_password(payload: ResetPasswordRequest) -> dict[str, str]:

    logger.info("auth_reset_password_attempt")

    try:

        data = decode_token(payload.reset_token, "password_reset")

    except ValueError as exc:

        raise HTTPException(status_code=401, detail="Invalid reset token") from exc

    try:

        user_id = ObjectId(data["sub"])

    except Exception as exc:

        raise HTTPException(status_code=401, detail="Invalid reset token") from exc

    user = await users_collection.find_one({"_id": user_id, "is_verified": True})

    if not user:

        raise HTTPException(status_code=401, detail="Invalid reset token")

    token_hash = str(user.get("password_reset_token_hash") or "").strip()
    if not token_hash or not verify_password(payload.reset_token, token_hash):
        raise HTTPException(status_code=401, detail="Invalid or already used reset token")

    await users_collection.update_one(

        {"_id": user_id},

        {

            "$set": {

                "password_hash": hash_password(payload.new_password),

                "updated_at": datetime.now(timezone.utc),

            },

            "$unset": {"reset_code_hash": "", "reset_code_expires_at": "", "password_reset_token_hash": ""},

        },

    )

    logger.info("auth_reset_password_success user_id=%s", str(user_id))

    return {"message": "Password reset successful"}

@router.post("/auth/login", response_model=TokenResponse)

async def login(

    payload: LoginRequest,

    response: Response,

    x_victory_client: str | None = Header(default=None, alias="X-Victory-Client"),

) -> TokenResponse:

    logger.info("auth_login_attempt email=%s", payload.email.lower())

    user = await users_collection.find_one({"email": payload.email.lower()})

    if not user or not str(user.get("password_hash") or "").strip() or not verify_password(payload.password, user["password_hash"]):

        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("is_verified"):

        raise HTTPException(status_code=403, detail="Email is not verified")

    logger.info("auth_login_success email=%s", payload.email.lower())

    return await _issue_tokens(user, response, issue_cookies=not _is_app_client_request(x_victory_client))

@router.post("/auth/firebase", response_model=TokenResponse)

async def firebase_login(payload: FirebaseAuthRequest, response: Response) -> TokenResponse:

    profile = _verify_firebase_id_token(payload.id_token)

    user = await _upsert_firebase_user(profile)

    logger.info("auth_firebase_login_success email=%s", str(profile.get("email") or "").lower())

    return await _issue_tokens(user, response)

@router.post("/auth/google", response_model=TokenResponse)

async def google_login(
    payload: GoogleAuthRequest,
    response: Response,
    x_victory_client: str | None = Header(default=None, alias="X-Victory-Client"),
) -> TokenResponse:

    profile, provider = _resolve_google_profile(payload)

    if provider == "firebase":

        user = await _upsert_firebase_user(profile)

    else:

        user = await _upsert_google_user(profile)

    user = await _maybe_activate_phase_one_beta_subscription(user)

    logger.info("auth_google_login_success provider=%s email=%s", provider, str(profile.get("email") or "").lower())

    return await _issue_tokens(user, response, issue_cookies=not _is_app_client_request(x_victory_client))

@router.post("/auth/refresh", response_model=TokenResponse)

async def refresh(

    response: Response,

    payload: RefreshRequest | None = None,

    session_token: str | None = Cookie(default=None),

    x_victory_client: str | None = Header(default=None, alias="X-Victory-Client"),

) -> TokenResponse:

    logger.info("auth_refresh_attempt")

    request_session_token = payload.session_token if payload and payload.session_token else None

    token = request_session_token or session_token

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

    if not _token_matches_auth_session(data, user):

        raise HTTPException(status_code=401, detail="Session expired")

    logger.info("auth_refresh_success user_id=%s", str(user["_id"]))

    return await _issue_tokens(user, response, issue_cookies=not _is_app_client_request(x_victory_client))

@router.post("/auth/logout")

async def logout(

    response: Response,

    payload: LogoutRequest | None = None,

    authorization: str | None = Header(default=None),

    session_token: str | None = Cookie(default=None),

    x_victory_client: str | None = Header(default=None, alias="X-Victory-Client"),

) -> dict[str, str]:

    user: dict | None = None

    access_token = str(authorization or "").replace("Bearer ", "", 1).strip()
    if access_token:
        try:
            access_payload = decode_token(access_token, "access")
            user_id = ObjectId(access_payload["sub"])
            candidate = await users_collection.find_one({"_id": user_id, "is_verified": True})
            if candidate and _token_matches_auth_session(access_payload, candidate):
                user = candidate
        except Exception:
            user = None

    request_session_token = payload.session_token if payload and payload.session_token else None
    effective_session_token = request_session_token or session_token
    if user is None and effective_session_token:
        try:
            session_payload = decode_token(effective_session_token, "session")
            user_id = ObjectId(session_payload["sub"])
            candidate = await users_collection.find_one({"_id": user_id, "is_verified": True})
            if candidate and _token_matches_auth_session(session_payload, candidate):
                user = candidate
        except Exception:
            user = None

    if user is not None:
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"auth_session_version": _get_auth_session_version(user) + 1}},
        )

    if _is_app_client_request(x_victory_client):

        return {"message": "Logged out"}

    response.delete_cookie(

        "access_token",

        secure=settings.cookie_secure,

        samesite=settings.cookie_samesite,

    )

    response.delete_cookie(

        "session_token",

        secure=settings.cookie_secure,

        samesite=settings.cookie_samesite,

    )

    return {"message": "Logged out"}

@router.get("/auth/validate")

async def validate_authorization(user: dict = Depends(_require_access_user)) -> dict[str, str]:

    return {"status": "ok"}
