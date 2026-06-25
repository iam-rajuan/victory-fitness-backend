from bson import ObjectId
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import users_collection
from .security import decode_token


bearer_scheme = HTTPBearer(auto_error=False)
SUBSCRIPTION_ACCESS = {
    "NONE": [],
    "SILVER": ["home", "workout", "challenge", "community", "profile"],
    "GOLD": ["home", "workout", "challenge", "community", "mealPlan", "profile"],
    "PLATINUM": [
        "home",
        "workout",
        "challenge",
        "community",
        "mealPlan",
        "nutrition_tracker",
        "meal_analysis",
        "profile",
        "workoutplan",
        "longevity",
    ],
    "INNER_CIRCLE": [
        "home",
        "workout",
        "challenge",
        "mealPlan",
        "nutrition_tracker",
        "meal_analysis",
        "profile",
        "workoutplan",
        "longevity",
        "application",
        "community",
        "coach_victor",
        "longevity_plan",
    ],
}

def _get_auth_session_version(user: dict) -> int:
    try:
        return max(int(user.get("auth_session_version") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _token_matches_auth_session(payload: dict, user: dict) -> bool:
    try:
        token_version = max(int(payload.get("ver") or 0), 0)
    except (TypeError, ValueError):
        token_version = 0
    return token_version == _get_auth_session_version(user)


async def get_verified_user(authorization: str | None) -> dict:
    token = (authorization or "").replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await get_verified_user_from_access_token(token)


async def get_verified_user_from_access_token(token: str) -> dict:
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
    if not _token_matches_auth_session(data, user):
        raise HTTPException(status_code=401, detail="Session expired")

    return user


async def require_access_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await get_verified_user(f"Bearer {token}")


async def require_admin_user(user: dict = Security(require_access_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def normalize_subscription_tier(value: object) -> str:
    tier = str(value or "").strip().upper().replace(" ", "_")
    return tier if tier in SUBSCRIPTION_ACCESS else "NONE"


def resolve_subscription_access(tier: object) -> list[str]:
    return list(SUBSCRIPTION_ACCESS.get(normalize_subscription_tier(tier), []))


def user_has_subscription_access(user: dict, feature: str) -> bool:
    if bool(user.get("is_admin")):
        return True
    tier = user.get("subscription_tier") or user.get("subscription_role") or user.get("tier")
    return feature in resolve_subscription_access(tier)


def ensure_subscription_feature_access(user: dict, feature: str, detail: str) -> None:
    if not user_has_subscription_access(user, feature):
        raise HTTPException(status_code=403, detail=detail)
