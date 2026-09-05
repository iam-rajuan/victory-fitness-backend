import html
import json
from datetime import timedelta
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response as FastAPIResponse

from ...core.legacy import *

router = APIRouter()

GOOGLE_OAUTH_RESULTS: dict[str, dict] = {}


def _is_local_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}


def _request_origin(request: Request | None) -> str:
    if request is None:
        return ""

    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    forwarded_host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")

    return str(request.base_url).rstrip("/")


def _resolve_google_redirect_uri(request: Request | None = None) -> str:
    configured = str(getattr(settings, "google_redirect_uri", "") or "").strip()
    if configured and not _is_local_url(configured):
        return configured

    origin = _request_origin(request)
    if origin and not _is_local_url(origin):
        return f"{origin}/auth/google/callback"

    return configured


def _is_allowed_google_return_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    allowed_origins = {str(item).rstrip("/") for item in (getattr(settings, "cors_origins", []) or [])}
    allowed_origins.update(
        {
            "http://localhost:3000",
            "http://localhost:8081",
            "https://victory-fitness-app-one.vercel.app",
            "https://victoryfitnessapp.com",
        }
    )
    return normalized in allowed_origins


def _google_oauth_error_page(message: str, *, origin: str = "*") -> FastAPIResponse:
    payload = json.dumps({"type": "victory-google-auth", "ok": False, "error": message})
    target_origin = origin if origin != "*" else "*"
    body = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Google sign-in</title></head>
<body>
<script>
  const payload = {payload};
  if (window.opener) {{
    window.opener.postMessage(payload, {json.dumps(target_origin)});
    window.close();
  }} else {{
    document.body.textContent = payload.error || "Google sign-in failed.";
  }}
</script>
</body>
</html>"""
    return FastAPIResponse(content=body, media_type="text/html", status_code=200)


def _google_oauth_success_page(auth: TokenResponse, origin: str) -> FastAPIResponse:
    payload = json.dumps(
        {"type": "victory-google-auth", "ok": True, "auth": auth.model_dump(mode="json")},
        separators=(",", ":"),
    )
    body = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Google sign-in</title></head>
<body>
<script>
  const payload = {payload};
  if (window.opener) {{
    window.opener.postMessage(payload, {json.dumps(origin)});
    window.close();
  }} else {{
    document.body.textContent = "Google sign-in complete. You can close this window.";
  }}
</script>
</body>
</html>"""
    return FastAPIResponse(content=body, media_type="text/html", status_code=200)


def _google_oauth_complete_redirect(origin: str, payload: dict) -> RedirectResponse:
    encoded_payload = quote(json.dumps(payload, separators=(",", ":")))
    return RedirectResponse(f"{origin}/google-auth-complete#victory_google_auth={encoded_payload}")


def _google_oauth_result_redirect(origin: str, flow_id: str) -> RedirectResponse:
    return RedirectResponse(f"{origin}/google-auth-complete?{urlencode({'status': 'complete', 'flow_id': flow_id})}")


def _store_google_oauth_result(flow_id: str, payload: dict) -> None:
    normalized_flow_id = str(flow_id or "").strip()
    if not normalized_flow_id:
        return
    GOOGLE_OAUTH_RESULTS[normalized_flow_id] = {
        "created_at": datetime.now(timezone.utc),
        "payload": payload,
    }


def _get_google_oauth_result(flow_id: str) -> dict | None:
    normalized_flow_id = str(flow_id or "").strip()
    if not normalized_flow_id:
        return None

    now = datetime.now(timezone.utc)
    expired_keys = [
        key
        for key, record in GOOGLE_OAUTH_RESULTS.items()
        if _as_utc(record.get("created_at")) < now - timedelta(minutes=10)
    ]
    for key in expired_keys:
        GOOGLE_OAUTH_RESULTS.pop(key, None)

    record = GOOGLE_OAUTH_RESULTS.get(normalized_flow_id)
    if not record:
        return None
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else None


def _exchange_google_oauth_code(code: str, redirect_uri: str | None = None) -> dict:
    client_id = str(getattr(settings, "google_client_id", "") or "").strip()
    client_secret = str(getattr(settings, "google_client_secret", "") or "").strip()
    resolved_redirect_uri = str(redirect_uri or _resolve_google_redirect_uri() or "").strip()
    token_uri = str(getattr(settings, "google_token_uri", "") or "https://oauth2.googleapis.com/token").strip()
    if not client_id or not client_secret or not resolved_redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    body = urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": resolved_redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = UrlRequest(
        token_uri,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Google authorization failed") from exc


