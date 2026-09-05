import asyncio

import base64

import inspect

import json

from io import BytesIO

import logging

from mimetypes import guess_type

import re

from functools import lru_cache

from typing import Any

from uuid import uuid4

from calendar import month_abbr

from datetime import datetime, timedelta, timezone

from pathlib import Path

from time import perf_counter

from urllib.parse import parse_qs, unquote, urlencode, urlparse

from urllib.request import Request as UrlRequest, urlopen

from docx import Document as DocxDocument
from pypdf import PdfReader
from bson import ObjectId
from pymongo import ReturnDocument

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, Security, UploadFile, WebSocket, WebSocketDisconnect, status

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse

from fastapi.security import HTTPAuthorizationCredentials

from fastapi.staticfiles import StaticFiles

from starlette.exceptions import HTTPException as StarletteHTTPException

from pydantic import BaseModel, EmailStr, Field

from jose import jwt

try:

    from PIL import Image, ImageDraw, ImageFont

except ModuleNotFoundError:

    Image = None

    ImageDraw = None

    ImageFont = None

from ..coach_archive import (

    build_archive_record,

    hydrate_archive_messages,

    load_thread_snapshot,

    s3_archive_enabled,

    store_thread_snapshot,

)

from ..challenge_plan_ai import ChallengePlanGenerationInput, generate_challenge_plan

from ..coach_victor import generate_coach_victor_reply

from ..config import settings

from ..database import DatabaseNotConfiguredError, close_database_connection, ensure_indexes, users_collection

from ..dependencies import (

    bearer_scheme,
    find_invalid_subscription_features as dependency_find_invalid_subscription_features,

    get_verified_user as dependency_get_verified_user,

    get_verified_user_from_access_token as dependency_get_verified_user_from_access_token,
    list_subscription_feature_catalog as dependency_list_subscription_feature_catalog,
    normalize_subscription_feature_access as dependency_normalize_subscription_feature_access,

    require_access_user as dependency_require_access_user,

    require_admin_user as dependency_require_admin_user,

)

from ..email_service import send_password_reset_email, send_verification_email

from ..journal_ai import generate_journal_analysis

from ..longevity_ai import generate_longevity_weekly_plan

from ..models import AppNotificationItem, AppNotificationListResponse, PushTokenRequest

from ..push_service import notify_user, notify_users_of_published_workout, subscribe_notification_events
from ..challenge_milestone import generate_challenge_milestone_message
from ..trial_campaign import process_trial_campaign

from ..models import (

    AdminCoachingApplicationUpdateRequest,

    AdminChangePasswordRequest,

    AdminChallengeItem,

    AdminChallengeListResponse,

    AdminChallengePlanGenerateRequest,

    AdminChallengePlanGenerateResponse,

    AdminDirectUploadRequest,

    AdminDirectUploadResponse,

    AdminSupportMessageUpdateRequest,

    AdminChallengeRequest,

    AdminProfileResponse,

    AboutUsResponse,

    AdminCommunityPostCreateRequest,

    AdminCommunityPostUpdateRequest,

    BodyMetricsResponse,

    ChallengeChatMessageCreateRequest,

    ChallengeChatMessageUpdateRequest,

    ChallengeChatMessageResponse,

    ChallengeDetailResponse,

    ChallengeParticipantResponse,

    ChallengeChatEventResponse,

    ChallengePlanCompletionRequest,

    ChallengePlanDay,

    ChallengePlanExercise,

    ChallengePlanSection,

    ChallengePlanDayProgressResponse,

    ChallengePlanProgressResponse,

    ChallengeProgressReportResponse,

    ChallengeChatReactionToggleRequest,

    ChallengeChatThreadResponse,

    CoachVictorChatRequest,

    CoachVictorChatResponse,

    CoachVictorHistoryResponse,

    CoachingApplicationCreateRequest,

    CoachingApplicationListResponse,

    CoachingApplicationResponse,

    CommunityCommentCreateRequest,

    CommunityCommentResponse,

    CommunityPostCreateRequest,

    CommunityPostListResponse,

    CommunityPostResponse,

    CommunityReactionUserResponse,

    CommunityReactionToggleResponse,

    ChallengeOverviewResponse,

    ChallengeChatSummaryResponse,

    FAQItemResponse,

    FAQListResponse,

    FAQRequest,

    HomepageQuote,

    HomepageQuoteListResponse,

    HomepageQuoteRequest,

    AdminMasterclassItem,

    AdminMasterclassListResponse,

    AdminMasterclassRequest,

    AdminNotificationItem,

    AdminNotificationListResponse,

    AdminNotificationUpdateRequest,
    AdminTestNotificationRequest,

    AdminSubscriberItem,

    AdminSubscriberListResponse,

    AdminSubscriptionFeatureItem,

    AdminSubscriptionFeatureListResponse,

    AdminSubscriptionPlanItem,

    AdminSubscriptionPlanListResponse,

    AdminSubscriptionPlanRequest,

    AppSubscriptionPlanItem,

    AppSubscriptionPlanListResponse,

    DashboardOverviewChartPoint,

    AdminUserChartPoint,

    AdminUserDetailResponse,

    AdminUserListItem,

    AdminUserListResponse,

    AdminTrialCohortItem,

    AdminTrialCohortResponse,

    AdminTrialDropoutItem,

    AdminTrialDropoutResponse,

    PhaseOneBetaCountryItem,

    PhaseOneBetaSummaryResponse,

    PhaseOneBetaUserItem,

    GoldTrialConfigResponse,

    GoldTrialConfigUpdateRequest,

    GoldTrialDecisionOption,

    GoldTrialDecisionResponse,

    GoldTrialMessageConfig,

    GoldTrialOutcomeBreakdownResponse,

    GoldTrialStartResponse,

    GoldTrialSummaryResponse,

    AdminUserManagementOverviewResponse,

    AdminUserSummaryResponse,

    AdminUserUpdateRequest,

    AdminWorkoutItem,

    AdminWorkoutListResponse,

    AdminWorkoutRequest,

    AdminWorkoutSyncDebugResponse,

    AdminWorkoutSyncResponse,

    DashboardOverviewRecentUser,

    DashboardOverviewResponse,

    ForgotPasswordRequest,

    JournalAnalysisRequest,

    JournalLatestAnalysisResponse,

    JournalAnalysisResponse,

    JournalEntryCreateRequest,

    JournalEntryListResponse,

    JournalEntryResponse,

    JournalEntryUpdateRequest,

    LongevityCircleListResponse,

    LongevityCircleResponse,

    LongevityDashboardResponse,

    LongevityHabitResponse,

    LongevityHabitUpdateRequest,

    LongevityHabitsResponse,

    LongevityHealCategoriesResponse,

    LongevityHealCategoryResponse,

    LongevityMasterclassListResponse,

    LongevityMasterclassResponse,

    LongevityOverviewResponse,

    LongevityQuickActionResponse,

    LongevityWearableDeviceResponse,

    LongevityWearablesResponse,

    LongevityWeeklyPlanSectionResponse,

    LongevityWeeklyPlanResponse,

    MealImageAnalysisListResponse,

    MealImageAnalysisRequest,

    MealImageAnalysisResponse,

    LoginRequest,

    MeResponse,

    NutritionAdviceRequest,

    NutritionAdviceResponse,

    ProfileImageUploadRequest,

    ProfileImageUploadResponse,

    PrivacyPolicyResponse,

    NutritionMealCompletionUpdateRequest,

    NutritionPlanJobResponse,

    NutritionPlanRequest,

    NutritionPlanResponse,

    NutritionPlanSaveResponse,

    OnboardingContentResponse,
    OnboardingStateResponse,

    OnboardingSlideResponse,

    LogoutRequest,

    RefreshRequest,

    RegisterRequest,

    ResendVerificationRequest,

    ResetPasswordRequest,

    ChallengeProgressUpdateRequest,

    GoogleAuthRequest,

    UpdateAboutUsRequest,

    UpdateBodyMetricsRequest,

    UpdateMeRequest,
    UpdateOnboardingStateRequest,

    UpdatePrivacyPolicyRequest,

    UpdateTermsConditionRequest,

    TermsConditionResponse,

    TokenResponse,

    StartChallengeResponse,

    StrengthWorkoutPlanRequest,

    StrengthWorkoutPlanProgressUpdateRequest,

    StrengthWorkoutPlanListResponse,

    StrengthWorkoutPlanCompletionReportResponse,

    StrengthWorkoutPlanResponse,

    SupportMessageCreateRequest,

    SupportMessageListResponse,

    SupportMessageResponse,

    UpdateAdminProfileRequest,

    VerifyEmailRequest,

    VerifyResetCodeRequest,

    UserActiveChallengeResponse,

    UserCompletedChallengeResponse,

    UserReadyChallengeResponse,

    VideoWorkoutPlanRequest,

    VideoWorkoutPlanResponse,

    WorkoutLibraryCategory,

    WorkoutLibraryItem,

    WorkoutLibraryResponse,

    UpdateSubscriptionRequest,

)

from ..database import (

    app_content_collection,
    phase_one_beta_slots_collection,

    challenge_chat_messages_collection,

    challenge_message_reactions_collection,

    challenge_memberships_collection,

    challenges_collection,

    coaching_applications_collection,

    coach_victor_archives_collection,

    coach_victor_threads_collection,

    community_comments_collection,

    community_posts_collection,

    community_reactions_collection,

    admin_audit_logs_collection,

    longevity_os_profiles_collection,

    nutrition_progressive_plan_jobs_collection,

    nutrition_progressive_plans_collection,

    journal_entries_collection,

    meal_analysis_entries_collection,

    nutrition_plans_collection,

    nutrition_plan_jobs_collection,

    strength_workout_plans_collection,

    support_messages_collection,

    workouts_collection,

    # Section 18 analytics collections
    analytics_events_collection,
    workout_logs_collection,
    completion_cards_collection,
    invites_collection,
    payment_events_collection,
    points_log_collection,
    accountability_pairs_collection,

)

from ..nutrition_ai import (

    NutritionPlanRefusalError,

    build_nutrition_plan_signature,

    generate_meal_document_analysis,

    generate_meal_image_analysis,

    generate_nutrition_advice,

    generate_nutrition_plan,

    generate_progressive_nutrition_plan_day,

)

from ..repositories.content import ensure_content_record, upsert_content_record

from ..repositories.workouts import list_public_workout_records

from ..serializers.content import (

    serialize_about_us_record as shared_serialize_about_us_record,

    serialize_privacy_policy_record as shared_serialize_privacy_policy_record,

    serialize_terms_condition_record as shared_serialize_terms_condition_record,

)

from ..serializers.workouts import serialize_public_workout_record as shared_serialize_public_workout_record

from ..utils.datetime import as_utc as shared_as_utc

from ..utils.html import html_to_plain_text as shared_html_to_plain_text

from ..workout_plan_ai import (

    StrengthWorkoutPlanInput,

    VideoWorkoutPlanInput,

    generate_strength_workout_plan,

    generate_video_workout_plan,

)
from ..vimeo_sync import VimeoSyncError, get_vimeo_status, sync_vimeo_workouts

from ..security import (

    create_token,

    create_verification_code,

    decode_token,

    hash_password,

    verify_password,

)

from ..wearables import (

    backfill_current_health_metrics_from_history,

    build_longevity_metric_insights,

    build_longevity_wearables_response,

    router as wearables_router,

    start_integration_queue,

    start_wearables_scheduler,

    stop_integration_queue,

    stop_wearables_scheduler,

)

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

logger = logging.getLogger("victory_fitness.api")

async def _run_analytics_migrations() -> None:
    """One-shot back-fills for the Section 18 analytics layer.

    Safe to call on every startup — every step is idempotent (skip rows where
    the new field is already populated).
    """
    try:
        from ..utils.country import backfill_country_codes
        updated = await backfill_country_codes(users_collection, logger=logger)
        if updated:
            logger.info("analytics_migration country_code back-filled for %s users", updated)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("analytics_migration_failed: %s", exc)

async def _record_admin_audit(admin_user: dict, action: str, resource: str, resource_id: str = "", details: dict | None = None) -> None:
    await admin_audit_logs_collection.insert_one({
        "admin_id": str(admin_user.get("_id") or ""),
        "admin_email": str(admin_user.get("email") or ""),
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "details": details or {},
        "created_at": datetime.now(timezone.utc),
    })

