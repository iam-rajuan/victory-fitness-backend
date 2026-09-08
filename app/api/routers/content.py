import hashlib
import time
from typing import Any
from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/content/privacy-policy", response_model=PrivacyPolicyResponse)

async def get_privacy_policy() -> PrivacyPolicyResponse:

    record = await _ensure_privacy_policy_record()

    return _serialize_privacy_policy_record(record)

@router.get("/content/about-us", response_model=AboutUsResponse)

async def get_about_us() -> AboutUsResponse:

    record = await _ensure_about_us_record()

    return _serialize_about_us_record(record)

@router.get("/content/onboarding", response_model=OnboardingContentResponse)

async def get_onboarding_content() -> OnboardingContentResponse:

    items = await _get_dashboard_onboarding_items()

    slides = [

        OnboardingSlideResponse(

            id=str(item.get("id") or uuid4().hex),

            badge=str(item.get("badge") or "").strip(),

            title_lines=[

                str(line).strip()

                for line in item.get("title_lines") or []

                if str(line).strip()

            ],

            title_accent_index=item.get("title_accent_index") if isinstance(item.get("title_accent_index"), int) else None,

            description=str(item.get("description") or "").strip(),

            show_skip=bool(item.get("show_skip", False)),

            button_label=str(item.get("button_label") or "").strip(),

            button_arrow=str(item.get("button_arrow") or "").strip(),

            has_secondary=bool(item.get("has_secondary", False)),

            secondary_label=str(item.get("secondary_label") or "").strip(),

            has_footer=bool(item.get("has_footer", False)),

            footer_text=str(item.get("footer_text") or "").strip(),

        )

        for item in items

    ]

    return OnboardingContentResponse(slides=slides)

@router.get("/content/homepage/quote", response_model=HomepageQuote | None)
async def get_homepage_quote(app_version: str | None = None) -> HomepageQuote | None:
    items = await _load_homepage_quotes()
    active_items = [item for item in items if item.get("active", True)]
    if not active_items:
        active_items = DEFAULT_HOMEPAGE_QUOTES
    if not active_items:
        return None

    # 1. Highest priority: Quote explicitly selected by admin in the dashboard
    selected_items = [item for item in active_items if item.get("selected")]
    if selected_items:
        return HomepageQuote(**selected_items[0])

    # 2. Version match if tagged by admin
    if app_version:
        version_matched = [item for item in active_items if str(item.get("version") or "").strip() == app_version.strip()]
        if version_matched:
            return HomepageQuote(**version_matched[0])
        seed = int(hashlib.sha256(app_version.strip().encode("utf-8")).hexdigest()[:8], 16)
        return HomepageQuote(**active_items[seed % len(active_items)])

    return HomepageQuote(**active_items[0])


_network_activity_cache: dict[str, tuple[float, dict]] = {}