@router.get("/auth/google/start")
async def google_oauth_start(
    request: Request,
    return_origin: str = Query(..., min_length=8, max_length=300),
    flow_id: str = Query(..., min_length=12, max_length=120),
) -> RedirectResponse:
    origin = return_origin.rstrip("/")
    if not _is_allowed_google_return_origin(origin):
        raise HTTPException(status_code=400, detail="Invalid Google sign-in return origin")

    client_id = str(getattr(settings, "google_client_id", "") or "").strip()
    redirect_uri = _resolve_google_redirect_uri(request)
    auth_uri = str(getattr(settings, "google_auth_uri", "") or "https://accounts.google.com/o/oauth2/auth").strip()
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")

    state = create_token(origin, "google_oauth_state", timedelta(minutes=10), extra_claims={"flow_id": flow_id})
    authorization_url = f"{auth_uri}?{urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    })}"
    return RedirectResponse(authorization_url)


@router.get("/auth/google/result")
async def google_oauth_result(flow_id: str = Query(..., min_length=12, max_length=120)) -> dict:
    payload = _get_google_oauth_result(flow_id)
    if not payload:
        return {"status": "pending"}
    return {"status": "complete", "payload": payload}


@router.get("/auth/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> FastAPIResponse:
    origin = "*"
    try:
        if not state:
            return _google_oauth_error_page("Google sign-in state was missing.")
        try:
            state_payload = decode_token(state, "google_oauth_state")
        except ValueError:
            return _google_oauth_error_page("Google sign-in session expired. Please try again.")

        origin = str(state_payload.get("sub") or "").rstrip("/")
        if not _is_allowed_google_return_origin(origin):
            return _google_oauth_error_page("Google sign-in return origin is not allowed.")
        flow_id = str(state_payload.get("flow_id") or "").strip()

        if error:
            detail = html.unescape(str(error_description or error))
            _store_google_oauth_result(flow_id, {"type": "victory-google-auth", "ok": False, "error": detail or "Google sign-in was cancelled."})
            return _google_oauth_result_redirect(origin, flow_id)
        if not code:
            _store_google_oauth_result(flow_id, {"type": "victory-google-auth", "ok": False, "error": "Google authorization code was missing."})
            return _google_oauth_result_redirect(origin, flow_id)

        token_response = _exchange_google_oauth_code(code, _resolve_google_redirect_uri(request))
        id_token = str(token_response.get("id_token") or "").strip()
        if not id_token:
            _store_google_oauth_result(flow_id, {"type": "victory-google-auth", "ok": False, "error": "Google did not return an ID token."})
            return _google_oauth_result_redirect(origin, flow_id)

        profile = _verify_google_id_token(id_token)
        access_token = str(token_response.get("access_token") or "").strip()
        if access_token:
            try:
                profile = _merge_google_profiles(profile, _fetch_google_userinfo(access_token))
            except HTTPException as exc:
                if exc.status_code >= 500:
                    logger.warning("auth_google_callback_userinfo_merge_failed detail=%s", exc.detail)
                else:
                    raise
        user = await _upsert_google_user(profile)
        user = await _maybe_activate_phase_one_beta_subscription(user)
        redirect = _google_oauth_result_redirect(origin, flow_id)
        auth = await _issue_tokens(user, redirect, issue_cookies=True)
        _store_google_oauth_result(flow_id, {"type": "victory-google-auth", "ok": True, "auth": auth.model_dump(mode="json")})
        return redirect
    except HTTPException as exc:
        if origin != "*":
            _store_google_oauth_result(locals().get("flow_id", ""), {"type": "victory-google-auth", "ok": False, "error": str(exc.detail)})
            return _google_oauth_result_redirect(origin, locals().get("flow_id", ""))
        return _google_oauth_error_page(str(exc.detail), origin=origin)
    except Exception:
        logger.exception("auth_google_callback_failed")
        if origin != "*":
            _store_google_oauth_result(locals().get("flow_id", ""), {"type": "victory-google-auth", "ok": False, "error": "Google sign-in failed. Please try again."})
            return _google_oauth_result_redirect(origin, locals().get("flow_id", ""))
        return _google_oauth_error_page("Google sign-in failed. Please try again.", origin=origin)


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