async def _record_analytics_event(event_type: str, user_id: str | None = None, market: str | None = None, details: dict | None = None) -> None:
    """Fire-and-forget analytics event writer. Never raises."""
    if analytics_events_collection is None:
        return
    try:
        await analytics_events_collection.insert_one({
            "event_type": event_type,
            "user_id": str(user_id) if user_id else None,
            "market": (market or "").upper() or None,
            "details": details or {},
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("record_analytics_event failed: %s", exc)

_CLIENT_ANALYTICS_EVENTS = {
    "workout_library_visited",
    "workout_library_item_viewed",
}

class _AnalyticsEventRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    details: dict[str, Any] = Field(default_factory=dict)

# ---------------------------------------------------------------------------
# Section 18 — emit hooks for analytics tables.
# These minimal POST endpoints let the mobile app push events into the
# collections that the analytics endpoints read from.
# ---------------------------------------------------------------------------

class _WorkoutLogRequest(BaseModel):
    workout_id: str = Field(min_length=1, max_length=120)
    duration_seconds: int = 0
    status: str = Field(default="started", pattern=r"^(started|completed|abandoned)$")
    market: str | None = Field(default=None, min_length=2, max_length=2)

class _CompletionCardRequest(BaseModel):
    workout_id: str = Field(min_length=1, max_length=120)
    shared_to_whatsapp: bool = False
    image_url: str | None = Field(default=None, max_length=500)
    upsell_shown: bool = False
    upsell_clicked: bool = False

class _InviteRequest(BaseModel):
    recipient_email: EmailStr | None = None
    recipient_phone: str | None = Field(default=None, max_length=40)
    copy_variant: str | None = Field(default=None, pattern=r"^[a-z]$")

class _PaymentEventRequest(BaseModel):
    amount: str | float = Field(...)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    type: str = Field(default="subscription_renewed", max_length=60)
    tier: str = Field(default="GOLD", max_length=40)
    market: str | None = Field(default=None, min_length=2, max_length=2)

class _PointsLogRequest(BaseModel):
    points: int = Field(ge=0, le=10000)
    reason: str = Field(default="workout_completed", max_length=60)

class _AccountabilityPairRequest(BaseModel):
    partner_user_id: str = Field(min_length=1, max_length=120)

MEDIA_ROOT = Path("/tmp/victory-fitness-media") if settings.is_vercel else Path(__file__).resolve().parents[1] / "media"

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

COMMUNITY_IMAGE_MAX_SIZE_BYTES = 1 * 1024 * 1024

COMMUNITY_VIDEO_MAX_SIZE_BYTES = 20 * 1024 * 1024

@lru_cache(maxsize=1)

def _build_favicon_png_bytes() -> bytes:

    if Image is None:

        return b""

    canvas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

    draw = ImageDraw.Draw(canvas)

    draw.ellipse((2, 2, 13, 13), fill=(16, 185, 129, 255))

    draw.ellipse((5, 5, 10, 10), fill=(255, 255, 255, 255))

    buffer = BytesIO()

    canvas.save(buffer, format="PNG")

    return buffer.getvalue()

@lru_cache(maxsize=1)

def _build_favicon_ico_bytes() -> bytes:

    if Image is None:

        return b""

    canvas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

    draw = ImageDraw.Draw(canvas)

    draw.ellipse((2, 2, 13, 13), fill=(16, 185, 129, 255))

    draw.ellipse((5, 5, 10, 10), fill=(255, 255, 255, 255))

    buffer = BytesIO()

    canvas.save(buffer, format="ICO", sizes=[(16, 16)])

    return buffer.getvalue()

REMOTE_MEDIA_MIME_TO_EXTENSION = {

    "video/mp4": ".mp4",

    "video/quicktime": ".mov",

    "video/webm": ".webm",

    "video/x-m4v": ".m4v",

    "audio/mpeg": ".mp3",

    "audio/mp4": ".m4a",

    "audio/wav": ".wav",

    "audio/x-wav": ".wav",

    "audio/ogg": ".ogg",

    "application/ogg": ".ogg",

    "audio/webm": ".webm",

}

REMOTE_MEDIA_BLOCKED_HOSTS = {

    "youtube.com",

    "www.youtube.com",

    "m.youtube.com",

    "youtu.be",

    "player.vimeo.com",

    "vimeo.com",

    "www.vimeo.com",

}

STANDARD_NUTRITION_PLAN_MODE = "standard_v1"

PROGRESSIVE_NUTRITION_PLAN_MODE = "progressive_v2"

SUBSCRIPTION_TIERS = ("NONE", "SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE")

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

PRIVACY_POLICY_KEY = "privacy_policy"

TERMS_CONDITION_KEY = "terms_condition"

ABOUT_US_KEY = "about_us"

DEFAULT_PRIVACY_POLICY_TITLE = "Privacy Policy"

DEFAULT_PRIVACY_POLICY_HTML = """

<p>Last Updated: May 13, 2026</p>

<h2>1. Introduction</h2>

<p>Welcome to Victory Fitness. We are committed to protecting your personal information and your right to privacy.</p>

<h2>2. Information We Collect</h2>

<p>We collect information you provide directly to us, including account details and fitness-related profile information.</p>

<h2>3. How We Use Your Information</h2>

<p>We use your information to operate the app, personalize coaching, improve recommendations, and support your account.</p>

<h2>4. Data Security</h2>

<p>We use reasonable technical and organizational measures to protect your information, but no system can be guaranteed fully secure.</p>

<h2>5. Your Rights</h2>

<p>Depending on your location, you may have rights to access, correct, delete, or restrict the use of your personal information.</p>

<h2>6. Contact</h2>

<p>If you have questions about this policy, contact Victory Fitness support.</p>

""".strip()

DEFAULT_TERMS_CONDITION_TITLE = "Terms & Conditions"

DEFAULT_TERMS_CONDITION_HTML = """

<p>Last Updated: May 13, 2026</p>

<h2>1. Agreement</h2>

<p>By using Victory Fitness, you agree to these Terms & Conditions and our related policies.</p>

<h2>2. Use of the Service</h2>

<p>You agree to use the app lawfully and only for its intended fitness, wellness, and account-management purposes.</p>

<h2>3. Accounts</h2>

<p>You are responsible for maintaining the confidentiality of your account credentials and for activities under your account.</p>

<h2>4. Health Disclaimer</h2>

<p>Victory Fitness provides educational and informational content only and does not replace professional medical advice.</p>

<h2>5. Termination</h2>

<p>We may suspend or terminate access if these terms are violated or if the service is misused.</p>

<h2>6. Contact</h2>

<p>If you have questions about these terms, contact Victory Fitness support.</p>

""".strip()

DEFAULT_ABOUT_US_TITLE = "About Us"

DEFAULT_ABOUT_US_HTML = """

<h2>About Victory Fitness</h2>

<p>Victory Fitness is built to help people train with more structure, eat with more clarity, and stay consistent for the long term.</p>

<h2>Our Mission</h2>

<p>We combine coaching, personalized planning, and practical fitness tools so users can build healthier routines that fit real life.</p>

<h2>What We Offer</h2>

<p>Victory Fitness brings together workout support, nutrition guidance, journaling, accountability, and progress tracking in one place.</p>

<h2>Our Focus</h2>

<p>We focus on practical, sustainable progress instead of extreme plans, helping users improve strength, energy, recovery, and confidence.</p>

""".strip()

DEFAULT_LONGEVITY_QUICK_ACTIONS = [

    {"id": "log-bio", "label": "Log Bio", "image": "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=600&q=80", "color": "#4F8EF7"},

    {"id": "fasting", "label": "Fasting", "image": "https://images.unsplash.com/photo-1495555961410-b96095ce83be?w=600&q=80", "color": "#F59E0B"},

    {"id": "heal-food", "label": "Heal with Food", "image": "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=600&q=80", "color": "#10B981"},

    {"id": "masterclass", "label": "Masterclass", "image": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=600&q=80", "color": "#4F8EF7"},

    {"id": "circles", "label": "Circles", "image": "https://images.unsplash.com/photo-1526506118085-60ce8714f8c5?w=600&q=80", "color": "#F472B6"},

]

DEFAULT_LONGEVITY_HEAL_CATEGORIES = [

    {"id": "hbp", "label": "HIGH BLOOD PRESSURE", "image": "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=600&q=80", "color": "#F59E0B"},

    {"id": "diabetes", "label": "DIABETES", "image": "https://images.unsplash.com/photo-1505253758473-96b7015fcd40?w=600&q=80", "color": "#4F8EF7"},

    {"id": "bodyfat", "label": "BODY FAT", "image": "https://images.unsplash.com/photo-1605296867304-46d5465a13f1?w=600&q=80", "color": "#6366F1"},

    {"id": "liver", "label": "HEALTHY LIVER", "image": "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=600&q=80", "color": "#EF4444"},

    {"id": "immunity", "label": "IMMUNITY AND INFECTION", "image": "https://images.unsplash.com/photo-1584362917165-526a968579e8?w=600&q=80", "color": "#FF6B6B"},

    {"id": "mental", "label": "MENTAL HEALTH AND ANXIETY", "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600&q=80", "color": "#F97316"},

    {"id": "heart", "label": "HEART HEALTH", "image": "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=600&q=80", "color": "#00C9A7"},

    {"id": "respiratory", "label": "RESPIRATORY HEALTH", "image": "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=600&q=80", "color": "#10B981"},

    {"id": "skin", "label": "SKIN CONDITIONS", "image": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?w=600&q=80", "color": "#A855F7"},

    {"id": "recovery", "label": "POST WORKOUT RECOVERY", "image": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80", "color": "#EC4899"},

]

FITNESS_STATS_MEMBERSHIP_PROJECTION = {

    "_id": 0,

    "status": 1,

    "challenge_id": 1,

    "plan_progress": 1,

}

FITNESS_STATS_CHALLENGE_PROJECTION = {

    "_id": 1,

    "points": 1,

    "plan_days": 1,

}

CHALLENGE_OVERVIEW_MEMBERSHIP_PROJECTION = {

    "_id": 1,

    "challenge_id": 1,

    "status": 1,

    "progress_days_completed": 1,

    "plan_progress": 1,

    "completed_at": 1,

    "last_read_message_at": 1,

    "joined_at": 1,

    "started_at": 1,

}

CHALLENGE_OVERVIEW_CHALLENGE_PROJECTION = {

    "_id": 1,

    "title": 1,

    "description": 1,

    "why_it_matters": 1,

    "plan_text": 1,

    "category": 1,

    "duration_days": 1,

    "points": 1,

    "difficulty": 1,

    "status": 1,

    "thumbnail": 1,

    "plan_days": 1,

    "created_at": 1,

}

DEFAULT_LONGEVITY_WEARABLES = [

    {"id": "fitbit", "name": "Fitbit", "status": "CONNECT", "active": False, "image": "https://images.unsplash.com/photo-1575311373937-040b8e1fd5b2?w=600&q=80"},

    {"id": "apple-health", "name": "Apple Health", "status": "CONNECTED", "active": True, "image": "https://images.unsplash.com/photo-1434493789847-2f02dc6ca35d?w=600&q=80"},

    {"id": "google-fit", "name": "Google Fit", "status": "CONNECT", "active": False, "image": "https://images.unsplash.com/photo-1510017803434-a899398421b3?w=600&q=80"},

    {"id": "garmin", "name": "Garmin", "status": "CONNECT", "active": False, "image": "https://images.unsplash.com/photo-1557438159-8664b4c7301c?w=600&q=80"},

]

DEFAULT_LONGEVITY_HABITS = [

    {"id": "hydration", "title": "Hydration", "subtitle": "Support energy and recovery", "icon": "water-outline", "done": True},

    {"id": "sleep-7h", "title": "7h+ Sleep", "subtitle": "Protect repair and recovery", "icon": "moon-outline", "done": True},

    {"id": "zone-2", "title": "Zone 2 Cardio", "subtitle": "Aerobic base for heart health", "icon": "heart-outline", "done": False},

    {"id": "breathwork", "title": "Breathwork", "subtitle": "Downshift stress response", "icon": "reorder-two-outline", "done": False},

    {"id": "steps-8k", "title": "8k Steps", "subtitle": "Maintain a steady movement baseline", "icon": "walk-outline", "done": False},

]

DEFAULT_LONGEVITY_MASTERCLASSES = [

    {

        "id": "mc-heart-zone2",

        "title": "Zone 2 For Heart Health",

        "description": "Build aerobic capacity, improve recovery, and support long-term cardiovascular resilience.",

        "thumbnail": "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=600&q=80",

    },

    {

        "id": "mc-recovery-blueprint",

        "title": "Post Workout Recovery Blueprint",

        "description": "Use sleep, hydration, and recovery windows to turn training stress into adaptation.",

        "thumbnail": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80",

    },

    {

        "id": "mc-mental-reset",

        "title": "Mental Reset Protocol",

        "description": "Calm stress, sharpen focus, and create a repeatable reset routine for anxious days.",

        "thumbnail": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600&q=80",

    },

    {

        "id": "mc-immunity-stack",

        "title": "Immunity Support Stack",

        "description": "Layer sleep, movement, nutrition, and recovery into a sustainable immune-support routine.",

        "thumbnail": "https://images.unsplash.com/photo-1584362917165-526a968579e8?w=600&q=80",

    },

]

DASHBOARD_FAQS_KEY = "dashboard_faqs"

DASHBOARD_NOTIFICATIONS_KEY = "dashboard_notifications"

DASHBOARD_SUBSCRIPTION_PLANS_KEY = "dashboard_subscription_plans"

DASHBOARD_MASTERCLASSES_KEY = "dashboard_masterclasses"

DASHBOARD_ONBOARDING_KEY = "dashboard_onboarding"

DEFAULT_DASHBOARD_FAQS = [

    {

        "id": "faq-reset-password",

        "question": "How do I reset my password?",

        "answer": "Use the forgot password flow on the sign-in page and enter the verification code sent to your email.",

    },

    {

        "id": "faq-update-billing",

        "question": "How can I update my billing information?",

        "answer": "Open the billing or subscription area in your account and follow the update prompts provided there.",

    },

    {

        "id": "faq-refund-policy",

        "question": "What is the refund policy?",

        "answer": "Contact support with your order details and the team will review the request based on your plan and billing status.",

    },

]

DEFAULT_DASHBOARD_NOTIFICATIONS = [

    {

        "id": "notification-dashboard-online",

        "title": "Dashboard Online",

        "message": "The admin dashboard is connected and ready to manage users, content, and challenges.",

        "read": False,

        "createdAt": "2026-06-19T00:00:00Z",

    }

]

DEFAULT_DASHBOARD_SUBSCRIPTION_PLANS = [

    {

        "id": "plan-silver",

        "tier": "VICTORY SILVER",

        "description": "Good start, but not enough for full transformation.",

        "priceMonthly": 19,

        "priceYearly": 199,

        "discountPercentage": None,

        "discountStartDate": None,

        "discountEndDate": None,

        "isApplicationOnly": False,

        "isMostPopular": False,

        "iconType": "silver_medal",

        "features": [

            "Full Workout Library (120+)",

            "Basic Programs",

            "Limited Challenges",

        ],

    },

    {

        "id": "plan-gold",

        "tier": "VICTORY GOLD",

        "description": "This is where real consistency starts. Structure and accountability.",

        "priceMonthly": 29,

        "priceYearly": 299,

        "discountPercentage": None,

        "discountStartDate": None,

        "discountEndDate": None,

        "isApplicationOnly": False,

        "isMostPopular": True,

        "iconType": "gold_medal",

        "features": [

            "All Silver features",

            "Accountability System (Tracking, Reminders)",

            "Community Challenges and Nutrition",

            "Basic wearable data (sleep and activity)",

        ],

    },

    {

        "id": "plan-gold-beta-21-day",

        "tier": "21-DAY GOLD BETA",

        "description": "Free 21-day Gold beta access for approved testers during Phase 1.",

        "priceMonthly": 0,

        "priceYearly": 0,

        "discountPercentage": None,

        "discountStartDate": None,

        "discountEndDate": None,

        "isApplicationOnly": False,

        "isMostPopular": False,

        "iconType": "gold_medal",

        "features": [

            "All Silver features",

            "Accountability System (Tracking, Reminders)",

            "Community Challenges and Nutrition",

            "Basic wearable data (sleep and activity)",

        ],

        "featureAccess": [

            "home",

            "workout",

            "challenge",

            "community",

            "mealPlan",

            "profile",

        ],

    },

    {

        "id": "plan-platinum",

        "tier": "VICTORY PLATINUM",

        "description": "For those who want more precision and faster results.",

        "priceMonthly": 39,

        "priceYearly": 399,

        "discountPercentage": None,

        "discountStartDate": None,

        "discountEndDate": None,

        "isApplicationOnly": False,

        "isMostPopular": False,

        "iconType": "diamond",

        "features": [

            "All Gold features",

            "Personalized Plans",

            "Feedback System and Priority Support",

            "Full wearable syncing and AI adjustments",

        ],

    },

    {

        "id": "plan-inner-circle",

        "tier": "VICTORY INNER CIRCLE",

        "description": "For those who are ready to commit. Direct coaching with Victor.",

        "priceMonthly": None,

        "priceYearly": None,

        "discountPercentage": None,

        "discountStartDate": None,

        "discountEndDate": None,

        "isApplicationOnly": True,

        "isMostPopular": False,

        "iconType": "circle",

        "features": [

            "Direct Coaching with Victor",

            "Personal Structure and Plan",

            "Accountability Check-Ins and Adjustments",

            "Advanced AI health insights and trends",

        ],

    },

]

DEFAULT_DASHBOARD_MASTERCLASSES = [

    {

        "id": "masterclass-heart-zone2",

        "title": "Zone 2 For Heart Health",

        "category": "Science",

        "duration": "15:00",

        "description": "Build aerobic capacity, improve recovery, and support long-term cardiovascular resilience.",

        "videoUrl": "https://vimeo.com/740239410",

        "audioUrl": "",

        "educationalContent": "",

        "thumbnailUrl": "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=600&q=80",

    },

    {

        "id": "masterclass-recovery-blueprint",

        "title": "Post Workout Recovery Blueprint",

        "category": "Nutrition",

        "duration": "18:00",

        "description": "Use sleep, hydration, and recovery windows to turn training stress into adaptation.",

        "videoUrl": "https://vimeo.com/847239103",

        "audioUrl": "",

        "educationalContent": "",

        "thumbnailUrl": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80",

    },

]

DEFAULT_DASHBOARD_ONBOARDING = [

    {

        "id": "performance-first",

        "badge": "PERFORMANCE FIRST",

        "title_lines": ["UNLEASH YOUR", "POTENTIAL"],

        "title_accent_index": 1,

        "description": "Elite discipline meets data-driven precision. Track every rep, optimize your recovery, and transcend your limits with our high-octane performance ecosystem.",

        "show_skip": False,

        "button_label": "NEXT",

        "button_arrow": "->",

        "has_secondary": False,

        "secondary_label": "",

        "has_footer": False,

        "footer_text": "",

    },

    {

        "id": "precision-tracking",

        "badge": "",

        "title_lines": ["PRECISION", "TRACKING"],

        "title_accent_index": None,

        "description": "Experience real-time analytics fueled by proprietary algorithms. Every rep, breath, and heartbeat becomes actionable data.",

        "show_skip": False,

        "button_label": "NEXT",

        "button_arrow": "->",

        "has_secondary": False,

        "secondary_label": "",

        "has_footer": False,

        "footer_text": "",

    },

    {

        "id": "stronger-together",

        "badge": "",

        "title_lines": ["STRONGER", "TOGETHER"],

        "title_accent_index": None,

        "description": "Unlock your full potential by training with a global network of elite athletes. Share data, compete in challenges, and never train alone.",

        "show_skip": False,

        "button_label": "GET STARTED",

        "button_arrow": ">",

        "has_secondary": False,

        "secondary_label": "",

        "has_footer": True,

        "footer_text": "VICTORY FITNESS OS V2.0",

    },

]

class ChallengeChatSocketManager:

    def __init__(self) -> None:

        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, challenge_id: str, websocket: WebSocket) -> None:

        await websocket.accept()

        self._connections.setdefault(challenge_id, set()).add(websocket)

    def disconnect(self, challenge_id: str, websocket: WebSocket) -> None:

        connections = self._connections.get(challenge_id)

        if not connections:

            return

        connections.discard(websocket)

        if not connections:

            self._connections.pop(challenge_id, None)

    async def broadcast(self, challenge_id: str, payload: dict) -> None:

        connections = list(self._connections.get(challenge_id, set()))

        stale: list[WebSocket] = []

        for websocket in connections:

            try:

                await websocket.send_json(payload)

            except Exception:

                stale.append(websocket)

        for websocket in stale:

            self.disconnect(challenge_id, websocket)

challenge_chat_socket_manager = ChallengeChatSocketManager()

class NotificationSocketManager:

    def __init__(self) -> None:

        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:

        await websocket.accept()

        self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:

        connections = self._connections.get(user_id)

        if not connections:

            return

        connections.discard(websocket)

        if not connections:

            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict) -> None:

        connections = list(self._connections.get(user_id, set()))

        stale: list[WebSocket] = []

        for websocket in connections:

            try:

                await websocket.send_json(payload)

            except Exception:

                stale.append(websocket)

        for websocket in stale:

            self.disconnect(user_id, websocket)

notification_socket_manager = NotificationSocketManager()

async def _broadcast_notification_event(user_id: str, payload: dict) -> None:

    await notification_socket_manager.send_to_user(user_id, payload)

subscribe_notification_events(_broadcast_notification_event)

async def _get_challenge_or_404(challenge_id: str) -> dict:

    if not ObjectId.is_valid(challenge_id):

        raise HTTPException(status_code=404, detail="Challenge not found")

    challenge = await challenges_collection.find_one({"_id": ObjectId(challenge_id)})

    if not challenge:

        raise HTTPException(status_code=404, detail="Challenge not found")

    return challenge

async def _get_challenge_membership_or_403(challenge_id: str, user_id: str) -> dict:

    membership = await challenge_memberships_collection.find_one(

        {"challenge_id": challenge_id, "user_id": user_id}

    )

    if not membership:

        raise HTTPException(status_code=403, detail="Challenge membership required")

    return membership

def _ensure_challenge_read_access(membership: dict | None, challenge: dict) -> None:

    challenge_status = str(challenge.get("status") or "ACTIVE").upper()

    membership_status = str((membership or {}).get("status") or "").upper()

    if challenge_status != "ACTIVE" and membership_status not in {"ACTIVE", "COMPLETED", "LEFT"}:

        raise HTTPException(status_code=403, detail="Challenge is not available")

    if membership_status not in {"ACTIVE", "COMPLETED", "LEFT"}:

        raise HTTPException(status_code=403, detail="Challenge membership required")

def _ensure_challenge_write_access(membership: dict | None, challenge: dict) -> None:

    _ensure_challenge_read_access(membership, challenge)

    membership_status = str((membership or {}).get("status") or "").upper()

    challenge_status = str(challenge.get("status") or "ACTIVE").upper()

    if membership_status != "ACTIVE":

        raise HTTPException(status_code=403, detail="Challenge is not active for this user")

    if challenge_status != "ACTIVE":

        raise HTTPException(status_code=403, detail="Challenge is not active")

def _ensure_challenge_chat_write_access(membership: dict | None, challenge: dict) -> None:

    _ensure_challenge_read_access(membership, challenge)

    membership_status = str((membership or {}).get("status") or "").upper()

    challenge_status = str(challenge.get("status") or "ACTIVE").upper()

    if membership_status != "ACTIVE" or challenge_status != "ACTIVE":

        raise HTTPException(status_code=403, detail="Challenge chat is only available for active challenge members")

def _normalize_progress_list(value: object) -> list[str]:

    if not isinstance(value, list):

        return []

    items: list[str] = []

    for item in value:

        text = str(item or "").strip()

        if text and text not in items:

            items.append(text)

    return items

def _build_viewer_plan_progress(plan_days: list[dict], membership: dict) -> list[ChallengePlanDayProgressResponse]:

    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    progress_items: list[ChallengePlanDayProgressResponse] = []

    for day in plan_days:

        day_number = max(int(day.get("day_number") or 0), 0)

        raw_day = raw_progress.get(str(day_number), {}) if isinstance(raw_progress, dict) else {}

        raw_day = raw_day if isinstance(raw_day, dict) else {}

        progress_items.append(

            ChallengePlanDayProgressResponse(

                day_number=day_number,

                completed=bool(raw_day.get("completed")),

                completed_section_ids=_normalize_progress_list(raw_day.get("completed_section_ids")),

                completed_exercise_ids=_normalize_progress_list(raw_day.get("completed_exercise_ids")),

            )

        )

    return progress_items

def _count_completed_plan_days_from_start(plan_days: list[dict], raw_progress: dict | None) -> int:

    progress = raw_progress if isinstance(raw_progress, dict) else {}

    completed_count = 0

    for day in sorted(plan_days, key=lambda item: int(item.get("day_number") or 0)):

        day_number = str(day.get("day_number") or "")

        day_progress = progress.get(day_number, {})

        if isinstance(day_progress, dict) and bool(day_progress.get("completed")):

            completed_count += 1

            continue

        break

    return completed_count

def _calculate_challenge_points_earned(plan_days: list[dict], membership: dict, challenge_points: int) -> int:

    duration_days = max(len(plan_days), 1)

    completed_days = _count_completed_plan_days_from_start(

        plan_days,

        membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {},

    )

    if completed_days <= 0 or challenge_points <= 0:

        return 0

    if completed_days >= duration_days:

        return challenge_points

    return int(round(challenge_points * (completed_days / duration_days)))

def _calculate_challenge_completion_counts(plan_days: list[dict], membership: dict) -> tuple[int, int]:

    plan_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    completed_units = 0

    total_units = 0

    for day in plan_days:

        if not isinstance(day, dict):

            continue

        day_number = str(day.get("day_number") or "").strip()

        day_progress = plan_progress.get(day_number, {}) if day_number else {}

        day_progress = day_progress if isinstance(day_progress, dict) else {}

        valid_section_ids, valid_exercise_ids = _get_plan_day_ids(day)

        if valid_exercise_ids:

            total_units += len(valid_exercise_ids)

            if bool(day_progress.get("completed")):

                completed_units += len(valid_exercise_ids)

                continue

            completed_exercise_ids = {

                str(value or "").strip()

                for value in day_progress.get("completed_exercise_ids", [])

                if str(value or "").strip()

            }

            completed_units += len([exercise_id for exercise_id in valid_exercise_ids if exercise_id in completed_exercise_ids])

            continue

        if valid_section_ids:

            total_units += len(valid_section_ids)

            if bool(day_progress.get("completed")):

                completed_units += len(valid_section_ids)

                continue

            completed_section_ids = {

                str(value or "").strip()

                for value in day_progress.get("completed_section_ids", [])

                if str(value or "").strip()

            }

            completed_units += len([section_id for section_id in valid_section_ids if section_id in completed_section_ids])

            continue

        total_units += 1

        if bool(day_progress.get("completed")):

            completed_units += 1

    return completed_units, total_units

def _has_completed_challenge_day_today(membership: dict) -> bool:

    plan_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    today = datetime.now(timezone.utc).date()

    for raw_day in plan_progress.values():

        if not isinstance(raw_day, dict) or not raw_day.get("completed"):

            continue

        updated_at = _coerce_utc_datetime(raw_day.get("updated_at"))

        if updated_at and updated_at.date() == today:

            return True

    return False

async def _load_challenge_participants(challenge_id: str) -> list[ChallengeParticipantResponse]:

    memberships = await challenge_memberships_collection.find(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    ).to_list(length=100)

    user_ids = [ObjectId(str(item.get("user_id"))) for item in memberships if ObjectId.is_valid(str(item.get("user_id") or ""))]

    users_by_id: dict[str, dict] = {}

    if user_ids:

        users = await users_collection.find({"_id": {"$in": user_ids}}).to_list(length=len(user_ids))

        users_by_id = {str(user["_id"]): user for user in users}

    participants: list[ChallengeParticipantResponse] = []

    for membership in memberships:

        user_id = str(membership.get("user_id") or "")

        user = users_by_id.get(user_id, {})

        participants.append(

            ChallengeParticipantResponse(

                user_id=user_id,

                name=str(user.get("name") or membership.get("user_name") or "Victory Member"),

                profile_image=str(user.get("profile_image") or ""),

            )

        )

    return participants

async def _load_message_reactions_map(challenge_id: str, message_ids: list[str]) -> dict[str, list[dict]]:

    if not message_ids:

        return {}

    records = await challenge_message_reactions_collection.find(

        {"challenge_id": challenge_id, "message_id": {"$in": message_ids}}

    ).to_list(length=None)

    user_ids = [ObjectId(str(item.get("user_id"))) for item in records if ObjectId.is_valid(str(item.get("user_id") or ""))]

    users_by_id: dict[str, dict] = {}

    if user_ids:

        users = await users_collection.find({"_id": {"$in": user_ids}}).to_list(length=len(user_ids))

        users_by_id = {str(user["_id"]): user for user in users}

    grouped: dict[str, list[dict]] = {}

    for record in records:

        message_id = str(record.get("message_id") or "")

        user_id = str(record.get("user_id") or "")

        user = users_by_id.get(user_id, {})

        grouped.setdefault(message_id, []).append(

            {

                "emoji": str(record.get("emoji") or ""),

                "user_id": user_id,

                "user_name": str(user.get("name") or "Victory Member"),

            }

        )

    return grouped

def _serialize_challenge_chat_message(

    document: dict,

    author: dict | None,

    viewer_user_id: str | None,

    reactions: list[dict] | None = None,

) -> dict:

    author_id = str(document.get("author_id") or "")

    author_name = str((author or {}).get("name") or ("Coach Victor" if author_id == "coach_bot" else "Victory Member"))

    author_role = str((author or {}).get("role") or ("coach" if author_id == "coach_bot" else "member"))

    deleted = bool(document.get("deleted_at"))

    return {

        "id": str(document.get("_id") or ""),

        "challenge_id": str(document.get("challenge_id") or ""),

        "author_id": author_id,

        "author_name": author_name,

        "author_role": author_role,

        "author_profile_image": str((author or {}).get("profile_image") or ""),

        "message_type": str(document.get("message_type") or "message"),

        "content": "" if deleted else str(document.get("content") or ""),

        "image_url": "" if deleted else str(document.get("image_url") or ""),

        "reply_to_message_id": str(document.get("reply_to_message_id") or "") or None,

        "progress_payload": document.get("progress_payload") if isinstance(document.get("progress_payload"), dict) else None,

        "created_at": document.get("created_at") or datetime.now(timezone.utc),

        "updated_at": document.get("updated_at") or document.get("created_at") or datetime.now(timezone.utc),

        "can_delete": bool(viewer_user_id and viewer_user_id == author_id and author_id not in {"coach_bot", "system"}),

        "can_edit": bool(viewer_user_id and viewer_user_id == author_id and author_id not in {"coach_bot", "system"} and not deleted),

        "is_edited": bool(document.get("edited_at")),

        "is_deleted": deleted,

        "reactions": reactions or [],

    }

async def _serialize_single_challenge_chat_message(document: dict, viewer_user_id: str | None) -> dict:

    author_id = str(document.get("author_id") or "")

    author = None

    if ObjectId.is_valid(author_id):

        author = await users_collection.find_one({"_id": ObjectId(author_id)})

    reactions_map = await _load_message_reactions_map(

        str(document.get("challenge_id") or ""),

        [str(document.get("_id") or "")],

    )

    return _serialize_challenge_chat_message(

        document,

        author,

        viewer_user_id,

        reactions_map.get(str(document.get("_id") or ""), []),

    )

async def _load_challenge_chat_messages(challenge_id: str, viewer_user_id: str | None, *, limit: int = 50) -> list[dict]:

    records = await challenge_chat_messages_collection.find(

        {"challenge_id": challenge_id},

        sort=[("created_at", 1), ("_id", 1)],

    ).to_list(length=max(limit, 1))

    author_ids = [ObjectId(str(item.get("author_id"))) for item in records if ObjectId.is_valid(str(item.get("author_id") or ""))]

    authors_by_id: dict[str, dict] = {}

    if author_ids:

        authors = await users_collection.find({"_id": {"$in": author_ids}}).to_list(length=len(author_ids))

        authors_by_id = {str(author["_id"]): author for author in authors}

    message_ids = [str(record.get("_id") or "") for record in records]

    reactions_map = await _load_message_reactions_map(challenge_id, message_ids)

    return [

        _serialize_challenge_chat_message(

            record,

            authors_by_id.get(str(record.get("author_id") or "")),

            viewer_user_id,

            reactions_map.get(str(record.get("_id") or ""), []),

        )

        for record in records[-limit:]

    ]

async def _count_unread_challenge_messages(challenge_id: str, user_id: str, membership: dict) -> int:

    last_read_at = _coerce_utc_datetime(membership.get("last_read_message_at"))

    query: dict[str, Any] = {"challenge_id": challenge_id, "author_id": {"$ne": user_id}}

    if last_read_at is not None:

        query["created_at"] = {"$gt": last_read_at}

    return max(int(await challenge_chat_messages_collection.count_documents(query)), 0)

async def _get_challenge_message_or_404(challenge_id: str, message_id: str) -> dict:

    if not ObjectId.is_valid(message_id):

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    message = await challenge_chat_messages_collection.find_one(

        {"_id": ObjectId(message_id), "challenge_id": challenge_id}

    )

    if not message:

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    return message

async def _broadcast_challenge_chat_event(

    event: str,

    challenge_id: str,

    document: dict | None = None,

    message_id: str | None = None,

) -> None:

    payload: dict[str, Any] = {

        "event": event,

        "challenge_id": challenge_id,

        "message": None,

        "message_id": message_id,

    }

    if document is not None:

        payload["message"] = await _serialize_single_challenge_chat_message(document, None)

        payload["message_id"] = payload["message"]["id"]

    await challenge_chat_socket_manager.broadcast(challenge_id, payload)

def _serialize_challenge_plan_progress_response(

    challenge_id: str,

    membership: dict,

    plan_days: list[dict],

) -> ChallengePlanProgressResponse:

    challenge_points = max(int(membership.get("challenge_points") or 0), 0)

    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    return ChallengePlanProgressResponse(

        challenge_id=challenge_id,

        viewer_membership_status=str(membership.get("status") or "ACTIVE"),

        viewer_progress_days_completed=_count_completed_plan_days_from_start(plan_days, raw_progress),

        viewer_points_earned=_calculate_challenge_points_earned(plan_days, membership, challenge_points),

        viewer_plan_progress=_build_viewer_plan_progress(plan_days, membership),

    )

def _build_cors_response_headers(request: Request) -> dict[str, str]:

    origin = str(request.headers.get("origin") or "").strip()

    if not origin:

        return {}

    if origin in settings.cors_origins:

        return {

            "Access-Control-Allow-Origin": origin,

            "Access-Control-Allow-Credentials": "true",

            "Vary": "Origin",

        }

    origin_regex = settings.cors_origin_regex

    if origin_regex and re.match(origin_regex, origin):

        return {

            "Access-Control-Allow-Origin": origin,

            "Access-Control-Allow-Credentials": "true",

            "Vary": "Origin",

        }

    return {}

def _cors_json_response(request: Request, *, status_code: int, content: dict[str, Any]) -> JSONResponse:

    response = JSONResponse(status_code=status_code, content=content)

    for header_name, header_value in _build_cors_response_headers(request).items():

        response.headers[header_name] = header_value

    return response

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

    log_method = logger.warning if duration_ms >= settings.slow_request_threshold_ms else logger.info

    log_event = "request_slow" if duration_ms >= settings.slow_request_threshold_ms else "request_completed"

    log_method(

        "%s method=%s path=%s status_code=%s duration_ms=%s",

        log_event,

        request.method,

        request.url.path,

        response.status_code,

        duration_ms,

    )

    return response

async def database_not_configured_handler(

    request: Request,

    exc: DatabaseNotConfiguredError,

) -> JSONResponse:

    logger.error("database_not_configured path=%s detail=%s", request.url.path, str(exc))

    return _cors_json_response(request, status_code=503, content={"detail": str(exc)})

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

    return _cors_json_response(request, status_code=exc.status_code, content={"detail": exc.detail})

async def unhandled_exception_handler(

    request: Request,

    exc: Exception,

) -> JSONResponse:

    detail = str(exc).strip() or "Internal server error"

    from ..observability import capture_exception

    logger.exception(

        "unhandled_exception method=%s path=%s detail=%s",

        request.method,

        request.url.path,

        detail,

    )
    capture_exception(
        exc,
        context={
            "method": request.method,
            "path": request.url.path,
            "detail": detail,
            "request_id": getattr(request.state, "request_id", ""),
            "trace_id": getattr(request.state, "trace_id", ""),
        },
    )

    return _cors_json_response(request, status_code=500, content={"detail": "Internal server error"})

async def _require_access_user(

    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),

    access_token: str | None = Cookie(default=None),

) -> dict:

    return await dependency_require_access_user(credentials, access_token)

async def _require_admin_user(user: dict = Depends(_require_access_user)) -> dict:

    return await dependency_require_admin_user(user)

async def _require_challenge_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "challenge", "Your current plan does not include challenge access")

    return user

async def _require_workout_plan_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "workoutplan", "Your current plan does not include workout plan access")

    return user

async def _require_meal_plan_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "mealPlan", "Your current plan does not include meal plan access")

    return user

async def _require_nutrition_tracker_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "nutrition_tracker", "Your current plan does not include nutrition tracker access")

    return user

async def _require_meal_analysis_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "meal_analysis", "Your current plan does not include meal analysis access")

    return user

async def _require_longevity_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "longevity", "Your current plan does not include Longevity OS access")

    return user

async def _require_community_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "community", "Your current plan does not include community access")

    return user

async def _require_coach_victor_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "coach_victor", "Your current plan does not include Coach Victor access")

    return user

async def _require_application_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "application", "Your current plan does not include application access")

    return user

async def _require_longevity_plan_access_user(user: dict = Depends(_require_access_user)) -> dict:

    _ensure_subscription_feature_access(user, "longevity_plan", "Your current plan does not include Longevity plan generation")

    return user

class FirebaseAuthRequest(BaseModel):

    id_token: str = Field(min_length=20)

def _read_json_url(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:

    request = UrlRequest(url, headers=headers or {})

    with urlopen(request, timeout=10) as response:

        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):

        raise HTTPException(status_code=500, detail="Unable to load remote identity payload")

    return payload

@lru_cache(maxsize=1)

def _get_firebase_certificates() -> dict[str, str]:

    cert_url = (getattr(settings, "firebase_auth_provider_cert_url", "") or "").strip()

    if not cert_url:

        raise HTTPException(status_code=500, detail="Firebase auth is not configured")

    payload = _read_json_url(cert_url)

    return {str(k): str(v) for k, v in payload.items() if str(k).strip() and str(v).strip()}

@lru_cache(maxsize=1)

def _get_google_certificates() -> dict[str, str]:

    cert_url = (getattr(settings, "google_auth_provider_cert_url", "") or "").strip()

    if not cert_url:

        raise HTTPException(status_code=500, detail="Google auth is not configured")

    payload = _read_json_url(cert_url)

    return {str(k): str(v) for k, v in payload.items() if str(k).strip() and str(v).strip()}

@lru_cache(maxsize=1)

def _get_google_jwks() -> list[dict[str, Any]]:

    payload = _read_json_url("https://www.googleapis.com/oauth2/v3/certs")

    keys = payload.get("keys")

    if not isinstance(keys, list):

        return []

    return [key for key in keys if isinstance(key, dict)]

def _verify_firebase_id_token(id_token: str) -> dict[str, Any]:

    project_id = (getattr(settings, "firebase_project_id", "") or getattr(settings, "google_project_id", "") or "").strip()

    if not project_id:

        raise HTTPException(status_code=500, detail="Firebase auth is not configured")

    try:

        header = jwt.get_unverified_header(id_token)

    except Exception as exc:

        raise HTTPException(status_code=401, detail="Invalid Firebase token") from exc

    kid = str(header.get("kid") or "").strip()

    certificate = _get_firebase_certificates().get(kid)

    if not certificate:

        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    issuer = f"https://securetoken.google.com/{project_id}"

    try:

        payload = jwt.decode(

            id_token,

            certificate,

            algorithms=["RS256"],

            audience=project_id,

            issuer=issuer,

        )

    except Exception as exc:

        raise HTTPException(status_code=401, detail="Invalid Firebase token") from exc

    return payload

