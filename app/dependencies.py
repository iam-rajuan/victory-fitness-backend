from bson import ObjectId
from datetime import datetime, timezone
from fastapi import Cookie, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import users_collection
from .security import decode_token

PHASE_ONE_BETA_SUBSCRIPTION_SOURCE = "beta_trial"


bearer_scheme = HTTPBearer(auto_error=False)
SUBSCRIPTION_FEATURE_CATALOG = [
    {
        "key": "home",
        "label": "Home Dashboard",
        "description": "Main home feed, highlights, and entry overview cards.",
        "category": "Core Access",
        "defaultTiers": ["SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/"],
    },
    {
        "key": "workout",
        "label": "Workout Library",
        "description": "Workout browsing, workout detail screens, and published training videos.",
        "category": "Core Access",
        "defaultTiers": ["SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/workout", "/workout-library"],
    },
    {
        "key": "challenge",
        "label": "Challenges",
        "description": "Challenge catalog, joining challenges, progress tracking, and day completion.",
        "category": "Core Access",
        "defaultTiers": ["SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/challenge", "/challenges"],
    },
    {
        "key": "community",
        "label": "Community Feed",
        "description": "Community posts, challenge chat, reactions, comments, and shared accountability feed.",
        "category": "Core Access",
        "defaultTiers": ["SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/community", "/challenges", "/challenge"],
    },
    {
        "key": "mealPlan",
        "label": "Meal Plan",
        "description": "Nutrition plan generation, meal plan dashboard, and guided nutrition onboarding flows.",
        "category": "Nutrition",
        "defaultTiers": ["GOLD", "PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/mealPlan"],
    },
    {
        "key": "nutrition_tracker",
        "label": "Nutrition Tracker",
        "description": "Meal logging, daily nutrition tracking, and tracker-specific insights within meal planning.",
        "category": "Nutrition",
        "defaultTiers": ["PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/mealPlan"],
    },
    {
        "key": "meal_analysis",
        "label": "AI Meal Analysis",
        "description": "AI meal image and document analysis with saved analysis history.",
        "category": "Nutrition",
        "defaultTiers": ["PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/mealPlan"],
    },
    {
        "key": "profile",
        "label": "Profile",
        "description": "Profile screen, rank, settings, and subscription summary access.",
        "category": "Core Access",
        "defaultTiers": ["SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/profile"],
    },
    {
        "key": "workoutplan",
        "label": "Workout Plan AI",
        "description": "Personalized multi-day workout plan generation, saved plans, and adaptive progress reports.",
        "category": "Advanced Coaching",
        "defaultTiers": ["PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/workoutplan"],
    },
    {
        "key": "longevity",
        "label": "Longevity OS",
        "description": "Longevity dashboard, health insights, wearable sync, habits, and recovery views.",
        "category": "Advanced Coaching",
        "defaultTiers": ["PLATINUM", "INNER_CIRCLE"],
        "routeHints": ["/profile/longevity-os"],
    },
    {
        "key": "application",
        "label": "Coaching Application",
        "description": "Application form access for premium/direct coaching programmes.",
        "category": "Premium Coaching",
        "defaultTiers": ["INNER_CIRCLE"],
        "routeHints": ["/profile/application"],
    },
    {
        "key": "coach_victor",
        "label": "Coach Victor",
        "description": "AI Coach Victor chat, conversation history, and direct coaching entry points.",
        "category": "Premium Coaching",
        "defaultTiers": ["INNER_CIRCLE"],
        "routeHints": ["/chat"],
    },
    {
        "key": "longevity_plan",
        "label": "Longevity Plan AI",
        "description": "AI-generated weekly longevity plans and health-profile-based recommendation plans.",
        "category": "Premium Coaching",
        "defaultTiers": ["INNER_CIRCLE"],
        "routeHints": ["/profile/longevity-os", "/profile/heal/[id]"],
    },
]
SUBSCRIPTION_FEATURE_KEYS = {item["key"] for item in SUBSCRIPTION_FEATURE_CATALOG}
SUBSCRIPTION_ACCESS = {
    "NONE": [],
    "SILVER": ["home", "workout", "challenge", "community", "profile"],
    "GOLD": ["home", "workout", "challenge", "community", "mealPlan", "profile"],
    "GOLD_BETA": ["home", "workout", "challenge", "community", "mealPlan", "profile"],
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


def list_subscription_feature_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": item["key"],
            "label": item["label"],
            "description": item["description"],
            "category": item["category"],
            "defaultTiers": list(item["defaultTiers"]),
            "routeHints": list(item["routeHints"]),
        }
        for item in SUBSCRIPTION_FEATURE_CATALOG
    ]


def find_invalid_subscription_features(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    invalid: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        if value not in SUBSCRIPTION_FEATURE_KEYS:
            invalid.append(value)
    return invalid


def normalize_subscription_feature_access(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        if not value or value in seen or value not in SUBSCRIPTION_FEATURE_KEYS:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized

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
    access_token: str | None = Cookie(default=None),
) -> dict:
    token = credentials.credentials if credentials else access_token
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await get_verified_user(f"Bearer {token}")


async def require_admin_user(user: dict = Security(require_access_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def normalize_subscription_tier(value: object) -> str:
    tier = str(value or "").strip().upper().replace(" ", "_")
    if tier == "GOLD_BETA":
        return "GOLD_BETA"
    return tier if tier in SUBSCRIPTION_ACCESS else "NONE"


def resolve_subscription_access(tier: object) -> list[str]:
    return list(SUBSCRIPTION_ACCESS.get(normalize_subscription_tier(tier), []))


def _as_utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def user_has_active_gold_trial(user: dict, now: datetime | None = None) -> bool:
    if str(user.get("subscription_purchase_source") or "").strip() == PHASE_ONE_BETA_SUBSCRIPTION_SOURCE:
        start_at = _as_utc_datetime(user.get("trial_start_at"))
        end_at = _as_utc_datetime(user.get("trial_end_at"))
        if not start_at or not end_at:
            return False
        current = now or datetime.now(timezone.utc)
        current = current if current.tzinfo else current.replace(tzinfo=timezone.utc)
        return start_at <= current < end_at
    if normalize_subscription_tier(user.get("trial_tier_granted")) != "GOLD":
        return False
    if str(user.get("trial_outcome") or "").strip():
        return False
    start_at = _as_utc_datetime(user.get("trial_start_at"))
    end_at = _as_utc_datetime(user.get("trial_end_at"))
    if not start_at or not end_at:
        return False
    current = now or datetime.now(timezone.utc)
    current = current if current.tzinfo else current.replace(tzinfo=timezone.utc)
    return start_at <= current < end_at


def user_has_subscription_access(user: dict, feature: str) -> bool:
    if bool(user.get("is_admin")):
        return True
    configured_access = user.get("subscription_access")
    subscription = user.get("subscription") if isinstance(user.get("subscription"), dict) else {}
    if not configured_access and isinstance(subscription.get("access"), list):
        configured_access = subscription.get("access")
    if isinstance(configured_access, list) and configured_access:
        return feature in {str(item).strip() for item in configured_access if str(item).strip()}
    if user_has_active_gold_trial(user) and feature in resolve_subscription_access("GOLD"):
        return True
    tier = user.get("subscription_tier") or user.get("subscription_role") or user.get("tier")
    return feature in resolve_subscription_access(tier)


def ensure_subscription_feature_access(user: dict, feature: str, detail: str) -> None:
    if not user_has_subscription_access(user, feature):
        raise HTTPException(status_code=403, detail=detail)