def _time_ago_label(moment: datetime | None) -> str:
    if not isinstance(moment, datetime):
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minutes = max(int((datetime.now(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds() // 60), 0)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _avatar_color_for_user(user_id: str) -> str:
    palette = ["#00F0D0", "#A855F7", "#FFD700", "#38BDF8", "#FB7185"]
    digest = hashlib.sha256(str(user_id or "").encode("utf-8")).hexdigest()
    return palette[int(digest[:2], 16) % len(palette)]


def _coerce_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None

async def _get_optional_auth_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    access_token: str | None = Cookie(default=None),
) -> dict | None:
    try:
        if not credentials and not access_token:
            return None
        return await dependency_require_access_user(credentials, access_token)
    except Exception:
        return None

@router.get("/content/network-activity")
async def get_network_activity(user: dict | None = Depends(_get_optional_auth_user)):
    user_id = str(user.get("_id")) if user else "guest"
    now_ts = time.time()
    if user_id in _network_activity_cache:
        cached_time, cached_data = _network_activity_cache[user_id]
        if now_ts - cached_time < 300: # 5-min TTL per user
            return cached_data

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    connected_user_ids: set[str] = set()
    user_trained_today = False
    
    if user:
        uid = str(user["_id"])
        # Check if current user logged a workout today
        try:
            user_log = await workout_logs_collection.find_one({
                "user_id": uid,
                "$or": [
                    {"started_at": {"$gte": today_start}},
                    {"completed_at": {"$gte": today_start}},
                    {"created_at": {"$gte": today_start}}
                ]
            })
            if user_log:
                user_trained_today = True
        except Exception:
            pass

        # 1. Connected via invites
        try:
            invites = await invites_collection.find({
                "accepted": True,
                "$or": [
                    {"user_id": uid},
                    {"inviter_id": uid},
                    {"accepted_by_user_id": uid},
                    {"invited_user_id": uid},
                    {"invitee_id": uid},
                ]
            }).to_list(length=100)
            for inv in invites:
                for key in ["user_id", "inviter_id", "accepted_by_user_id", "invited_user_id", "invitee_id"]:
                    other_id = str(inv.get(key) or "").strip()
                    if other_id and other_id != uid:
                        connected_user_ids.add(other_id)
        except Exception:
            pass

        # 2. Connected via accountability_pairs
        try:
            pairs = await accountability_pairs_collection.find({
                "status": "active",
                "$or": [
                    {"user_ids": uid},
                    {"user_a_id": uid},
                    {"user_b_id": uid},
                    {"user_id": uid},
                    {"partner_id": uid},
                ]
            }).to_list(length=100)
            for p in pairs:
                for other_id in [str(item) for item in (p.get("user_ids") or [])]:
                    if other_id and other_id != uid:
                        connected_user_ids.add(other_id)
                for key in ["user_a_id", "user_b_id", "user_id", "partner_id"]:
                    other_id = str(p.get(key) or "").strip()
                    if other_id and other_id != uid:
                        connected_user_ids.add(other_id)
        except Exception:
            pass

        # 3. Connected via challenge_participants
        try:
            memberships = await challenge_memberships_collection.find({"user_id": uid}).to_list(length=50)
            c_ids = [m.get("challenge_id") for m in memberships if m.get("challenge_id")]
            if c_ids:
                other_memberships = await challenge_memberships_collection.find({
                    "challenge_id": {"$in": c_ids},
                    "user_id": {"$ne": uid}
                }).to_list(length=200)
                for om in other_memberships:
                    other_id = str(om.get("user_id") or "").strip()
                    if other_id and other_id != uid:
                        connected_user_ids.add(other_id)
        except Exception:
            pass

    count = 0
    if connected_user_ids:
        try:
            # Respect privacy toggle: only count users who haven't opted out
            allowed_users = await users_collection.find({
                "_id": {"$in": [ObjectId(cid) for cid in connected_user_ids if ObjectId.is_valid(cid)]},
                "share_activity_with_network": {"$ne": False}
            }, projection={"_id": 1}).to_list(length=len(connected_user_ids))
            allowed_ids = {str(u["_id"]) for u in allowed_users}

            if allowed_ids:
                trained_ids = await workout_logs_collection.distinct(
                    "user_id",
                    {
                        "user_id": {"$in": list(allowed_ids)},
                        "$or": [
                            {"started_at": {"$gte": today_start}},
                            {"completed_at": {"$gte": today_start}},
                            {"created_at": {"$gte": today_start}}
                        ]
                    }
                )
                count = len(trained_ids)
        except Exception:
            pass

    recent_completions = []
    if connected_user_ids:
        try:
            allowed_users = await users_collection.find(
                {
                    "_id": {"$in": [ObjectId(cid) for cid in connected_user_ids if ObjectId.is_valid(cid)]},
                    "share_activity_with_network": {"$ne": False},
                },
                projection={"_id": 1, "name": 1},
            ).to_list(length=len(connected_user_ids))
            allowed_by_id = {str(u["_id"]): u for u in allowed_users}
            if allowed_by_id:
                cursor = (
                    workout_logs_collection.find(
                        {
                            "user_id": {"$in": list(allowed_by_id.keys())},
                            "$or": [
                                {"started_at": {"$gte": today_start}},
                                {"completed_at": {"$gte": today_start}},
                                {"created_at": {"$gte": today_start}},
                            ],
                        }
                    )
                    .sort("completed_at", -1)
                    .limit(5)
                )
                for log in await cursor.to_list(length=5):
                    log_user_id = str(log.get("user_id") or "")
                    connected_user = allowed_by_id.get(log_user_id) or {}
                    completed_at = _coerce_utc_datetime(log.get("completed_at") or log.get("started_at") or log.get("created_at"))
                    title = str(log.get("title") or log.get("workout_id") or "completed a workout").strip()
                    recent_completions.append(
                        {
                            "id": str(log.get("_id") or ""),
                            "name": str(connected_user.get("name") or "Someone"),
                            "action": f"completed {title}",
                            "time_ago": _time_ago_label(completed_at),
                            "avatar_color": _avatar_color_for_user(log_user_id),
                        }
                    )
        except Exception:
            recent_completions = []

    if user_trained_today:
        headline = f"You trained today — {count} other{'s' if count != 1 else ''} did too."
    elif count > 0:
        headline = f"{count} people in your network trained today"
    else:
        headline = "Be the first in your network to train today"

    tier = str(user.get("subscription_tier") or "NONE").upper().replace(" ", "_") if user else "NONE"
    is_silver_or_above = (
        tier in ["SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE", "GOLD_BETA"]
        or bool(user and user.get("gold_trial", {}).get("active"))
        or bool(user and user.get("is_admin"))
    )

    data = {
        "active_today": count,
        "user_trained_today": user_trained_today,
        "headline": headline,
        "is_silver_or_above": is_silver_or_above,
        "recent_completions": recent_completions,
    }
    _network_activity_cache[user_id] = (now_ts, data)
    return data