def _verify_google_id_token(id_token: str) -> dict[str, Any]:

    google_client_id = (getattr(settings, "google_client_id", "") or "").strip()

    if not google_client_id:

        raise HTTPException(status_code=500, detail="Google auth is not configured")

    try:

        header = jwt.get_unverified_header(id_token)

    except Exception as exc:

        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    kid = str(header.get("kid") or "").strip()

    candidate_keys: list[Any] = []

    certificate = _get_google_certificates().get(kid)

    if certificate:

        candidate_keys.append(certificate)

    candidate_keys.extend([key for key in _get_google_jwks() if str(key.get("kid") or "").strip() == kid])

    if not candidate_keys:

        _get_google_certificates.cache_clear()
        _get_google_jwks.cache_clear()
        certificate = _get_google_certificates().get(kid)
        if certificate:
            candidate_keys.append(certificate)
        candidate_keys.extend([key for key in _get_google_jwks() if str(key.get("kid") or "").strip() == kid])

    if not candidate_keys:

        logger.warning("auth_google_token_unknown_kid kid=%s", kid)

        return _verify_google_id_token_with_tokeninfo(id_token, google_client_id, fallback_reason="unknown_kid")

    last_error: Exception | None = None

    for candidate_key in candidate_keys:

        for issuer in ("https://accounts.google.com", "accounts.google.com"):

            try:

                return jwt.decode(

                    id_token,

                    candidate_key,

                    algorithms=["RS256"],

                    audience=google_client_id,

                    issuer=issuer,

                )

            except Exception as exc:

                last_error = exc

    logger.warning("auth_google_token_verify_failed kid=%s error=%s", kid, type(last_error).__name__ if last_error else "unknown")

    return _verify_google_id_token_with_tokeninfo(id_token, google_client_id, fallback_reason="local_verify_failed")

def _verify_google_id_token_with_tokeninfo(id_token: str, google_client_id: str, *, fallback_reason: str) -> dict[str, Any]:

    try:

        payload = _read_json_url(f"https://oauth2.googleapis.com/tokeninfo?{urlencode({'id_token': id_token})}")

    except Exception as exc:

        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    audience = str(payload.get("aud") or "").strip()

    if audience != google_client_id:

        logger.warning("auth_google_tokeninfo_audience_mismatch reason=%s", fallback_reason)

        raise HTTPException(status_code=401, detail="Invalid Google token")

    issuer = str(payload.get("iss") or "").strip()

    if issuer not in {"https://accounts.google.com", "accounts.google.com"}:

        logger.warning("auth_google_tokeninfo_issuer_mismatch reason=%s issuer=%s", fallback_reason, issuer)

        raise HTTPException(status_code=401, detail="Invalid Google token")

    try:

        expires_at = int(str(payload.get("exp") or "0"))

    except ValueError:

        expires_at = 0

    if expires_at <= int(datetime.now(timezone.utc).timestamp()):

        raise HTTPException(status_code=401, detail="Google token expired")

    if not str(payload.get("sub") or "").strip():

        raise HTTPException(status_code=401, detail="Google account is missing a provider user ID")

    if not str(payload.get("email") or "").strip():

        raise HTTPException(status_code=401, detail="Google account is missing an email")

    if not _bool_from_provider_claim(payload.get("email_verified")):

        raise HTTPException(status_code=401, detail="Google account email is not verified")

    logger.info("auth_google_tokeninfo_verify_success reason=%s", fallback_reason)

    return payload

def _bool_from_provider_claim(value: Any) -> bool:

    if isinstance(value, bool):

        return value

    if isinstance(value, str):

        return value.strip().lower() == "true"

    return False

def _split_display_name(display_name: str, email: str) -> tuple[str, str, str]:

    normalized_display_name = str(display_name or "").strip()

    if not normalized_display_name:

        local_part = str(email or "").split("@")[0].strip()

        normalized_display_name = local_part or "Victory Fitness User"

    parts = [segment for segment in normalized_display_name.split() if segment]

    first_name = parts[0] if parts else normalized_display_name

    last_name = " ".join(parts[1:]).strip() if len(parts) > 1 else ""

    full_name = f"{first_name} {last_name}".strip() or normalized_display_name

    return first_name, last_name, full_name

def _provider_identity_field(auth_provider: str) -> str:

    if auth_provider == "google":

        return "google_sub"

    return "firebase_uid"

def _provider_identity_query(auth_provider: str, provider_user_id: str) -> dict[str, Any]:

    normalized_provider_user_id = str(provider_user_id or "").strip()

    if not normalized_provider_user_id:

        return {}

    if auth_provider == "google":

        return {
            "$or": [
                {"google_sub": normalized_provider_user_id},
                {"auth_provider": "google", "auth_provider_user_id": normalized_provider_user_id},
                {"auth_provider": "google", "firebase_uid": normalized_provider_user_id},
            ]
        }

    return {
        "$or": [
            {"firebase_uid": normalized_provider_user_id},
            {"auth_provider": "firebase", "auth_provider_user_id": normalized_provider_user_id},
        ]
    }

def _merge_google_profiles(id_token_profile: dict[str, Any], access_token_profile: dict[str, Any] | None) -> dict[str, Any]:

    if not access_token_profile:

        return id_token_profile

    merged = dict(access_token_profile)

    merged.update({key: value for key, value in id_token_profile.items() if value not in (None, "")})

    id_email = str(id_token_profile.get("email") or "").strip().lower()

    access_email = str(access_token_profile.get("email") or "").strip().lower()

    if id_email and access_email and id_email != access_email:

        raise HTTPException(status_code=401, detail="Google account details did not match")

    id_sub = str(id_token_profile.get("sub") or "").strip()

    access_sub = str(access_token_profile.get("sub") or "").strip()

    if id_sub and access_sub and id_sub != access_sub:

        raise HTTPException(status_code=401, detail="Google account details did not match")

    return merged

def _fetch_google_userinfo(access_token: str) -> dict[str, Any]:

    token = str(access_token or "").strip()

    if not token:

        raise HTTPException(status_code=401, detail="Missing Google access token")

    try:

        return _read_json_url(

            "https://openidconnect.googleapis.com/v1/userinfo",

            headers={"Authorization": f"Bearer {token}"},

        )

    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(status_code=401, detail="Invalid Google access token") from exc

async def _upsert_identity_user(profile: dict[str, Any], auth_provider: str) -> dict:

    email = str(profile.get("email") or "").strip().lower()

    if not email:

        raise HTTPException(status_code=401, detail="Google account is missing an email")

    if not _bool_from_provider_claim(profile.get("email_verified")):

        raise HTTPException(status_code=401, detail="Google account email is not verified")

    display_name = str(profile.get("name") or profile.get("displayName") or email.split("@")[0]).strip()

    photo_url = str(
        profile.get("picture")
        or profile.get("photoUrl")
        or profile.get("photo_url")
        or profile.get("avatar_url")
        or ""
    ).strip()

    provider_user_id = str(profile.get("sub") or profile.get("user_id") or profile.get("localId") or "").strip()

    if not provider_user_id:

        raise HTTPException(status_code=401, detail="Google account is missing a provider user ID")

    provider_identity_field = _provider_identity_field(auth_provider)
    first_name, last_name, full_name = _split_display_name(display_name, email)

    now = datetime.now(timezone.utc)

    existing_user = await users_collection.find_one(_provider_identity_query(auth_provider, provider_user_id))

    if not existing_user:

        existing_user = await users_collection.find_one({"email": email})

    if not existing_user:

        user_doc = {

            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,

            "email": email,
            "contact_number": "",
            "marketing_consent": False,
            "signup_source": f"{auth_provider}_oauth",

            "is_verified": True,

            "role": "user",

            "is_admin": False,

            "subscription_tier": "NONE",

            "subscription_role": "NONE",

            "subscription_status": "NONE",

            "subscription_billing_cycle": "yearly",

            "subscription_is_purchased": False,

            "subscription_purchase_source": "",

            "password_hash": "",

            "auth_provider": auth_provider,

            "auth_providers": [auth_provider],
            "auth_provider_user_id": provider_user_id,
            provider_identity_field: provider_user_id,

            "profile_image": photo_url,

            "onboarding_completed": False,

            "created_at": now,

            "updated_at": now,

        }

        inserted = await users_collection.insert_one(user_doc)

        return await users_collection.find_one({"_id": inserted.inserted_id}) or user_doc

    update_doc: dict[str, Any] = {

        "is_verified": True,

        "auth_provider": str(existing_user.get("auth_provider") or auth_provider),
        "auth_provider_user_id": provider_user_id,
        provider_identity_field: provider_user_id,
        "auth_providers": sorted(
            {
                str(item).strip()
                for item in [*(existing_user.get("auth_providers") or []), existing_user.get("auth_provider"), auth_provider]
                if str(item).strip()
            }
        ),

        "updated_at": now,

    }

    if full_name and not str(existing_user.get("name") or "").strip():

        update_doc["name"] = full_name

    if first_name and not str(existing_user.get("first_name") or "").strip():

        update_doc["first_name"] = first_name

    if last_name and not str(existing_user.get("last_name") or "").strip():

        update_doc["last_name"] = last_name

    if photo_url:

        update_doc["profile_image"] = photo_url

    await users_collection.update_one(

        {"_id": existing_user["_id"]},

        {

            "$set": update_doc,

            "$unset": {

                "verification_code_hash": "",

                "verification_code_expires_at": "",

                "previous_verification_code_hash": "",

                "previous_verification_code_expires_at": "",

                "profileImage": "",

            },

        },

    )

    return await users_collection.find_one({"_id": existing_user["_id"]}) or existing_user

async def _upsert_firebase_user(profile: dict[str, Any]) -> dict:

    return await _upsert_identity_user(profile, "firebase")

async def _upsert_google_user(profile: dict[str, Any]) -> dict:

    return await _upsert_identity_user(profile, "google")

def _resolve_google_profile(payload: GoogleAuthRequest) -> tuple[dict[str, Any], str]:

    id_token = str(payload.id_token or "").strip()

    access_token = str(payload.access_token or "").strip()

    if not id_token:

        raise HTTPException(status_code=400, detail="Missing Google ID token")

    google_exc: HTTPException | None = None

    try:

        profile = _verify_google_id_token(id_token)

        if access_token:

            try:

                profile = _merge_google_profiles(profile, _fetch_google_userinfo(access_token))

            except HTTPException as exc:

                if exc.status_code >= 500:

                    logger.warning("auth_google_userinfo_merge_failed detail=%s", exc.detail)

                else:

                    raise

        return profile, "google"

    except HTTPException as exc:

        google_exc = exc

        if exc.status_code >= 500:

            logger.warning("auth_google_id_token_verify_failed detail=%s", exc.detail)

    try:

        profile = _verify_firebase_id_token(id_token)

        return profile, "firebase"

    except HTTPException as firebase_exc:

        if google_exc and google_exc.status_code < 500:

            raise google_exc

        raise firebase_exc

async def startup() -> None:

    logger.info("startup_begin")

    if settings.using_default_jwt_secret:

        logger.warning("security_warning using default JWT secret; set JWT_SECRET_KEY before production deployment")

    if not settings.mongodb_configured:

        logger.info("startup_jobs_skipped reason=database_not_configured")

        return

    await _seed_admin_user()

    if not settings.startup_jobs_enabled:

        logger.info("startup_jobs_skipped reason=disabled")

        return

    await ensure_indexes()

    await backfill_current_health_metrics_from_history()

    await start_integration_queue()

    await start_wearables_scheduler()

    await _run_analytics_migrations()

    logger.info("startup_complete")

async def shutdown() -> None:

    logger.info("shutdown_begin")

    if not settings.startup_jobs_enabled:

        logger.info("shutdown_jobs_skipped reason=disabled")

        return

    if not settings.mongodb_configured:

        logger.info("shutdown_jobs_skipped reason=database_not_configured")

        return

    await stop_wearables_scheduler()

    await stop_integration_queue()

    await close_database_connection()

    logger.info("shutdown_complete")

def _serialize_strength_workout_plan_record(record: dict) -> StrengthWorkoutPlanResponse:

    plan_data = dict(record.get("plan") or {})

    normalized_days: list[dict[str, Any]] = []

    for raw_day in plan_data.get("days") or []:

        if not isinstance(raw_day, dict):

            continue

        day_exercises = [dict(exercise) for exercise in raw_day.get("exercises", []) if isinstance(exercise, dict)]

        raw_sections = raw_day.get("sections") or []

        normalized_sections: list[dict[str, Any]] = []

        if isinstance(raw_sections, list) and raw_sections:

            for section in raw_sections:

                if not isinstance(section, dict):

                    continue

                section_exercises = [dict(exercise) for exercise in section.get("exercises", []) if isinstance(exercise, dict)]

                normalized_sections.append(

                    {

                        "id": str(section.get("id") or "").strip() or f"{str(raw_day.get('day') or 'day').lower()}-section-{len(normalized_sections) + 1}",

                        "title": str(section.get("title") or "Workout Block").strip() or "Workout Block",

                        "estimated_minutes": max(int(section.get("estimated_minutes") or 0), 0),

                        "exercises": section_exercises,

                    }

                )

        if not normalized_sections:

            grouped_sections: dict[str, dict[str, Any]] = {}

            section_order: list[str] = []

            for index, exercise in enumerate(day_exercises):

                exercise_type = str(exercise.get("type") or "work").strip() or "work"

                section_key = re.sub(r"[^a-z0-9]+", "-", exercise_type.lower()).strip("-") or f"section-{index + 1}"

                section_id = f"{str(raw_day.get('day') or 'day').lower()}-{section_key}"

                if section_id not in grouped_sections:

                    grouped_sections[section_id] = {

                        "id": section_id,

                        "title": exercise_type.title(),

                        "estimated_minutes": 0,

                        "exercises": [],

                    }

                    section_order.append(section_id)

                grouped_sections[section_id]["exercises"].append(exercise)

            for section_id in section_order:

                section = grouped_sections[section_id]

                section["estimated_minutes"] = max(len(section["exercises"]) * 6, 6)

                normalized_sections.append(section)

        normalized_days.append(

            {

                **raw_day,

                "sections": normalized_sections,

                "exercises": day_exercises,

            }

        )

    plan_data["days"] = normalized_days

    raw_progress = record.get("progress") or []

    normalized_progress: list[dict[str, Any]] = []

    for item in raw_progress:

        if not isinstance(item, dict):

            continue

        normalized_progress.append(

            {

                "day": str(item.get("day") or "").strip(),

                "started": bool(item.get("started")),

                "completed": bool(item.get("completed")),

                "completed_section_ids": [

                    str(value).strip()

                    for value in item.get("completed_section_ids", [])

                    if str(value).strip()

                ],

                "completed_exercise_ids": [

                    str(value).strip()

                    for value in item.get("completed_exercise_ids", [])

                    if str(value).strip()

                ],

                "started_at": item.get("started_at"),

                "completed_at": item.get("completed_at"),

            }

        )

    plan_data["plan_id"] = str(record["_id"])

    plan_data["created_at"] = record.get("created_at")

    plan_data["progress"] = normalized_progress

    return StrengthWorkoutPlanResponse(**plan_data)

def _build_strength_workout_completion_png(
    plan: StrengthWorkoutPlanResponse,
    user_name: str,
    completed_day: str = "",
    full_plan: bool = False,
) -> tuple[bytes, str]:
    _require_pillow()
    progress_by_day = {item.day: item for item in plan.progress}
    completed_days = sum(1 for item in plan.progress if item.completed)
    total_days = max(len(plan.days), 1)
    selected_day = next((day for day in plan.days if day.day == completed_day), None)
    if selected_day is None:
        selected_day = next((day for day in reversed(plan.days) if progress_by_day.get(day.day) and progress_by_day[day.day].completed), None)
    selected_day = selected_day or (plan.days[0] if plan.days else None)
    selected_progress = progress_by_day.get(selected_day.day) if selected_day else None
    completed_exercise_ids = set(selected_progress.completed_exercise_ids if selected_progress else [])
    completed_section_ids = set(selected_progress.completed_section_ids if selected_progress else [])
    entries: list[str] = []
    if selected_day:
        for section in selected_day.sections:
            if section.id in completed_section_ids:
                entries.extend(exercise.name for exercise in section.exercises)
            else:
                entries.extend(exercise.name for exercise in section.exercises if exercise.id in completed_exercise_ids)
    entries = entries[:7]
    total_exercises = sum(len(section.exercises) for day in plan.days for section in day.sections)
    completed_exercises = sum(len(item.completed_exercise_ids) for item in plan.progress)
    width, height = 900, 1400
    image = Image.new("RGB", (width, height), "#03192A")
    draw = ImageDraw.Draw(image)
    cyan, white, muted, pink = "#00D9F5", "#F7F7F7", "#A9B8C8", "#FF4B70"
    title_font = _load_report_font(42, bold=True)
    heading_font = _load_report_font(32, bold=True)
    section_font = _load_report_font(21, bold=True)
    body_font = _load_report_font(18)
    small_font = _load_report_font(15)
    draw.rounded_rectangle((36, 55, width - 36, height - 28), radius=34, fill="#06111D", outline=cyan, width=3)

    def center_text(y: int, text: str, font: Any, fill: str) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

    draw.ellipse((width // 2 - 32, 120, width // 2 + 32, 184), fill=cyan)
    center_text(137, "VF", _load_report_font(25, bold=True), "#03192A")
    center_text(230, "YOUR VICTORY", title_font, white)
    center_text(292, "CUSTOM STRENGTH PLAN COMPLETED" if full_plan else "STRENGTH WORKOUT COMPLETED", section_font, cyan)
    draw.rounded_rectangle((100, 370, width - 100, 790), radius=24, fill="#101F2E", outline="#273E50", width=2)
    title_lines = _wrap_report_text(draw, str(plan.summary or "Custom Strength Plan").upper(), heading_font, 620)[:3]
    title_y = 420
    for line in title_lines:
        center_text(title_y, line, heading_font, white)
        title_y += 43
    center_text(title_y + 20, f"{selected_day.day if selected_day else 'Workout'} · {user_name or 'Victory Member'}", body_font, muted)
    draw.rounded_rectangle((150, 570, width - 150, 590), radius=10, fill="#203243")
    draw.rounded_rectangle((150, 570, 150 + int(600 * min(completed_days / total_days, 1)), 590), radius=10, fill=cyan)
    draw.text((150, 630), "COMPLETED EXERCISES", font=section_font, fill=cyan)
    row_y = 680
    for entry in entries or ["Keep building your strength."]:
        draw.ellipse((154, row_y + 5, 168, row_y + 19), fill=cyan)
        draw.text((190, row_y), entry, font=body_font, fill=white if entries else muted)
        row_y += 34
    for x, label, value, color in ((140, "PLAN DAYS", f"{completed_days}/{total_days}", cyan), (475, "EXERCISES", f"{completed_exercises}/{max(total_exercises, completed_exercises or 1)}", pink)):
        draw.rounded_rectangle((x, 910, x + 285, 1030), radius=18, fill="#030606", outline="#27343A", width=2)
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((x + (285 - (box[2] - box[0])) / 2, 930), label, font=small_font, fill=white)
        value_box = draw.textbbox((0, 0), value, font=heading_font)
        draw.text((x + (285 - (value_box[2] - value_box[0])) / 2, 962), value, font=heading_font, fill=color)
    draw.rounded_rectangle((140, 1090, width - 140, 1180), radius=28, fill="#00C5F0")
    member = str(user_name or "Victory Member").upper()
    member_box = draw.textbbox((0, 0), member, font=section_font)
    draw.text(((width - (member_box[2] - member_box[0])) / 2, 1120), member, font=section_font, fill="#06131D")
    center_text(1245, "VICTORY-FITNESS.APP", section_font, "#B1BDCA")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    day_name = selected_day.title if selected_day else "Strength workout"
    share_message = "\n".join([
        "Victory Fitness",
        f"{'Custom strength plan' if full_plan else day_name} completed by {user_name or 'Victory Member'}",
        f"Plan progress: {completed_days}/{total_days} days | Exercises: {completed_exercises}/{max(total_exercises, completed_exercises or 1)}",
    ])
    return output.getvalue(), share_message

def _serialize_onboarding_state(record: dict) -> dict[str, Any]:
    state = dict(record.get("onboarding_state") or {})
    personal_profile = dict(state.get("personalProfile") or {})
    anamnese = dict(state.get("anamnese") or {})
    suggestion = state.get("suggestion")
    metrics = dict(record.get("body_metrics") or {})

    normalized_suggestion: dict[str, Any] | None = None
    if isinstance(suggestion, dict):
        normalized_suggestion = {
            "tier": str(suggestion.get("tier") or "GOLD").strip().upper() or "GOLD",
            "title": str(suggestion.get("title") or "").strip(),
            "reason": str(suggestion.get("reason") or "").strip(),
            "note": str(suggestion.get("note") or "").strip() or None,
        }

    updated_at = state.get("updatedAt")
    if updated_at and not isinstance(updated_at, datetime):
        updated_at = None

    try:
        current_step = max(int(state.get("currentStep") or 0), 0)
    except (TypeError, ValueError):
        current_step = 0

    return {
        "userId": str(record["_id"]),
        "currentStep": current_step,
        "language": str(state.get("language") or "").strip(),
        "country": str(state.get("country") or record.get("country") or "").strip(),
        "countryCode": (str(state.get("countryCode") or record.get("country_code") or "").upper() or None),
        "motivationStatement": str(state.get("motivationStatement") or record.get("motivation_statement") or "").strip(),
        "personalProfile": {
            "age": str(personal_profile.get("age") or metrics.get("age") or "").strip(),
            "gender": str(personal_profile.get("gender") or metrics.get("gender") or "").strip(),
            "height": str(personal_profile.get("height") or metrics.get("height") or "").strip(),
            "heightUnit": "cm",
            "weight": str(personal_profile.get("weight") or metrics.get("weight") or "").strip(),
            "weightUnit": "lb" if str(personal_profile.get("weightUnit") or "kg").strip().lower() == "lb" else "kg",
        },
        "anamnese": {
            "primaryGoal": str(anamnese.get("primaryGoal") or "").strip(),
            "activityLevel": str(anamnese.get("activityLevel") or "").strip(),
            "healthConcerns": [str(item).strip() for item in anamnese.get("healthConcerns", []) if str(item).strip()],
            "healthNotes": str(anamnese.get("healthNotes") or "").strip(),
            "daysPerWeek": str(anamnese.get("daysPerWeek") or "").strip(),
            "timePerSession": str(anamnese.get("timePerSession") or "").strip(),
            "equipmentAccess": str(anamnese.get("equipmentAccess") or "").strip(),
        },
        "suggestion": normalized_suggestion,
        "updatedAt": updated_at,
        "completed": bool(record.get("onboarding_completed", False)),
    }

def _calculate_habit_streak(habits: list[dict]) -> int:

    return sum(1 for habit in habits if bool(habit.get("done")))

def _build_default_longevity_profile(user: dict) -> dict:

    age = str((user.get("body_metrics") or {}).get("age") or "").strip()

    chronological_age = age if age else "N/A"

    biological_age = chronological_age if age else "N/A"

    now = datetime.now(timezone.utc)

    return {

        "user_id": str(user["_id"]),

        "overview": {

            "biological_age": biological_age,

            "chronological_age": chronological_age,

            "trending_years_younger": 2.4 if age else 0,

            "recovery_score": 82 if age else 0,

            "hrv_ms": 41 if age else 0,

            "sleep_score": 76 if age else 0,

        },

        "quick_actions": [dict(item) for item in DEFAULT_LONGEVITY_QUICK_ACTIONS],

        "wearables": {

            "devices": [dict(item) for item in DEFAULT_LONGEVITY_WEARABLES],

            "last_synced_at": None,

            "has_data": False,

            "sync_message": "No data synced yet. Connect a device and press sync to begin your longevity analysis.",

        },

        "habits": [dict(item) for item in DEFAULT_LONGEVITY_HABITS],

        "heal_categories": [dict(item) for item in DEFAULT_LONGEVITY_HEAL_CATEGORIES],

        "weekly_plan": None,

        "masterclasses": [dict(item) for item in DEFAULT_LONGEVITY_MASTERCLASSES],

        "circles": [],

        "created_at": now,

        "updated_at": now,

    }

async def _get_or_create_longevity_profile(user: dict) -> dict:

    user_id = str(user["_id"])

    profile = await longevity_os_profiles_collection.find_one({"user_id": user_id})

    if profile:

        return profile

    document = _build_default_longevity_profile(user)

    await longevity_os_profiles_collection.insert_one(document)

    return document

async def _serialize_longevity_dashboard(profile: dict) -> LongevityDashboardResponse:

    habits_raw = [dict(item) for item in profile.get("habits") or []]

    user_id = str(profile.get("user_id") or "")

    wearables = await build_longevity_wearables_response(user_id)

    metric_insights = await build_longevity_metric_insights(user_id)

    overview_payload = dict(profile.get("overview") or {})

    masterclass_items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    if metric_insights.get("has_metrics"):

        overview_payload.update(metric_insights.get("overview") or {})

    return LongevityDashboardResponse(

        overview=LongevityOverviewResponse(**overview_payload),

        quick_actions=[LongevityQuickActionResponse(**item) for item in profile.get("quick_actions") or []],

        wearables=wearables,

        habits=LongevityHabitsResponse(

            streak_days=_calculate_habit_streak(habits_raw),

            habits=[LongevityHabitResponse(**item) for item in habits_raw],

        ),

        heal_categories=[LongevityHealCategoryResponse(**item) for item in profile.get("heal_categories") or []],

        weekly_plan=LongevityWeeklyPlanResponse(**profile["weekly_plan"]) if isinstance(profile.get("weekly_plan"), dict) else None,

        masterclasses=[

            LongevityMasterclassResponse(

                id=item["id"],

                title=item["title"],

                description=item["description"],

                thumbnail=item["thumbnailUrl"],

                videoUrl=item["videoUrl"],

                videoSource=item["videoSource"],

                audioUrl=item["audioUrl"],

                category=item["category"],

                duration=item["duration"],

                educationalContent=item["educationalContent"],

            )

            for item in masterclass_items

        ],

        circles=[LongevityCircleResponse(**item) for item in profile.get("circles") or []],

    )

async def _notify_challenge_chat_participants(
    challenge_id: str,
    author_id: str,
    challenge_title: str,
    content: str,
) -> None:
    memberships = await challenge_memberships_collection.find({"challenge_id": challenge_id}).to_list(length=None)
    participant_ids = {
        str(item.get("user_id") or "").strip()
        for item in memberships
        if isinstance(item, dict) and str(item.get("user_id") or "").strip() != author_id
    }
    object_ids = [ObjectId(item) for item in participant_ids if ObjectId.is_valid(item)]
    if not object_ids:
        return
    recipients = await users_collection.find({"_id": {"$in": object_ids}, "is_admin": {"$ne": True}}).to_list(length=None)
    preview = " ".join(str(content or "").split())[:120] or "Sent an image in the challenge chat."
    results = await asyncio.gather(*[
        notify_user(
            users_collection,
            recipient,
            f"New message in {challenge_title or 'your challenge'}",
            preview,
            "challenge_chat_message",
            {"type": "challenge_chat", "challengeId": challenge_id, "route": f"/challenges/{challenge_id}"},
        )
        for recipient in recipients
    ], return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.warning("challenge_chat_notification_failed challenge_id=%s error=%s", challenge_id, result)

async def _store_membership_plan_progress(

    *,

    challenge: dict,

    membership: dict,

    user: dict,

    day_number: int,

    completed_section_ids: list[str],

    completed_exercise_ids: list[str],

    completed: bool,

    emit_progress_message: bool,

) -> ChallengePlanProgressResponse:

    plan_days = _get_normalized_plan_days(challenge)

    plan_day = _get_plan_day_or_404(plan_days, day_number)

    valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

    normalized_section_ids = []

    for section_id in completed_section_ids:

        if section_id in valid_section_ids and section_id not in normalized_section_ids:

            normalized_section_ids.append(section_id)

    normalized_exercise_ids = []

    for exercise_id in completed_exercise_ids:

        if exercise_id in valid_exercise_ids and exercise_id not in normalized_exercise_ids:

            normalized_exercise_ids.append(exercise_id)

    for section in plan_day.get("sections") or []:

        section_id = str(section.get("id") or "")

        exercises = section.get("exercises") if isinstance(section.get("exercises"), list) else []

        exercise_ids = [

            str(exercise.get("id") or "")

            for exercise in exercises

            if str(exercise.get("id") or "")

        ]

        if exercise_ids and all(exercise_id in normalized_exercise_ids for exercise_id in exercise_ids):

            if section_id and section_id not in normalized_section_ids:

                normalized_section_ids.append(section_id)

        elif section_id in normalized_section_ids and exercise_ids:

            normalized_section_ids = [value for value in normalized_section_ids if value != section_id]

    total_sections = len(valid_section_ids)

    is_day_completed = bool(completed or (total_sections > 0 and len(normalized_section_ids) >= total_sections))

    if total_sections == 0 and completed:

        is_day_completed = True

    existing_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    next_plan_progress = dict(existing_progress)

    next_plan_progress[str(day_number)] = {

        "completed": is_day_completed,

        "completed_section_ids": normalized_section_ids,

        "completed_exercise_ids": normalized_exercise_ids,

        "updated_at": datetime.now(timezone.utc).isoformat(),

    }

    progress_days_completed = _count_completed_plan_days_from_start(plan_days, next_plan_progress)

    duration_days = max(int(challenge.get("duration_days") or 0), 1)

    next_status = "COMPLETED" if progress_days_completed >= duration_days else "ACTIVE"

    now = datetime.now(timezone.utc)

    update_doc = {

        "plan_progress": next_plan_progress,

        "progress_days_completed": progress_days_completed,

        "status": next_status,

        "updated_at": now,

    }

    update_operations: dict[str, dict] = {"$set": update_doc}

    if next_status == "COMPLETED":

        update_doc["completed_at"] = now

    elif membership.get("completed_at"):

        update_operations["$unset"] = {"completed_at": ""}

    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        update_operations,

    )

    if emit_progress_message and is_day_completed:

        progress_payload = {

            "completed_day": day_number,

            "total_days": duration_days,

            "membership_status": next_status,

        }

        message_document = {

            "_id": ObjectId(),

            "challenge_id": str(challenge["_id"]),

            "author_id": str(user["_id"]),

            "message_type": "progress_update",

            "content": f"Completed day {day_number}.",

            "image_url": "",

            "reply_to_message_id": None,

            "progress_payload": progress_payload,

            "created_at": now,

            "updated_at": now,

        }

        await challenge_chat_messages_collection.insert_one(message_document)

        await _broadcast_challenge_chat_event("message_created", str(challenge["_id"]), message_document)

        milestone_message = await asyncio.to_thread(
            generate_challenge_milestone_message,
            str(user.get("name") or "there"),
            str(challenge.get("title") or "your challenge"),
            day_number,
            duration_days,
            next_status,
        )
        await notify_user(
            users_collection,
            user,
            "Challenge milestone reached",
            milestone_message,
            "challenge_milestone",
            {"type": "challenge", "challengeId": str(challenge["_id"]), "day": day_number, "totalDays": duration_days, "milestone": True, "route": f"/challenges/progress/{challenge['_id']}"},
        )

    updated_membership = await challenge_memberships_collection.find_one({"_id": membership["_id"]})

    if not updated_membership:

        raise HTTPException(status_code=404, detail="Challenge membership not found")

    membership_with_points = dict(updated_membership)

    membership_with_points["challenge_points"] = max(int(challenge.get("points") or 0), 0)

    return _serialize_challenge_plan_progress_response(str(challenge["_id"]), membership_with_points, plan_days)

def _get_current_challenge_day_number(membership: dict, plan_days: list[dict], duration_days: int) -> int:

    started_at_raw = membership.get("started_at")

    if started_at_raw:

        try:

            started_at = datetime.fromisoformat(str(started_at_raw).replace("Z", "+00:00"))

            if started_at.tzinfo is None:

                started_at = started_at.replace(tzinfo=timezone.utc)

            else:

                started_at = started_at.astimezone(timezone.utc)

            today = datetime.now(timezone.utc).date()

            started_day = started_at.date()

            elapsed_days = max((today - started_day).days, 0)

            calendar_day_number = min(max(elapsed_days + 1, 1), max(duration_days, 1))

            return calendar_day_number

        except ValueError:

            pass

    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    for day in plan_days:

        day_number = max(int(day.get("day_number") or 0), 0)

        raw_day_progress = raw_progress.get(str(day_number), {}) if isinstance(raw_progress, dict) else {}

        if not bool(isinstance(raw_day_progress, dict) and raw_day_progress.get("completed")):

            return day_number

    next_day = max(int(membership.get("progress_days_completed") or 0), 0) + 1

    return min(max(next_day, 1), max(duration_days, 1))

def _get_normalized_plan_days(challenge: dict) -> list[dict]:

    return _normalize_challenge_plan_days(

        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

        duration_days=max(int(challenge.get("duration_days") or 0), 1)

    )

def _get_plan_day_or_404(plan_days: list[dict], day_number: int) -> dict:

    plan_day = next((day for day in plan_days if int(day.get("day_number") or 0) == day_number), None)

    if not plan_day:

        raise HTTPException(status_code=404, detail="Challenge plan day not found")

    return plan_day

def _get_plan_day_ids(plan_day: dict) -> tuple[list[str], list[str]]:

    valid_section_ids = [

        str(section.get("id") or "")

        for section in plan_day.get("sections") or []

        if str(section.get("id") or "")

    ]

    valid_exercise_ids = [

        str(exercise.get("id") or "")

        for section in plan_day.get("sections") or []

        for exercise in (section.get("exercises") or [])

        if str(exercise.get("id") or "")

    ]

    return valid_section_ids, valid_exercise_ids

def _get_membership_day_progress(membership: dict, day_number: int) -> dict:

    existing_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    existing_day_progress = existing_progress.get(str(day_number), {}) if isinstance(existing_progress, dict) else {}

    return existing_day_progress if isinstance(existing_day_progress, dict) else {}

def _normalize_completed_progress_ids(

    existing_day_progress: dict,

    valid_section_ids: list[str] | set[str],

    valid_exercise_ids: list[str] | set[str],

) -> tuple[list[str], list[str]]:

    allowed_section_ids = set(valid_section_ids)

    allowed_exercise_ids = set(valid_exercise_ids)

    completed_section_ids = [

        str(value)

        for value in existing_day_progress.get("completed_section_ids", [])

        if isinstance(value, str) and value in allowed_section_ids

    ]

    completed_exercise_ids = [

        str(value)

        for value in existing_day_progress.get("completed_exercise_ids", [])

        if isinstance(value, str) and value in allowed_exercise_ids

    ]

    return completed_section_ids, completed_exercise_ids

def _get_plan_section_or_404(plan_day: dict, section_id: str) -> dict:

    section_record = next(

        (section for section in (plan_day.get("sections") or []) if str(section.get("id") or "") == section_id),

        None,

    )

    if not section_record:

        raise HTTPException(status_code=404, detail="Challenge plan section not found")

    return section_record

def _get_section_exercise_ids(section_record: dict) -> list[str]:

    return [

        str(exercise.get("id") or "")

        for exercise in (section_record.get("exercises") or [])

        if str(exercise.get("id") or "")

    ]

def _resolve_plan_section_for_exercise(plan_day: dict, exercise_id: str, section_id: str | None = None) -> dict:

    for section in plan_day.get("sections") or []:

        current_section_id = str(section.get("id") or "")

        if section_id and current_section_id != section_id:

            continue

        if exercise_id in _get_section_exercise_ids(section):

            return section

    if section_id:

        raise HTTPException(status_code=404, detail="Challenge plan section not found")

    raise HTTPException(status_code=404, detail="Challenge plan exercise not found")

async def _complete_current_challenge_day(

    challenge_id: str,

    user: dict,

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    if _has_completed_challenge_day_today(membership):

        raise HTTPException(status_code=409, detail="You can only complete one challenge day per day")

    plan_days = _get_normalized_plan_days(challenge)

    duration_days = max(int(challenge.get("duration_days") or 0), 1)

    day_number = _get_current_challenge_day_number(membership, plan_days, duration_days)

    plan_day = next((day for day in plan_days if int(day.get("day_number") or 0) == day_number), None)

    if plan_day:

        existing_day_progress = _get_membership_day_progress(membership, day_number)

        valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

        completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

            existing_day_progress,

            valid_section_ids,

            valid_exercise_ids,

        )

        if valid_exercise_ids and len(completed_exercise_ids) < len(valid_exercise_ids):

            raise HTTPException(status_code=400, detail="Complete every exercise before marking the day done")

        if not valid_exercise_ids and valid_section_ids and len(completed_section_ids) < len(valid_section_ids):

            raise HTTPException(status_code=400, detail="Complete every section before marking the day done")

        return await _store_membership_plan_progress(

            challenge=challenge,

            membership=membership,

            user=user,

            day_number=day_number,

            completed_section_ids=completed_section_ids,

            completed_exercise_ids=completed_exercise_ids,

            completed=True,

            emit_progress_message=True,

        )

    current_progress = _count_completed_plan_days_from_start(

        plan_days,

        membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {},

    ) if plan_days else max(int(membership.get("progress_days_completed") or 0), 0)

    next_progress = max(current_progress, min(day_number, duration_days))

    next_status = "COMPLETED" if next_progress >= duration_days else "ACTIVE"

    now = datetime.now(timezone.utc)

    existing_plan_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    next_plan_progress = dict(existing_plan_progress)

    next_plan_progress[str(day_number)] = {

        "completed": True,

        "completed_section_ids": [],

        "completed_exercise_ids": [],

        "updated_at": now.isoformat(),

    }

    update_doc = {

        "plan_progress": next_plan_progress,

        "progress_days_completed": next_progress,

        "status": next_status,

        "updated_at": now,

    }

    update_operations: dict[str, dict] = {"$set": update_doc}

    if next_status == "COMPLETED":

        update_doc["completed_at"] = now

    elif membership.get("completed_at"):

        update_operations["$unset"] = {"completed_at": ""}

    await challenge_memberships_collection.update_one({"_id": membership["_id"]}, update_operations)

    progress_payload = {

        "completed_day": day_number,

        "total_days": duration_days,

        "membership_status": next_status,

    }

    message_document = {

        "_id": ObjectId(),

        "challenge_id": str(challenge["_id"]),

        "author_id": str(user["_id"]),

        "message_type": "progress_update",

        "content": f"Completed day {day_number}.",

        "image_url": "",

        "reply_to_message_id": None,

        "progress_payload": progress_payload,

        "created_at": now,

        "updated_at": now,

    }

    await challenge_chat_messages_collection.insert_one(message_document)

    await _broadcast_challenge_chat_event("message_created", str(challenge["_id"]), message_document)

    updated_membership = await challenge_memberships_collection.find_one({"_id": membership["_id"]})

    if not updated_membership:

        raise HTTPException(status_code=404, detail="Challenge membership not found")

    membership_with_points = dict(updated_membership)

    membership_with_points["challenge_points"] = max(int(challenge.get("points") or 0), 0)

    return _serialize_challenge_plan_progress_response(str(challenge["_id"]), membership_with_points, plan_days)

async def _complete_challenge_plan_exercise_internal(

    challenge: dict,

    membership: dict,

    user: dict,

    day_number: int,

    exercise_id: str,

    payload: ChallengePlanCompletionRequest,

    section_id: str | None = None,

) -> ChallengePlanProgressResponse:

    plan_days = _get_normalized_plan_days(challenge)

    plan_day = _get_plan_day_or_404(plan_days, day_number)

    matched_section = _resolve_plan_section_for_exercise(plan_day, exercise_id, section_id)

    resolved_section_id = str(matched_section.get("id") or "")

    section_exercise_ids = _get_section_exercise_ids(matched_section)

    valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

    existing_day_progress = _get_membership_day_progress(membership, day_number)

    completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

        existing_day_progress,

        valid_section_ids,

        valid_exercise_ids,

    )

    if payload.completed and exercise_id not in completed_exercise_ids:

        completed_exercise_ids.append(exercise_id)

    if not payload.completed:

        completed_exercise_ids = [value for value in completed_exercise_ids if value != exercise_id]

    if section_exercise_ids and all(value in completed_exercise_ids for value in section_exercise_ids):

        if resolved_section_id not in completed_section_ids:

            completed_section_ids.append(resolved_section_id)

    else:

        completed_section_ids = [value for value in completed_section_ids if value != resolved_section_id]

    prior_completed = bool(isinstance(existing_day_progress, dict) and existing_day_progress.get("completed"))

    will_complete_day = False

    if valid_section_ids:

        will_complete_day = len({value for value in completed_section_ids if value in valid_section_ids}) >= len(valid_section_ids)

    return await _store_membership_plan_progress(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        completed_section_ids=completed_section_ids,

        completed_exercise_ids=completed_exercise_ids,

        completed=will_complete_day,

        emit_progress_message=will_complete_day and not prior_completed,

    )

async def _notify_users_of_new_challenge(challenge: dict) -> None:
    challenge_id = str(challenge.get("_id") or "")
    if not challenge_id:
        return
    users = await users_collection.find({"is_admin": {"$ne": True}, "is_verified": True}).to_list(length=None)
    for user in users:
        marked = await users_collection.update_one(
            {"_id": user["_id"], "challenge_availability_notification_ids": {"$ne": challenge_id}},
            {"$addToSet": {"challenge_availability_notification_ids": challenge_id}},
        )
        if marked.modified_count:
            duration_days = max(int(challenge.get("duration_days") or 0), 0)
            await notify_user(
                users_collection,
                user,
                "New challenge available",
                f"{str(challenge.get('title') or 'A new challenge')} is ready. Start today and complete each day to keep your points.",
                "challenge_available",
                {"type": "challenge", "challengeId": challenge_id, "durationDays": duration_days, "route": f"/challenges/{challenge_id}"},
            )

GOLD_TRIAL_CONFIG_KEY = "gold_trial_config"
GOLD_TRIAL_TIER = "gold"
GOLD_TRIAL_DURATION_DAYS = 5
GOLD_TRIAL_OUTCOMES = {"converted_gold", "downgraded_silver", "lapsed"}
PHASE_ONE_BETA_SUBSCRIPTION_SOURCE = "beta_trial"
PHASE_ONE_BETA_PLAN_ID = "plan-gold-beta-21-day"

DEFAULT_GOLD_TRIAL_MESSAGES = [
    {
        "day": 0,
        "title": "Welcome to Victory Gold",
        "body": "Hi {name}, your Gold trial is active. Ask Coach Victor one question right now to get your first win.",
        "channels": ["push", "in_app", "email"],
        "video_url": "",
        "active": True,
    },
    {
        "day": 1,
        "title": "Have you set up your meal plan?",
        "body": "Have you set up your meal plan yet? Takes 2 minutes.",
        "channels": ["push", "in_app", "email"],
        "video_url": "",
        "active": True,
    },
    {
        "day": 2,
        "title": "See what Gold can do",
        "body": "Watch your mid-trial Victory Fitness video and choose one Gold feature to try today.",
        "channels": ["push", "in_app", "email", "video"],
        "video_url": "",
        "active": True,
    },
    {
        "day": 3,
        "title": "Keep your momentum going",
        "body": "{engagement_message}",
        "channels": ["push", "in_app", "email"],
        "video_url": "",
        "active": True,
    },
    {
        "day": 4,
        "title": "Your trial ends tomorrow",
        "body": "Tomorrow your trial ends. Here is what you have used so far: {usage_summary}",
        "channels": ["push", "in_app"],
        "video_url": "",
        "active": True,
    },
    {
        "day": 5,
        "title": "Your Gold trial is complete",
        "body": "Your Gold trial has ended. Compare Silver and Gold using what you actually tried, then choose your plan.",
        "channels": ["push", "in_app", "email", "video"],
        "video_url": "",
        "active": True,
    },
]

def _trial_cohort_key(value: datetime) -> str:
    return _as_utc(value).strftime("%Y-%m")

def _trial_datetime(value: object) -> datetime | None:
    return _as_utc(value) if isinstance(value, datetime) else None

def _is_phase_one_beta_enabled() -> bool:
    return bool(getattr(settings, "phase_one_beta_enabled", False))

def _phase_one_beta_duration_days() -> int:
    return max(int(getattr(settings, "phase_one_beta_duration_days", 21) or 21), 1)

def _phase_one_beta_max_users() -> int:
    return max(int(getattr(settings, "phase_one_beta_max_users", 300) or 300), 1)

def _phase_one_beta_access_codes() -> set[str]:
    return {
        str(code).strip().upper()
        for code in getattr(settings, "phase_one_beta_access_codes", []) or []
        if str(code).strip()
    }

def _trial_type_for_user(user: dict) -> str | None:
    if str(user.get("subscription_purchase_source") or "").strip() == PHASE_ONE_BETA_SUBSCRIPTION_SOURCE:
        return PHASE_ONE_BETA_SUBSCRIPTION_SOURCE
    if bool((user.get("beta_phase_one") or {}).get("is_beta_tester")):
        return PHASE_ONE_BETA_SUBSCRIPTION_SOURCE
    if str(user.get("trial_tier_granted") or "").strip().lower() == GOLD_TRIAL_TIER:
        return "gold_trial"
    return None

def _is_phase_one_beta_user(user: dict) -> bool:
    return _trial_type_for_user(user) == PHASE_ONE_BETA_SUBSCRIPTION_SOURCE

def _phase_one_beta_is_active(user: dict, now: datetime | None = None) -> bool:
    if not _is_phase_one_beta_user(user):
        return False
    started_at = _trial_started_at(user)
    ended_at = _trial_ended_at(user, started_at)
    if not started_at or not ended_at:
        return False
    current = now or datetime.now(timezone.utc)
    return started_at <= current < ended_at

def _phase_one_beta_status(user: dict, now: datetime | None = None) -> str:
    if not _is_phase_one_beta_user(user):
        return "NONE"
    return "ACTIVE" if _phase_one_beta_is_active(user, now) else "EXPIRED"

def _is_phase_one_beta_code_valid(code: str | None) -> bool:
    normalized = str(code or "").strip().upper()
    valid_codes = _phase_one_beta_access_codes()
    return bool(normalized and valid_codes and normalized in valid_codes)

async def _claim_phase_one_beta_slot(user_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    existing = await phase_one_beta_slots_collection.find_one(
        {"campaign": "phase_one_gold_beta", "claimed_by": user_id}
    )
    if existing:
        return existing

    claimed_slot = await phase_one_beta_slots_collection.find_one_and_update(
        {
            "campaign": "phase_one_gold_beta",
            "$or": [{"claimed_by": None}, {"claimed_by": {"$exists": False}}],
        },
        {
            "$set": {
                "claimed_by": user_id,
                "claimed_at": current,
                "updated_at": current,
            }
        },
        sort=[("slot_number", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if not claimed_slot:
        raise HTTPException(status_code=409, detail="Phase 1 beta enrollment capacity has been reached")
    return claimed_slot

async def _activate_phase_one_beta_subscription(user: dict, *, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    if _is_phase_one_beta_user(user):
        return user

    end_at = current + timedelta(days=_phase_one_beta_duration_days())
    feature_access = _resolve_subscription_access("GOLD")
    dashboard_plans = await _get_dashboard_subscription_plan_items()
    beta_plan = next(
        (
            _serialize_admin_subscription_plan_item(item)
            for item in dashboard_plans
            if str(item.get("id") or "").strip() == PHASE_ONE_BETA_PLAN_ID
        ),
        None,
    )
    if beta_plan and isinstance(beta_plan.get("featureAccess"), list) and beta_plan.get("featureAccess"):
        feature_access = [str(item).strip() for item in beta_plan["featureAccess"] if str(item).strip()]
    update_doc: dict[str, Any] = {
        # PHASE 1 BETA:
        # Stripe payment flow is temporarily disabled.
        # Re-enable for commercial launch after beta validation.
        "subscription_tier": "GOLD_BETA",
        "subscription_role": "GOLD_BETA",
        "subscription_status": "ACTIVE",
        "subscription_billing_cycle": "yearly",
        "subscription_is_purchased": False,
        "subscription_purchase_source": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE,
        "subscription_plan_id": PHASE_ONE_BETA_PLAN_ID,
        "subscription_price_amount": 0,
        "subscription_original_price_amount": 0,
        "subscription_discount_percentage": 100,
        "subscription_access": feature_access,
        "subscription_started_at": user.get("subscription_started_at") or current,
        "subscription_confirmed_at": current,
        "subscription": {
            "tier": "GOLD_BETA",
            "role": "GOLD_BETA",
            "status": "ACTIVE",
            "billing_cycle": "yearly",
            "is_purchased": False,
            "purchase_source": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE,
            "access": feature_access,
            "started_at": user.get("subscription_started_at") or current,
            "confirmed_at": current,
            "trial_type": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE,
            "payment_required": False,
            "payment_provider": None,
            "price": 0,
            "currency": "EUR",
            "expires_at": end_at,
        },
        "trial_tier_granted": GOLD_TRIAL_TIER,
        "trial_start_at": current,
        "trial_end_at": end_at,
        "trial_outcome": None,
        "trial_outcome_at": None,
        "trial_campaign_sent_days": [0],
        "trial_engagement": {"days": [0], "coach_messages": 0},
        "beta_phase_one": {
            "campaign": "phase_one_gold_beta",
            "trial_type": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE,
            "is_beta_tester": True,
            "price": 0,
            "currency": "EUR",
            "payment_required": False,
            "payment_provider": None,
            "started_at": current,
            "expires_at": end_at,
            "duration_days": _phase_one_beta_duration_days(),
            "enrolled_at": current,
            "status": "active",
        },
        "updated_at": current,
    }
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": update_doc,
            "$unset": {
                "phase_one_beta_requested_code": "",
            },
        },
    )
    updated_user = await users_collection.find_one({"_id": user["_id"]})
    return updated_user or {**user, **update_doc}

async def _maybe_activate_phase_one_beta_subscription(user: dict, *, requested_code: str | None = None) -> dict:
    if not _is_phase_one_beta_enabled():
        return user
    if _is_phase_one_beta_user(user):
        return user

    candidate_code = requested_code if requested_code is not None else user.get("phase_one_beta_requested_code")
    if not _is_phase_one_beta_code_valid(candidate_code):
        return user

    await _claim_phase_one_beta_slot(str(user["_id"]))
    return await _activate_phase_one_beta_subscription(user)

def _trial_started_at(user: dict) -> datetime | None:
    return _trial_datetime(user.get("trial_start_at") or user.get("subscription_started_at"))

def _trial_ended_at(user: dict, started_at: datetime | None = None) -> datetime | None:
    explicit = _trial_datetime(user.get("trial_end_at"))
    if explicit:
        return explicit
    started = started_at or _trial_started_at(user)
    if _is_phase_one_beta_user(user):
        return started + timedelta(days=_phase_one_beta_duration_days()) if started else None
    return started + timedelta(days=GOLD_TRIAL_DURATION_DAYS) if started else None

def _trial_is_active(user: dict, now: datetime | None = None) -> bool:
    if _is_phase_one_beta_user(user):
        return _phase_one_beta_is_active(user, now)
    if str(user.get("trial_tier_granted") or "").strip().lower() != GOLD_TRIAL_TIER:
        return False
    if str(user.get("trial_outcome") or "").strip() in GOLD_TRIAL_OUTCOMES:
        return False
    started_at = _trial_started_at(user)
    ended_at = _trial_ended_at(user, started_at)
    if not started_at or not ended_at:
        return False
    current = now or datetime.now(timezone.utc)
    return started_at <= current < ended_at

def _trial_usage_from_user(user: dict) -> dict[str, Any]:
    engagement = user.get("trial_engagement") if isinstance(user.get("trial_engagement"), dict) else {}
    days = sorted({int(day) for day in (engagement.get("days") or []) if str(day).lstrip("-").isdigit()})
    return {
        "ai_message_count": max(int(engagement.get("coach_messages") or 0), 0),
        "nutrition_plan_count": 1 if engagement.get("nutrition_plan_created_at") else 0,
        "meal_logged_count": max(int(engagement.get("meal_logged_count") or 0), 0),
        "challenge_count": max(int(engagement.get("challenge_count") or 0), 0),
        "engaged_days": days,
    }

def _trial_summary(user: dict, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    started_at = _trial_started_at(user)
    ended_at = _trial_ended_at(user, started_at)
    days_remaining = 0
    if ended_at and current < ended_at:
        days_remaining = max(int(((ended_at - current).total_seconds() + 86399) // 86400), 0)
    return {
        "tier_granted": str(user.get("trial_tier_granted") or "").strip() or None,
        "start_at": started_at,
        "end_at": ended_at,
        "outcome": str(user.get("trial_outcome") or "").strip() or None,
        "active": _trial_is_active(user, current),
        "days_remaining": days_remaining,
        "campaign_days_sent": sorted({int(day) for day in (user.get("trial_campaign_sent_days") or []) if str(day).lstrip("-").isdigit()}),
        "usage": _trial_usage_from_user(user),
        "trial_type": _trial_type_for_user(user),
        "is_beta_tester": _is_phase_one_beta_user(user),
    }

def _trial_outcome_for_subscription(tier: str, is_purchased: bool) -> str | None:
    normalized = _normalize_subscription_tier(tier)
    if not is_purchased or normalized == "NONE":
        return None
    if normalized == "SILVER":
        return "downgraded_silver"
    if normalized in {"GOLD", "PLATINUM", "INNER_CIRCLE"}:
        return "converted_gold"
    return None

async def _record_trial_engagement(user: dict, kind: str) -> None:
    started_at = _trial_started_at(user)
    if not started_at:
        return
    day = int((datetime.now(timezone.utc) - started_at).total_seconds() // 86400)
    max_day = _phase_one_beta_duration_days() if _is_phase_one_beta_user(user) else GOLD_TRIAL_DURATION_DAYS
    if day < 0 or day > max_day:
        return
    update: dict = {
        "$addToSet": {"trial_engagement.days": day},
    }
    if kind == "coach_message":
        update["$inc"] = {"trial_engagement.coach_messages": 1}
    elif kind == "nutrition_plan":
        update["$set"] = {"trial_engagement.nutrition_plan_created_at": datetime.now(timezone.utc)}
    await users_collection.update_one({"_id": user["_id"]}, update)

async def _get_gold_trial_config_record() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = await app_content_collection.find_one({"key": GOLD_TRIAL_CONFIG_KEY})
    if not record:
        record = {
            "key": GOLD_TRIAL_CONFIG_KEY,
            "tierLabel": "Try Gold free for 5 days",
            "trialTierGranted": GOLD_TRIAL_TIER,
            "durationDays": GOLD_TRIAL_DURATION_DAYS,
            "messages": DEFAULT_GOLD_TRIAL_MESSAGES,
            "fallbackRule": "skip_to_next_channel_and_notify_admin",
            "created_at": now,
            "updated_at": now,
        }
        await app_content_collection.update_one({"key": GOLD_TRIAL_CONFIG_KEY}, {"$setOnInsert": record}, upsert=True)
    return record

def _serialize_gold_trial_config(record: dict[str, Any]) -> dict[str, Any]:
    messages = []
    raw_messages = record.get("messages") if isinstance(record.get("messages"), list) else DEFAULT_GOLD_TRIAL_MESSAGES
    by_day: dict[int, dict[str, Any]] = {}
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        try:
            day = int(item.get("day"))
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 5:
            by_day[day] = item
    for default in DEFAULT_GOLD_TRIAL_MESSAGES:
        day = int(default["day"])
        item = {**default, **by_day.get(day, {})}
        messages.append({
            "day": day,
            "title": str(item.get("title") or default["title"]).strip(),
            "body": str(item.get("body") or default["body"]).strip(),
            "channels": [str(channel).strip() for channel in (item.get("channels") or default["channels"]) if str(channel).strip()],
            "video_url": str(item.get("video_url") or "").strip(),
            "active": bool(item.get("active", True)),
        })
    return {
        "tierLabel": str(record.get("tierLabel") or "Try Gold free for 5 days"),
        "trialTierGranted": GOLD_TRIAL_TIER,
        "durationDays": GOLD_TRIAL_DURATION_DAYS,
        "messages": messages,
        "fallbackRule": "skip_to_next_channel_and_notify_admin",
        "updatedAt": record.get("updated_at"),
    }

async def _gold_trial_decision_options(user: dict) -> list[GoldTrialDecisionOption]:
    usage = _trial_usage_from_user(user)
    plan_items = await _get_dashboard_subscription_plan_items()
    prices: dict[str, int | None] = {"SILVER": 199, "GOLD": None}
    for item in plan_items:
        tier = _normalize_subscription_plan_tier_key(item.get("tier"))
        if tier in prices:
            serialized = _serialize_app_subscription_plan_item(item)
            prices[tier] = serialized.get("discountedPriceYearly") or serialized.get("priceYearly") or prices[tier]
    return [
        GoldTrialDecisionOption(
            tier="SILVER",
            label="Silver",
            priceYearly=prices["SILVER"],
            includes=["Workouts", "Challenges", "Silver Community"],
            missing=["AI Coach", "Nutrition Planner", "AI meal-plan generation"],
            demonstratedUsage=usage,
        ),
        GoldTrialDecisionOption(
            tier="GOLD",
            label="Gold",
            priceYearly=prices["GOLD"],
            includes=["AI Coach", "Nutrition Planner", "AI meal-plan generation", "Workouts", "Challenges", "Silver Community"],
            missing=[],
            demonstratedUsage=usage,
        ),
    ]

def _trial_user_converted(user: dict) -> bool:
    tier = _normalize_subscription_tier(user.get("subscription_tier"))
    return tier != "NONE" and (bool(user.get("subscription_is_purchased")) or str(user.get("subscription_status") or "").upper() in {"ACTIVE", "PAID"})

def _decode_meal_analysis_base64(raw_value: str) -> bytes:
    normalized = str(raw_value or "").strip()
    if not normalized:
        raise ValueError("No document content was provided")
    try:
        return base64.b64decode(normalized, validate=True)
    except Exception as exc:
        raise ValueError("The uploaded file could not be decoded") from exc

def _decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.strip():
            return text
    return ""

def _extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()

def _extract_docx_text(data: bytes) -> str:
    document = DocxDocument(BytesIO(data))
    lines = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text and paragraph.text.strip()]
    return "\n".join(lines).strip()

def _extract_rtf_text(data: bytes) -> str:
    text = _decode_text_bytes(data)
    if not text:
        return ""
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()

def _extract_meal_analysis_document_text(document_base64: str, mime_type: str, file_name: str | None) -> str:
    data = _decode_meal_analysis_base64(document_base64)
    normalized_mime = str(mime_type or "").strip().lower()
    suffix = Path(str(file_name or "")).suffix.lower()

    if normalized_mime.startswith("text/") or suffix in {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".log"}:
        return _decode_text_bytes(data).strip()
    if normalized_mime == "application/rtf" or suffix == ".rtf":
        return _extract_rtf_text(data)
    if normalized_mime == "application/pdf" or suffix == ".pdf":
        return _extract_pdf_text(data)
    if normalized_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or suffix == ".docx":
        return _extract_docx_text(data)
    if normalized_mime.startswith("application/msword") or suffix == ".doc":
        raise ValueError("Legacy .doc files are not supported yet. Save the file as .docx, .pdf, or .txt and try again.")

    extracted = _decode_text_bytes(data).strip()
    if extracted:
        return extracted
    raise ValueError("This file type could not be read for meal analysis. Upload an image, txt, pdf, docx, or rtf file.")

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

async def _persist_nutrition_plan_record(user_id: str, profile_hash: str, plan_data: dict) -> None:

    try:

        existing_record = await nutrition_plans_collection.find_one(

            _standard_nutrition_filter(user_id, profile_hash),

            sort=[("created_at", -1)],

        )

        if existing_record and existing_record.get("plan"):

            logger.info(

                "nutrition_plan_background_save_skipped user_id=%s plan_id=%s",

                user_id,

                str(existing_record["_id"]),

            )

            return

        created_at = datetime.now(timezone.utc)

        insert_result = await nutrition_plans_collection.insert_one(

            {

                "user_id": user_id,

                "profile_hash": profile_hash,

                "generation_mode": STANDARD_NUTRITION_PLAN_MODE,

                "plan": plan_data,

                "created_at": created_at,

                "updated_at": created_at,

            }

        )

        logger.info(

            "nutrition_plan_background_saved user_id=%s plan_id=%s days=%s",

            user_id,

            str(insert_result.inserted_id),

            len(plan_data.get("days") or []),

        )

    except Exception as exc:  # noqa: BLE001

        logger.exception("nutrition_plan_background_save_failed user_id=%s error=%s", user_id, exc)

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

    return _upload_image_to_s3("profile-images", user_id, image_base64, mime_type, file_name)

def _upload_community_image_to_s3(

    user_id: str,

    image_base64: str,

    mime_type: str,

    file_name: str | None,

    *,

    max_size_bytes: int = COMMUNITY_IMAGE_MAX_SIZE_BYTES,

) -> str:

    return _upload_binary_to_s3(

        "community-images",

        user_id,

        image_base64,

        mime_type,

        file_name,

        allowed_types={

            "image/jpeg": ".jpg",

            "image/jpg": ".jpg",

            "image/png": ".png",

            "image/webp": ".webp",

        },

        invalid_type_message="Only JPEG, PNG, and WEBP images are supported",

        invalid_payload_message="Image payload is not valid base64",

        max_size_bytes=max_size_bytes,

        upload_log_label="image",

    )

def _upload_community_video_to_s3(

    user_id: str,

    video_base64: str,

    mime_type: str,

    file_name: str | None,

    *,

    max_size_bytes: int = COMMUNITY_VIDEO_MAX_SIZE_BYTES,

) -> str:

    return _upload_binary_to_s3(

        "community-videos",

        user_id,

        video_base64,

        mime_type,

        file_name,

        allowed_types={

            "video/mp4": ".mp4",

            "video/quicktime": ".mov",

            "video/webm": ".webm",

        },

        invalid_type_message="Only MP4, MOV, and WEBM videos are supported",

        invalid_payload_message="Video payload is not valid base64",

        max_size_bytes=max_size_bytes,

        upload_log_label="video",

    )

def _upload_workout_video_to_s3(

    user_id: str,

    video_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_video_to_s3("workout-videos", user_id, video_base64, mime_type, file_name)

def _upload_masterclass_video_to_s3(

    user_id: str,

    video_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_video_to_s3("masterclass-videos", user_id, video_base64, mime_type, file_name)

def _upload_masterclass_audio_to_s3(

    user_id: str,

    audio_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_audio_to_s3("masterclass-audio", user_id, audio_base64, mime_type, file_name)

def _upload_challenge_thumbnail_to_s3(

    user_id: str,

    image_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_image_to_s3("challenge-thumbnails", user_id, image_base64, mime_type, file_name)

def _upload_challenge_chat_image_to_s3(

    user_id: str,

    image_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_image_to_s3("challenge-chat-images", user_id, image_base64, mime_type, file_name)

def _build_inline_image_data_url(image_base64: str, mime_type: str) -> str:

    normalized_mime = str(mime_type or "image/jpeg").strip().lower() or "image/jpeg"

    return f"data:{normalized_mime};base64,{image_base64}"

def _build_local_media_url(relative_path: str) -> str:

    normalized_path = "/" + str(relative_path or "").lstrip("/")

    return normalized_path

def _store_binary_locally(

    folder_name: str,

    user_id: str,

    payload: bytes,

    extension: str,

    file_name: str | None,

) -> str:

    sanitized_file_name = re.sub(r"[^a-zA-Z0-9._-]", "-", str(file_name or "").strip()).strip("-")

    suffix = sanitized_file_name.rsplit(".", 1)[-1].lower() if "." in sanitized_file_name else ""

    if suffix and not extension.endswith(suffix):

        sanitized_file_name = ""

    object_name = sanitized_file_name or f"{uuid4().hex}{extension}"

    normalized_owner = re.sub(r"[^a-zA-Z0-9_-]", "-", str(user_id or "anonymous")).strip("-") or "anonymous"

    relative_dir = Path(folder_name) / normalized_owner

    absolute_dir = MEDIA_ROOT / relative_dir

    absolute_dir.mkdir(parents=True, exist_ok=True)

    absolute_path = absolute_dir / object_name

    absolute_path.write_bytes(payload)

    return _build_local_media_url((Path("media") / relative_dir / object_name).as_posix())

def _build_storage_object_key(

    folder_name: str,

    user_id: str,

    extension: str,

    file_name: str | None,

) -> tuple[str, str]:

    sanitized_file_name = re.sub(r"[^a-zA-Z0-9._-]", "-", str(file_name or "").strip()).strip("-")

    suffix = sanitized_file_name.rsplit(".", 1)[-1].lower() if "." in sanitized_file_name else ""

    if suffix and not extension.endswith(suffix):

        sanitized_file_name = ""

    object_name = sanitized_file_name or f"{uuid4().hex}{extension}"

    normalized_owner = re.sub(r"[^a-zA-Z0-9_-]", "-", str(user_id or "anonymous")).strip("-") or "anonymous"

    key_prefix = f"{settings.aws_s3_prefix}/{folder_name}/{normalized_owner}".strip("/")

    object_key = f"{key_prefix}/{object_name}"

    return object_key, object_name

def _store_media_bytes_to_storage(

    folder_name: str,

    user_id: str,

    payload: bytes,

    extension: str,

    file_name: str | None,

    *,

    content_type: str,

    upload_log_label: str,

) -> str:

    object_key, _ = _build_storage_object_key(folder_name, user_id, extension, file_name)

    if not s3_archive_enabled():

        return _store_binary_locally(folder_name, user_id, payload, extension, file_name)

    try:

        import boto3

    except ImportError:

        logger.warning("boto3_missing_for_%s_upload folder=%s user_id=%s", upload_log_label, folder_name, user_id)

        return _store_binary_locally(folder_name, user_id, payload, extension, file_name)

    client = boto3.client(

        "s3",

        region_name=settings.aws_region,

        aws_access_key_id=settings.aws_access_key_id,

        aws_secret_access_key=settings.aws_secret_access_key,

    )

    try:

        client.put_object(

            Bucket=settings.aws_s3_bucket,

            Key=object_key,

            Body=payload,

            ContentType=content_type,

            CacheControl="public, max-age=31536000",

        )

    except Exception as exc:  # noqa: BLE001

        logger.warning(

            "s3_%s_upload_failed folder=%s user_id=%s error=%s",

            upload_log_label,

            folder_name,

            user_id,

            exc,

        )

        return _store_binary_locally(folder_name, user_id, payload, extension, file_name)

    return f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{object_key}"

def _upload_binary_to_s3(

    folder_name: str,

    user_id: str,

    payload_base64: str,

    mime_type: str,

    file_name: str | None,

    *,

    allowed_types: dict[str, str],

    invalid_type_message: str,

    invalid_payload_message: str,

    max_size_bytes: int,

    upload_log_label: str,

) -> str:

    normalized_mime = str(mime_type or "").strip().lower()

    extension = allowed_types.get(normalized_mime)

    if extension is None:

        raise ValueError(invalid_type_message)

    try:

        payload = base64.b64decode(payload_base64, validate=True)

    except Exception as exc:  # noqa: BLE001

        raise ValueError(invalid_payload_message) from exc

    if len(payload) > max_size_bytes:

        raise ValueError(f"{upload_log_label.capitalize()} must be {max_size_bytes // (1024 * 1024)}MB or smaller")

    return _store_media_bytes_to_storage(

        folder_name,

        user_id,

        payload,

        extension,

        file_name,

        content_type=normalized_mime,

        upload_log_label=upload_log_label,

    )

def _upload_binary_bytes_to_s3(

    folder_name: str,

    user_id: str,

    payload: bytes,

    mime_type: str,

    file_name: str | None,

    *,

    allowed_types: dict[str, str],

    invalid_type_message: str,

    max_size_bytes: int,

    upload_log_label: str,

) -> str:

    normalized_mime = str(mime_type or "").strip().lower()

    extension = allowed_types.get(normalized_mime)

    if extension is None:

        raise ValueError(invalid_type_message)

    if len(payload) > max_size_bytes:

        raise ValueError(f"{upload_log_label.capitalize()} must be {max_size_bytes // (1024 * 1024)}MB or smaller")

    return _store_media_bytes_to_storage(

        folder_name,

        user_id,

        payload,

        extension,

        file_name,

        content_type=normalized_mime,

        upload_log_label=upload_log_label,

    )

def _upload_image_to_s3(

    folder_name: str,

    user_id: str,

    image_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_binary_to_s3(

        folder_name,

        user_id,

        image_base64,

        mime_type,

        file_name,

        allowed_types={

            "image/jpeg": ".jpg",

            "image/jpg": ".jpg",

            "image/png": ".png",

            "image/webp": ".webp",

        },

        invalid_type_message="Only JPEG, PNG, and WEBP images are supported",

        invalid_payload_message="Image payload is not valid base64",

        max_size_bytes=10 * 1024 * 1024,

        upload_log_label="image",

    )

def _upload_video_to_s3(

    folder_name: str,

    user_id: str,

    video_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_binary_to_s3(

        folder_name,

        user_id,

        video_base64,

        mime_type,

        file_name,

        allowed_types={

            "video/mp4": ".mp4",

            "video/quicktime": ".mov",

            "video/webm": ".webm",

        },

        invalid_type_message="Only MP4, MOV, and WEBM videos are supported",

        invalid_payload_message="Video payload is not valid base64",

        max_size_bytes=25 * 1024 * 1024,

        upload_log_label="video",

    )

def _upload_audio_to_s3(

    folder_name: str,

    user_id: str,

    audio_base64: str,

    mime_type: str,

    file_name: str | None,

) -> str:

    return _upload_binary_to_s3(

        folder_name,

        user_id,

        audio_base64,

        mime_type,

        file_name,

        allowed_types={

            "audio/mpeg": ".mp3",

            "audio/mp3": ".mp3",

            "audio/mp4": ".m4a",

            "audio/x-m4a": ".m4a",

            "audio/wav": ".wav",

            "audio/x-wav": ".wav",

            "audio/wave": ".wav",

            "audio/webm": ".webm",

            "audio/ogg": ".ogg",

            "application/ogg": ".ogg",

        },

        invalid_type_message="Only MP3, M4A, WAV, OGG, and WEBM audio files are supported",

        invalid_payload_message="Audio payload is not valid base64",

        max_size_bytes=25 * 1024 * 1024,

        upload_log_label="audio",

    )

def _create_presigned_media_upload(

    folder_name: str,

    user_id: str,

    mime_type: str,

    file_name: str | None,

    *,

    allowed_types: dict[str, str],

) -> AdminDirectUploadResponse:

    normalized_mime = str(mime_type or "").strip().lower()

    extension = allowed_types.get(normalized_mime)

    if extension is None:

        raise ValueError("Only MP4, MOV, and WEBM videos are supported")

    if not s3_archive_enabled():

        raise ValueError("Direct upload is not available because S3 storage is not configured")

    try:

        import boto3

        from botocore.config import Config

    except ImportError as exc:

        raise ValueError("Direct upload is not available because boto3 is not installed") from exc

    object_key, _ = _build_storage_object_key(folder_name, user_id, extension, file_name)

    file_url = f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{object_key}"

    client = boto3.client(

        "s3",

        region_name=settings.aws_region,

        endpoint_url=f"https://s3.{settings.aws_region}.amazonaws.com",

        aws_access_key_id=settings.aws_access_key_id,

        aws_secret_access_key=settings.aws_secret_access_key,

        config=Config(s3={"addressing_style": "virtual"}),

    )

    upload_url = client.generate_presigned_url(

        "put_object",

        Params={

            "Bucket": settings.aws_s3_bucket,

            "Key": object_key,

            "ContentType": normalized_mime,

            "CacheControl": "public, max-age=31536000",

        },

        ExpiresIn=900,

        HttpMethod="PUT",

    )

    return AdminDirectUploadResponse(

        uploadUrl=upload_url,

        fileUrl=file_url,

        headers={"Content-Type": normalized_mime, "Cache-Control": "public, max-age=31536000"},

    )

def _get_direct_upload_target(upload_type: str) -> tuple[str, dict[str, str]]:

    normalized_type = str(upload_type or "").strip().upper()

    allowed_types = {

        "video/mp4": ".mp4",

        "video/quicktime": ".mov",

        "video/webm": ".webm",

    }

    if normalized_type == "WORKOUT_VIDEO":

        return "workout-videos", allowed_types

    if normalized_type == "COMMUNITY_VIDEO":

        return "community-videos", allowed_types

    raise ValueError("Unsupported upload type")

def _delete_image_from_s3(image_url: str | None) -> None:

    normalized_url = str(image_url or "").strip()

    if not normalized_url or normalized_url.startswith("data:"):

        return

    local_media_base = _build_local_media_url("/media/")

    if normalized_url.startswith(local_media_base):

        relative_path = normalized_url.removeprefix(local_media_base).lstrip("/")

        local_path = MEDIA_ROOT / Path(relative_path)

        try:

            if local_path.exists():

                local_path.unlink()

        except Exception as exc:  # noqa: BLE001

            logger.warning("local_image_delete_failed image_url=%s error=%s", normalized_url, exc)

        return

    if not s3_archive_enabled():

        return

    parsed = urlparse(normalized_url)

    expected_host = f"{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com".lower().strip()

    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower().strip() != expected_host:

        return

    object_key = unquote(parsed.path.lstrip("/")).strip()

    if not object_key:

        return

    try:

        import boto3

    except ImportError:

        logger.warning("boto3_missing_for_image_delete image_url=%s", normalized_url)

        return

    client = boto3.client(

        "s3",

        region_name=settings.aws_region,

        aws_access_key_id=settings.aws_access_key_id,

        aws_secret_access_key=settings.aws_secret_access_key,

    )

    try:

        client.delete_object(Bucket=settings.aws_s3_bucket, Key=object_key)

    except Exception as exc:  # noqa: BLE001

        logger.warning("s3_image_delete_failed image_url=%s error=%s", normalized_url, exc)

def _normalize_external_video_url(video_url: str) -> str:

    normalized_url = str(video_url or "").strip()

    if not normalized_url:

        raise ValueError("Video link is empty")

    parsed = urlparse(normalized_url)

    scheme = parsed.scheme.lower().strip()

    host = parsed.netloc.lower().strip()

    path = parsed.path.strip()

    if scheme not in {"http", "https"} or not host:

        raise ValueError("Only valid YouTube and Vimeo links are supported")

    if host == "youtu.be":

        video_id = path.strip("/").split("/", 1)[0]

        if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id or ""):

            return f"https://www.youtube.com/embed/{video_id}?playsinline=1&rel=0"

        raise ValueError("That YouTube link is not valid")

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:

        if path.startswith("/embed/"):

            video_id = path.split("/embed/", 1)[1].split("/", 1)[0]

        elif path.startswith("/shorts/"):

            video_id = path.split("/shorts/", 1)[1].split("/", 1)[0]

        else:

            video_id = parse_qs(parsed.query).get("v", [""])[0]

        if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id or ""):

            return f"https://www.youtube.com/embed/{video_id}?playsinline=1&rel=0"

        raise ValueError("That YouTube link is not valid")

    if host == "player.vimeo.com" and path.startswith("/video/"):

        video_id = path.split("/video/", 1)[1].split("/", 1)[0]

        if video_id.isdigit():

            return f"https://player.vimeo.com/video/{video_id}?playsinline=1&title=0&byline=0&portrait=0&dnt=1"

        raise ValueError("That Vimeo link is not valid")

    if host in {"vimeo.com", "www.vimeo.com"}:

        match = re.search(r"/(\d+)(?:$|[/?#])", path + "/")

        if match:

            video_id = match.group(1)

            return f"https://player.vimeo.com/video/{video_id}?playsinline=1&title=0&byline=0&portrait=0&dnt=1"

        raise ValueError("That Vimeo link is not valid")

    raise ValueError("Only YouTube and Vimeo links are supported")

def _is_platform_video_url(video_url: str) -> bool:

    normalized_url = str(video_url or "").strip()

    if not normalized_url:

        return False

    try:

        parsed = urlparse(normalized_url)

    except Exception:  # noqa: BLE001

        return False

    host = parsed.netloc.lower().strip()

    return host in REMOTE_MEDIA_BLOCKED_HOSTS

def _is_owned_media_url(video_url: str) -> bool:

    normalized_url = str(video_url or "").strip()

    if not normalized_url:

        return False

    if normalized_url.startswith("/media/"):

        return True

    parsed = urlparse(normalized_url)

    host = parsed.netloc.lower().strip()

    expected_host = f"{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com".lower().strip()

    return bool(expected_host and host == expected_host)

def _looks_like_remote_media_url(video_url: str) -> bool:

    normalized_url = str(video_url or "").strip()

    if not normalized_url or _is_platform_video_url(normalized_url) or _is_owned_media_url(normalized_url):

        return False

    parsed = urlparse(normalized_url)

    scheme = parsed.scheme.lower().strip()

    if scheme not in {"http", "https"}:

        return False

    suffix = Path(parsed.path).suffix.lower()

    if suffix in {".mp4", ".mov", ".m4v", ".webm", ".mp3", ".m4a", ".wav", ".ogg"}:

        return True

    guessed_type = (guess_type(parsed.path)[0] or "").split(";", 1)[0].lower().strip()

    return guessed_type.startswith("video/") or guessed_type.startswith("audio/")

def _download_remote_media_to_storage(

    folder_name: str,

    user_id: str,

    media_url: str,

    *,

    upload_log_label: str,

    max_size_bytes: int = 200 * 1024 * 1024,

) -> str:

    normalized_url = str(media_url or "").strip()

    if not normalized_url:

        raise ValueError("Media link is empty")

    if _is_platform_video_url(normalized_url):

        raise ValueError("Use a direct media file URL if you want the file stored in S3")

    if _is_owned_media_url(normalized_url):

        return normalized_url

    parsed = urlparse(normalized_url)

    if parsed.scheme.lower().strip() not in {"http", "https"} or not parsed.netloc.strip():

        raise ValueError("Only direct HTTP or HTTPS media links can be stored in S3")

    path_suffix = Path(parsed.path).suffix.lower()

    guessed_mime = (guess_type(parsed.path)[0] or "").split(";", 1)[0].lower().strip()

    mime_type = guessed_mime

    extension = REMOTE_MEDIA_MIME_TO_EXTENSION.get(mime_type, "")

    if not extension and path_suffix in {".mp4", ".mov", ".m4v", ".webm", ".mp3", ".m4a", ".wav", ".ogg"}:

        extension = path_suffix

        mime_type = {

            ".mp4": "video/mp4",

            ".mov": "video/quicktime",

            ".m4v": "video/x-m4v",

            ".webm": "video/webm",

            ".mp3": "audio/mpeg",

            ".m4a": "audio/mp4",

            ".wav": "audio/wav",

            ".ogg": "audio/ogg",

        }[extension]

    if not extension:

        raise ValueError("Only direct MP4, MOV, WEBM, MP3, M4A, WAV, and OGG media links can be stored in S3")

    request = UrlRequest(normalized_url, headers={"User-Agent": "VictoryFitnessMediaBot/1.0"})

    try:

        with urlopen(request, timeout=30) as response:

            content_type_header = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower().strip()

            content_length_header = response.headers.get("Content-Length")

            if content_length_header:

                try:

                    content_length = int(content_length_header)

                except Exception:

                    content_length = None

                if content_length is not None and content_length > max_size_bytes:

                    raise ValueError(f"{upload_log_label.capitalize()} must be {max_size_bytes // (1024 * 1024)}MB or smaller")

            detected_type = content_type_header if content_type_header not in {"", "application/octet-stream", "binary/octet-stream"} else mime_type

            if not detected_type.startswith("video/") and not detected_type.startswith("audio/"):

                raise ValueError("Only direct media file URLs can be stored in S3")

            payload = response.read(max_size_bytes + 1)

    except ValueError:

        raise

    except Exception as exc:  # noqa: BLE001

        raise ValueError(f"Unable to download media from the provided URL: {exc}") from exc

    if len(payload) > max_size_bytes:

        raise ValueError(f"{upload_log_label.capitalize()} must be {max_size_bytes // (1024 * 1024)}MB or smaller")

    filename = Path(parsed.path).name or None

    return _store_media_bytes_to_storage(

        folder_name,

        user_id,

        payload,

        extension,

        filename,

        content_type=mime_type,

        upload_log_label=upload_log_label,

    )

def _resolve_media_url_to_storage(

    raw_url: str,

    *,

    folder_name: str,

    user_id: str,

    upload_log_label: str,

    allow_embed_urls: bool,

) -> str:

    normalized_url = str(raw_url or "").strip()

    if not normalized_url:

        return ""

    if _is_owned_media_url(normalized_url):

        return normalized_url

    if _looks_like_remote_media_url(normalized_url):

        return _download_remote_media_to_storage(

            folder_name,

            user_id,

            normalized_url,

            upload_log_label=upload_log_label,

        )

    if allow_embed_urls:

        return _normalize_external_video_url(normalized_url)

    raise ValueError("Use a direct media file URL if you want the file stored in S3")

def _extract_vimeo_id_from_url(video_url: str) -> str:

    normalized_url = str(video_url or "").strip()

    if not normalized_url:

        return ""

    parsed = urlparse(normalized_url)

    host = parsed.netloc.lower().strip()

    path = parsed.path.strip()

    if host == "player.vimeo.com" and path.startswith("/video/"):

        video_id = path.split("/video/", 1)[1].split("/", 1)[0]

        return video_id if video_id.isdigit() else ""

    if host in {"vimeo.com", "www.vimeo.com"}:

        match = re.search(r"/(\d+)(?:$|[/?#])", path + "/")

        return match.group(1) if match else ""

    return ""

def _normalize_workout_video_url(video_source: str, raw_video_value: str, raw_vimeo_id: str) -> tuple[str, str]:

    normalized_source = str(video_source or "VIMEO").strip().upper() or "VIMEO"

    normalized_video_value = str(raw_video_value or "").strip()

    normalized_vimeo_id = str(raw_vimeo_id or "").strip()

    if normalized_source == "UPLOAD":

        return normalized_video_value, ""

    if normalized_source == "YOUTUBE":

        normalized_url = _normalize_external_video_url(normalized_video_value)

        if "youtube.com/embed/" not in normalized_url:

            raise ValueError("Use a valid YouTube link for YouTube workouts")

        return normalized_url, ""

    if normalized_vimeo_id:

        if not normalized_vimeo_id.isdigit():

            raise ValueError("Vimeo video ID must be numeric")

        return f"https://player.vimeo.com/video/{normalized_vimeo_id}?autoplay=0&title=0&byline=0&portrait=0&playsinline=1&dnt=1", normalized_vimeo_id

    if normalized_video_value:

        normalized_url = _normalize_external_video_url(normalized_video_value)

        vimeo_id = _extract_vimeo_id_from_url(normalized_video_value) or _extract_vimeo_id_from_url(normalized_url)

        if not vimeo_id:

            raise ValueError("Use a valid Vimeo link for Vimeo workouts")

        return normalized_url, vimeo_id

    raise ValueError("A Vimeo ID or Vimeo link is required")

async def _prepare_workout_video_payload(payload: AdminWorkoutRequest, owner_key: str, user_id: str) -> tuple[str, str]:

    if payload.video_base64:

        try:

            video_url = _upload_workout_video_to_s3(

                owner_key or user_id,

                payload.video_base64,

                payload.video_mime_type,

                payload.video_file_name,

            )

        except ValueError:

            raise

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Workout video upload failed: {exc}") from exc

        return video_url, ""

    normalized_video_value = str(payload.videoUrl or "").strip()

    if normalized_video_value and _is_owned_media_url(normalized_video_value):

        return normalized_video_value, ""

    if normalized_video_value and _looks_like_remote_media_url(normalized_video_value):

        try:

            stored_url = _download_remote_media_to_storage(

                "workout-videos",

                user_id,

                normalized_video_value,

                upload_log_label="video",

            )

        except ValueError:

            raise

        return stored_url, ""

    try:

        return _normalize_workout_video_url(payload.videoSource, payload.videoUrl, payload.vimeoId)

    except ValueError:

        raise

def _normalize_masterclass_video_url(video_source: str, raw_video_value: str) -> str:

    normalized_source = str(video_source or "VIMEO").strip().upper() or "VIMEO"

    normalized_video_value = str(raw_video_value or "").strip()

    if normalized_source == "UPLOAD":

        if not normalized_video_value:

            raise ValueError("Upload a video file before saving")

        return normalized_video_value

    if not normalized_video_value:

        if normalized_source == "YOUTUBE":

            raise ValueError("A YouTube link is required")

        raise ValueError("A Vimeo link is required")

    normalized_url = _normalize_external_video_url(normalized_video_value)

    if normalized_source == "YOUTUBE":

        if "youtube.com/embed/" not in normalized_url:

            raise ValueError("Use a valid YouTube link for YouTube masterclasses")

        return normalized_url

    if "player.vimeo.com/video/" not in normalized_url:

        raise ValueError("Use a valid Vimeo link for Vimeo masterclasses")

    return normalized_url

async def _prepare_masterclass_video_payload(payload: AdminMasterclassRequest, user_id: str) -> str:

    if payload.video_base64:

        try:

            return _upload_masterclass_video_to_s3(

                user_id,

                payload.video_base64,

                payload.video_mime_type,

                payload.video_file_name,

            )

        except ValueError:

            raise

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Masterclass video upload failed: {exc}") from exc

    normalized_video_value = str(payload.videoUrl or "").strip()

    if normalized_video_value and _is_owned_media_url(normalized_video_value):

        return normalized_video_value

    if normalized_video_value and _looks_like_remote_media_url(normalized_video_value):

        try:

            return _download_remote_media_to_storage(

                "masterclass-videos",

                user_id,

                normalized_video_value,

                upload_log_label="video",

            )

        except ValueError:

            raise

    try:

        return _normalize_masterclass_video_url(payload.videoSource, payload.videoUrl)

    except ValueError:

        raise

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

async def _ensure_privacy_policy_record() -> dict:

    return await ensure_content_record(

        key=PRIVACY_POLICY_KEY,

        default_title=DEFAULT_PRIVACY_POLICY_TITLE,

        default_html_content=DEFAULT_PRIVACY_POLICY_HTML,

    )

async def _ensure_terms_condition_record() -> dict:

    return await ensure_content_record(

        key=TERMS_CONDITION_KEY,

        default_title=DEFAULT_TERMS_CONDITION_TITLE,

        default_html_content=DEFAULT_TERMS_CONDITION_HTML,

    )

async def _ensure_about_us_record() -> dict:

    return await ensure_content_record(

        key=ABOUT_US_KEY,

        default_title=DEFAULT_ABOUT_US_TITLE,

        default_html_content=DEFAULT_ABOUT_US_HTML,

    )

async def _ensure_items_record(key: str, default_items: list[dict]) -> dict:

    projection = {"_id": 0, "key": 1, "items": 1, "created_at": 1, "updated_at": 1}

    record = await app_content_collection.find_one({"key": key}, projection=projection)

    if record and isinstance(record.get("items"), list):

        return record

    now = datetime.now(timezone.utc)

    document = {

        "key": key,

        "items": [dict(item) for item in default_items],

        "created_at": now,

        "updated_at": now,

    }

    await app_content_collection.update_one(

        {"key": key},

        {"$setOnInsert": document},

        upsert=True,

    )

    saved = await app_content_collection.find_one({"key": key}, projection=projection)

    return saved or document

async def _replace_items_record(key: str, items: list[dict]) -> dict:

    now = datetime.now(timezone.utc)

    await app_content_collection.update_one(

        {"key": key},

        {

            "$set": {

                "key": key,

                "items": [dict(item) for item in items],

                "updated_at": now,

            },

            "$setOnInsert": {"created_at": now},

        },

        upsert=True,

    )

    return await _ensure_items_record(key, items)

async def _get_dashboard_faq_items() -> list[dict]:

    record = await _ensure_items_record(DASHBOARD_FAQS_KEY, DEFAULT_DASHBOARD_FAQS)

    return [dict(item) for item in record.get("items") or [] if isinstance(item, dict)]

async def _get_dashboard_notification_items() -> list[dict]:

    record = await _ensure_items_record(DASHBOARD_NOTIFICATIONS_KEY, DEFAULT_DASHBOARD_NOTIFICATIONS)

    return [dict(item) for item in record.get("items") or [] if isinstance(item, dict)]

async def _get_dashboard_subscription_plan_items() -> list[dict]:

    record = await _ensure_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, DEFAULT_DASHBOARD_SUBSCRIPTION_PLANS)
    items = [dict(item) for item in record.get("items") or [] if isinstance(item, dict)]
    beta_plan_id = "plan-gold-beta-21-day"
    if not any(str(item.get("id") or "").strip() == beta_plan_id for item in items):
        beta_plan = next(
            (dict(item) for item in DEFAULT_DASHBOARD_SUBSCRIPTION_PLANS if str(item.get("id") or "").strip() == beta_plan_id),
            None,
        )
        if beta_plan:
            insert_index = next(
                (index + 1 for index, item in enumerate(items) if str(item.get("id") or "").strip() == "plan-gold"),
                len(items),
            )
            items.insert(insert_index, beta_plan)
            await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, items)

    return items

async def _get_dashboard_masterclass_items() -> list[dict]:

    record = await _ensure_items_record(DASHBOARD_MASTERCLASSES_KEY, DEFAULT_DASHBOARD_MASTERCLASSES)

    return [dict(item) for item in record.get("items") or [] if isinstance(item, dict)]

async def _get_dashboard_onboarding_items() -> list[dict]:

    record = await _ensure_items_record(DASHBOARD_ONBOARDING_KEY, DEFAULT_DASHBOARD_ONBOARDING)

    return [dict(item) for item in record.get("items") or [] if isinstance(item, dict)]

def _serialize_faq_item(item: dict) -> dict:

    return {

        "id": str(item.get("id") or uuid4().hex),

        "question": str(item.get("question") or "").strip(),

        "answer": str(item.get("answer") or "").strip(),

    }

def _serialize_admin_notification_item(item: dict) -> dict:

    created_at = item.get("createdAt") or item.get("created_at") or datetime.now(timezone.utc)

    if isinstance(created_at, str):

        try:

            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        except ValueError:

            created_at = datetime.now(timezone.utc)

    return {

        "id": str(item.get("id") or uuid4().hex),

        "title": str(item.get("title") or "").strip(),

        "message": str(item.get("message") or "").strip(),

        "read": bool(item.get("read", False)),

        "createdAt": _as_utc(created_at),

    }

def _coerce_optional_datetime(value: object) -> datetime | None:

    if isinstance(value, datetime):

        return _as_utc(value)

    if isinstance(value, str) and value.strip():

        try:

            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))

        except ValueError:

            return None

    return None

def _normalize_subscription_discount_fields(item: dict) -> tuple[int | None, datetime | None, datetime | None]:

    raw_percentage = item.get("discountPercentage")

    percentage = None

    try:

        if raw_percentage is not None and str(raw_percentage).strip() != "":

            percentage = max(0, min(int(raw_percentage), 100))

    except (TypeError, ValueError):

        percentage = None

    start_date = _coerce_optional_datetime(item.get("discountStartDate") or item.get("discount_start_date"))

    end_date = _coerce_optional_datetime(item.get("discountEndDate") or item.get("discount_end_date"))

    if percentage is not None and percentage <= 0:

        percentage = None

    return percentage, start_date, end_date

def _is_subscription_discount_active(

    percentage: int | None,

    start_date: datetime | None,

    end_date: datetime | None,

    now: datetime | None = None,

) -> bool:

    if percentage is None:

        return False

    current_time = _as_utc(now or datetime.now(timezone.utc))

    if start_date and current_time < _as_utc(start_date):

        return False

    if end_date and current_time > _as_utc(end_date):

        return False

    return True

def _calculate_discounted_price(price: int | None, percentage: int | None, active: bool) -> int | None:

    if price is None:

        return None

    if not active or percentage is None:

        return price

    return max(int(round(price * (100 - percentage) / 100)), 0)

def _normalize_subscription_plan_tier_key(value: object) -> str:

    normalized = str(value or "").strip().upper().replace(" ", "_")

    if "INNER" in normalized and "CIRCLE" in normalized:

        return "INNER_CIRCLE"

    if "PLATINUM" in normalized:

        return "PLATINUM"

    if "GOLD" in normalized:

        return "GOLD"

    if "SILVER" in normalized:

        return "SILVER"

    return normalized

def _normalize_plan_feature_access(item: dict) -> list[str]:

    tier = _normalize_subscription_plan_tier_key(item.get("tier"))

    features = item.get("featureAccess") or item.get("feature_access")

    if not isinstance(features, list) or not features:

        return _resolve_subscription_access(tier)

    return dependency_normalize_subscription_feature_access(features)

def _find_invalid_plan_feature_access(item: dict) -> list[str]:

    features = item.get("featureAccess") or item.get("feature_access")

    return dependency_find_invalid_subscription_features(features)

def _get_subscription_feature_catalog() -> list[dict[str, object]]:

    return dependency_list_subscription_feature_catalog()

def _serialize_admin_subscription_plan_item(item: dict) -> dict:

    discount_percentage, discount_start_date, discount_end_date = _normalize_subscription_discount_fields(item)

    return {

        "id": str(item.get("id") or uuid4().hex),

        "tier": str(item.get("tier") or "").strip(),

        "description": str(item.get("description") or "").strip(),

        "priceMonthly": item.get("priceMonthly"),

        "priceYearly": item.get("priceYearly"),

        "discountPercentage": discount_percentage,

        "discountStartDate": discount_start_date,

        "discountEndDate": discount_end_date,

        "isApplicationOnly": bool(item.get("isApplicationOnly", False)),

        "isMostPopular": bool(item.get("isMostPopular", False)),

        "iconType": str(item.get("iconType") or "").strip(),

        "features": [

            str(feature).strip()

            for feature in item.get("features") or []

            if str(feature).strip()

        ],

        "featureAccess": _normalize_plan_feature_access(item),

    }

def _serialize_app_subscription_plan_item(item: dict, now: datetime | None = None) -> dict:

    normalized = _serialize_admin_subscription_plan_item(item)
    plan_id = str(normalized.get("id") or "").strip()
    subscription_tier = "GOLD_BETA" if plan_id == "plan-gold-beta-21-day" else _normalize_subscription_plan_tier_key(normalized["tier"])

    discount_active = _is_subscription_discount_active(

        normalized.get("discountPercentage"),

        normalized.get("discountStartDate"),

        normalized.get("discountEndDate"),

        now,

    )

    price_monthly = normalized.get("priceMonthly")

    price_yearly = normalized.get("priceYearly")

    return {

        "id": normalized["id"],

        "subscriptionTier": subscription_tier,

        "title": normalized["tier"],

        "description": normalized["description"],

        "priceMonthly": price_monthly,

        "priceYearly": price_yearly,

        "discountedPriceMonthly": _calculate_discounted_price(price_monthly, normalized.get("discountPercentage"), discount_active),

        "discountedPriceYearly": _calculate_discounted_price(price_yearly, normalized.get("discountPercentage"), discount_active),

        "discountPercentage": normalized.get("discountPercentage"),

        "discountStartDate": normalized.get("discountStartDate"),

        "discountEndDate": normalized.get("discountEndDate"),

        "isDiscountActive": discount_active,

        "isApplicationOnly": normalized["isApplicationOnly"],

        "isMostPopular": normalized["isMostPopular"],

        "iconType": normalized["iconType"],

        "features": normalized["features"],

        "featureAccess": normalized["featureAccess"],

    }

def _serialize_admin_masterclass_item(item: dict) -> dict:

    thumbnail_url = str(item.get("thumbnailUrl") or item.get("thumbnail") or "").strip()

    return {

        "id": str(item.get("id") or uuid4().hex),

        "title": str(item.get("title") or "").strip(),

        "category": str(item.get("category") or "").strip(),

        "duration": str(item.get("duration") or "").strip(),

        "description": str(item.get("description") or "").strip(),

        "videoUrl": str(item.get("videoUrl") or "").strip(),

        "videoSource": str(item.get("videoSource") or "VIMEO").strip().upper() or "VIMEO",

        "audioUrl": str(item.get("audioUrl") or "").strip(),

        "educationalContent": str(item.get("educationalContent") or "").strip(),

        "thumbnailUrl": thumbnail_url,

    }

async def _build_admin_user_summary_response(year: int | None = None) -> AdminUserSummaryResponse:
    selected_year = year or datetime.now(timezone.utc).year
    year_start = datetime(selected_year, 1, 1, tzinfo=timezone.utc)
    next_year_start = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)
    base_filter = {"is_admin": {"$ne": True}}
    active_filter = {
        "$or": [
            {"is_verified": True},
            {"status": {"$regex": "^active$", "$options": "i"}},
        ]
    }
    total_users, active_users, yearly_users = await asyncio.gather(
        users_collection.count_documents(base_filter),
        users_collection.count_documents({"$and": [base_filter, active_filter]}),
        users_collection.find(
            {**base_filter, "created_at": {"$gte": year_start, "$lt": next_year_start}},
            projection={"created_at": 1, "is_verified": 1, "status": 1},
        ).to_list(length=None),
    )
    pending_users = max(total_users - active_users, 0)
    monthly = {month: {"userCount": 0, "activeUserCount": 0} for month in month_abbr[1:]}
    for record in yearly_users:
        created_at = record.get("created_at")
        if not isinstance(created_at, datetime):
            continue
        month = month_abbr[_as_utc(created_at).month]
        monthly[month]["userCount"] += 1
        if bool(record.get("is_verified")) or _normalize_admin_user_status(record) == "ACTIVE":
            monthly[month]["activeUserCount"] += 1
    return AdminUserSummaryResponse(
        totalUsers=total_users,
        activeUsers=active_users,
        pendingUsers=pending_users,
        userChart=[AdminUserChartPoint(month=month, **values) for month, values in monthly.items()],
    )

async def _build_admin_user_list_response(
    page: int = 1,
    limit: int = 10,
    query: str | None = None,
) -> AdminUserListResponse:
    normalized_page = max(int(page or 1), 1)
    normalized_limit = max(min(int(limit or 10), 100), 1)
    filter_doc: dict = {"is_admin": {"$ne": True}}
    search = (query or "").strip()
    if search:
        escaped = re.escape(search)
        filter_doc["$or"] = [
            {"name": {"$regex": escaped, "$options": "i"}},
            {"email": {"$regex": escaped, "$options": "i"}},
            {"country": {"$regex": escaped, "$options": "i"}},
            {"contact_number": {"$regex": escaped, "$options": "i"}},
            {"role": {"$regex": escaped, "$options": "i"}},
            {"status": {"$regex": escaped, "$options": "i"}},
        ]
    skip = (normalized_page - 1) * normalized_limit
    total, records = await asyncio.gather(
        users_collection.count_documents(filter_doc),
        users_collection.find(filter_doc, sort=[("created_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(normalized_limit)
        .to_list(length=normalized_limit),
    )
    return AdminUserListResponse(
        total=total,
        page=normalized_page,
        limit=normalized_limit,
        users=[AdminUserListItem(**_serialize_admin_user_record(record)) for record in records],
    )

def _serialize_admin_workout_record(record: dict) -> dict:
    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))
    updated_at = _as_utc(record.get("updated_at") or created_at)
    video_source = str(record.get("video_source") or "VIMEO").strip().upper() or "VIMEO"
    return {
        "id": str(record.get("_id") or ""),
        "title": str(record.get("title") or "").strip(),
        "vimeoId": str(record.get("vimeo_id") or "").strip(),
        "videoUrl": str(record.get("video_url") or "").strip(),
        "videoSource": video_source,
        "tag": str(record.get("tag") or "").strip(),
        "visibility": str(record.get("visibility") or "Published").strip(),
        "providerVisibility": str(record.get("provider_visibility") or record.get("visibility") or "Published").strip(),
        "thumbnail": str(record.get("thumbnail") or record.get("thumbnail_url") or "").strip(),
        "dateAdded": created_at,
        "updatedAt": updated_at,
    }

async def _load_challenge_stats_map(challenge_ids: list[str]) -> dict[str, dict[str, int]]:
    stats = {challenge_id: {"participantCount": 0, "completionCount": 0} for challenge_id in challenge_ids}
    if not challenge_ids:
        return stats
    pipeline = [
        {"$match": {"challenge_id": {"$in": challenge_ids}}},
        {
            "$group": {
                "_id": "$challenge_id",
                "participantCount": {
                    "$sum": {"$cond": [{"$in": ["$status", ["ACTIVE", "COMPLETED"]]}, 1, 0]}
                },
                "completionCount": {"$sum": {"$cond": [{"$eq": ["$status", "COMPLETED"]}, 1, 0]}},
            }
        },
    ]
    async for row in challenge_memberships_collection.aggregate(pipeline):
        challenge_id = str(row.get("_id") or "")
        if challenge_id:
            stats[challenge_id] = {
                "participantCount": int(row.get("participantCount") or 0),
                "completionCount": int(row.get("completionCount") or 0),
            }
    return stats

def _normalize_challenge_plan_days(value: object, duration_days: int | None = None) -> list[dict]:
    normalized_days: list[dict] = []
    if not isinstance(value, list):
        value = []
    for index, raw_day in enumerate(value, start=1):
        if isinstance(raw_day, ChallengePlanDay):
            raw_day = raw_day.model_dump()
        if not isinstance(raw_day, dict):
            continue
        try:
            day_number = int(raw_day.get("day_number") or raw_day.get("dayNumber") or raw_day.get("day") or index)
        except (TypeError, ValueError):
            day_number = index
        sections: list[dict] = []
        for section_index, raw_section in enumerate(raw_day.get("sections") or [], start=1):
            if isinstance(raw_section, ChallengePlanSection):
                raw_section = raw_section.model_dump()
            if not isinstance(raw_section, dict):
                continue
            exercises: list[dict] = []
            for exercise_index, raw_exercise in enumerate(raw_section.get("exercises") or [], start=1):
                if isinstance(raw_exercise, ChallengePlanExercise):
                    raw_exercise = raw_exercise.model_dump()
                if not isinstance(raw_exercise, dict):
                    continue
                exercise_id = str(raw_exercise.get("id") or f"day-{day_number}-exercise-{exercise_index}")
                exercises.append(
                    {
                        "id": exercise_id[:80],
                        "name": str(raw_exercise.get("name") or f"Exercise {exercise_index}").strip()[:160],
                        "details": str(raw_exercise.get("details") or raw_exercise.get("description") or "Complete this exercise.").strip()[:240],
                        "notes": str(raw_exercise.get("notes") or "").strip()[:400],
                        "workout_id": str(raw_exercise.get("workout_id") or raw_exercise.get("workoutId") or "").strip()[:80],
                        "workout_title": str(raw_exercise.get("workout_title") or raw_exercise.get("workoutTitle") or "").strip()[:160],
                        "workout_vimeo_id": str(raw_exercise.get("workout_vimeo_id") or raw_exercise.get("workoutVimeoId") or "").strip()[:80],
                        "workout_video_url": str(raw_exercise.get("workout_video_url") or raw_exercise.get("workoutVideoUrl") or "").strip()[:2000],
                        "workout_video_source": str(raw_exercise.get("workout_video_source") or raw_exercise.get("workoutVideoSource") or "VIMEO").strip().upper()[:20],
                        "workout_thumbnail": str(raw_exercise.get("workout_thumbnail") or raw_exercise.get("workoutThumbnail") or "").strip(),
                    }
                )
            section_id = str(raw_section.get("id") or f"day-{day_number}-section-{section_index}")
            sections.append(
                {
                    "id": section_id[:80],
                    "title": str(raw_section.get("title") or f"Section {section_index}").strip()[:160],
                    "description": str(raw_section.get("description") or "").strip()[:400],
                    "estimated_minutes": max(0, min(int(raw_section.get("estimated_minutes") or raw_section.get("estimatedMinutes") or 10), 240)),
                    "exercises": exercises,
                }
            )
        normalized_days.append(
            {
                "day_number": max(1, min(day_number, 365)),
                "title": str(raw_day.get("title") or f"Day {day_number}").strip()[:160],
                "focus": str(raw_day.get("focus") or raw_day.get("title") or "Training").strip()[:200],
                "notes": str(raw_day.get("notes") or "").strip()[:1200],
                "sections": sections,
            }
        )
    if not normalized_days:
        return []

    if duration_days is None or len(normalized_days) >= duration_days:
        return normalized_days

    for day_number in range(len(normalized_days) + 1, max(duration_days, 0) + 1):
        normalized_days.append(
            {
                "day_number": max(1, min(day_number, 365)),
                "title": f"Day {day_number}",
                "focus": "Training",
                "notes": "",
                "sections": [],
            }
        )

    return normalized_days

def _extract_plan_day_numbers(plan_days: list[dict]) -> list[int]:
    numbers: list[int] = []
    for day in plan_days:
        if not isinstance(day, dict):
            continue
        try:
            numbers.append(int(day.get("day_number") or day.get("dayNumber") or day.get("day") or 0))
        except (TypeError, ValueError):
            continue
    return [number for number in numbers if number > 0]

def _build_challenge_plan_text(plan_days: list[dict]) -> str:
    lines: list[str] = []
    for day in plan_days:
        if not isinstance(day, dict):
            continue
        day_number = day.get("day_number") or day.get("dayNumber") or ""
        title = str(day.get("title") or "").strip()
        focus = str(day.get("focus") or "").strip()
        lines.append(f"Day {day_number}: {title}".strip())
        if focus:
            lines.append(f"Focus: {focus}")
        notes = str(day.get("notes") or "").strip()
        if notes:
            lines.append(notes)
    return "\n".join(line for line in lines if line).strip()

def _normalize_challenge_thumbnail(value: object) -> str:
    return str(value or "").strip()

def _coerce_utc_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None

def _challenge_difficulty_color(value: object) -> str:
    difficulty = str(value or "").strip().upper()
    if difficulty == "ADVANCED":
        return "#F97316"
    if difficulty == "INTERMEDIATE":
        return "#F59E0B"
    return "#22C55E"

async def _build_challenge_overview_response(user: dict) -> ChallengeOverviewResponse:
    user_id = str(user.get("_id") or "")
    memberships = await challenge_memberships_collection.find({"user_id": user_id}).to_list(length=None)

    latest_membership_by_challenge: dict[str, dict] = {}
    for membership in memberships:
        challenge_id = str(membership.get("challenge_id") or "").strip()
        if not challenge_id:
            continue
        current = latest_membership_by_challenge.get(challenge_id)
        current_updated = _coerce_utc_datetime((current or {}).get("updated_at")) if current else None
        next_updated = _coerce_utc_datetime(membership.get("updated_at"))
        if current is None or (next_updated and (current_updated is None or next_updated >= current_updated)):
            latest_membership_by_challenge[challenge_id] = membership

    active_memberships = [
        membership for membership in latest_membership_by_challenge.values()
        if str(membership.get("status") or "").strip().upper() == "ACTIVE"
    ]
    completed_memberships = [
        membership for membership in latest_membership_by_challenge.values()
        if str(membership.get("status") or "").strip().upper() == "COMPLETED"
    ]

    membership_challenge_ids = list(latest_membership_by_challenge.keys())
    challenge_object_ids = [ObjectId(challenge_id) for challenge_id in membership_challenge_ids if ObjectId.is_valid(challenge_id)]
    membership_challenges = await challenges_collection.find({"_id": {"$in": challenge_object_ids}}).to_list(length=len(challenge_object_ids))

    ready_challenge_records = await challenges_collection.find(
        {"status": "ACTIVE"},
        sort=[("created_at", -1), ("_id", -1)],
    ).to_list(length=200)

    challenge_map = {str(record.get("_id") or ""): record for record in [*membership_challenges, *ready_challenge_records]}
    stats_map = await _load_challenge_stats_map(list(challenge_map.keys()))
    active_limit = _get_user_active_challenge_limit(user)
    active_membership_count = len(active_memberships)

    active_chats: list[ChallengeChatSummaryResponse] = []
    for membership in active_memberships:
        challenge_id = str(membership.get("challenge_id") or "")
        challenge = challenge_map.get(challenge_id)
        if not challenge:
            continue
        last_message = await challenge_chat_messages_collection.find_one(
            {"challenge_id": challenge_id},
            sort=[("created_at", -1), ("_id", -1)],
        )
        last_read_at = _coerce_utc_datetime(membership.get("last_read_message_at"))
        unread_filter: dict[str, object] = {"challenge_id": challenge_id}
        if last_read_at is not None:
            unread_filter["created_at"] = {"$gt": last_read_at}
        unread_count = await challenge_chat_messages_collection.count_documents(unread_filter)
        active_chats.append(
            ChallengeChatSummaryResponse(
                id=challenge_id,
                challenge_id=challenge_id,
                name=str(challenge.get("title") or "Challenge"),
                last_message=str((last_message or {}).get("content") or ""),
                last_message_at=(last_message or {}).get("created_at"),
                unread_count=max(int(unread_count or 0), 0),
                avatar=_normalize_challenge_thumbnail(challenge.get("thumbnail")),
            )
        )

    active_challenges: list[UserActiveChallengeResponse] = []
    for membership in active_memberships:
        challenge_id = str(membership.get("challenge_id") or "")
        challenge = challenge_map.get(challenge_id)
        if not challenge:
            continue
        duration_days = max(int(challenge.get("duration_days") or 0), 1)
        completed_days = max(int(membership.get("progress_days_completed") or 0), 0)
        progress = min(completed_days / duration_days, 1.0)
        days_left = max(duration_days - completed_days, 0)
        active_challenges.append(
            UserActiveChallengeResponse(
                id=str(membership.get("_id") or challenge_id),
                challenge_id=challenge_id,
                title=str(challenge.get("title") or ""),
                description=str(challenge.get("description") or ""),
                why_it_matters=str(challenge.get("why_it_matters") or ""),
                type=str(challenge.get("category") or "Challenge"),
                plan_text=str(challenge.get("plan_text") or ""),
                duration_days=duration_days,
                days_left=days_left,
                total_days=duration_days,
                progress=progress,
                points=max(int(challenge.get("points") or 0), 0),
                participants=int((stats_map.get(challenge_id) or {}).get("participantCount") or 0),
                thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),
                color="#4F8EF7",
                created_at=challenge.get("created_at"),
            )
        )

    completed_challenges: list[UserCompletedChallengeResponse] = []
    for membership in completed_memberships:
        challenge_id = str(membership.get("challenge_id") or "")
        challenge = challenge_map.get(challenge_id)
        if not challenge:
            continue
        challenge_points = max(int(challenge.get("points") or 0), 0)
        completed_at = _coerce_utc_datetime(membership.get("completed_at")) or _coerce_utc_datetime(membership.get("updated_at")) or datetime.now(timezone.utc)
        completed_challenges.append(
            UserCompletedChallengeResponse(
                id=str(membership.get("_id") or challenge_id),
                challenge_id=challenge_id,
                title=str(challenge.get("title") or ""),
                description=str(challenge.get("description") or ""),
                why_it_matters=str(challenge.get("why_it_matters") or ""),
                duration_days=max(int(challenge.get("duration_days") or 0), 0),
                type=str(challenge.get("category") or "Challenge"),
                earned_points=challenge_points,
                participants=int((stats_map.get(challenge_id) or {}).get("participantCount") or 0),
                thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),
                completed_at=completed_at,
                color="#22C55E",
                created_at=challenge.get("created_at"),
            )
        )

    ready_to_start: list[UserReadyChallengeResponse] = []
    for challenge in ready_challenge_records:
        challenge_id = str(challenge.get("_id") or "")
        membership = latest_membership_by_challenge.get(challenge_id)
        membership_status = str((membership or {}).get("status") or "").strip().upper()
        if membership_status in {"ACTIVE", "COMPLETED"}:
            continue
        can_start = active_limit is None or active_membership_count < active_limit
        ready_to_start.append(
            UserReadyChallengeResponse(
                id=challenge_id,
                title=str(challenge.get("title") or ""),
                description=str(challenge.get("description") or ""),
                why_it_matters=str(challenge.get("why_it_matters") or ""),
                plan_text=str(challenge.get("plan_text") or ""),
                duration_days=max(int(challenge.get("duration_days") or 0), 0),
                type=str(challenge.get("category") or "Challenge"),
                points=max(int(challenge.get("points") or 0), 0),
                participants=int((stats_map.get(challenge_id) or {}).get("participantCount") or 0),
                difficulty=str(challenge.get("difficulty") or "BEGINNER"),
                difficulty_color=_challenge_difficulty_color(challenge.get("difficulty")),
                status=str(challenge.get("status") or "ACTIVE"),
                can_start=can_start,
                thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),
                created_at=challenge.get("created_at"),
            )
        )

    active_chats.sort(key=lambda item: item.last_message_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    active_challenges.sort(key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    completed_challenges.sort(key=lambda item: item.completed_at, reverse=True)
    ready_to_start.sort(key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    return ChallengeOverviewResponse(
        active_chats=active_chats,
        active_challenges=active_challenges,
        completed_challenges=completed_challenges,
        ready_to_start=ready_to_start,
    )

async def _sync_workout_library_from_challenge_plan(plan_days: list[dict], category: str) -> None:
    return None

def _serialize_admin_challenge_record(record: dict, stats: dict[str, dict[str, int]] | None = None) -> dict:
    challenge_id = str(record.get("_id") or "")
    challenge_stats = (stats or {}).get(challenge_id, {})
    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))
    updated_at = _as_utc(record.get("updated_at") or created_at)
    return {
        "id": challenge_id,
        "title": str(record.get("title") or "").strip(),
        "description": str(record.get("description") or "").strip(),
        "whyItMatters": str(record.get("why_it_matters") or record.get("whyItMatters") or "").strip(),
        "planText": str(record.get("plan_text") or record.get("planText") or "").strip(),
        "planDays": _normalize_challenge_plan_days(record.get("plan_days") or record.get("planDays") or []),
        "category": str(record.get("category") or "").strip(),
        "durationDays": int(record.get("duration_days") or record.get("durationDays") or 0),
        "points": int(record.get("points") or 0),
        "difficulty": str(record.get("difficulty") or "BEGINNER").strip().upper(),
        "status": str(record.get("status") or "DRAFT").strip().upper(),
        "thumbnail": str(record.get("thumbnail") or "").strip(),
        "participantCount": int(challenge_stats.get("participantCount") or 0),
        "completionCount": int(challenge_stats.get("completionCount") or 0),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }

HOMEPAGE_QUOTES_KEY = "homepage_quotes"
DEFAULT_HOMEPAGE_QUOTES = [
    {
        "id": "homepage-quote-default",
        "text": "Every rep is a vote for the person you are becoming.",
        "author": "Victory Fitness",
        "active": True,
    }
]

async def _load_homepage_quotes() -> list[dict]:
    record = await _ensure_items_record(HOMEPAGE_QUOTES_KEY, DEFAULT_HOMEPAGE_QUOTES)
    return [_serialize_homepage_quote_item(item) for item in record.get("items") or [] if isinstance(item, dict)]

async def _save_homepage_quotes(items: list[dict]) -> None:
    await _replace_items_record(HOMEPAGE_QUOTES_KEY, [_serialize_homepage_quote_item(item) for item in items])

def _serialize_homepage_quote_item(item: dict) -> dict:
    return {
        "id": str(item.get("id") or uuid4().hex),
        "text": str(item.get("text") or "").strip(),
        "author": str(item.get("author") or "").strip() or "Victory Fitness",
        "active": bool(item.get("active", True)),
    }

def _serialize_admin_subscriber_record(record: dict) -> dict:

    subscription = _build_subscription_summary(record)

    return {

        "id": str(record.get("_id")),

        "fullName": str(record.get("name") or "").strip() or "Unnamed User",

        "email": str(record.get("email") or "").strip(),

        "subscriptionTier": subscription["tier"],

        "contactNumber": str(record.get("contact_number") or "").strip(),

        "country": str(record.get("country") or "").strip(),

        "status": subscription["status"],

        "joinedDate": _as_utc(record.get("created_at") or datetime.now(timezone.utc)),

        "profileImage": str(record.get("profile_image") or "").strip(),

        "subscriptionRole": subscription["role"],

        "subscriptionBillingCycle": subscription["billing_cycle"],

        "subscriptionStartedAt": _as_utc(subscription["started_at"]) if isinstance(subscription.get("started_at"), datetime) else None,

        "subscriptionConfirmedAt": _as_utc(subscription["confirmed_at"]) if isinstance(subscription.get("confirmed_at"), datetime) else None,

        "subscriptionIsPurchased": bool(subscription["is_purchased"]),

        "subscriptionAccess": list(subscription["access"] or []),

    }

def _serialize_privacy_policy_record(record: dict) -> PrivacyPolicyResponse:

    return shared_serialize_privacy_policy_record(

        record,

        key=PRIVACY_POLICY_KEY,

        default_title=DEFAULT_PRIVACY_POLICY_TITLE,

    )

def _serialize_terms_condition_record(record: dict) -> TermsConditionResponse:

    return shared_serialize_terms_condition_record(

        record,

        key=TERMS_CONDITION_KEY,

        default_title=DEFAULT_TERMS_CONDITION_TITLE,

    )

def _serialize_about_us_record(record: dict) -> AboutUsResponse:

    return shared_serialize_about_us_record(

        record,

        key=ABOUT_US_KEY,

        default_title=DEFAULT_ABOUT_US_TITLE,

    )

def _serialize_coaching_application_record(record: dict) -> CoachingApplicationResponse:

    first_name = str(record.get("first_name") or "").strip()

    last_name = str(record.get("last_name") or "").strip()

    return CoachingApplicationResponse(

        id=str(record.get("_id")),

        user_id=str(record.get("user_id") or ""),

        first_name=first_name,

        last_name=last_name,

        full_name=f"{first_name} {last_name}".strip(),

        email=str(record.get("email") or ""),

        phone_number=str(record.get("phone_number") or ""),

        goal=str(record.get("goal") or ""),

        obstacle=str(record.get("obstacle") or ""),

        investment=str(record.get("investment") or ""),

        commitment=str(record.get("commitment") or ""),

        injury=str(record.get("injury") or ""),

        additional_notes=str(record.get("additional_notes") or ""),

        agreement_accepted=bool(record.get("agreement_accepted", True)),

        status=str(record.get("status") or "NEW"),

        admin_notes=str(record.get("admin_notes") or ""),

        created_at=_as_utc(record.get("created_at") or datetime.now(timezone.utc)),

        updated_at=_as_utc(record.get("updated_at") or record.get("created_at") or datetime.now(timezone.utc)),

    )

def _serialize_support_message_record(record: dict) -> SupportMessageResponse:

    return SupportMessageResponse(

        id=str(record.get("_id")),

        user_id=str(record.get("user_id") or ""),

        user_name=str(record.get("user_name") or "Member"),

        user_email=str(record.get("user_email") or ""),

        subject=str(record.get("subject") or ""),

        message=str(record.get("message") or ""),

        status=str(record.get("status") or "OPEN"),

        admin_notes=str(record.get("admin_notes") or ""),

        created_at=_as_utc(record.get("created_at") or datetime.now(timezone.utc)),

        updated_at=_as_utc(record.get("updated_at") or record.get("created_at") or datetime.now(timezone.utc)),

    )

def _get_allowed_community_audiences(user: dict) -> list[str]:

    if bool(user.get("is_admin")):

        return ["ALL", "SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"]

    membership = _normalize_subscription_tier(user.get("subscription_tier") or user.get("tier"))

    hierarchy = {

        "SILVER": ["ALL", "SILVER"],

        "GOLD": ["ALL", "SILVER", "GOLD"],

        "PLATINUM": ["ALL", "SILVER", "GOLD", "PLATINUM"],

        "INNER_CIRCLE": ["ALL", "SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"],

    }

    return hierarchy.get(membership, [])

def _get_community_post_audience_for_user(user: dict) -> str:

    if bool(user.get("is_admin")):

        return "ALL"

    tier = _normalize_subscription_tier(user.get("subscription_tier") or user.get("tier"))

    if tier in {"SILVER", "GOLD", "PLATINUM", "INNER_CIRCLE"}:

        return tier

    return "SILVER"

def _serialize_community_post_record(record: dict, author_record: dict | None = None) -> dict:

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    updated_at = _as_utc(record.get("updated_at") or created_at)

    author_role = str(record.get("author_role") or "user")

    author_name = str(record.get("author_name") or "Member")

    author_profile_image = str(record.get("author_profile_image") or "")

    if author_record:

        author_role = str(author_record.get("role") or ("admin" if author_record.get("is_admin") else "user")).strip() or "user"

        author_name = str(author_record.get("name") or "Member").strip() or "Member"

        author_profile_image = str(author_record.get("profile_image") or "").strip()

    return {

        "id": str(record.get("_id")),

        "author_id": str(record.get("author_id") or ""),

        "author_name": author_name,

        "author_role": author_role,

        "author_profile_image": author_profile_image,

        "audience": str(record.get("audience") or "ALL"),

        "content": str(record.get("content") or ""),

        "image_url": str(record.get("image_url") or ""),

        "video_url": str(record.get("video_url") or ""),

        "audio_url": str(record.get("audio_url") or ""),

        "like_count": int(record.get("like_count") or 0),

        "comment_count": int(record.get("comment_count") or 0),

        "viewer_has_liked": False,

        "can_delete": False,

        "comments": [],

        "reactions": [],

        "created_at": created_at,

        "updated_at": updated_at,

        "flagged": bool(record.get("flagged", False)),

        "flag_reason": str(record.get("flag_reason") or ""),

        "moderation_status": str(record.get("moderation_status") or ("reviewing" if record.get("flagged") else "published")),

        "moderator_notes": str(record.get("moderator_notes") or ""),

}

def _serialize_community_comment_record(record: dict, author_record: dict | None = None) -> dict:

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    author_role = str(record.get("author_role") or "user")

    author_name = str(record.get("author_name") or "Member")

    author_profile_image = str(record.get("author_profile_image") or "")

    if author_record:

        author_role = str(author_record.get("role") or ("admin" if author_record.get("is_admin") else "user")).strip() or "user"

        author_name = str(author_record.get("name") or "Member").strip() or "Member"

        author_profile_image = str(author_record.get("profile_image") or "").strip()

    return {

        "id": str(record.get("_id")),

        "post_id": str(record.get("post_id") or ""),

        "author_name": author_name,

        "author_role": author_role,

        "author_profile_image": author_profile_image,

        "content": str(record.get("content") or ""),

        "created_at": created_at,

    }

def _serialize_community_reaction_user_record(record: dict, user_record: dict | None) -> dict:

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    role = ""

    if user_record:

        role = str(user_record.get("role") or ("admin" if user_record.get("is_admin") else "user"))

    return {

        "user_id": str(record.get("user_id") or ""),

        "user_name": str((user_record or {}).get("name") or "Member"),

        "user_role": role or "user",

        "user_profile_image": str((user_record or {}).get("profile_image") or ""),

        "created_at": created_at,

    }

async def _serialize_community_post_records(

    records: list[dict],

    viewer_user: dict | None,

    comment_limit_per_post: int = 3,

    include_reactions: bool = False,

) -> list[dict]:

    if not records:

        return []

    author_records_by_id = await _load_community_author_records(records)

    post_ids = [str(record.get("_id")) for record in records if record.get("_id")]

    viewer_user_id = str(viewer_user.get("_id") or "") if viewer_user else None

    comments_by_post = await _load_community_comments(records, limit_per_post=comment_limit_per_post)

    liked_post_ids = await _load_community_liked_post_ids(post_ids, viewer_user_id)

    reactions_by_post = await _load_community_reactions(records) if include_reactions else {}

    serialized_posts: list[dict] = []

    for record in records:

        author_id = str(record.get("author_id") or "")

        serialized = _serialize_community_post_record(record, author_records_by_id.get(author_id))

        post_id = serialized["id"]

        serialized["viewer_has_liked"] = post_id in liked_post_ids

        serialized["can_delete"] = bool(viewer_user) and _can_delete_community_post(record, viewer_user)

        serialized["comments"] = comments_by_post.get(post_id, [])

        serialized["reactions"] = reactions_by_post.get(post_id, [])

        serialized_posts.append(serialized)

    return serialized_posts

async def _load_community_comments(records: list[dict], limit_per_post: int = 3) -> dict[str, list[dict]]:

    post_ids = [str(record.get("_id")) for record in records if record.get("_id")]

    if not post_ids:

        return {}

    comments = await community_comments_collection.find(

        {"post_id": {"$in": post_ids}},

        sort=[("created_at", 1), ("_id", 1)],

    ).to_list(length=1000)

    author_records_by_id = await _load_community_author_records(comments)

    comments_by_post: dict[str, list[dict]] = {post_id: [] for post_id in post_ids}

    for comment in comments:

        post_id = str(comment.get("post_id") or "")

        if not post_id:

            continue

        author_id = str(comment.get("author_id") or "")

        comments_by_post.setdefault(post_id, []).append(

            _serialize_community_comment_record(comment, author_records_by_id.get(author_id))

        )

    if limit_per_post > 0:

        return {

            post_id: post_comments[-limit_per_post:]

            for post_id, post_comments in comments_by_post.items()

        }

    return comments_by_post

async def _load_community_author_records(records: list[dict]) -> dict[str, dict]:

    author_ids = {

        str(record.get("author_id") or "").strip()

        for record in records

        if str(record.get("author_id") or "").strip()

    }

    if not author_ids:

        return {}

    object_ids: list[ObjectId] = []

    for author_id in author_ids:

        try:

            object_ids.append(ObjectId(author_id))

        except Exception:

            continue

    if not object_ids:

        return {}

    author_records = await users_collection.find({"_id": {"$in": object_ids}}).to_list(length=len(object_ids))

    return {str(author_record.get("_id")): author_record for author_record in author_records}

async def _load_community_liked_post_ids(post_ids: list[str], viewer_user_id: str | None) -> set[str]:

    if not viewer_user_id or not post_ids:

        return set()

    reactions = await community_reactions_collection.find(

        {"post_id": {"$in": post_ids}, "user_id": viewer_user_id},

        {"post_id": 1},

    ).to_list(length=len(post_ids))

    return {str(reaction.get("post_id") or "") for reaction in reactions if reaction.get("post_id")}

async def _load_community_reactions(records: list[dict]) -> dict[str, list[dict]]:

    post_ids = [str(record.get("_id")) for record in records if record.get("_id")]

    if not post_ids:

        return {}

    reactions = await community_reactions_collection.find(

        {"post_id": {"$in": post_ids}},

        sort=[("created_at", -1), ("_id", -1)],

    ).to_list(length=5000)

    user_ids = []

    for reaction in reactions:

        user_id = str(reaction.get("user_id") or "")

        if user_id:

            user_ids.append(user_id)

    object_ids: list[ObjectId] = []

    for user_id in set(user_ids):

        try:

            object_ids.append(ObjectId(user_id))

        except Exception:

            continue

    user_records = await users_collection.find({"_id": {"$in": object_ids}}).to_list(length=len(object_ids)) if object_ids else []

    users_by_id = {str(user_record.get("_id")): user_record for user_record in user_records}

    reactions_by_post: dict[str, list[dict]] = {post_id: [] for post_id in post_ids}

    for reaction in reactions:

        post_id = str(reaction.get("post_id") or "")

        if not post_id:

          continue

        user_id = str(reaction.get("user_id") or "")

        reactions_by_post.setdefault(post_id, []).append(

            _serialize_community_reaction_user_record(reaction, users_by_id.get(user_id))

        )

    return reactions_by_post

async def _get_community_post_or_404(post_id: str) -> dict:

    try:

        object_id = ObjectId(post_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid community post id") from exc

    record = await community_posts_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Community post not found")

    return record

async def _sync_community_author_profile(user_record: dict) -> None:

    author_id = str(user_record.get("_id") or "")

    if not author_id:

        return

    await community_posts_collection.update_many(

        {"author_id": author_id},

        {"$unset": {"author_name": "", "author_role": "", "author_profile_image": ""}},

    )

    await community_comments_collection.update_many(

        {"author_id": author_id},

        {"$unset": {"author_name": "", "author_role": "", "author_profile_image": ""}},

    )

def _can_delete_community_post(record: dict, user: dict) -> bool:

    if user.get("is_admin"):

        return True

    return str(record.get("author_id") or "") == str(user.get("_id") or "")

def _delete_community_post_media(record: dict) -> None:

    _delete_image_from_s3(record.get("image_url"))

    _delete_image_from_s3(record.get("video_url"))

def _ensure_community_post_access(record: dict, user: dict) -> None:

    audience = str(record.get("audience") or "ALL").strip().upper()

    if audience not in _get_allowed_community_audiences(user):

        raise HTTPException(status_code=404, detail="Community post not found")

def _html_to_plain_text(html_content: str) -> str:

    return shared_html_to_plain_text(html_content)

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

def _is_app_client_request(client_name: str | None) -> bool:

    return str(client_name or "").strip().lower() == "app"

def _get_auth_session_version(user: dict) -> int:

    try:

        return max(int(user.get("auth_session_version") or 0), 0)

    except (TypeError, ValueError):

        return 0

def _token_matches_auth_session(payload: dict[str, Any], user: dict) -> bool:

    try:

        token_version = max(int(payload.get("ver") or 0), 0)

    except (TypeError, ValueError):

        token_version = 0

    return token_version == _get_auth_session_version(user)

async def _consume_returning_user_recognition(user: dict) -> dict | None:
    """Return a one-time welcome-back prompt only for consented former trial users."""
    if not bool(user.get("marketing_consent")):
        return None

    started_at = _trial_started_at(user)
    if not started_at:
        return None

    subscription = _build_subscription_summary(user)
    if bool(subscription.get("is_purchased")) or str(subscription.get("status") or "").upper() in {"ACTIVE", "PAID"}:
        return None
    if _trial_datetime(user.get("winback_last_shown_at")):
        return None

    now = datetime.now(timezone.utc)
    if now < started_at + timedelta(days=5):
        return None

    claimed = await users_collection.update_one(
        {"_id": user["_id"], "marketing_consent": True, "winback_last_shown_at": {"$exists": False}},
        {"$set": {"winback_last_shown_at": now}},
    )
    if not claimed.modified_count:
        return None
    name = str(user.get("name") or "there").strip()
    started_label = started_at.strftime("%b %d, %Y")
    return {
        "title": "Welcome back to Victory Fitness",
        "message": f"Welcome back, {name}. You started your Gold trial on {started_label}. Ready to commit to your next step?",
        "action_label": "Choose your subscription",
        "action_route": "/plan",
        "trial_started_at": started_at,
    }

async def _issue_tokens(user: dict, response: Response | None, *, issue_cookies: bool = True) -> TokenResponse:

    user_id = str(user["_id"])

    profile_summary = await _serialize_me_record(user)
    returning_user = await _consume_returning_user_recognition(user)

    auth_session_version = _get_auth_session_version(user)

    access_token = create_token(

        user_id,

        "access",

        timedelta(minutes=settings.access_token_expire_minutes),

        extra_claims={"ver": auth_session_version},

    )

    session_token = create_token(

        user_id,

        "session",

        timedelta(days=settings.session_token_expire_days),

        extra_claims={"ver": auth_session_version},

    )

    if response and issue_cookies:

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
        returning_user=returning_user,

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

            "points": profile_summary.get("points", 0),

            "workouts_completed": profile_summary.get("workouts_completed", 0),

            "workouts_total": profile_summary.get("workouts_total", 0),

            "streak_days": profile_summary.get("streak_days", 0),

            "rank": profile_summary.get("rank", "Noob"),

            "subscription_tier": profile_summary.get("subscription_tier", "NONE"),

            "subscription_role": profile_summary.get("subscription_role", "NONE"),

            "subscription_status": profile_summary.get("subscription_status", "NONE"),

            "subscription_started_at": profile_summary.get("subscription_started_at"),

            "subscription_confirmed_at": profile_summary.get("subscription_confirmed_at"),

            "subscription_billing_cycle": profile_summary.get("subscription_billing_cycle", "yearly"),

            "subscription_is_purchased": profile_summary.get("subscription_is_purchased", False),

            "subscription_purchase_source": profile_summary.get("subscription_purchase_source", ""),

            "subscription_access": profile_summary.get("subscription_access", []),

            "subscription": profile_summary.get("subscription", {}),
            "trial_tier_granted": profile_summary.get("trial_tier_granted"),
            "trial_start_at": profile_summary.get("trial_start_at"),
            "trial_end_at": profile_summary.get("trial_end_at"),
            "trial_outcome": profile_summary.get("trial_outcome"),
            "gold_trial": profile_summary.get("gold_trial", {}),
            "marketing_consent": bool(user.get("marketing_consent")),

        },

    )

async def _seed_admin_user() -> None:

    if not settings.admin_seed_enabled:

        logger.info("admin_seed_skipped reason=disabled")

        return

    admin_accounts = list(getattr(settings, "admin_seed_accounts", []) or [])

    if not admin_accounts:

        logger.info("admin_seed_skipped reason=missing_credentials")

        return

    now = datetime.now(timezone.utc)

    def _default_admin_display_name(email: str) -> str:
        local_part = str(email or "").split("@")[0].strip()
        if not local_part:
            return "Victory Admin"
        normalized = re.sub(r"[^a-zA-Z0-9]+", " ", local_part).strip()
        if not normalized:
            return "Victory Admin"
        return " ".join(segment.capitalize() for segment in normalized.split())

    for account in admin_accounts:
        admin_email = str(account.get("email") or "").strip().lower()
        admin_password = str(account.get("password") or "").strip()
        admin_name = _default_admin_display_name(admin_email)
        if not admin_email or not admin_password:
            continue

        existing_user = await users_collection.find_one({"email": admin_email})

        if existing_user:
            current_password_hash = str(existing_user.get("password_hash") or "").strip()
            password_matches_seed = bool(current_password_hash) and verify_password(admin_password, current_password_hash)
            should_sync_password = settings.admin_seed_sync_password and not password_matches_seed

            logger.info(
                "admin_seed_validation email=%s exists=true password_hash_present=%s password_matches_seed=%s sync_password=%s",
                admin_email,
                bool(current_password_hash),
                password_matches_seed,
                should_sync_password,
            )

            await users_collection.update_one(

                {"_id": existing_user["_id"]},

                {

                    "$set": {

                        "name": existing_user.get("name") or admin_name,

                        "email": admin_email,

                        "role": "admin",

                        "is_admin": True,

                        "is_verified": True,

                        "subscription_tier": "INNER_CIRCLE",

                        "subscription_role": "INNER_CIRCLE",

                        "subscription_status": "ACTIVE",

                        "subscription_billing_cycle": "yearly",

                        "subscription_is_purchased": True,

                        "subscription_purchase_source": "admin_seed",

                        "password_hash": hash_password(admin_password) if should_sync_password else current_password_hash,

                        "updated_at": now,

                    },

                    "$unset": {

                        "verification_code_hash": "",

                        "verification_code_expires_at": "",

                    },

                },

            )

            logger.info(
                "admin_seed_exists email=%s login_ready=%s",
                admin_email,
                password_matches_seed or should_sync_password,
            )

            continue

        await users_collection.insert_one(

            {

                "name": admin_name,

                "email": admin_email,

                "password_hash": hash_password(admin_password),

                "is_verified": True,

                "role": "admin",

                "is_admin": True,

                "subscription_tier": "INNER_CIRCLE",

                "subscription_role": "INNER_CIRCLE",

                "subscription_status": "ACTIVE",

                "subscription_billing_cycle": "yearly",

                "subscription_is_purchased": True,

                "subscription_purchase_source": "admin_seed",

                "created_at": now,

                "updated_at": now,

            }

        )

        logger.info(
            "admin_seed_validation email=%s exists=false password_hash_present=true password_matches_seed=true sync_password=true",
            admin_email,
        )
        logger.info("admin_seed_created email=%s", admin_email)

def _normalize_admin_user_status(record: dict) -> str:

    status = str(record.get("status") or "").strip().upper()

    if status in {"ACTIVE", "INACTIVE", "PENDING"}:

        return status

    return "ACTIVE" if record.get("is_verified") else "PENDING"

def _normalize_subscription_tier(value: object) -> str:

    tier = str(value or "").strip().upper().replace(" ", "_")

    return tier if tier in SUBSCRIPTION_TIERS else "NONE"

def _normalize_subscription_status(value: object, tier: str) -> str:

    status = str(value or "").strip().upper().replace(" ", "_")

    if status in {"ACTIVE", "PENDING_PAYMENT", "CANCELLED", "CANCELED", "EXPIRED"}:

        return "CANCELLED" if status == "CANCELED" else status

    return "ACTIVE" if tier != "NONE" else "NONE"

def _normalize_billing_cycle(value: object) -> str:

    cycle = str(value or "").strip().lower()

    return cycle if cycle in {"monthly", "yearly"} else "yearly"

def _resolve_subscription_access(tier: str) -> list[str]:

    normalized_tier = _normalize_subscription_tier(tier)

    return list(SUBSCRIPTION_ACCESS.get(normalized_tier, []))

def _user_has_subscription_access(user: dict, feature: str) -> bool:

    if bool(user.get("is_admin")):

        return True

    configured_access = user.get("subscription_access")

    subscription = user.get("subscription") if isinstance(user.get("subscription"), dict) else {}

    if not configured_access and isinstance(subscription.get("access"), list):

        configured_access = subscription.get("access")

    if isinstance(configured_access, list) and configured_access:

        return feature in {str(item).strip() for item in configured_access if str(item).strip()}

    if _is_phase_one_beta_user(user):
        if _phase_one_beta_is_active(user):
            return feature in set(_resolve_subscription_access("GOLD"))
        return False

    if _trial_is_active(user) and feature in _resolve_subscription_access("GOLD"):

        return True

    return feature in _resolve_subscription_access(

        str(user.get("subscription_tier") or user.get("subscription_role") or user.get("tier") or "")

    )

def _ensure_subscription_feature_access(user: dict, feature: str, detail: str) -> None:

    if not _user_has_subscription_access(user, feature):

        raise HTTPException(status_code=403, detail=detail)

def _get_user_active_challenge_limit(user: dict) -> int | None:

    return None

def _get_user_ready_challenge_limit(user: dict) -> int:

    return 1000

def _get_user_monthly_nutrition_generation_limit(user: dict) -> int | None:

    tier = _normalize_subscription_tier(user.get("subscription_tier") or user.get("subscription_role") or user.get("tier"))

    if tier == "GOLD":

        return 3

    return None

async def _enforce_nutrition_generation_limit(user: dict) -> None:

    monthly_limit = _get_user_monthly_nutrition_generation_limit(user)

    if monthly_limit is None:

        return

    user_id = str(user["_id"])

    window_start = datetime.now(timezone.utc) - timedelta(days=30)

    standard_count, progressive_count = await asyncio.gather(

        nutrition_plans_collection.count_documents(

            {"user_id": user_id, "created_at": {"$gte": window_start}}

        ),

        nutrition_progressive_plans_collection.count_documents(

            {"user_id": user_id, "created_at": {"$gte": window_start}}

        ),

    )

    total_generated = int(standard_count or 0) + int(progressive_count or 0)

    if total_generated >= monthly_limit:

        raise HTTPException(

            status_code=403,

            detail=f"Your current plan allows up to {monthly_limit} nutrition plan generations every 30 days",

        )

def _require_pillow() -> None:

    if Image is None or ImageDraw is None or ImageFont is None:

        raise HTTPException(

            status_code=503,

            detail="Progress report image generation is unavailable because Pillow is not installed on the server",

        )

def _build_subscription_summary(record: dict) -> dict:

    subscription = record.get("subscription") if isinstance(record.get("subscription"), dict) else {}

    tier = _normalize_subscription_tier(

        record.get("subscription_tier")

        or record.get("subscription_role")

        or record.get("tier")

        or subscription.get("tier")

        or subscription.get("role")

    )

    status = _normalize_subscription_status(

        record.get("subscription_status")

        or record.get("subscription_state")

        or subscription.get("status"),

        tier,

    )

    is_purchased = bool(

        record.get("subscription_is_purchased")

        if record.get("subscription_is_purchased") is not None

        else subscription.get("is_purchased")

    ) and tier != "NONE" and status == "ACTIVE"

    purchase_source = str(

        record.get("subscription_purchase_source")

        or subscription.get("purchase_source")

        or ""

    ).strip()

    record_access = record.get("subscription_access")

    if isinstance(record_access, list) and record_access:

        access = [str(item).strip() for item in record_access if str(item).strip()]

    elif isinstance(subscription.get("access"), list) and subscription.get("access"):

        access = [str(item).strip() for item in subscription.get("access") if str(item).strip()]

    else:

        access = _resolve_subscription_access(tier)

    if _is_phase_one_beta_user(record):
        beta_status = _phase_one_beta_status(record)
        if beta_status != "ACTIVE":
            access = []
        purchase_source = PHASE_ONE_BETA_SUBSCRIPTION_SOURCE
        tier = "GOLD_BETA"
        status = beta_status
        is_purchased = False

    if not _is_phase_one_beta_user(record) and _trial_is_active(record):

        access = sorted(set(access) | set(_resolve_subscription_access("GOLD")))

    return {

        "tier": tier,

        "role": tier,

        "status": status,

        "started_at": record.get("subscription_started_at") or subscription.get("started_at"),

        "confirmed_at": record.get("subscription_confirmed_at") or subscription.get("confirmed_at"),

        "billing_cycle": _normalize_billing_cycle(

            record.get("subscription_billing_cycle") or subscription.get("billing_cycle")

        ),

        "is_purchased": is_purchased,

        "purchase_source": purchase_source,

        "access": access,

    }

async def _resolve_subscription_checkout_plan(

    subscription_tier: str,

    billing_cycle: str,

    plan_id: str | None = None,

) -> dict | None:

    normalized_tier = _normalize_subscription_tier(subscription_tier)

    if normalized_tier == "NONE":

        return None

    items = await _get_dashboard_subscription_plan_items()

    matched: dict | None = None

    for item in items:

        item_id = str(item.get("id") or "")

        item_tier = _normalize_subscription_plan_tier_key(item.get("tier"))

        if plan_id and item_id == plan_id:

            matched = item

            break

        if item_tier == normalized_tier:

            matched = item

            if not plan_id:

                break

    if not matched:

        raise HTTPException(status_code=404, detail="Subscription plan not found")

    matched_tier = _normalize_subscription_plan_tier_key(matched.get("tier"))

    if matched_tier != normalized_tier:

        raise HTTPException(status_code=400, detail="Selected plan does not match the requested subscription tier")

    plan = _serialize_app_subscription_plan_item(matched)

    if plan["isApplicationOnly"]:

        return {

            "plan_id": plan["id"],

            "price": None,

            "original_price": None,

            "discount_percentage": plan["discountPercentage"] if plan["isDiscountActive"] else None,

            "billing_cycle": billing_cycle,

            "title": plan["title"],

            "feature_access": plan["featureAccess"],

        }

    original_price = plan["priceMonthly"] if billing_cycle == "monthly" else plan["priceYearly"]

    final_price = plan["discountedPriceMonthly"] if billing_cycle == "monthly" else plan["discountedPriceYearly"]

    return {

        "plan_id": plan["id"],

        "price": final_price,

        "original_price": original_price,

        "discount_percentage": plan["discountPercentage"] if plan["isDiscountActive"] else None,

        "billing_cycle": billing_cycle,

        "title": plan["title"],

        "feature_access": plan["featureAccess"],

    }

async def _build_subscription_update_doc(existing_user: dict, payload: UpdateSubscriptionRequest, now: datetime) -> dict:

    tier = _normalize_subscription_tier(payload.subscription_tier)

    billing_cycle = _normalize_billing_cycle(payload.billing_cycle)

    subscription_status = "ACTIVE" if payload.confirm_payment and tier != "NONE" else "NONE"

    is_purchased = bool(payload.confirm_payment and tier != "NONE")

    checkout_plan = await _resolve_subscription_checkout_plan(tier, billing_cycle, payload.plan_id) if tier != "NONE" else None

    feature_access = checkout_plan["feature_access"] if checkout_plan and is_purchased else []

    update_doc: dict = {

        "subscription_tier": tier,

        "subscription_role": tier,

        "subscription_status": subscription_status,

        "subscription_billing_cycle": billing_cycle,

        "subscription_is_purchased": is_purchased,

        "subscription_purchase_source": "manual_confirm" if is_purchased else "",

        "subscription_plan_id": checkout_plan["plan_id"] if checkout_plan and is_purchased else "",

        "subscription_price_amount": checkout_plan["price"] if checkout_plan and is_purchased else None,

        "subscription_original_price_amount": checkout_plan["original_price"] if checkout_plan and is_purchased else None,

        "subscription_discount_percentage": checkout_plan["discount_percentage"] if checkout_plan and is_purchased else None,

        "subscription_access": feature_access,

        "subscription": {

            "tier": tier,

            "role": tier,

            "status": subscription_status,

            "billing_cycle": billing_cycle,

            "is_purchased": is_purchased,

            "purchase_source": "manual_confirm" if is_purchased else "",

            "access": feature_access,

        },

        "updated_at": now,

    }

    if tier == "NONE":

        update_doc["subscription_started_at"] = None

        update_doc["subscription_confirmed_at"] = None

        update_doc["subscription_billing_cycle"] = "yearly"

        update_doc["subscription_is_purchased"] = False

        update_doc["subscription_role"] = "NONE"

        update_doc["subscription_purchase_source"] = ""

        update_doc["subscription_plan_id"] = ""

        update_doc["subscription_price_amount"] = None

        update_doc["subscription_original_price_amount"] = None

        update_doc["subscription_discount_percentage"] = None

        update_doc["subscription_access"] = []

        update_doc["subscription"] = {

            "tier": "NONE",

            "role": "NONE",

            "status": "NONE",

            "billing_cycle": "yearly",

            "is_purchased": False,

            "purchase_source": "",

            "access": [],

        }

    else:

        update_doc["subscription_started_at"] = existing_user.get("subscription_started_at") or now

        update_doc["subscription_confirmed_at"] = now if subscription_status == "ACTIVE" else existing_user.get("subscription_confirmed_at")

        update_doc["subscription"]["started_at"] = update_doc["subscription_started_at"]

        update_doc["subscription"]["confirmed_at"] = update_doc["subscription_confirmed_at"]

    trial_outcome = _trial_outcome_for_subscription(tier, is_purchased)
    if trial_outcome and _trial_started_at(existing_user):
        update_doc["trial_outcome"] = trial_outcome
        update_doc["trial_outcome_at"] = now

    return update_doc

async def _serialize_me_record(record: dict) -> dict:

    stats = await _calculate_user_fitness_stats(str(record["_id"]))

    subscription_summary = _build_subscription_summary(record)
    trial_summary = _trial_summary(record)

    return {

        "id": str(record["_id"]),
        "created_at": record.get("created_at"),

        "name": str(record.get("name") or ""),

        "email": str(record.get("email") or ""),

        "is_verified": bool(record.get("is_verified")),

        "role": str(record.get("role") or ("admin" if record.get("is_admin") else "user")),

        "is_admin": bool(record.get("is_admin")),

        "country": str(record.get("country") or ""),

        "country_code": (str(record.get("country_code") or "").upper() or None),
        "motivation_statement": str(record.get("motivation_statement") or "").strip() or None,
        "identity_statement": str(record.get("identity_statement") or "").strip() or None,
        "workout_unlock_label": str(record.get("workout_unlock_label") or "").strip() or None,
        "training_trigger_context": str(record.get("training_trigger_context") or "").strip() or None,
        "training_trigger_action": str(record.get("training_trigger_action") or "").strip() or None,

        "profileImage": str(record.get("profile_image") or ""),

        "onboarding_completed": bool(record.get("onboarding_completed", False)),

        "points": stats["points"],

        "workouts_completed": stats["workouts_completed"],

        "workouts_total": stats["workouts_total"],

        "streak_days": stats["streak_days"],

        "rank": stats["rank"],

        "next_rank": stats["next_rank"],

        "points_to_next_rank": stats["points_to_next_rank"],

        "rank_progress_fraction": stats["rank_progress_fraction"],

        "subscription_tier": subscription_summary["tier"],

        "subscription_role": subscription_summary["role"],

        "subscription_status": subscription_summary["status"],

        "subscription_started_at": subscription_summary["started_at"],

        "subscription_confirmed_at": subscription_summary["confirmed_at"],

        "subscription_billing_cycle": subscription_summary["billing_cycle"],

        "subscription_is_purchased": subscription_summary["is_purchased"],

        "subscription_purchase_source": subscription_summary["purchase_source"],

        "subscription_access": subscription_summary["access"],

        "subscription": subscription_summary,
        "trial_tier_granted": trial_summary["tier_granted"],
        "trial_start_at": trial_summary["start_at"],
        "trial_end_at": trial_summary["end_at"],
        "trial_outcome": trial_summary["outcome"],
        "gold_trial": trial_summary,
        "marketing_consent": bool(record.get("marketing_consent")),

    }

RANK_TIERS = [

    ("Noob", 0),

    ("Bronze", 500),

    ("Silver", 1600),

    ("Gold", 3500),

    ("Platinum", 5000),

    ("Diamond", 10000),

    ("Master", 20000),

    ("Champion", 35000),

    ("Titan", 50000),

    ("Legend", 75000),

    ("Immortal", 100000),

]

def _resolve_rank(points: int) -> str:

    current_rank = "Noob"

    for label, minimum_points in RANK_TIERS:

        if points >= minimum_points:

            current_rank = label

    return current_rank

def _resolve_rank_progress(points: int) -> dict[str, int | float | str]:

    current_index = 0

    for index, (_, minimum_points) in enumerate(RANK_TIERS):

        if points >= minimum_points:

            current_index = index

    current_rank, current_floor = RANK_TIERS[current_index]

    next_tier = RANK_TIERS[current_index + 1] if current_index + 1 < len(RANK_TIERS) else None

    if not next_tier:

        return {

            "rank": current_rank,

            "next_rank": current_rank,

            "points_to_next_rank": 0,

            "rank_progress_fraction": 1.0,

        }

    next_rank, next_threshold = next_tier

    span = max(next_threshold - current_floor, 1)

    points_in_tier = max(points - current_floor, 0)

    return {

        "rank": current_rank,

        "next_rank": next_rank,

        "points_to_next_rank": max(next_threshold - points, 0),

        "rank_progress_fraction": min(points_in_tier / span, 1.0),

    }

def _parse_completed_activity_date(value: object) -> datetime | None:

    if isinstance(value, datetime):

        return _as_utc(value)

    if isinstance(value, str):

        try:

            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))

        except ValueError:

            return None

    return None

def _calculate_current_streak(completed_dates: set) -> int:

    if not completed_dates:

        return 0

    current_day = max(completed_dates)

    streak = 0

    while current_day in completed_dates:

        streak += 1

        current_day = current_day - timedelta(days=1)

    return streak

async def _calculate_user_fitness_stats(user_id: str) -> dict[str, int | str]:

    memberships = await challenge_memberships_collection.find(

        {"user_id": user_id},

        projection=FITNESS_STATS_MEMBERSHIP_PROJECTION,

    ).to_list(length=None)

    if not memberships:

        return {

            "points": 0,

            "workouts_completed": 0,

            "workouts_total": 0,

            "streak_days": 0,

            "rank": "Noob",

            "next_rank": "Bronze",

            "points_to_next_rank": 500,

            "rank_progress_fraction": 0.0,

        }

    points = 0

    workouts_completed = 0

    workouts_total = 0

    completed_dates: set = set()

    challenge_ids: list[ObjectId] = []

    for membership in memberships:

        try:

            challenge_ids.append(ObjectId(str(membership.get("challenge_id") or "")))

        except Exception:

            continue

    if challenge_ids:

        challenge_records = await challenges_collection.find(

            {"_id": {"$in": challenge_ids}},

            projection=FITNESS_STATS_CHALLENGE_PROJECTION,

        ).to_list(length=len(challenge_ids))

        challenges_by_id = {str(record["_id"]): record for record in challenge_records}

        for membership in memberships:

            challenge = challenges_by_id.get(str(membership.get("challenge_id") or ""))

            if not challenge:

                continue

            plan_days = _normalize_challenge_plan_days(

                challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

                duration_days=max(int(challenge.get("duration_days") or 0), 1)

            )

            challenge_points = max(int(challenge.get("points") or 0), 0)

            membership_with_points = dict(membership)

            membership_with_points["challenge_points"] = challenge_points

            points += _calculate_challenge_points_earned(plan_days, membership_with_points, challenge_points)

            completed_units, total_units = _calculate_challenge_completion_counts(plan_days, membership)

            workouts_completed += completed_units

            workouts_total += total_units

            plan_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

            for day in plan_days:

                day_number = str(day.get("day_number") or "")

                day_progress = plan_progress.get(day_number, {}) if isinstance(plan_progress, dict) else {}

                if isinstance(day_progress, dict) and bool(day_progress.get("completed")):

                    completed_at = _parse_completed_activity_date(day_progress.get("updated_at"))

                    if completed_at:

                        completed_dates.add(completed_at.date())

    rank_progress = _resolve_rank_progress(points)

    return {

        "points": points,

        "workouts_completed": workouts_completed,

        "workouts_total": workouts_total,

        "streak_days": _calculate_current_streak(completed_dates),

        "rank": str(rank_progress["rank"]),

        "next_rank": str(rank_progress["next_rank"]),

        "points_to_next_rank": int(rank_progress["points_to_next_rank"]),

        "rank_progress_fraction": float(rank_progress["rank_progress_fraction"]),

    }

def _serialize_admin_profile_record(record: dict) -> dict:

    return {

        "id": str(record["_id"]),

        "fullName": str(record.get("name") or ""),

        "email": str(record.get("email") or ""),

        "role": str(record.get("role") or "admin"),

        "country": str(record.get("country") or ""),

        "contactNumber": str(record.get("contact_number") or ""),

        "profileImage": str(record.get("profile_image") or ""),

        "isVerified": bool(record.get("is_verified")),

    }

def _serialize_admin_user_record(record: dict) -> dict:

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    updated_at = _as_utc(record.get("updated_at") or created_at)

    role = str(record.get("role") or ("admin" if record.get("is_admin") else "user"))

    subscription_summary = _build_subscription_summary(record)
    trial_summary = _trial_summary(record)
    is_beta_tester = bool(trial_summary.get("is_beta_tester"))

    return {

        "id": str(record["_id"]),

        "fullName": str(record.get("name") or "Unknown"),

        "email": str(record.get("email") or ""),

        "role": role,

        "status": _normalize_admin_user_status(record),

        "isVerified": bool(record.get("is_verified")),

        "contactNumber": str(record.get("contact_number") or ""),

        "country": str(record.get("country") or ""),

        "country_code": (str(record.get("country_code") or "").upper() or None),

        "createdAt": created_at,

        "updatedAt": updated_at,

        "profileImage": str(record.get("profile_image") or ""),

        "subscription_tier": subscription_summary["tier"],

        "subscription_role": subscription_summary["role"],

        "subscription_status": subscription_summary["status"],

        "subscription_started_at": subscription_summary["started_at"],

        "subscription_confirmed_at": subscription_summary["confirmed_at"],

        "subscription_billing_cycle": subscription_summary["billing_cycle"],

        "subscription_is_purchased": subscription_summary["is_purchased"],

        "subscription_purchase_source": subscription_summary["purchase_source"],

        "subscription_access": subscription_summary["access"],

        "trial_type": trial_summary["trial_type"],

        "is_beta_tester": is_beta_tester,

        "trial_start_at": trial_summary["start_at"],

        "trial_end_at": trial_summary["end_at"],

        "trial_days_remaining": int(trial_summary["days_remaining"] or 0),

        "trial_status": subscription_summary["status"] if is_beta_tester else None,

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

def _trial_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None

def _upload_community_audio_to_s3(
    user_id: str,
    audio_base64: str,
    mime_type: str,
    file_name: str | None,
) -> str:
    return _upload_audio_to_s3("community-audio", user_id, audio_base64, mime_type, file_name)

__all__ = [name for name in globals() if not name.startswith('__')]
