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

from urllib.parse import parse_qs, unquote, urlparse

from urllib.request import Request as UrlRequest, urlopen



from docx import Document as DocxDocument
from pypdf import PdfReader
from bson import ObjectId

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, Security, UploadFile, WebSocket, WebSocketDisconnect, status

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse

from fastapi.security import HTTPAuthorizationCredentials

from fastapi.staticfiles import StaticFiles

from starlette.exceptions import HTTPException as StarletteHTTPException

from pydantic import BaseModel, Field

from jose import jwt

try:

    from PIL import Image, ImageDraw, ImageFont

except ModuleNotFoundError:

    Image = None

    ImageDraw = None

    ImageFont = None



from .coach_archive import (

    build_archive_record,

    hydrate_archive_messages,

    load_thread_snapshot,

    s3_archive_enabled,

    store_thread_snapshot,

)

from .challenge_plan_ai import ChallengePlanGenerationInput, generate_challenge_plan

from .coach_victor import generate_coach_victor_reply

from .config import settings

from .database import DatabaseNotConfiguredError, close_database_connection, ensure_indexes, users_collection

from .dependencies import (

    bearer_scheme,

    get_verified_user as dependency_get_verified_user,

    get_verified_user_from_access_token as dependency_get_verified_user_from_access_token,

    require_access_user as dependency_require_access_user,

    require_admin_user as dependency_require_admin_user,

)

from .email_service import send_password_reset_email, send_verification_email

from .journal_ai import generate_journal_analysis

from .longevity_ai import generate_longevity_weekly_plan

from .models import AppNotificationItem, AppNotificationListResponse, PushTokenRequest


from .push_service import notify_user, notify_users_of_published_workout
from .challenge_milestone import generate_challenge_milestone_message
from .trial_campaign import process_trial_campaign


from .models import (

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


    TrialConversionResponse,


    TrialConversionUser,

    AdminMasterclassItem,

    AdminMasterclassListResponse,

    AdminMasterclassRequest,

    AdminNotificationItem,

    AdminNotificationListResponse,

    AdminNotificationUpdateRequest,
    AdminTestNotificationRequest,

    AdminSubscriberItem,

    AdminSubscriberListResponse,

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

from .database import (

    app_content_collection,

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

)

from .nutrition_ai import (

    NutritionPlanRefusalError,

    build_nutrition_plan_signature,

    generate_meal_document_analysis,

    generate_meal_image_analysis,

    generate_nutrition_advice,

    generate_nutrition_plan,

    generate_progressive_nutrition_plan_day,

)

from .repositories.content import ensure_content_record, upsert_content_record

from .repositories.workouts import list_public_workout_records

from .serializers.content import (

    serialize_about_us_record as shared_serialize_about_us_record,

    serialize_privacy_policy_record as shared_serialize_privacy_policy_record,

    serialize_terms_condition_record as shared_serialize_terms_condition_record,

)

from .serializers.workouts import serialize_public_workout_record as shared_serialize_public_workout_record

from .utils.datetime import as_utc as shared_as_utc

from .utils.html import html_to_plain_text as shared_html_to_plain_text

from .workout_plan_ai import (

    StrengthWorkoutPlanInput,

    VideoWorkoutPlanInput,

    generate_strength_workout_plan,

    generate_video_workout_plan,

)
from .vimeo_sync import VimeoSyncError, get_vimeo_status, sync_vimeo_workouts

from .security import (

    create_token,

    create_verification_code,

    decode_token,

    hash_password,

    verify_password,

)

from .wearables import (

    backfill_current_health_metrics_from_history,

    build_longevity_metric_insights,

    build_longevity_wearables_response,

    router as wearables_router,

    start_integration_queue,

    start_wearables_scheduler,

    stop_integration_queue,

    stop_wearables_scheduler,

)





app = FastAPI(title=settings.app_name)

app.include_router(wearables_router)

logger = logging.getLogger("victory_fitness.api")


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

MEDIA_ROOT = Path("/tmp/victory-fitness-media") if settings.is_vercel else Path(__file__).resolve().parents[1] / "media"

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")



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





@app.get("/favicon.ico")

async def get_favicon_ico() -> Response:

    content = _build_favicon_ico_bytes()

    if not content:

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(content=content, media_type="image/x-icon")





@app.get("/favicon.png")

async def get_favicon_png() -> Response:

    content = _build_favicon_png_bytes()

    if not content:

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(content=content, media_type="image/png")



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



app.add_middleware(

    CORSMiddleware,

    allow_origins=settings.cors_origins,

    allow_origin_regex=settings.cors_origin_regex,

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





@app.exception_handler(DatabaseNotConfiguredError)

async def database_not_configured_handler(

    request: Request,

    exc: DatabaseNotConfiguredError,

) -> JSONResponse:

    logger.error("database_not_configured path=%s detail=%s", request.url.path, str(exc))

    return _cors_json_response(request, status_code=503, content={"detail": str(exc)})





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

    return _cors_json_response(request, status_code=exc.status_code, content={"detail": exc.detail})





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

    certificate = _get_google_certificates().get(kid)

    if not certificate:

        raise HTTPException(status_code=401, detail="Invalid Google token")



    try:

        payload = jwt.decode(

            id_token,

            certificate,

            algorithms=["RS256"],

            audience=google_client_id,

            issuer="https://accounts.google.com",

        )

    except Exception:

        try:

            payload = jwt.decode(

                id_token,

                certificate,

                algorithms=["RS256"],

                audience=google_client_id,

                issuer="accounts.google.com",

            )

        except Exception as exc:

            raise HTTPException(status_code=401, detail="Invalid Google token") from exc



    return payload





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



    email_verified = profile.get("email_verified")

    if email_verified is False:

        raise HTTPException(status_code=401, detail="Google account email is not verified")



    display_name = str(profile.get("name") or profile.get("displayName") or email.split("@")[0]).strip()

    photo_url = str(profile.get("picture") or profile.get("photoUrl") or "").strip()

    firebase_uid = str(profile.get("sub") or profile.get("user_id") or profile.get("localId") or "").strip()

    now = datetime.now(timezone.utc)



    existing_user = await users_collection.find_one({"email": email})

    if not existing_user:

        user_doc = {

            "name": display_name,

            "email": email,

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

            "firebase_uid": firebase_uid,

            "profile_image": photo_url,

            "onboarding_completed": False,

            "created_at": now,

            "updated_at": now,

        }

        inserted = await users_collection.insert_one(user_doc)

        return await users_collection.find_one({"_id": inserted.inserted_id}) or user_doc



    update_doc: dict[str, Any] = {

        "is_verified": True,

        "auth_provider": auth_provider,

        "updated_at": now,

    }

    if display_name and not str(existing_user.get("name") or "").strip():

        update_doc["name"] = display_name

    if photo_url:

        update_doc["profile_image"] = photo_url

    if firebase_uid:

        update_doc["firebase_uid"] = firebase_uid



    await users_collection.update_one(

        {"_id": existing_user["_id"]},

        {

            "$set": update_doc,

            "$unset": {

                "verification_code_hash": "",

                "verification_code_expires_at": "",

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



    if not id_token and not access_token:

        raise HTTPException(status_code=400, detail="Missing Google token")



    if id_token:

        try:

            profile = _verify_google_id_token(id_token)

            return profile, "google"

        except HTTPException as exc:

            if access_token or exc.status_code >= 500:

                logger.warning("auth_google_id_token_verify_failed detail=%s", exc.detail)

            else:

                try:

                    profile = _verify_firebase_id_token(id_token)

                    return profile, "firebase"

                except HTTPException:

                    raise exc



        try:

            profile = _verify_firebase_id_token(id_token)

            return profile, "firebase"

        except HTTPException as firebase_exc:

            if not access_token:

                raise firebase_exc



    profile = _fetch_google_userinfo(access_token)

    return profile, "google"





@app.on_event("startup")

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

    logger.info("startup_complete")





@app.on_event("shutdown")

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



    records = await list_public_workout_records(filter_doc)



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
    center_text(292, "STRENGTH WORKOUT COMPLETED", section_font, cyan)
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
        f"{day_name} completed by {user_name or 'Victory Member'}",
        f"Plan progress: {completed_days}/{total_days} days | Exercises: {completed_exercises}/{max(total_exercises, completed_exercises or 1)}",
    ])
    return output.getvalue(), share_message


@app.get("/ai/workout-plan/strength/{plan_id}/report", response_model=StrengthWorkoutPlanCompletionReportResponse)
async def workout_strength_plan_completion_report(
    plan_id: str,
    day: str = "",
    user: dict = Depends(_require_workout_plan_access_user),
) -> StrengthWorkoutPlanCompletionReportResponse:
    if not ObjectId.is_valid(plan_id):
        raise HTTPException(status_code=404, detail="Strength workout plan not found")
    record = await strength_workout_plans_collection.find_one({"_id": ObjectId(plan_id), "user_id": str(user["_id"])})
    if not record or not isinstance(record.get("plan"), dict):
        raise HTTPException(status_code=404, detail="Strength workout plan not found")
    plan = _serialize_strength_workout_plan_record(record)
    png_bytes, share_message = _build_strength_workout_completion_png(plan, str(user.get("name") or "Victory Member"), day)
    return StrengthWorkoutPlanCompletionReportResponse(
        file_name="victory-fitness-strength-completion.png",
        mime_type="image/png",
        image_base64=base64.b64encode(png_bytes).decode("ascii"),
        share_message=share_message,
    )


@app.post("/ai/workout-plan/strength", response_model=StrengthWorkoutPlanResponse)

async def workout_strength_plan(

    payload: StrengthWorkoutPlanRequest,

    user: dict = Depends(_require_workout_plan_access_user),

) -> StrengthWorkoutPlanResponse:

    plan_data = generate_strength_workout_plan(

        StrengthWorkoutPlanInput(

            goal=str(payload.goal or ""),

            level=str(payload.level or ""),

            split=str(payload.split or ""),

            height=str(payload.height or ""),

            gender=str(payload.gender or ""),

            bench=str(payload.bench or ""),

            squat=str(payload.squat or ""),

            deadlift=str(payload.deadlift or ""),

            equipment=[str(item) for item in payload.equipment],

            frequency=str(payload.frequency or ""),

            days=[str(item) for item in payload.days],

            age=str(payload.age or ""),

            weight=str(payload.weight or ""),

        )

    )

    created_at = datetime.now(timezone.utc)

    insert_result = await strength_workout_plans_collection.insert_one(

        {

            "user_id": str(user["_id"]),

            "input": payload.model_dump(),

            "plan": plan_data,

            "progress": [],

            "created_at": created_at,

            "updated_at": created_at,

        }

    )

    return _serialize_strength_workout_plan_record(

        {

            "_id": insert_result.inserted_id,

            "plan": plan_data,

            "progress": [],

            "created_at": created_at,

        }

    )





@app.get("/ai/workout-plan/strength/latest", response_model=StrengthWorkoutPlanResponse)

async def workout_strength_plan_latest(

    user: dict = Depends(_require_workout_plan_access_user),

) -> StrengthWorkoutPlanResponse:

    record = await strength_workout_plans_collection.find_one(

        {"user_id": str(user["_id"])},

        sort=[("created_at", -1)],

    )

    if not record or not isinstance(record.get("plan"), dict):

        raise HTTPException(status_code=404, detail="Strength workout plan not found")



    return _serialize_strength_workout_plan_record(record)





@app.get("/ai/workout-plan/strength", response_model=StrengthWorkoutPlanListResponse)

async def workout_strength_plan_list(

    user: dict = Depends(_require_workout_plan_access_user),

) -> StrengthWorkoutPlanListResponse:

    records = await strength_workout_plans_collection.find(

        {"user_id": str(user["_id"])},

        sort=[("created_at", -1)],

    ).to_list(length=100)



    items: list[StrengthWorkoutPlanResponse] = []

    for record in records:

        if not isinstance(record.get("plan"), dict):

            continue

        items.append(_serialize_strength_workout_plan_record(record))



    return StrengthWorkoutPlanListResponse(items=items)





@app.patch("/ai/workout-plan/strength/{plan_id}/progress", response_model=StrengthWorkoutPlanResponse)

async def workout_strength_plan_progress_update(

    plan_id: str,

    payload: StrengthWorkoutPlanProgressUpdateRequest,

    user: dict = Depends(_require_workout_plan_access_user),

) -> StrengthWorkoutPlanResponse:

    if not ObjectId.is_valid(plan_id):

        raise HTTPException(status_code=404, detail="Strength workout plan not found")



    record = await strength_workout_plans_collection.find_one(

        {"_id": ObjectId(plan_id), "user_id": str(user["_id"])},

    )

    if not record or not isinstance(record.get("plan"), dict):

        raise HTTPException(status_code=404, detail="Strength workout plan not found")



    day_key = str(payload.day or "").strip()

    if not day_key:

        raise HTTPException(status_code=400, detail="Day is required")



    plan_days = record["plan"].get("days") or []

    selected_day = next(

        (day for day in plan_days if str(day.get("day") or "").strip() == day_key),

        None,

    )

    if not isinstance(selected_day, dict):

        raise HTTPException(status_code=400, detail="Workout day not found")



    selected_day_response = _serialize_strength_workout_plan_record(

        {

            "_id": record["_id"],

            "plan": {"summary": record["plan"].get("summary"), "days": [selected_day]},

            "progress": [],

            "created_at": record.get("created_at"),

        }

    ).days[0]



    valid_exercise_ids = [

        str(exercise.id).strip()

        for section in selected_day_response.sections

        for exercise in section.exercises

        if str(exercise.id).strip()

    ]

    valid_section_ids = [str(section.id).strip() for section in selected_day_response.sections if str(section.id).strip()]

    section_exercise_map = {

        str(section.id).strip(): [str(exercise.id).strip() for exercise in section.exercises if str(exercise.id).strip()]

        for section in selected_day_response.sections

    }



    raw_progress = record.get("progress") or []

    progress_map: dict[str, dict[str, Any]] = {}

    for item in raw_progress:

        if not isinstance(item, dict):

            continue

        item_day = str(item.get("day") or "").strip()

        if item_day:

            progress_map[item_day] = dict(item)



    now = datetime.now(timezone.utc)

    day_progress = progress_map.get(

        day_key,

        {

            "day": day_key,

            "started": False,

            "completed": False,

            "completed_section_ids": [],

            "completed_exercise_ids": [],

            "started_at": None,

            "completed_at": None,

        },

    )

    existing_completed_section_ids = {

        str(value).strip()

        for value in day_progress.get("completed_section_ids", [])

        if str(value).strip()

    }

    completed_section_ids = [section_id for section_id in valid_section_ids if section_id in existing_completed_section_ids]

    existing_completed_ids = {

        str(value).strip()

        for value in day_progress.get("completed_exercise_ids", [])

        if str(value).strip()

    }

    completed_exercise_ids = [exercise_id for exercise_id in valid_exercise_ids if exercise_id in existing_completed_ids]



    if payload.section_id:

        section_id = str(payload.section_id).strip()

        if section_id not in valid_section_ids:

            raise HTTPException(status_code=400, detail="Workout section not found")

        section_exercise_ids = section_exercise_map.get(section_id, [])

        should_complete = True if payload.completed is None else bool(payload.completed)

        if should_complete:

            if section_id not in completed_section_ids:

                completed_section_ids.append(section_id)

            for exercise_id in section_exercise_ids:

                if exercise_id not in completed_exercise_ids:

                    completed_exercise_ids.append(exercise_id)

            day_progress["started"] = True

            day_progress["started_at"] = day_progress.get("started_at") or now

        else:

            completed_section_ids = [value for value in completed_section_ids if value != section_id]

            completed_exercise_ids = [value for value in completed_exercise_ids if value not in section_exercise_ids]

    elif payload.exercise_id:

        exercise_id = str(payload.exercise_id).strip()

        if exercise_id not in valid_exercise_ids:

            raise HTTPException(status_code=400, detail="Workout exercise not found")



        should_complete = True if payload.completed is None else bool(payload.completed)

        if should_complete:

            if exercise_id not in completed_exercise_ids:

                completed_exercise_ids.append(exercise_id)

            day_progress["started"] = True

            day_progress["started_at"] = day_progress.get("started_at") or now

        else:

            completed_exercise_ids = [value for value in completed_exercise_ids if value != exercise_id]

    elif payload.completed is not None:

        if payload.completed:

            completed_section_ids = valid_section_ids[:]

            completed_exercise_ids = valid_exercise_ids[:]

            day_progress["started"] = True

            day_progress["started_at"] = day_progress.get("started_at") or now

        else:

            completed_section_ids = []

            completed_exercise_ids = []



    if payload.started is not None:

        day_progress["started"] = bool(payload.started)

        if day_progress["started"]:

            day_progress["started_at"] = day_progress.get("started_at") or now

        elif not completed_exercise_ids and not completed_section_ids:

            day_progress["started_at"] = None



    completed_section_ids = [

        section_id

        for section_id in valid_section_ids

        if all(exercise_id in completed_exercise_ids for exercise_id in section_exercise_map.get(section_id, []))

    ]



    is_completed = False

    if valid_section_ids:

        is_completed = len(completed_section_ids) >= len(valid_section_ids)

    elif valid_exercise_ids:

        is_completed = len(completed_exercise_ids) >= len(valid_exercise_ids)

    elif payload.completed is not None:

        is_completed = bool(payload.completed)



    day_progress["completed_section_ids"] = completed_section_ids

    day_progress["completed_exercise_ids"] = completed_exercise_ids

    day_progress["completed"] = is_completed

    if is_completed:

        day_progress["started"] = True

        day_progress["started_at"] = day_progress.get("started_at") or now

        day_progress["completed_at"] = now

    else:

        day_progress["completed_at"] = None



    progress_map[day_key] = day_progress

    ordered_progress = [progress_map[str(day.get("day") or "").strip()] for day in plan_days if str(day.get("day") or "").strip() in progress_map]



    await strength_workout_plans_collection.update_one(

        {"_id": record["_id"]},

        {

            "$set": {

                "progress": ordered_progress,

                "updated_at": now,

            }

        },

    )



    record["progress"] = ordered_progress

    record["updated_at"] = now

    return _serialize_strength_workout_plan_record(record)





@app.delete("/ai/workout-plan/strength/latest")

async def workout_strength_plan_delete_latest(

    user: dict = Depends(_require_workout_plan_access_user),

) -> dict[str, str]:

    record = await strength_workout_plans_collection.find_one(

        {"user_id": str(user["_id"])},

        sort=[("created_at", -1)],

    )

    if not record:

        raise HTTPException(status_code=404, detail="Strength workout plan not found")



    await strength_workout_plans_collection.delete_one({"_id": record["_id"]})

    return {"status": "success", "message": "Strength workout plan deleted"}





@app.delete("/ai/workout-plan/strength/{plan_id}")

async def workout_strength_plan_delete(

    plan_id: str,

    user: dict = Depends(_require_workout_plan_access_user),

) -> dict[str, str]:

    if not ObjectId.is_valid(plan_id):

        raise HTTPException(status_code=404, detail="Strength workout plan not found")



    record = await strength_workout_plans_collection.find_one(

        {"_id": ObjectId(plan_id), "user_id": str(user["_id"])},

    )

    if not record:

        raise HTTPException(status_code=404, detail="Strength workout plan not found")



    await strength_workout_plans_collection.delete_one({"_id": record["_id"]})

    return {"status": "success", "message": "Strength workout plan deleted"}





@app.post("/ai/workout-plan/video", response_model=VideoWorkoutPlanResponse)

async def workout_video_plan(

    payload: VideoWorkoutPlanRequest,

    _: dict = Depends(_require_workout_plan_access_user),

) -> VideoWorkoutPlanResponse:

    records = await workouts_collection.find(

        {"visibility": "Published"},

        sort=[("created_at", -1), ("_id", -1)],

    ).to_list(length=50)

    workouts = [_serialize_public_workout_record(record) for record in records]

    plan = generate_video_workout_plan(

        VideoWorkoutPlanInput(

            goal=str(payload.goal or ""),

            level=str(payload.level or ""),

            days=str(payload.days or ""),

            duration=str(payload.duration or ""),

            time=str(payload.time or ""),

            notes=str(payload.notes or ""),

            equipment=str(payload.equipment or ""),

        ),

        workouts,

    )

    return VideoWorkoutPlanResponse(**plan)





@app.post("/auth/register", status_code=status.HTTP_202_ACCEPTED)

async def register(payload: RegisterRequest) -> dict[str, str]:

    email = payload.email.lower()

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

    update_doc = {

        "$set": {

            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,

            "email": email,
            "contact_number": mobile,
            "marketing_consent": payload.marketing_consent,
            "signup_source": payload.signup_source.strip() or "organic",
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

    await users_collection.update_one({"email": email}, update_doc, upsert=True)



    try:

        send_verification_email(email, code)

    except RuntimeError as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc



    logger.info("auth_register_code_sent email=%s", email)

    return {"message": "Verification code sent", "email": email}


@app.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(payload: ResendVerificationRequest) -> dict[str, str]:
    email = payload.email.lower()
    user = await users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(status_code=404, detail="No pending registration found for this email")
    if user.get("is_verified"):
        raise HTTPException(status_code=409, detail="Email is already registered")

    code = create_verification_code()
    now = datetime.now(timezone.utc)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "verification_code_hash": hash_password(code),
            "verification_code_expires_at": now + timedelta(minutes=10),
            "updated_at": now,
        }},
    )

    try:
        send_verification_email(email, code)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("auth_register_code_resent email=%s", email)
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

    code_hash = str(user.get("verification_code_hash") or "").strip()
    if not code_hash or not verify_password(payload.code, code_hash):

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





@app.post("/auth/forgot-password")

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





@app.post("/auth/verify-reset-code")

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





@app.post("/auth/reset-password")

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





@app.post("/auth/login", response_model=TokenResponse)

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





@app.post("/auth/firebase", response_model=TokenResponse)

async def firebase_login(payload: FirebaseAuthRequest, response: Response) -> TokenResponse:

    profile = _verify_firebase_id_token(payload.id_token)

    user = await _upsert_firebase_user(profile)

    logger.info("auth_firebase_login_success email=%s", str(profile.get("email") or "").lower())

    return await _issue_tokens(user, response)





@app.post("/auth/google", response_model=TokenResponse)

async def google_login(payload: GoogleAuthRequest, response: Response) -> TokenResponse:

    profile, provider = _resolve_google_profile(payload)

    if provider == "firebase":

        user = await _upsert_firebase_user(profile)

    else:

        user = await _upsert_google_user(profile)

    logger.info("auth_google_login_success provider=%s email=%s", provider, str(profile.get("email") or "").lower())

    return await _issue_tokens(user, response)





@app.post("/auth/refresh", response_model=TokenResponse)

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





@app.post("/auth/logout")

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





@app.get("/auth/validate")

async def validate_authorization(user: dict = Depends(_require_access_user)) -> dict[str, str]:

    return {"status": "ok"}





@app.get("/me", response_model=MeResponse)

async def get_me(user: dict = Depends(_require_access_user)) -> MeResponse:

    return MeResponse(**(await _serialize_me_record(user)))


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


@app.post("/me/push-token")
async def register_push_token(
    payload: PushTokenRequest,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    token = payload.token.strip()
    platform = payload.platform.strip().lower() or "unknown"
    now = datetime.now(timezone.utc)
    existing_tokens = [item for item in (user.get("push_tokens") or []) if isinstance(item, dict)]
    updated_tokens = [item for item in existing_tokens if item.get("token") != token]
    updated_tokens.append({"token": token, "platform": platform, "updated_at": now})
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"push_tokens": updated_tokens[-10:]}},
    )
    return {"registered": True}


@app.get("/me/notifications", response_model=AppNotificationListResponse)
async def list_app_notifications(user: dict = Depends(_require_access_user)) -> AppNotificationListResponse:
    records = [item for item in (user.get("app_notifications") or []) if isinstance(item, dict)]
    records.sort(key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return AppNotificationListResponse(items=[AppNotificationItem(**item) for item in records[:50]])


@app.delete("/me/notifications/{notification_id}")
async def delete_app_notification(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    result = await users_collection.update_one(
        {"_id": user["_id"]},
        {"$pull": {"app_notifications": {"id": notification_id}}},
    )
    return {"deleted": bool(result.modified_count)}


@app.patch("/me/notifications/{notification_id}/read")
async def mark_app_notification_read(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    result = await users_collection.update_one(
        {"_id": user["_id"], "app_notifications.id": notification_id},
        {"$set": {"app_notifications.$.read": True}},
    )
    return {"read": bool(result.modified_count)}


@app.get("/me/activity-notifications/dismissed")
async def list_dismissed_activity_notifications(
    user: dict = Depends(_require_access_user),
) -> dict[str, list[str]]:
    return {
        "ids": [
            str(item)
            for item in (user.get("dismissed_activity_notification_ids") or [])
            if str(item).strip()
        ]
    }


@app.delete("/me/activity-notifications/{notification_id}")
async def delete_activity_notification(
    notification_id: str,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    notification_id = notification_id.strip()
    if not notification_id:
        raise HTTPException(status_code=400, detail="Notification id is required")
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"dismissed_activity_notification_ids": notification_id}},
    )
    return {"deleted": True}


@app.delete("/me/push-token")
async def unregister_push_token(
    payload: PushTokenRequest,
    user: dict = Depends(_require_access_user),
) -> dict[str, bool]:
    token = payload.token.strip()
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$pull": {"push_tokens": {"token": token}}},
    )
    return {"removed": True}


@app.post("/jobs/trial-campaign")
async def run_trial_campaign(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    expected = str(getattr(settings, "cron_secret", "") or "").strip()
    supplied = str(authorization or "").replace("Bearer ", "", 1).strip()
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")
    return await process_trial_campaign(
        users_collection,
        challenge_memberships_collection,
        challenges_collection,
        coach_victor_threads_collection,
        nutrition_plans_collection,
    )


@app.post("/jobs/nutrition")
async def run_nutrition_job_queue(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=2, ge=1, le=10),
) -> dict[str, Any]:
    """Process durable MongoDB-backed nutrition jobs from a scheduler/cron call."""
    expected = str(getattr(settings, "cron_secret", "") or "").strip()
    supplied = str(authorization or "").replace("Bearer ", "", 1).strip()
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")

    processed = 0
    failed = 0
    for _ in range(limit):
        standard = await nutrition_plan_jobs_collection.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
            sort=[("created_at", 1)],
        )
        if standard:
            try:
                await _process_nutrition_plan_job(str(standard["_id"]), str(standard["user_id"]), standard.get("payload") or {}, str(standard.get("profile_hash") or ""))
                processed += 1
            except Exception:
                failed += 1
            continue

        progressive = await nutrition_progressive_plan_jobs_collection.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "generating_monday", "updated_at": datetime.now(timezone.utc)}},
            sort=[("created_at", 1)],
        )
        if not progressive:
            break
        try:
            await _process_progressive_nutrition_plan_job(str(progressive["_id"]), str(progressive["user_id"]), progressive.get("payload") or {}, str(progressive.get("profile_hash") or ""))
            processed += 1
        except Exception:
            failed += 1
    return {"processed": processed, "failed": failed}


@app.get("/me/onboarding", response_model=OnboardingStateResponse)
async def get_me_onboarding(user: dict = Depends(_require_access_user)) -> OnboardingStateResponse:
    return OnboardingStateResponse(**_serialize_onboarding_state(user))





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


@app.patch("/me/onboarding", response_model=OnboardingStateResponse)
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

    if payload.personalProfile is not None:
        personal_profile_update = payload.personalProfile.model_dump()
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



    updated_user = await users_collection.find_one({"_id": user["_id"]})

    if updated_user:

        await _sync_community_author_profile(updated_user)



    logger.info("profile_image_upload_success user_id=%s", user_id)

    return ProfileImageUploadResponse(image_url=image_url)





@app.patch("/me/subscription", response_model=MeResponse)

async def update_subscription(

    payload: UpdateSubscriptionRequest,

    user: dict = Depends(_require_access_user),

) -> MeResponse:

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





@app.get("/admin/me", response_model=AdminProfileResponse)

async def get_admin_profile(admin_user: dict = Depends(_require_admin_user)) -> AdminProfileResponse:

    return AdminProfileResponse(**_serialize_admin_profile_record(admin_user))





@app.patch("/admin/me", response_model=AdminProfileResponse)

async def update_admin_profile(

    payload: UpdateAdminProfileRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminProfileResponse:

    update_doc: dict = {}



    if payload.fullName is not None:

        update_doc["name"] = payload.fullName.strip()

    if payload.country is not None:

        update_doc["country"] = payload.country.strip()

    if payload.contactNumber is not None:

        update_doc["contact_number"] = payload.contactNumber.strip()



    if not update_doc:

        return AdminProfileResponse(**_serialize_admin_profile_record(admin_user))



    update_doc["updated_at"] = datetime.now(timezone.utc)

    await users_collection.update_one({"_id": admin_user["_id"]}, {"$set": update_doc})



    updated_admin = await users_collection.find_one({"_id": admin_user["_id"]})

    if not updated_admin:

        raise HTTPException(status_code=404, detail="Admin user not found")



    await _sync_community_author_profile(updated_admin)

    return AdminProfileResponse(**_serialize_admin_profile_record(updated_admin))





@app.post("/admin/me/profile-image", response_model=ProfileImageUploadResponse)

async def upload_admin_profile_image(

    payload: ProfileImageUploadRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> ProfileImageUploadResponse:

    user_id = str(admin_user["_id"])

    logger.info("admin_profile_image_upload_attempt user_id=%s", user_id)



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

        {"_id": admin_user["_id"]},

        {

            "$set": {

                "profile_image": image_url,

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )



    updated_admin = await users_collection.find_one({"_id": admin_user["_id"]})

    if updated_admin:

        await _sync_community_author_profile(updated_admin)



    logger.info("admin_profile_image_upload_success user_id=%s", user_id)

    return ProfileImageUploadResponse(image_url=image_url)





@app.post("/admin/me/change-password")

async def change_admin_password(

    payload: AdminChangePasswordRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    current_hash = str(admin_user.get("password_hash") or "")

    if not current_hash or not verify_password(payload.current_password, current_hash):

        raise HTTPException(status_code=400, detail="Current password is incorrect")



    if payload.current_password == payload.new_password:

        raise HTTPException(status_code=400, detail="New password must be different from the current password")



    await users_collection.update_one(

        {"_id": admin_user["_id"]},

        {

            "$set": {

                "password_hash": hash_password(payload.new_password),

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )



    return {"status": "success"}





@app.get("/me/body-metrics", response_model=BodyMetricsResponse)

async def get_body_metrics(user: dict = Depends(_require_access_user)) -> BodyMetricsResponse:

    metrics = dict(user.get("body_metrics") or {})

    return BodyMetricsResponse(

        age=str(metrics.get("age") or ""),

        height=str(metrics.get("height") or ""),

        weight=str(metrics.get("weight") or ""),

        gender=str(metrics.get("gender") or ""),

    )





@app.patch("/me/body-metrics", response_model=BodyMetricsResponse)

async def update_body_metrics(

    payload: UpdateBodyMetricsRequest,

    user: dict = Depends(_require_access_user),

) -> BodyMetricsResponse:

    next_metrics = dict(user.get("body_metrics") or {})



    if payload.age is not None:

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





@app.get("/longevity-os/dashboard", response_model=LongevityDashboardResponse)

async def longevity_dashboard(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityDashboardResponse:

    profile = await _get_or_create_longevity_profile(user)

    return await _serialize_longevity_dashboard(profile)





@app.get("/longevity-os/heal/categories", response_model=LongevityHealCategoriesResponse)

async def longevity_heal_categories(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityHealCategoriesResponse:

    profile = await _get_or_create_longevity_profile(user)

    return LongevityHealCategoriesResponse(

        categories=[LongevityHealCategoryResponse(**item) for item in profile.get("heal_categories") or []]

    )





@app.post("/longevity-os/heal/weekly-plan", response_model=LongevityWeeklyPlanResponse)

async def longevity_generate_weekly_plan(

    user: dict = Depends(_require_longevity_plan_access_user),

) -> LongevityWeeklyPlanResponse:

    profile = await _get_or_create_longevity_profile(user)

    metric_insights = await build_longevity_metric_insights(str(user["_id"]))

    heal_categories = [

        str(item.get("label") or "").strip()

        for item in profile.get("heal_categories") or []

        if str(item.get("label") or "").strip()

    ]

    habit_titles = [

        str(item.get("title") or "").strip()

        for item in profile.get("habits") or []

        if str(item.get("title") or "").strip() and bool(item.get("done"))

    ]

    plan = generate_longevity_weekly_plan(

        {

            "user_name": str(user.get("name") or "Victory member").strip(),

            "overview": metric_insights.get("overview") or {},

            "summary": metric_insights.get("summary") or {},

            "focus_areas": metric_insights.get("focus_areas") or [],

            "history": metric_insights.get("history") or {},

            "heal_categories": heal_categories,

            "completed_habits": habit_titles,

        }

    )

    response = LongevityWeeklyPlanResponse(

        message=plan.summary,

        plan_sections=[

            LongevityWeeklyPlanSectionResponse(

                id=section.id,

                title=section.title,

                summary=section.summary,

                actions=section.actions,

            )

            for section in plan.sections

        ],

        generated_at=datetime.now(timezone.utc),

    )

    await longevity_os_profiles_collection.update_one(

        {"_id": profile["_id"]},

        {"$set": {"weekly_plan": response.model_dump(), "updated_at": datetime.now(timezone.utc)}},

    )

    return response





@app.get("/longevity-os/habits", response_model=LongevityHabitsResponse)

async def longevity_habits(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityHabitsResponse:

    profile = await _get_or_create_longevity_profile(user)

    habits = [dict(item) for item in profile.get("habits") or []]

    return LongevityHabitsResponse(

        streak_days=_calculate_habit_streak(habits),

        habits=[LongevityHabitResponse(**item) for item in habits],

    )





@app.patch("/longevity-os/habits/{habit_id}", response_model=LongevityHabitsResponse)

async def longevity_update_habit(

    habit_id: str,

    payload: LongevityHabitUpdateRequest,

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityHabitsResponse:

    profile = await _get_or_create_longevity_profile(user)

    habits = [dict(item) for item in profile.get("habits") or []]

    updated = False

    for habit in habits:

        if str(habit.get("id") or "") == habit_id:

            habit["done"] = payload.done

            updated = True

            break

    if not updated:

        raise HTTPException(status_code=404, detail="Habit not found")



    await longevity_os_profiles_collection.update_one(

        {"_id": profile["_id"]},

        {"$set": {"habits": habits, "updated_at": datetime.now(timezone.utc)}},

    )

    return LongevityHabitsResponse(

        streak_days=_calculate_habit_streak(habits),

        habits=[LongevityHabitResponse(**item) for item in habits],

    )





@app.get("/longevity-os/masterclasses", response_model=LongevityMasterclassListResponse)

async def longevity_masterclasses(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityMasterclassListResponse:

    await _get_or_create_longevity_profile(user)

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    return LongevityMasterclassListResponse(

        items=[

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

            for item in items

        ]

    )





@app.get("/longevity-os/circles", response_model=LongevityCircleListResponse)

async def longevity_circles(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityCircleListResponse:

    profile = await _get_or_create_longevity_profile(user)

    return LongevityCircleListResponse(

        items=[LongevityCircleResponse(**item) for item in profile.get("circles") or []]

    )





@app.get("/content/privacy-policy", response_model=PrivacyPolicyResponse)

async def get_privacy_policy() -> PrivacyPolicyResponse:

    record = await _ensure_privacy_policy_record()

    return _serialize_privacy_policy_record(record)





@app.get("/admin/content/privacy-policy", response_model=PrivacyPolicyResponse)

async def admin_get_privacy_policy(_: dict = Depends(_require_admin_user)) -> PrivacyPolicyResponse:

    record = await _ensure_privacy_policy_record()

    return _serialize_privacy_policy_record(record)





@app.put("/admin/content/privacy-policy", response_model=PrivacyPolicyResponse)

async def admin_update_privacy_policy(

    payload: UpdatePrivacyPolicyRequest,

    _: dict = Depends(_require_admin_user),

) -> PrivacyPolicyResponse:

    record = await upsert_content_record(

        key=PRIVACY_POLICY_KEY,

        title=payload.title,

        html_content=payload.html_content,

    )

    if not record:

        raise HTTPException(status_code=500, detail="Privacy policy could not be saved")

    return _serialize_privacy_policy_record(record)





@app.get("/admin/content/terms-condition", response_model=TermsConditionResponse)

async def admin_get_terms_condition(_: dict = Depends(_require_admin_user)) -> TermsConditionResponse:

    record = await _ensure_terms_condition_record()

    return _serialize_terms_condition_record(record)





@app.put("/admin/content/terms-condition", response_model=TermsConditionResponse)

async def admin_update_terms_condition(

    payload: UpdateTermsConditionRequest,

    _: dict = Depends(_require_admin_user),

) -> TermsConditionResponse:

    record = await upsert_content_record(

        key=TERMS_CONDITION_KEY,

        title=payload.title,

        html_content=payload.html_content,

    )

    if not record:

        raise HTTPException(status_code=500, detail="Terms & Conditions could not be saved")

    return _serialize_terms_condition_record(record)





@app.get("/content/about-us", response_model=AboutUsResponse)

async def get_about_us() -> AboutUsResponse:

    record = await _ensure_about_us_record()

    return _serialize_about_us_record(record)





@app.get("/content/onboarding", response_model=OnboardingContentResponse)

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





@app.get("/admin/content/about-us", response_model=AboutUsResponse)

async def admin_get_about_us(_: dict = Depends(_require_admin_user)) -> AboutUsResponse:

    record = await _ensure_about_us_record()

    return _serialize_about_us_record(record)





@app.put("/admin/content/about-us", response_model=AboutUsResponse)

async def admin_update_about_us(

    payload: UpdateAboutUsRequest,

    _: dict = Depends(_require_admin_user),

) -> AboutUsResponse:

    record = await upsert_content_record(

        key=ABOUT_US_KEY,

        title=payload.title,

        html_content=payload.html_content,

    )

    if not record:

        raise HTTPException(status_code=500, detail="About Us could not be saved")

    return _serialize_about_us_record(record)





@app.get("/admin/faqs", response_model=FAQListResponse)

async def admin_list_faqs(

    _: dict = Depends(_require_admin_user),

) -> FAQListResponse:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    return FAQListResponse(items=[FAQItemResponse(**item) for item in items])





@app.post("/admin/faqs", response_model=FAQItemResponse, status_code=status.HTTP_201_CREATED)

async def admin_create_faq(

    payload: FAQRequest,

    _: dict = Depends(_require_admin_user),

) -> FAQItemResponse:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    faq = {

        "id": uuid4().hex,

        "question": payload.question.strip(),

        "answer": payload.answer.strip(),

    }

    items.insert(0, faq)

    await _replace_items_record(DASHBOARD_FAQS_KEY, items)

    return FAQItemResponse(**faq)





@app.patch("/admin/faqs/{faq_id}", response_model=FAQItemResponse)

async def admin_update_faq(

    faq_id: str,

    payload: FAQRequest,

    _: dict = Depends(_require_admin_user),

) -> FAQItemResponse:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    updated_faq: dict | None = None

    for item in items:

        if item["id"] == faq_id:

            item["question"] = payload.question.strip()

            item["answer"] = payload.answer.strip()

            updated_faq = item

            break

    if not updated_faq:

        raise HTTPException(status_code=404, detail="FAQ not found")



    await _replace_items_record(DASHBOARD_FAQS_KEY, items)

    return FAQItemResponse(**updated_faq)





@app.delete("/admin/faqs/{faq_id}")

async def admin_delete_faq(

    faq_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    items = [_serialize_faq_item(item) for item in await _get_dashboard_faq_items()]

    next_items = [item for item in items if item["id"] != faq_id]

    if len(next_items) == len(items):

        raise HTTPException(status_code=404, detail="FAQ not found")



    await _replace_items_record(DASHBOARD_FAQS_KEY, next_items)

    return {"status": "success", "message": "FAQ deleted"}





@app.get("/admin/notifications", response_model=AdminNotificationListResponse)

async def admin_list_notifications(

    _: dict = Depends(_require_admin_user),

) -> AdminNotificationListResponse:

    items = [_serialize_admin_notification_item(item) for item in await _get_dashboard_notification_items()]

    items.sort(key=lambda item: item["createdAt"], reverse=True)

    return AdminNotificationListResponse(items=[AdminNotificationItem(**item) for item in items])





@app.post("/admin/notifications/test")
async def admin_send_test_notification(
    payload: AdminTestNotificationRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> dict[str, object]:
    email = payload.email.strip().lower()
    user = await users_collection.find_one({"email": email, "is_admin": {"$ne": True}})
    if not user:
        raise HTTPException(status_code=404, detail="App user not found for that email")
    tokens = [item for item in (user.get("push_tokens") or []) if isinstance(item, dict) and str(item.get("token") or "").strip()]
    delivery = await notify_user(
        users_collection,
        user,
        "Victory Fitness test notification",
        "Push notifications are connected successfully.",
        "test_notification",
        {"type": "test_notification", "route": "/notifications"},
    )
    return {"status": delivery.get("status", "sent"), "email": email, "registeredDevices": len(tokens), "delivery": delivery}


@app.patch("/admin/notifications/{notification_id}", response_model=AdminNotificationItem)
async def admin_update_notification(

    notification_id: str,

    payload: AdminNotificationUpdateRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminNotificationItem:

    items = [_serialize_admin_notification_item(item) for item in await _get_dashboard_notification_items()]

    updated_item: dict | None = None

    for item in items:

        if item["id"] == notification_id:

            item["read"] = payload.read

            updated_item = item

            break

    if not updated_item:

        raise HTTPException(status_code=404, detail="Notification not found")



    await _replace_items_record(DASHBOARD_NOTIFICATIONS_KEY, items)

    return AdminNotificationItem(**updated_item)





@app.patch("/admin/notifications/actions/read-all", response_model=AdminNotificationListResponse)

async def admin_mark_all_notifications_read(

    _: dict = Depends(_require_admin_user),

) -> AdminNotificationListResponse:

    items = [_serialize_admin_notification_item(item) for item in await _get_dashboard_notification_items()]

    for item in items:

        item["read"] = True

    await _replace_items_record(DASHBOARD_NOTIFICATIONS_KEY, items)

    return AdminNotificationListResponse(items=[AdminNotificationItem(**item) for item in items])





@app.get("/admin/subscription-plans", response_model=AdminSubscriptionPlanListResponse)

async def admin_list_subscription_plans(

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriptionPlanListResponse:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    return AdminSubscriptionPlanListResponse(items=[AdminSubscriptionPlanItem(**item) for item in items])





@app.get("/subscription-plans", response_model=AppSubscriptionPlanListResponse)

async def list_subscription_plans() -> AppSubscriptionPlanListResponse:

    items = [_serialize_app_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    return AppSubscriptionPlanListResponse(items=[AppSubscriptionPlanItem(**item) for item in items])





@app.post("/admin/subscription-plans", response_model=AdminSubscriptionPlanItem, status_code=status.HTTP_201_CREATED)

async def admin_create_subscription_plan(

    payload: AdminSubscriptionPlanRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriptionPlanItem:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    plan = _serialize_admin_subscription_plan_item(

        {

            "id": uuid4().hex,

            **payload.model_dump(),

        }

    )

    items.append(plan)

    await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, items)

    return AdminSubscriptionPlanItem(**plan)





@app.patch("/admin/subscription-plans/{plan_id}", response_model=AdminSubscriptionPlanItem)

async def admin_update_subscription_plan(

    plan_id: str,

    payload: AdminSubscriptionPlanRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriptionPlanItem:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    updated_plan: dict | None = None

    for index, item in enumerate(items):

        if item["id"] == plan_id:

            items[index] = _serialize_admin_subscription_plan_item({"id": plan_id, **payload.model_dump()})

            updated_plan = items[index]

            break

    if not updated_plan:

        raise HTTPException(status_code=404, detail="Subscription plan not found")



    await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, items)

    return AdminSubscriptionPlanItem(**updated_plan)





@app.delete("/admin/subscription-plans/{plan_id}")

async def admin_delete_subscription_plan(

    plan_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    next_items = [item for item in items if item["id"] != plan_id]

    if len(next_items) == len(items):

        raise HTTPException(status_code=404, detail="Subscription plan not found")



    await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, next_items)

    return {"status": "success", "message": "Subscription plan deleted"}





@app.get("/admin/masterclasses", response_model=AdminMasterclassListResponse)

async def admin_list_masterclasses(

    _: dict = Depends(_require_admin_user),

) -> AdminMasterclassListResponse:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    return AdminMasterclassListResponse(items=[AdminMasterclassItem(**item) for item in items])





@app.post("/admin/masterclasses", response_model=AdminMasterclassItem, status_code=status.HTTP_201_CREATED)

async def admin_create_masterclass(

    payload: AdminMasterclassRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminMasterclassItem:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    payload_data = payload.model_dump()

    try:

        payload_data["videoUrl"] = await _prepare_masterclass_video_payload(payload, str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.audio_base64:

        try:

            payload_data["audioUrl"] = _upload_masterclass_audio_to_s3(

                str(admin_user["_id"]),

                payload.audio_base64,

                payload.audio_mime_type,

                payload.audio_file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Masterclass audio upload failed: {exc}") from exc

    elif str(payload.audioUrl or "").strip():

        audio_value = str(payload.audioUrl or "").strip()

        if _looks_like_remote_media_url(audio_value):

            try:

                payload_data["audioUrl"] = _download_remote_media_to_storage(

                    "masterclass-audio",

                    str(admin_user["_id"]),

                    audio_value,

                    upload_log_label="audio",

                )

            except ValueError as exc:

                raise HTTPException(status_code=400, detail=str(exc)) from exc

            except Exception as exc:

                raise HTTPException(status_code=500, detail=f"Masterclass audio download failed: {exc}") from exc

        else:

            payload_data["audioUrl"] = audio_value

    masterclass = _serialize_admin_masterclass_item(

        {

            "id": uuid4().hex,

            **payload_data,

        }

    )

    items.insert(0, masterclass)

    await _replace_items_record(DASHBOARD_MASTERCLASSES_KEY, items)

    return AdminMasterclassItem(**masterclass)





@app.patch("/admin/masterclasses/{masterclass_id}", response_model=AdminMasterclassItem)

async def admin_update_masterclass(

    masterclass_id: str,

    payload: AdminMasterclassRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminMasterclassItem:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    updated_masterclass: dict | None = None

    payload_data = payload.model_dump()

    try:

        payload_data["videoUrl"] = await _prepare_masterclass_video_payload(payload, str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.clear_audio:

        payload_data["audioUrl"] = ""

    elif payload.audio_base64:

        try:

            payload_data["audioUrl"] = _upload_masterclass_audio_to_s3(

                str(admin_user["_id"]),

                payload.audio_base64,

                payload.audio_mime_type,

                payload.audio_file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Masterclass audio upload failed: {exc}") from exc

    elif str(payload.audioUrl or "").strip():

        audio_value = str(payload.audioUrl or "").strip()

        if _looks_like_remote_media_url(audio_value):

            try:

                payload_data["audioUrl"] = _download_remote_media_to_storage(

                    "masterclass-audio",

                    str(admin_user["_id"]),

                    audio_value,

                    upload_log_label="audio",

                )

            except ValueError as exc:

                raise HTTPException(status_code=400, detail=str(exc)) from exc

            except Exception as exc:

                raise HTTPException(status_code=500, detail=f"Masterclass audio download failed: {exc}") from exc

        else:

            payload_data["audioUrl"] = audio_value

    for index, item in enumerate(items):

        if item["id"] == masterclass_id:

            items[index] = _serialize_admin_masterclass_item({"id": masterclass_id, **payload_data})

            updated_masterclass = items[index]

            break

    if not updated_masterclass:

        raise HTTPException(status_code=404, detail="Masterclass not found")



    await _replace_items_record(DASHBOARD_MASTERCLASSES_KEY, items)

    return AdminMasterclassItem(**updated_masterclass)





@app.delete("/admin/masterclasses/{masterclass_id}")

async def admin_delete_masterclass(

    masterclass_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    items = [_serialize_admin_masterclass_item(item) for item in await _get_dashboard_masterclass_items()]

    next_items = [item for item in items if item["id"] != masterclass_id]

    if len(next_items) == len(items):

        raise HTTPException(status_code=404, detail="Masterclass not found")



    await _replace_items_record(DASHBOARD_MASTERCLASSES_KEY, next_items)

    return {"status": "success", "message": "Masterclass deleted"}





@app.get("/admin/subscribers", response_model=AdminSubscriberListResponse)

async def admin_list_subscribers(

    page: int = 1,

    limit: int = 100,

    query: str | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriberListResponse:

    records = await users_collection.find({"is_admin": {"$ne": True}}).to_list(length=None)

    subscribers = [

        _serialize_admin_subscriber_record(record)

        for record in records

        if _build_subscription_summary(record)["tier"] != "NONE"

    ]



    normalized_query = str(query or "").strip().lower()

    if normalized_query:

        subscribers = [

            item

            for item in subscribers

            if normalized_query in str(item["fullName"]).lower()

            or normalized_query in str(item["email"]).lower()

            or normalized_query in str(item["contactNumber"]).lower()

            or normalized_query in str(item["country"]).lower()

            or normalized_query in str(item["subscriptionTier"]).lower()

        ]



    subscribers.sort(key=lambda item: item["joinedDate"], reverse=True)

    safe_page = max(page, 1)

    safe_limit = max(limit, 1)

    start = (safe_page - 1) * safe_limit

    paged = subscribers[start:start + safe_limit]

    return AdminSubscriberListResponse(

        total=len(subscribers),

        page=safe_page,

        limit=safe_limit,

        users=[AdminSubscriberItem(**item) for item in paged],

    )





@app.post("/applications", response_model=CoachingApplicationResponse, status_code=status.HTTP_201_CREATED)

async def create_coaching_application(

    payload: CoachingApplicationCreateRequest,

    user: dict = Depends(_require_application_access_user),

) -> CoachingApplicationResponse:

    if not payload.agreement_accepted:

        raise HTTPException(status_code=400, detail="You must accept the agreement before submitting")



    now = datetime.now(timezone.utc)

    document = {

        "_id": ObjectId(),

        "user_id": str(user["_id"]),

        "first_name": payload.first_name.strip(),

        "last_name": payload.last_name.strip(),

        "email": payload.email.lower().strip(),

        "phone_number": str(payload.phone_number or "").strip(),

        "goal": payload.goal.strip(),

        "obstacle": payload.obstacle.strip(),

        "investment": payload.investment.strip(),

        "commitment": payload.commitment.strip(),

        "injury": payload.injury.strip(),

        "additional_notes": str(payload.additional_notes or "").strip(),

        "agreement_accepted": True,

        "status": "NEW",

        "admin_notes": "",

        "created_at": now,

        "updated_at": now,

    }

    await coaching_applications_collection.insert_one(document)

    return _serialize_coaching_application_record(document)





@app.post("/support/messages", response_model=SupportMessageResponse, status_code=status.HTTP_201_CREATED)

async def create_support_message(

    payload: SupportMessageCreateRequest,

    user: dict = Depends(_require_access_user),

) -> SupportMessageResponse:

    now = datetime.now(timezone.utc)

    document = {

        "_id": ObjectId(),

        "user_id": str(user["_id"]),

        "user_name": str(user.get("name") or "Member").strip() or "Member",

        "user_email": str(user.get("email") or "").strip().lower(),

        "subject": payload.subject.strip(),

        "message": payload.message.strip(),

        "status": "OPEN",

        "admin_notes": "",

        "created_at": now,

        "updated_at": now,

    }

    await support_messages_collection.insert_one(document)

    return _serialize_support_message_record(document)





@app.get("/admin/applications", response_model=CoachingApplicationListResponse)

async def admin_get_coaching_applications(_: dict = Depends(_require_admin_user)) -> CoachingApplicationListResponse:

    records = await coaching_applications_collection.find(

        {},

        sort=[("created_at", -1), ("_id", -1)],

        limit=300,

    ).to_list(length=300)

    return CoachingApplicationListResponse(

        applications=[_serialize_coaching_application_record(record) for record in records]

    )





@app.patch("/admin/applications/{application_id}", response_model=CoachingApplicationResponse)

async def admin_update_coaching_application(

    application_id: str,

    payload: AdminCoachingApplicationUpdateRequest,

    _: dict = Depends(_require_admin_user),

) -> CoachingApplicationResponse:

    try:

        object_id = ObjectId(application_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid application id") from exc



    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    if payload.status is not None:

        update_doc["status"] = payload.status.strip().upper()

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()



    await coaching_applications_collection.update_one({"_id": object_id}, {"$set": update_doc})

    record = await coaching_applications_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Application not found")

    return _serialize_coaching_application_record(record)





@app.get("/admin/support/messages", response_model=SupportMessageListResponse)

async def admin_get_support_messages(_: dict = Depends(_require_admin_user)) -> SupportMessageListResponse:

    records = await support_messages_collection.find(

        {},

        sort=[("created_at", -1), ("_id", -1)],

        limit=300,

    ).to_list(length=300)

    return SupportMessageListResponse(

        messages=[_serialize_support_message_record(record) for record in records]

    )





@app.patch("/admin/support/messages/{message_id}", response_model=SupportMessageResponse)

async def admin_update_support_message(

    message_id: str,

    payload: AdminSupportMessageUpdateRequest,

    _: dict = Depends(_require_admin_user),

) -> SupportMessageResponse:

    try:

        object_id = ObjectId(message_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid support message id") from exc



    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    if payload.status is not None:

        update_doc["status"] = payload.status.strip().upper()

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()



    await support_messages_collection.update_one({"_id": object_id}, {"$set": update_doc})

    record = await support_messages_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Support message not found")

    return _serialize_support_message_record(record)





@app.get("/community/posts", response_model=CommunityPostListResponse)

async def get_community_posts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(_require_community_access_user),
) -> CommunityPostListResponse:

    allowed_audiences = _get_allowed_community_audiences(user)

    query = {"audience": {"$in": allowed_audiences}}
    total = await community_posts_collection.count_documents(query)
    records = await community_posts_collection.find(

        query,

        sort=[("created_at", -1), ("_id", -1)],

        skip=(page - 1) * limit,
        limit=limit,

    ).to_list(length=limit)

    posts = await _serialize_community_post_records(records, user, include_reactions=False)

    return CommunityPostListResponse(

        posts=[CommunityPostResponse(**post) for post in posts], page=page, limit=limit, total=total, has_more=page * limit < total

    )





@app.post("/community/posts", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)

async def create_community_post(

    request: Request,

    user: dict = Depends(_require_community_access_user),

) -> CommunityPostResponse:

    content = ""

    image_base64 = ""

    video_base64 = ""

    external_video_url_raw = ""

    mime_type = "image/jpeg"

    file_name: str | None = None

    image_url = ""

    video_url = ""

    audio_url = ""



    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type:

        form = await request.form()

        content = str(form.get("content") or "").strip()

        external_video_url_raw = str(form.get("external_video_url") or "").strip()

        mime_type = str(form.get("mime_type") or mime_type).strip() or mime_type

        file_name = str(form.get("file_name") or "").strip() or None



        media_file = form.get("media_file") or form.get("media")

        if media_file is not None and hasattr(media_file, "read") and hasattr(media_file, "filename"):

            try:

                payload = await media_file.read()

                if payload:

                    file_name = media_file.filename or file_name

                    mime_type = str(media_file.content_type or mime_type).strip().lower() or mime_type

                    if mime_type.startswith("image/"):

                        if len(payload) > COMMUNITY_IMAGE_MAX_SIZE_BYTES:

                            raise HTTPException(

                                status_code=400,

                                detail=f"Image must be {COMMUNITY_IMAGE_MAX_SIZE_BYTES // (1024 * 1024)}MB or smaller",

                            )

                        try:

                            image_url = _upload_binary_bytes_to_s3(

                                "community-images",

                                str(user["_id"]),

                                payload,

                                mime_type,

                                file_name,

                                allowed_types={

                                    "image/jpeg": ".jpg",

                                    "image/jpg": ".jpg",

                                    "image/png": ".png",

                                    "image/webp": ".webp",

                                },

                                invalid_type_message="Only JPEG, PNG, and WEBP images are supported",

                                max_size_bytes=COMMUNITY_IMAGE_MAX_SIZE_BYTES,

                                upload_log_label="image",

                            )

                        except ValueError as exc:

                            raise HTTPException(status_code=400, detail=str(exc)) from exc

                        except Exception as exc:

                            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

                    elif mime_type.startswith("video/"):

                        if len(payload) > COMMUNITY_VIDEO_MAX_SIZE_BYTES:

                            raise HTTPException(

                                status_code=400,

                                detail=f"Video must be {COMMUNITY_VIDEO_MAX_SIZE_BYTES // (1024 * 1024)}MB or smaller",

                            )

                        try:

                            video_url = _upload_binary_bytes_to_s3(

                                "community-videos",

                                str(user["_id"]),

                                payload,

                                mime_type,

                                file_name,

                                allowed_types={

                                    "video/mp4": ".mp4",

                                    "video/quicktime": ".mov",

                                    "video/webm": ".webm",

                                },

                                invalid_type_message="Only MP4, MOV, and WEBM videos are supported",

                                max_size_bytes=COMMUNITY_VIDEO_MAX_SIZE_BYTES,

                                upload_log_label="video",

                            )

                        except ValueError as exc:

                            raise HTTPException(status_code=400, detail=str(exc)) from exc

                        except Exception as exc:

                            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

                    else:

                        raise HTTPException(status_code=400, detail="Only image or video files are supported")

            finally:

                close_method = getattr(media_file, "close", None)

                if callable(close_method):

                    close_result = close_method()

                    if inspect.isawaitable(close_result):

                        await close_result

        image_base64 = str(form.get("image_base64") or "").strip()

        video_base64 = str(form.get("video_base64") or "").strip()

    else:

        try:

            raw_payload = await request.json()

        except Exception:

            raw_payload = {}

        payload = CommunityPostCreateRequest.model_validate(raw_payload)

        content = str(payload.content or "").strip()

        image_base64 = str(payload.image_base64 or "").strip()

        video_base64 = str(payload.video_base64 or "").strip()

        external_video_url_raw = str(payload.external_video_url or "").strip()

        mime_type = str(payload.mime_type or mime_type).strip() or mime_type

        file_name = str(payload.file_name or "").strip() or None



    external_video_url = ""

    if external_video_url_raw:

        try:

            external_video_url = _resolve_media_url_to_storage(

                external_video_url_raw,

                folder_name="community-videos",

                user_id=str(user["_id"]),

                upload_log_label="video",

                allow_embed_urls=True,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc



    if not content and not image_url and not video_url and not image_base64 and not video_base64 and not external_video_url:

        raise HTTPException(status_code=400, detail="Post content, image, video, or supported video link is required.")



    now = datetime.now(timezone.utc)

    if image_base64 and not image_url:

        try:

            image_url = _upload_community_image_to_s3(

                str(user["_id"]),

                image_base64,

                mime_type,

                file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

    elif video_base64 and not video_url:

        try:

            video_url = _upload_community_video_to_s3(

                str(user["_id"]),

                video_base64,

                mime_type,

                file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

    elif external_video_url:

        video_url = external_video_url



    document = {

        "_id": ObjectId(),

        "author_id": str(user["_id"]),

        "audience": _get_community_post_audience_for_user(user),

        "content": content,

        "image_url": image_url,

        "video_url": video_url,

        "like_count": 0,

        "comment_count": 0,

        "created_at": now,

        "updated_at": now,

    }

    await community_posts_collection.insert_one(document)

    serialized = await _serialize_community_post_records([document], user, include_reactions=False)

    return CommunityPostResponse(**serialized[0])





@app.delete("/community/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)

async def delete_own_community_post(

    post_id: str,

    user: dict = Depends(_require_community_access_user),

) -> Response:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    if not _can_delete_community_post(record, user):

        raise HTTPException(status_code=403, detail="You can only delete your own post")



    await community_posts_collection.delete_one({"_id": record["_id"]})

    _delete_community_post_media(record)

    await community_comments_collection.delete_many({"post_id": str(record["_id"])})

    await community_reactions_collection.delete_many({"post_id": str(record["_id"])})

    return Response(status_code=status.HTTP_204_NO_CONTENT)





@app.get("/community/posts/{post_id}/comments", response_model=list[CommunityCommentResponse])

async def get_community_post_comments(

    post_id: str,

    user: dict = Depends(_require_community_access_user),

) -> list[CommunityCommentResponse]:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    comments = await _load_community_comments([record], limit_per_post=200)

    return [CommunityCommentResponse(**comment) for comment in comments.get(str(record["_id"]), [])]





@app.post("/community/posts/{post_id}/comments", response_model=CommunityCommentResponse, status_code=status.HTTP_201_CREATED)

async def create_community_post_comment(

    post_id: str,

    payload: CommunityCommentCreateRequest,

    user: dict = Depends(_require_community_access_user),

) -> CommunityCommentResponse:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    now = datetime.now(timezone.utc)

    comment_document = {

        "_id": ObjectId(),

        "post_id": str(record["_id"]),

        "author_id": str(user["_id"]),

        "content": payload.content.strip(),

        "created_at": now,

    }

    await community_comments_collection.insert_one(comment_document)

    await community_posts_collection.update_one(

        {"_id": record["_id"]},

        {

            "$inc": {"comment_count": 1},

            "$set": {"updated_at": now},

        },

    )

    return CommunityCommentResponse(**_serialize_community_comment_record(comment_document, user))





@app.post("/community/posts/{post_id}/reactions/toggle", response_model=CommunityReactionToggleResponse)

async def toggle_community_post_reaction(

    post_id: str,

    user: dict = Depends(_require_community_access_user),

) -> CommunityReactionToggleResponse:

    record = await _get_community_post_or_404(post_id)

    _ensure_community_post_access(record, user)

    reaction_filter = {"post_id": str(record["_id"]), "user_id": str(user["_id"])}

    existing = await community_reactions_collection.find_one(reaction_filter)

    now = datetime.now(timezone.utc)



    if existing:

        await community_reactions_collection.delete_one({"_id": existing["_id"]})

        await community_posts_collection.update_one(

            {"_id": record["_id"]},

            {

                "$inc": {"like_count": -1},

                "$set": {"updated_at": now},

            },

        )

        viewer_has_liked = False

    else:

        await community_reactions_collection.insert_one(

            {

                "_id": ObjectId(),

                "post_id": str(record["_id"]),

                "user_id": str(user["_id"]),

                "created_at": now,

            }

        )

        await community_posts_collection.update_one(

            {"_id": record["_id"]},

            {

                "$inc": {"like_count": 1},

                "$set": {"updated_at": now},

            },

        )

        viewer_has_liked = True



    updated_record = await community_posts_collection.find_one({"_id": record["_id"]})

    like_count = int((updated_record or {}).get("like_count") or 0)

    if like_count < 0:

        like_count = 0

        await community_posts_collection.update_one({"_id": record["_id"]}, {"$set": {"like_count": 0}})



    return CommunityReactionToggleResponse(

        post_id=str(record["_id"]),

        like_count=like_count,

        viewer_has_liked=viewer_has_liked,

    )





@app.get("/admin/community/posts", response_model=CommunityPostListResponse)

async def admin_get_community_posts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=160),
    _: dict = Depends(_require_admin_user),
) -> CommunityPostListResponse:

    query: dict[str, Any] = {}
    if search.strip():
        query["$or"] = [
            {"content": {"$regex": search.strip(), "$options": "i"}},
            {"author_name": {"$regex": search.strip(), "$options": "i"}},
        ]
    total = await community_posts_collection.count_documents(query)
    records = await community_posts_collection.find(

        query,

        sort=[("created_at", -1), ("_id", -1)],

        skip=(page - 1) * limit,
        limit=limit,

    ).to_list(length=limit)

    posts = await _serialize_community_post_records(records, None, comment_limit_per_post=200, include_reactions=True)

    return CommunityPostListResponse(

        posts=[CommunityPostResponse(**post) for post in posts], page=page, limit=limit, total=total, has_more=page * limit < total

    )


@app.get("/admin/community/feed", response_model=CommunityPostListResponse)
async def admin_get_community_feed(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=160),
    admin_user: dict = Depends(_require_admin_user),
) -> CommunityPostListResponse:
    """Feed section endpoint kept separate from broadcast and analytics sections."""
    return await admin_get_community_posts(page=page, limit=limit, search=search, _=admin_user)





@app.post("/admin/community/posts", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)

async def admin_create_community_post(

    payload: AdminCommunityPostCreateRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> CommunityPostResponse:

    external_video_url = ""

    if payload.external_video_url:

        try:

            external_video_url = _resolve_media_url_to_storage(

                payload.external_video_url,

                folder_name="community-videos",

                user_id=str(admin_user["_id"]),

                upload_log_label="video",

                allow_embed_urls=True,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc



    now = datetime.now(timezone.utc)

    image_url = ""

    video_url = ""

    if payload.image_base64:

        try:

            image_url = _upload_community_image_to_s3(

                str(admin_user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

    elif payload.video_base64:

        try:

            video_url = _upload_community_video_to_s3(

                str(admin_user["_id"]),

                payload.video_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

    elif payload.audio_base64:
        try:
            audio_url = _upload_community_audio_to_s3(
                str(admin_user["_id"]), payload.audio_base64, payload.mime_type, payload.file_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Community audio upload failed: {exc}") from exc

    elif external_video_url:

        video_url = external_video_url

    document = {

        "_id": ObjectId(),

        "author_id": str(admin_user["_id"]),

        "audience": payload.audience.strip(),

        "content": payload.content.strip(),

        "image_url": image_url,

        "video_url": video_url,

        "audio_url": audio_url,

        "like_count": 0,

        "comment_count": 0,

        "created_at": now,

        "updated_at": now,

    }

    await community_posts_collection.insert_one(document)

    serialized = await _serialize_community_post_records([document], admin_user, comment_limit_per_post=200, include_reactions=True)

    return CommunityPostResponse(**serialized[0])





@app.post("/admin/community/broadcast", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)
async def admin_send_community_broadcast(
    payload: AdminCommunityPostCreateRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> CommunityPostResponse:
    """Broadcast section endpoint for publishing a tier-targeted community post."""
    result = await admin_create_community_post(payload, admin_user)
    await _record_admin_audit(admin_user, "broadcast_created", "community_post", result.id, {"audience": payload.audience})
    return result


@app.patch("/admin/community/posts/{post_id}", response_model=CommunityPostResponse)

async def admin_update_community_post(

    post_id: str,

    payload: AdminCommunityPostUpdateRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> CommunityPostResponse:

    try:

        object_id = ObjectId(post_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid community post id") from exc



    existing_record = await community_posts_collection.find_one({"_id": object_id})

    if not existing_record:

        raise HTTPException(status_code=404, detail="Community post not found")



    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    external_video_url = None

    if payload.external_video_url is not None:

        external_raw = str(payload.external_video_url or "").strip()

        if external_raw:

            try:

                external_video_url = _resolve_media_url_to_storage(

                    external_raw,

                    folder_name="community-videos",

                    user_id=str(existing_record.get("author_id") or ""),

                    upload_log_label="video",

                    allow_embed_urls=True,

                )

            except ValueError as exc:

                raise HTTPException(status_code=400, detail=str(exc)) from exc

        else:

            external_video_url = ""

    if payload.content is not None:

        update_doc["content"] = payload.content.strip()

    if payload.audience is not None:

        update_doc["audience"] = payload.audience.strip()

    if payload.flagged is not None:
        update_doc["flagged"] = payload.flagged
        update_doc["flag_reason"] = payload.flag_reason.strip() if payload.flag_reason else ""

    if payload.moderation_status is not None:
        update_doc["moderation_status"] = payload.moderation_status
    if payload.moderator_notes is not None:
        update_doc["moderator_notes"] = payload.moderator_notes.strip()

    if payload.clear_image or payload.clear_media:

        update_doc["image_url"] = ""

        update_doc["video_url"] = ""

    elif payload.image_base64:

        try:

            update_doc["image_url"] = _upload_community_image_to_s3(

                str(existing_record.get("author_id") or ""),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

            update_doc["video_url"] = ""

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community image upload failed: {exc}") from exc

    elif payload.video_base64:

        try:

            update_doc["video_url"] = _upload_community_video_to_s3(

                str(existing_record.get("author_id") or ""),

                payload.video_base64,

                payload.mime_type,

                payload.file_name,

            )

            update_doc["image_url"] = ""

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Community video upload failed: {exc}") from exc

    elif external_video_url is not None:

        update_doc["video_url"] = external_video_url

        if external_video_url:

            update_doc["image_url"] = ""



    await community_posts_collection.update_one({"_id": object_id}, {"$set": update_doc})

    updated_record = await community_posts_collection.find_one({"_id": object_id})

    if not updated_record:

        raise HTTPException(status_code=500, detail="Community post could not be updated")

    serialized = await _serialize_community_post_records([updated_record], None, comment_limit_per_post=200, include_reactions=True)
    await _record_admin_audit(admin_user, "community_post_updated", "community_post", post_id, {"flagged": payload.flagged, "flag_reason": payload.flag_reason})

    return CommunityPostResponse(**serialized[0])





@app.delete("/admin/community/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)

async def admin_delete_community_post(

    post_id: str,

    _: dict = Depends(_require_admin_user),

) -> Response:

    try:

        object_id = ObjectId(post_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid community post id") from exc



    record = await community_posts_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Community post not found")

    delete_result = await community_posts_collection.delete_one({"_id": object_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Community post not found")

    _delete_community_post_media(record)

    await community_comments_collection.delete_many({"post_id": str(object_id)})

    await community_reactions_collection.delete_many({"post_id": str(object_id)})



    return Response(status_code=status.HTTP_204_NO_CONTENT)





@app.get("/challenges/overview", response_model=ChallengeOverviewResponse)

async def get_challenge_overview(

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeOverviewResponse:

    return await _build_challenge_overview_response(user)





@app.get("/challenges/{challenge_id}", response_model=ChallengeDetailResponse)

async def get_challenge_detail(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeDetailResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await challenge_memberships_collection.find_one(

        {"challenge_id": challenge_id, "user_id": str(user["_id"])}

    )

    if membership and str(membership.get("status") or "").upper() == "ACTIVE":

        total_days = max(int(challenge.get("duration_days") or 0), 1)

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

                if elapsed_days >= total_days:

                    now = datetime.now(timezone.utc)

                    await challenge_memberships_collection.update_one(

                        {"_id": membership["_id"]},

                        {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                    )

                    membership = dict(membership)

                    membership["status"] = "COMPLETED"

                    membership["completed_at"] = now

            except ValueError:

                pass

    challenge_status = str(challenge.get("status") or "ACTIVE").upper()

    membership_status = str((membership or {}).get("status") or "NOT_JOINED").upper()



    normalized_plan_days = _normalize_challenge_plan_days(

        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

        duration_days=max(int(challenge.get("duration_days") or 0), 1)

    )

    challenge_points = max(int(challenge.get("points") or 0), 0)

    participants = await _load_challenge_participants(challenge_id)

    participant_count = await challenge_memberships_collection.count_documents(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    )

    messages = await _load_challenge_chat_messages(challenge_id, str(user["_id"]), limit=50)



    has_joined = membership_status in {"ACTIVE", "COMPLETED"}

    viewer_plan_progress = _build_viewer_plan_progress(normalized_plan_days, membership or {}) if membership else []

    viewer_progress_days_completed = _count_completed_plan_days_from_start(

        normalized_plan_days,

        membership.get("plan_progress") if membership and isinstance(membership.get("plan_progress"), dict) else {},

    )

    current_day_number = _get_current_challenge_day_number(

        membership or {},

        normalized_plan_days,

        max(int(challenge.get("duration_days") or 0), 1),

    ) if membership and has_joined and challenge_status == "ACTIVE" else None

    viewer_points_earned = _calculate_challenge_points_earned(

        normalized_plan_days,

        {**(membership or {}), "challenge_points": challenge_points},

        challenge_points,

    ) if membership else 0

    unread_count = 0

    if membership and has_joined:

        unread_count = await _count_unread_challenge_messages(challenge_id, str(user["_id"]), membership)

    completed_today = _has_completed_challenge_day_today(membership or {}) if membership and has_joined else False



    can_start = False

    if challenge_status == "ACTIVE" and membership_status not in {"ACTIVE", "COMPLETED"}:

        active_challenge_limit = _get_user_active_challenge_limit(user)

        if active_challenge_limit is None:

            can_start = True

        else:

            active_membership_count = await challenge_memberships_collection.count_documents(

                {

                    "user_id": str(user["_id"]),

                    "status": "ACTIVE",

                    **({"challenge_id": {"$ne": challenge_id}} if membership_status == "LEFT" else {}),

                }

            )

            can_start = active_membership_count < active_challenge_limit



    can_post = has_joined and challenge_status == "ACTIVE"



    return ChallengeDetailResponse(

        challenge_id=challenge_id,

        title=str(challenge.get("title") or ""),

        description=str(challenge.get("description") or ""),

        why_it_matters=str(challenge.get("why_it_matters") or ""),

        plan_text=str(challenge.get("plan_text") or ""),

        plan_days=[ChallengePlanDay(**day) for day in normalized_plan_days],

        category=str(challenge.get("category") or "Challenge"),

        duration_days=max(int(challenge.get("duration_days") or 0), 0),

        points=challenge_points,

        difficulty=str(challenge.get("difficulty") or "BEGINNER"),

        status=str(challenge.get("status") or "ACTIVE"),

        thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

        participant_count=participant_count,

        participants=participants,

        viewer_membership_status=membership_status,

        viewer_progress_days_completed=viewer_progress_days_completed,

        viewer_points_earned=viewer_points_earned,

        viewer_plan_progress=viewer_plan_progress,

        unread_count=unread_count,

        can_start=can_start,

        can_post=can_post,

        has_joined=has_joined,

        current_day_number=current_day_number,

        can_complete_today=bool(has_joined and membership_status == "ACTIVE" and challenge_status == "ACTIVE" and current_day_number and not completed_today),

        completed_today=completed_today,

        messages=[ChallengeChatMessageResponse(**message) for message in messages],

        started_at=membership.get("started_at") if membership else None,

    )





@app.get("/challenges/{challenge_id}/chat", response_model=ChallengeChatThreadResponse)

async def get_challenge_chat_thread(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatThreadResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    if membership and str(membership.get("status") or "").upper() == "ACTIVE":

        total_days = max(int(challenge.get("duration_days") or 0), 1)

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

                if elapsed_days >= total_days:

                    now = datetime.now(timezone.utc)

                    await challenge_memberships_collection.update_one(

                        {"_id": membership["_id"]},

                        {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                    )

                    membership = dict(membership)

                    membership["status"] = "COMPLETED"

                    membership["completed_at"] = now

            except ValueError:

                pass

    _ensure_challenge_read_access(membership, challenge)



    messages = await _load_challenge_chat_messages(challenge_id, str(user["_id"]), limit=50)

    participants = await _load_challenge_participants(challenge_id)

    participant_count = await challenge_memberships_collection.count_documents(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    )

    unread_count = await _count_unread_challenge_messages(challenge_id, str(user["_id"]), membership)

    now = datetime.now(timezone.utc)

    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        {"$set": {"last_read_message_at": now, "updated_at": now}},

    )



    challenge_points = max(int(challenge.get("points") or 0), 0)

    membership_with_points = dict(membership)

    membership_with_points["challenge_points"] = challenge_points

    normalized_plan_days = _normalize_challenge_plan_days(
        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],
        duration_days=max(int(challenge.get("duration_days") or 0), 1)
    )

    viewer_plan_progress = _build_viewer_plan_progress(normalized_plan_days, membership)

    viewer_progress_days_completed = _count_completed_plan_days_from_start(

        normalized_plan_days,

        membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {},

    )

    return ChallengeChatThreadResponse(

        challenge_id=challenge_id,

        title=str(challenge.get("title") or ""),

        description=str(challenge.get("description") or ""),

        why_it_matters=str(challenge.get("why_it_matters") or ""),

        plan_text=str(challenge.get("plan_text") or ""),

        plan_days=[ChallengePlanDay(**day) for day in normalized_plan_days],

        category=str(challenge.get("category") or "Challenge"),

        duration_days=max(int(challenge.get("duration_days") or 0), 0),

        points=challenge_points,

        difficulty=str(challenge.get("difficulty") or "BEGINNER"),

        status=str(challenge.get("status") or "ACTIVE"),

        thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

        participant_count=participant_count,

        participants=participants,

        viewer_membership_status=str(membership.get("status") or "ACTIVE"),

        viewer_progress_days_completed=viewer_progress_days_completed,

        viewer_points_earned=_calculate_challenge_points_earned(

            normalized_plan_days,

            membership_with_points,

            challenge_points,

        ),

        viewer_plan_progress=viewer_plan_progress,

        unread_count=unread_count,

        messages=[ChallengeChatMessageResponse(**message) for message in messages],

        started_at=membership.get("started_at"),

    )





@app.websocket("/ws/challenges/{challenge_id}/chat")

async def challenge_chat_socket(

    websocket: WebSocket,

    challenge_id: str,

) -> None:

    token = websocket.query_params.get("token", "").strip()

    if not token:

        await websocket.close(code=4401, reason="Missing access token")

        return



    try:

        user = await _get_verified_user_from_access_token(token)

        _ensure_subscription_feature_access(user, "challenge", "Your current plan does not include challenge access")

        membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

        challenge = await _get_challenge_or_404(challenge_id)

        _ensure_challenge_read_access(membership, challenge)

    except HTTPException as exc:

        await websocket.close(code=4403 if exc.status_code == 403 else 4401, reason=str(exc.detail))

        return



    await challenge_chat_socket_manager.connect(challenge_id, websocket)

    try:

        while True:

            await websocket.receive_text()

    except WebSocketDisconnect:

        challenge_chat_socket_manager.disconnect(challenge_id, websocket)





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


@app.post("/challenges/{challenge_id}/chat/messages", response_model=ChallengeChatMessageResponse, status_code=status.HTTP_201_CREATED)

async def create_challenge_chat_message(

    challenge_id: str,

    payload: ChallengeChatMessageCreateRequest,



    background_tasks: BackgroundTasks,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_chat_write_access(membership, challenge)



    content = str(payload.content or "").strip()

    if not content and not payload.image_base64:

        raise HTTPException(status_code=400, detail="Message content or image is required")



    image_url = ""

    if payload.image_base64:

        try:

            image_url = _upload_challenge_chat_image_to_s3(

                str(user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge chat image upload failed: {exc}") from exc



    reply_to_message_id = str(payload.reply_to_message_id or "").strip() or None

    if reply_to_message_id and not ObjectId.is_valid(reply_to_message_id):

        raise HTTPException(status_code=400, detail="Invalid reply_to_message_id")

    if reply_to_message_id:

        await _get_challenge_message_or_404(challenge_id, reply_to_message_id)



    now = datetime.now(timezone.utc)

    document = {

        "_id": ObjectId(),

        "challenge_id": challenge_id,

        "author_id": str(user["_id"]),

        "message_type": "message",

        "content": content,

        "image_url": image_url,

        "reply_to_message_id": reply_to_message_id,

        "progress_payload": None,

        "created_at": now,

        "updated_at": now,

    }

    await challenge_chat_messages_collection.insert_one(document)

    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        {"$set": {"updated_at": now}},

    )

    await _broadcast_challenge_chat_event("message_created", challenge_id, document)

    background_tasks.add_task(
        _notify_challenge_chat_participants,
        challenge_id,
        str(user["_id"]),
        str(challenge.get("title") or "Your challenge"),
        content or "Sent an image in the challenge chat.",
    )

    if _challenge_message_mentions_coach(content):

        await _create_challenge_coach_reply(

            challenge=challenge,

            membership=membership,

            user=user,

            trigger_message=document,

        )



    return ChallengeChatMessageResponse(**_serialize_challenge_chat_message(document, user, str(user["_id"])))





@app.patch("/challenges/{challenge_id}/chat/messages/{message_id}", response_model=ChallengeChatMessageResponse)

async def update_challenge_chat_message(

    challenge_id: str,

    message_id: str,

    payload: ChallengeChatMessageUpdateRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    challenge = await _get_challenge_or_404(challenge_id)

    _ensure_challenge_chat_write_access(membership, challenge)

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    if str(message_record.get("author_id") or "") != str(user["_id"]):

        raise HTTPException(status_code=403, detail="You can only edit your own messages")

    if str(message_record.get("author_id") or "") in {"coach_bot", "system"}:

        raise HTTPException(status_code=400, detail="This message cannot be edited")

    if message_record.get("deleted_at"):

        raise HTTPException(status_code=400, detail="Deleted messages cannot be edited")



    now = datetime.now(timezone.utc)

    await challenge_chat_messages_collection.update_one(

        {"_id": message_record["_id"]},

        {

            "$set": {

                "content": payload.content.strip(),

                "updated_at": now,

                "edited_at": now,

            }

        },

    )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if not updated:

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    await _broadcast_challenge_chat_event("message_updated", challenge_id, updated)

    return ChallengeChatMessageResponse(**(await _serialize_single_challenge_chat_message(updated, str(user["_id"]))))





@app.delete("/challenges/{challenge_id}/chat/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)

async def delete_challenge_chat_message(

    challenge_id: str,

    message_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> Response:

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    challenge = await _get_challenge_or_404(challenge_id)

    _ensure_challenge_read_access(membership, challenge)

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    if str(message_record.get("author_id") or "") != str(user["_id"]):

        raise HTTPException(status_code=403, detail="You can only delete your own messages")

    if str(message_record.get("author_id") or "") in {"coach_bot", "system"}:

        raise HTTPException(status_code=400, detail="This message cannot be deleted")



    now = datetime.now(timezone.utc)

    await challenge_chat_messages_collection.update_one(

        {"_id": message_record["_id"]},

        {

            "$set": {

                "content": "",

                "image_url": "",

                "updated_at": now,

                "deleted_at": now,

            }

        },

    )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if updated:

        await _broadcast_challenge_chat_event("message_deleted", challenge_id, updated, message_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)





@app.post("/challenges/{challenge_id}/chat/messages/{message_id}/reactions/toggle", response_model=ChallengeChatMessageResponse)

async def toggle_challenge_chat_reaction(

    challenge_id: str,

    message_id: str,

    payload: ChallengeChatReactionToggleRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    challenge = await _get_challenge_or_404(challenge_id)

    _ensure_challenge_read_access(membership, challenge)

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    emoji = payload.emoji.strip()

    reaction_filter = {

        "message_id": message_id,

        "challenge_id": challenge_id,

        "user_id": str(user["_id"]),

        "emoji": emoji,

    }

    existing = await challenge_message_reactions_collection.find_one(reaction_filter)

    now = datetime.now(timezone.utc)

    if existing:

        await challenge_message_reactions_collection.delete_one({"_id": existing["_id"]})

    else:

        await challenge_message_reactions_collection.insert_one(

            {

                "_id": ObjectId(),

                "message_id": message_id,

                "challenge_id": challenge_id,

                "user_id": str(user["_id"]),

                "emoji": emoji,

                "created_at": now,

            }

        )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if not updated:

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    await _broadcast_challenge_chat_event("reaction_toggled", challenge_id, updated)

    return ChallengeChatMessageResponse(**(await _serialize_single_challenge_chat_message(updated, str(user["_id"]))))





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





@app.post("/challenges/{challenge_id}/plan/days/{day_number}/complete", response_model=ChallengePlanProgressResponse)

async def complete_challenge_plan_day(

    challenge_id: str,

    day_number: int,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    plan_days = _get_normalized_plan_days(challenge)

    plan_day = _get_plan_day_or_404(plan_days, day_number)

    existing_day_progress = _get_membership_day_progress(membership, day_number)

    valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

    completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

        existing_day_progress,

        valid_section_ids,

        valid_exercise_ids,

    )



    if payload.completed and valid_exercise_ids and len(completed_exercise_ids) < len(valid_exercise_ids):

        raise HTTPException(status_code=400, detail="Complete every exercise before marking the day done")

    if payload.completed and not valid_exercise_ids and valid_section_ids and len(completed_section_ids) < len(valid_section_ids):

        raise HTTPException(status_code=400, detail="Complete every section before marking the day done")



    if payload.completed and not valid_section_ids:

        completed_section_ids = []

    if payload.completed and not valid_exercise_ids:

        completed_exercise_ids = []

    if not payload.completed:

        completed_section_ids = []

        completed_exercise_ids = []



    return await _store_membership_plan_progress(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        completed_section_ids=completed_section_ids,

        completed_exercise_ids=completed_exercise_ids,

        completed=payload.completed,

        emit_progress_message=payload.completed,

    )





@app.post("/challenges/{challenge_id}/complete-today", response_model=ChallengePlanProgressResponse)

async def complete_challenge_today(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    return await _complete_current_challenge_day(challenge_id, user)





@app.post("/challenges/{challenge_id}/current-day/complete", response_model=ChallengePlanProgressResponse)

async def complete_current_challenge_day(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    return await _complete_current_challenge_day(challenge_id, user)





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





@app.post(

    "/challenges/{challenge_id}/plan/days/{day_number}/sections/{section_id}/complete",

    response_model=ChallengePlanProgressResponse,

)

async def complete_challenge_plan_section(

    challenge_id: str,

    day_number: int,

    section_id: str,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)



    plan_days = _get_normalized_plan_days(challenge)

    plan_day = _get_plan_day_or_404(plan_days, day_number)

    valid_section_ids, valid_exercise_ids = _get_plan_day_ids(plan_day)

    if section_id not in valid_section_ids:

        raise HTTPException(status_code=404, detail="Challenge plan section not found")



    existing_day_progress = _get_membership_day_progress(membership, day_number)

    prior_completed = bool(isinstance(existing_day_progress, dict) and existing_day_progress.get("completed"))

    if payload.completed:

        completed_section_ids = list(valid_section_ids)

        completed_exercise_ids = list(valid_exercise_ids)

        will_complete_day = True

    else:

        completed_section_ids, completed_exercise_ids = _normalize_completed_progress_ids(

            existing_day_progress,

            valid_section_ids,

            valid_exercise_ids,

        )

        section_record = _get_plan_section_or_404(plan_day, section_id)

        section_exercise_ids = _get_section_exercise_ids(section_record)

        completed_section_ids = [value for value in completed_section_ids if value != section_id]

        if section_exercise_ids:

            completed_exercise_ids = [value for value in completed_exercise_ids if value not in section_exercise_ids]

        will_complete_day = False



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





@app.post(

    "/challenges/{challenge_id}/plan/days/{day_number}/exercises/{exercise_id}/complete",

    response_model=ChallengePlanProgressResponse,

)

async def complete_challenge_plan_exercise_direct(

    challenge_id: str,

    day_number: int,

    exercise_id: str,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    return await _complete_challenge_plan_exercise_internal(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        exercise_id=exercise_id,

        payload=payload,

    )





@app.post(

    "/challenges/{challenge_id}/plan/days/{day_number}/sections/{section_id}/exercises/{exercise_id}/complete",

    response_model=ChallengePlanProgressResponse,

)

async def complete_challenge_plan_exercise(

    challenge_id: str,

    day_number: int,

    section_id: str,

    exercise_id: str,

    payload: ChallengePlanCompletionRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengePlanProgressResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)

    return await _complete_challenge_plan_exercise_internal(

        challenge=challenge,

        membership=membership,

        user=user,

        day_number=day_number,

        exercise_id=exercise_id,

        payload=payload,

        section_id=section_id,

    )





@app.post("/challenges/{challenge_id}/progress", response_model=ChallengeChatMessageResponse, status_code=status.HTTP_201_CREATED)

async def post_challenge_progress_update(

    challenge_id: str,

    payload: ChallengeProgressUpdateRequest,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeChatMessageResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    _ensure_challenge_write_access(membership, challenge)



    total_days = max(int(challenge.get("duration_days") or 0), 1)

    completed_day = min(payload.completed_day, total_days)

    plan_days = _normalize_challenge_plan_days(
        challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],
        duration_days=total_days
    )

    existing_plan_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    next_plan_progress = dict(existing_plan_progress)

    plan_day = next((day for day in plan_days if int(day.get("day_number") or 0) == completed_day), None)

    if plan_day:

        completed_section_ids = [

            str(section.get("id") or "")

            for section in plan_day.get("sections") or []

            if str(section.get("id") or "")

        ]

        next_plan_progress[str(completed_day)] = {

            "completed": True,

            "completed_section_ids": completed_section_ids,

            "updated_at": datetime.now(timezone.utc).isoformat(),

        }



    next_progress = _count_completed_plan_days_from_start(plan_days, next_plan_progress)

    next_status = "COMPLETED" if next_progress >= total_days else "ACTIVE"



    image_url = ""

    if payload.image_base64:

        try:

            image_url = _upload_challenge_chat_image_to_s3(

                str(user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge progress image upload failed: {exc}") from exc



    note = str(payload.note or "").strip()

    content = note or f"Completed day {completed_day}."

    now = datetime.now(timezone.utc)

    progress_payload = {

        "completed_day": completed_day,

        "total_days": total_days,

        "membership_status": next_status,

    }

    document = {

        "_id": ObjectId(),

        "challenge_id": challenge_id,

        "author_id": str(user["_id"]),

        "message_type": "progress_update",

        "content": content,

        "image_url": image_url,

        "reply_to_message_id": None,

        "progress_payload": progress_payload,

        "created_at": now,

        "updated_at": now,

    }

    await challenge_chat_messages_collection.insert_one(document)



    membership_update = {

        "progress_days_completed": next_progress,

        "plan_progress": next_plan_progress,

        "status": next_status,

        "updated_at": now,

    }

    if next_status == "COMPLETED":

        membership_update["completed_at"] = now



    await challenge_memberships_collection.update_one(

        {"_id": membership["_id"]},

        {"$set": membership_update},

    )

    await _broadcast_challenge_chat_event("message_created", challenge_id, document)



    return ChallengeChatMessageResponse(**_serialize_challenge_chat_message(document, user, str(user["_id"])))





@app.get("/challenges/{challenge_id}/progress/report", response_model=ChallengeProgressReportResponse)

async def get_challenge_progress_report(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> ChallengeProgressReportResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    membership = await _get_challenge_membership_or_403(challenge_id, str(user["_id"]))

    if membership and str(membership.get("status") or "").upper() == "ACTIVE":

        total_days = max(int(challenge.get("duration_days") or 0), 1)

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

                if elapsed_days >= total_days:

                    now = datetime.now(timezone.utc)

                    await challenge_memberships_collection.update_one(

                        {"_id": membership["_id"]},

                        {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                    )

                    membership = dict(membership)

                    membership["status"] = "COMPLETED"

                    membership["completed_at"] = now

            except ValueError:

                pass

    _ensure_challenge_read_access(membership, challenge)

    viewer_name = str(user.get("name") or "Victory Member").strip() or "Victory Member"

    png_bytes, share_message = _build_challenge_progress_report_png(challenge, membership, viewer_name)

    return ChallengeProgressReportResponse(

        file_name="victory-fitness-progress-report.png",

        mime_type="image/png",

        image_base64=base64.b64encode(png_bytes).decode("ascii"),

        share_message=share_message,

    )





@app.post("/challenges/{challenge_id}/start", response_model=StartChallengeResponse, status_code=status.HTTP_201_CREATED)

async def start_challenge(

    challenge_id: str,

    user: dict = Depends(_require_challenge_access_user),

) -> StartChallengeResponse:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc



    challenge = await challenges_collection.find_one({"_id": object_id})

    if not challenge:

        raise HTTPException(status_code=404, detail="Challenge not found")

    challenge_status = str(challenge.get("status") or "").upper()

    if challenge_status == "UPCOMING":

        raise HTTPException(status_code=400, detail="This challenge is coming soon and cannot be started yet")

    if challenge_status != "ACTIVE":

        raise HTTPException(status_code=400, detail="This challenge cannot be started")



    user_id = str(user["_id"])

    active_challenge_limit = _get_user_active_challenge_limit(user)

    if active_challenge_limit is not None:

        active_membership_count = await challenge_memberships_collection.count_documents(

            {"user_id": user_id, "status": "ACTIVE"}

        )

        if active_membership_count >= active_challenge_limit:

            raise HTTPException(

                status_code=403,

                detail=f"Your current plan allows up to {active_challenge_limit} active challenges",

            )



    existing_membership = await challenge_memberships_collection.find_one(

        {"user_id": user_id, "challenge_id": challenge_id}

    )

    if existing_membership:

        existing_status = str(existing_membership.get("status") or "").upper()

        if existing_status == "ACTIVE":

            return StartChallengeResponse(membership_id=str(existing_membership["_id"]))

        if existing_status == "COMPLETED":

            raise HTTPException(status_code=409, detail="You already completed this challenge")

        if existing_status == "LEFT":

            now = datetime.now(timezone.utc)

            await challenge_memberships_collection.update_one(

                {"_id": existing_membership["_id"]},

                {

                    "$set": {

                        "status": "ACTIVE",

                        "plan_progress": existing_membership.get("plan_progress") if isinstance(existing_membership.get("plan_progress"), dict) else {},

                        "updated_at": now,

                        "started_at": existing_membership.get("started_at") or now,

                    }

                },

            )

            await challenge_chat_messages_collection.insert_one(

                {

                    "_id": ObjectId(),

                    "challenge_id": challenge_id,

                    "author_id": "system",

                    "author_name": "Coach",

                    "author_role": "system",

                    "message_type": "system_event",

                    "content": f"{user.get('name') or 'A member'} joined the challenge.",

                    "image_url": "",

                    "reply_to_message_id": None,

                    "progress_payload": None,

                    "created_at": now,

                    "updated_at": now,

                }

            )

            return StartChallengeResponse(membership_id=str(existing_membership["_id"]))



    now = datetime.now(timezone.utc)

    document = {

        "user_id": user_id,

        "challenge_id": challenge_id,

        "status": "ACTIVE",

        "progress_days_completed": 0,

        "plan_progress": {},

        "joined_at": now,

        "started_at": now,

        "updated_at": now,

    }

    insert_result = await challenge_memberships_collection.insert_one(document)



    await challenge_chat_messages_collection.insert_one(

        {

            "_id": ObjectId(),

            "challenge_id": challenge_id,

            "author_id": "system",

            "author_name": "Coach",

            "author_role": "system",

            "message_type": "system_event",

            "content": f"{user.get('name') or 'A member'} joined the challenge.",

            "image_url": "",

            "reply_to_message_id": None,

            "progress_payload": None,

            "created_at": now,

            "updated_at": now,

        }

    )



    await notify_user(
        users_collection,
        user,
        "Challenge started",
        f"You are ready for {str(challenge.get('title') or 'your challenge')}. Complete day 1 today to build your streak.",
        "challenge_started",
        {"type": "challenge", "challengeId": challenge_id, "route": f"/challenges/progress/{challenge_id}"},
    )
    return StartChallengeResponse(membership_id=str(insert_result.inserted_id))





@app.get("/admin/challenges", response_model=AdminChallengeListResponse)

async def admin_list_challenges(

    query: str | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminChallengeListResponse:

    filter_doc = {}

    search = (query or "").strip()

    if search:

        escaped = re.escape(search)

        filter_doc["$or"] = [

            {"title": {"$regex": escaped, "$options": "i"}},

            {"category": {"$regex": escaped, "$options": "i"}},

            {"difficulty": {"$regex": escaped, "$options": "i"}},

            {"status": {"$regex": escaped, "$options": "i"}},

        ]



    records = await challenges_collection.find(

        filter_doc,

        sort=[("duration_days", 1), ("created_at", -1), ("_id", -1)],

    ).to_list(length=None)

    stats = await _load_challenge_stats_map([str(record["_id"]) for record in records])



    return AdminChallengeListResponse(

        total=len(records),

        challenges=[AdminChallengeItem(**_serialize_admin_challenge_record(record, stats)) for record in records],

    )





@app.post("/admin/challenges/generate-plan", response_model=AdminChallengePlanGenerateResponse)

async def admin_generate_challenge_plan(

    payload: AdminChallengePlanGenerateRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminChallengePlanGenerateResponse:

    generated = generate_challenge_plan(

        ChallengePlanGenerationInput(

            title=payload.title.strip(),

            description=payload.description.strip(),

            category=payload.category.strip(),

            difficulty=payload.difficulty.strip(),

            duration_days=payload.durationDays,

        )

    )

    plan_days = _normalize_challenge_plan_days(generated.get("plan_days") if isinstance(generated, dict) else [])

    if not plan_days:

        raise HTTPException(status_code=500, detail="Failed to generate challenge plan")

    plan_text = _build_challenge_plan_text(plan_days)

    duration_days = max(_extract_plan_day_numbers(plan_days), default=payload.durationDays)

    return AdminChallengePlanGenerateResponse(

        title=payload.title.strip(),

        description=str(generated.get("summary") or payload.description).strip(),

        planText=plan_text,

        planDays=[ChallengePlanDay(**day) for day in plan_days],

        durationDays=duration_days,

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


@app.post("/admin/challenges", response_model=AdminChallengeItem, status_code=status.HTTP_201_CREATED)
async def admin_create_challenge(

    payload: AdminChallengeRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminChallengeItem:

    now = datetime.now(timezone.utc)

    plan_days = _normalize_challenge_plan_days(payload.planDays)

    derived_duration_days = max(_extract_plan_day_numbers(plan_days), default=payload.durationDays)

    plan_text = _build_challenge_plan_text(plan_days) if plan_days else str(payload.planText or "").strip()

    thumbnail = _normalize_challenge_thumbnail(payload.thumbnail)

    if payload.image_base64:

        try:

            thumbnail = _upload_challenge_thumbnail_to_s3(

                str(admin_user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge thumbnail upload failed: {exc}") from exc

    document = {

        "title": payload.title.strip(),

        "description": payload.description.strip(),

        "why_it_matters": str(payload.whyItMatters or "").strip(),

        "plan_text": plan_text,

        "plan_days": plan_days,

        "category": payload.category.strip(),

        "duration_days": derived_duration_days,

        "points": payload.points,

        "difficulty": payload.difficulty,

        "status": payload.status,

        "thumbnail": thumbnail,

        "created_at": now,

        "updated_at": now,

    }

    insert_result = await challenges_collection.insert_one(document)

    document["_id"] = insert_result.inserted_id

    await _sync_workout_library_from_challenge_plan(plan_days, payload.category)
    if str(payload.status or "").upper() in {"ACTIVE", "UPCOMING"}:
        await _notify_users_of_new_challenge(document)

    return AdminChallengeItem(**_serialize_admin_challenge_record(document))





@app.patch("/admin/challenges/{challenge_id}", response_model=AdminChallengeItem)

async def admin_update_challenge(

    challenge_id: str,

    payload: AdminChallengeRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminChallengeItem:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc



    existing = await challenges_collection.find_one({"_id": object_id})

    if not existing:

        raise HTTPException(status_code=404, detail="Challenge not found")



    previous_thumbnail = _normalize_challenge_thumbnail(existing.get("thumbnail"))

    thumbnail = _normalize_challenge_thumbnail(payload.thumbnail)

    if payload.image_base64:

        try:

            thumbnail = _upload_challenge_thumbnail_to_s3(

                str(admin_user["_id"]),

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Challenge thumbnail upload failed: {exc}") from exc

    if previous_thumbnail and previous_thumbnail != thumbnail:

        _delete_image_from_s3(previous_thumbnail)



    plan_days = _normalize_challenge_plan_days(payload.planDays)

    derived_duration_days = max(_extract_plan_day_numbers(plan_days), default=payload.durationDays)

    plan_text = _build_challenge_plan_text(plan_days) if plan_days else str(payload.planText or "").strip()

    update_doc = {

        "title": payload.title.strip(),

        "description": payload.description.strip(),

        "why_it_matters": str(payload.whyItMatters or "").strip(),

        "plan_text": plan_text,

        "plan_days": plan_days,

        "category": payload.category.strip(),

        "duration_days": derived_duration_days,

        "points": payload.points,

        "difficulty": payload.difficulty,

        "status": payload.status,

        "thumbnail": thumbnail,

        "updated_at": datetime.now(timezone.utc),

    }

    await challenges_collection.update_one({"_id": object_id}, {"$set": update_doc})

    await _sync_workout_library_from_challenge_plan(plan_days, payload.category)



    updated = await challenges_collection.find_one({"_id": object_id})

    if not updated:

        raise HTTPException(status_code=404, detail="Challenge not found")

    was_available = str(existing.get("status") or "").upper() in {"ACTIVE", "UPCOMING"}
    is_available = str(updated.get("status") or "").upper() in {"ACTIVE", "UPCOMING"}
    if is_available and not was_available:
        await _notify_users_of_new_challenge(updated)

    stats = await _load_challenge_stats_map([challenge_id])

    return AdminChallengeItem(**_serialize_admin_challenge_record(updated, stats))





@app.delete("/admin/challenges/{challenge_id}")

async def admin_delete_challenge(

    challenge_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc



    existing = await challenges_collection.find_one({"_id": object_id})

    if not existing:

        raise HTTPException(status_code=404, detail="Challenge not found")



    _delete_image_from_s3(_normalize_challenge_thumbnail(existing.get("thumbnail")))

    delete_result = await challenges_collection.delete_one({"_id": object_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Challenge not found")



    await challenge_memberships_collection.delete_many({"challenge_id": challenge_id})

    await challenge_chat_messages_collection.delete_many({"challenge_id": challenge_id})

    return {"status": "success", "message": "Challenge deleted"}





@app.get("/admin/challenges/{challenge_id}/chat", response_model=ChallengeChatThreadResponse)

async def admin_get_challenge_chat_thread(

    challenge_id: str,

    _: dict = Depends(_require_admin_user),

) -> ChallengeChatThreadResponse:

    challenge = await _get_challenge_or_404(challenge_id)

    messages = await _load_challenge_chat_messages(challenge_id, None, limit=200)

    participants = await _load_challenge_participants(challenge_id)

    participant_count = await challenge_memberships_collection.count_documents(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}}

    )

    return ChallengeChatThreadResponse(

        challenge_id=challenge_id,

        title=str(challenge.get("title") or ""),

        description=str(challenge.get("description") or ""),

        plan_text=str(challenge.get("plan_text") or ""),

        plan_days=[ChallengePlanDay(**day) for day in _normalize_challenge_plan_days(challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [])],

        category=str(challenge.get("category") or "Challenge"),

        duration_days=max(int(challenge.get("duration_days") or 0), 0),

        points=max(int(challenge.get("points") or 0), 0),

        difficulty=str(challenge.get("difficulty") or "BEGINNER"),

        status=str(challenge.get("status") or "ACTIVE"),

        thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

        participant_count=participant_count,

        participants=participants,

        viewer_membership_status="ADMIN",

        viewer_progress_days_completed=0,

        viewer_plan_progress=[],

        unread_count=0,

        messages=[ChallengeChatMessageResponse(**message) for message in messages],

    )





@app.delete("/admin/challenges/{challenge_id}/chat/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)

async def admin_delete_challenge_chat_message(

    challenge_id: str,

    message_id: str,

    _: dict = Depends(_require_admin_user),

) -> Response:

    message_record = await _get_challenge_message_or_404(challenge_id, message_id)

    now = datetime.now(timezone.utc)

    await challenge_chat_messages_collection.update_one(

        {"_id": message_record["_id"]},

        {

            "$set": {

                "content": "",

                "image_url": "",

                "updated_at": now,

                "deleted_at": now,

                "deleted_by_admin": True,

            }

        },

    )

    updated = await challenge_chat_messages_collection.find_one({"_id": message_record["_id"]})

    if updated:

        await _broadcast_challenge_chat_event("message_deleted", challenge_id, updated, message_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)





@app.get("/admin/dashboard/overview", response_model=DashboardOverviewResponse)

async def admin_dashboard_overview(

    year: int | None = None,

    _: dict = Depends(_require_admin_user),

) -> DashboardOverviewResponse:

    selected_year = year or datetime.now(timezone.utc).year

    year_start = datetime(selected_year, 1, 1, tzinfo=timezone.utc)

    next_year_start = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    week_start = now - timedelta(days=now.weekday())

    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    non_admin_filter = {"is_admin": {"$ne": True}}



    total_users = await users_collection.count_documents(non_admin_filter)

    workouts_this_week = await workouts_collection.count_documents({"created_at": {"$gte": week_start}})

    challenge_completions = await challenge_memberships_collection.count_documents({"status": "COMPLETED"})

    active_challenges = await challenges_collection.count_documents({"status": "ACTIVE"})

    ready_challenges = await challenges_collection.count_documents({"status": {"$in": ["ACTIVE", "UPCOMING"]}})

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

        workoutsThisWeek=workouts_this_week,

        challengeCompletions=challenge_completions,

        activeChallenges=active_challenges,

        readyChallenges=ready_challenges,

        vimeoApiStatus=get_vimeo_status(),

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





def _trial_cohort_key(value: datetime) -> str:
    return _as_utc(value).strftime("%Y-%m")


async def _record_trial_engagement(user: dict, kind: str) -> None:
    started_at = _trial_started_at(user)
    if not started_at:
        return
    day = int((datetime.now(timezone.utc) - started_at).total_seconds() // 86400)
    if day < 0 or day > 5:
        return
    update: dict = {
        "$addToSet": {"trial_engagement.days": day},
    }
    if kind == "coach_message":
        update["$inc"] = {"trial_engagement.coach_messages": 1}
    elif kind == "nutrition_plan":
        update["$set"] = {"trial_engagement.nutrition_plan_created_at": datetime.now(timezone.utc)}
    await users_collection.update_one({"_id": user["_id"]}, update)


def _trial_user_converted(user: dict) -> bool:
    return bool(user.get("subscription_is_purchased")) or str(user.get("subscription_status") or "").upper() in {"ACTIVE", "PAID"}


def _trial_started_at(user: dict) -> datetime | None:
    value = user.get("subscription_started_at")
    return _as_utc(value) if isinstance(value, datetime) else None


@app.get("/admin/trials/cohorts", response_model=AdminTrialCohortResponse)
async def admin_trial_cohorts(_: dict = Depends(_require_admin_user)) -> AdminTrialCohortResponse:
    now = datetime.now(timezone.utc)
    users = await users_collection.find({"is_admin": {"$ne": True}, "subscription_started_at": {"$ne": None}}).to_list(length=None)
    grouped: dict[tuple[str, str], dict] = {}
    for user in users:
        started_at = _trial_started_at(user)
        if not started_at:
            continue
        key = (_trial_cohort_key(started_at), str(user.get("signup_source") or "organic").strip() or "organic")
        bucket = grouped.setdefault(key, {"total": 0, "converted": 0, "dropouts": 0, "engaged": {str(day): 0 for day in range(6)}})
        bucket["total"] += 1
        if _trial_user_converted(user):
            bucket["converted"] += 1
        elif now >= started_at + timedelta(days=5):
            bucket["dropouts"] += 1
        engagement_days = (user.get("trial_engagement") or {}).get("days") or []
        for day in engagement_days:
            if str(day) in bucket["engaged"]:
                bucket["engaged"][str(day)] += 1
    cohorts = []
    for (cohort, signup_source), bucket in sorted(grouped.items(), reverse=True):
        total = bucket["total"]
        cohorts.append(AdminTrialCohortItem(
            cohort=cohort,
            signupSource=signup_source,
            totalUsers=total,
            convertedUsers=bucket["converted"],
            dropoutUsers=bucket["dropouts"],
            conversionRate=round((bucket["converted"] / total) * 100, 2) if total else 0,
            engagedUsersByDay=bucket["engaged"],
        ))
    return AdminTrialCohortResponse(cohorts=cohorts)


@app.get("/admin/trials/dropouts", response_model=AdminTrialDropoutResponse)
async def admin_trial_dropouts(
    limit: int = 100,
    _: dict = Depends(_require_admin_user),
) -> AdminTrialDropoutResponse:
    now = datetime.now(timezone.utc)
    records = await users_collection.find({
        "is_admin": {"$ne": True},
        "marketing_consent": True,
        "subscription_started_at": {"$ne": None},
    }, sort=[("subscription_started_at", -1)]).to_list(length=min(max(limit, 1), 500))
    dropouts = []
    for user in records:
        started_at = _trial_started_at(user)
        if not started_at or _trial_user_converted(user) or now < started_at + timedelta(days=5):
            continue
        engagement = user.get("trial_engagement") or {}
        engagement_days = [int(day) for day in (engagement.get("days") or []) if str(day).isdigit()]
        dropouts.append(AdminTrialDropoutItem(
            id=str(user["_id"]),
            fullName=str(user.get("name") or "Unknown"),
            email=str(user.get("email") or ""),
            signupSource=str(user.get("signup_source") or "organic"),
            cohort=_trial_cohort_key(started_at),
            trialStartedAt=started_at,
            marketingConsent=True,
            lastEngagedDay=max(engagement_days) if engagement_days else None,
            coachMessages=max(int(engagement.get("coach_messages") or 0), 0),
            nutritionPlanCreated=bool(engagement.get("nutrition_plan_created_at")),
            campaignDaysSent=sorted({int(day) for day in (user.get("trial_campaign_sent_days") or []) if str(day).isdigit()}),
        ))
    return AdminTrialDropoutResponse(total=len(dropouts), users=dropouts)


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

            {"video_url": {"$regex": escaped, "$options": "i"}},

            {"video_source": {"$regex": escaped, "$options": "i"}},

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





@app.post("/admin/uploads/presign", response_model=AdminDirectUploadResponse)

async def admin_create_direct_upload(

    payload: AdminDirectUploadRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminDirectUploadResponse:

    try:

        folder_name, allowed_types = _get_direct_upload_target(payload.uploadType)

        return _create_presigned_media_upload(

            folder_name,

            str(admin_user["_id"]),

            payload.contentType,

            payload.fileName,

            allowed_types=allowed_types,

        )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc





@app.post("/uploads/presign", response_model=AdminDirectUploadResponse)

async def create_direct_upload(

    payload: AdminDirectUploadRequest,

    user: dict = Depends(_require_community_access_user),

) -> AdminDirectUploadResponse:

    if payload.uploadType != "COMMUNITY_VIDEO":

        raise HTTPException(status_code=400, detail="Unsupported upload type")



    try:

        folder_name, allowed_types = _get_direct_upload_target(payload.uploadType)

        return _create_presigned_media_upload(

            folder_name,

            str(user["_id"]),

            payload.contentType,

            payload.fileName,

            allowed_types=allowed_types,

        )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"Direct upload initialization failed: {exc}") from exc





@app.post("/admin/workouts", response_model=AdminWorkoutItem, status_code=status.HTTP_201_CREATED)

async def admin_create_workout(

    payload: AdminWorkoutRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminWorkoutItem:

    now = datetime.now(timezone.utc)

    video_source = str(payload.videoSource or "VIMEO").strip().upper() or "VIMEO"

    try:

        video_url, vimeo_id = await _prepare_workout_video_payload(payload, f"workout-{uuid4().hex}", str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc



    if not video_url:

        raise HTTPException(status_code=400, detail="A workout video is required")



    existing_filter = {"video_url": video_url}

    if vimeo_id:

        existing_filter = {"$or": [{"video_url": video_url}, {"vimeo_id": vimeo_id}]}

    existing_workout = await workouts_collection.find_one(existing_filter)

    if existing_workout:

        raise HTTPException(status_code=409, detail="A workout with this video already exists")



    thumbnail = (payload.thumbnail or "").strip()

    if payload.image_base64:

        try:

            thumbnail = _upload_image_to_s3(

                "workout-thumbnails",

                f"workout-{uuid4().hex}",

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Workout thumbnail upload failed: {exc}") from exc



    document = {

        "title": payload.title.strip(),

        "video_url": video_url,

        "video_source": video_source,

        "tag": payload.tag.strip(),

        "visibility": payload.visibility,

        "thumbnail": thumbnail,

        "created_at": now,

        "updated_at": now,

    }

    if vimeo_id:

        document["vimeo_id"] = vimeo_id

    insert_result = await workouts_collection.insert_one(document)

    document["_id"] = insert_result.inserted_id

    return AdminWorkoutItem(**_serialize_admin_workout_record(document))





@app.patch("/admin/workouts/{workout_id}", response_model=AdminWorkoutItem)

async def admin_update_workout(

    workout_id: str,

    payload: AdminWorkoutRequest,

    background_tasks: BackgroundTasks,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminWorkoutItem:

    try:

        object_id = ObjectId(workout_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid workout id") from exc



    existing_workout = await workouts_collection.find_one({"_id": object_id})

    if not existing_workout:

        raise HTTPException(status_code=404, detail="Workout not found")



    video_source = str(payload.videoSource or "VIMEO").strip().upper() or "VIMEO"

    try:

        video_url, vimeo_id = await _prepare_workout_video_payload(payload, f"workout-{object_id}", str(admin_user["_id"]))

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    duplicate_filter = {"video_url": video_url, "_id": {"$ne": object_id}}

    if vimeo_id:

        duplicate_filter = {"$or": [{"video_url": video_url, "_id": {"$ne": object_id}}, {"vimeo_id": vimeo_id, "_id": {"$ne": object_id}}]}

    duplicate_workout = await workouts_collection.find_one(duplicate_filter)

    if duplicate_workout:

        raise HTTPException(status_code=409, detail="A workout with this video already exists")



    previous_thumbnail = str(existing_workout.get("thumbnail") or "").strip()

    thumbnail = (payload.thumbnail or "").strip()

    if payload.image_base64:

        try:

            thumbnail = _upload_image_to_s3(

                "workout-thumbnails",

                f"workout-{object_id}",

                payload.image_base64,

                payload.mime_type,

                payload.file_name,

            )

        except Exception as exc:

            raise HTTPException(status_code=500, detail=f"Workout thumbnail upload failed: {exc}") from exc

    if previous_thumbnail and previous_thumbnail != thumbnail:

        _delete_image_from_s3(previous_thumbnail)



    update_doc = {

        "title": payload.title.strip(),

        "video_url": video_url,

        "video_source": video_source,

        "tag": payload.tag.strip(),

        "visibility": payload.visibility,

        "thumbnail": thumbnail,

        "updated_at": datetime.now(timezone.utc),

    }

    update_operation: dict[str, Any] = {"$set": update_doc}

    if vimeo_id:

        update_doc["vimeo_id"] = vimeo_id

    else:

        update_operation["$unset"] = {"vimeo_id": ""}

    await workouts_collection.update_one({"_id": object_id}, update_operation)



    updated_workout = await workouts_collection.find_one({"_id": object_id})

    if not updated_workout:

        raise HTTPException(status_code=404, detail="Workout not found")

    if str(existing_workout.get("visibility") or "Draft") != "Published" and payload.visibility == "Published":
        background_tasks.add_task(notify_users_of_published_workout, users_collection, updated_workout)



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

    try:

        summary = await sync_vimeo_workouts()

    except VimeoSyncError as exc:

        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info(
        "admin_workout_sync_result synced_count=%s videos_discovered=%s modules_synced=%s synced_vimeo_ids=%s",
        summary.synced_count,
        summary.videos_discovered,
        summary.modules_synced,
        [str(item.get("vimeoId") or "").strip() for item in (summary.synced_videos or []) if isinstance(item, dict)],
    )

    return AdminWorkoutSyncResponse(

        message="Vimeo workout library synced successfully.",

        syncedCount=summary.synced_count,

        modulesSynced=summary.modules_synced,

        videosDiscovered=summary.videos_discovered,

        syncedVideos=summary.synced_videos or [],

    )


@app.get("/admin/workouts/sync/debug", response_model=AdminWorkoutSyncDebugResponse)
async def admin_debug_synced_workouts(
    limit: int = 50,
    _: dict = Depends(_require_admin_user),
) -> AdminWorkoutSyncDebugResponse:
    capped_limit = max(1, min(int(limit or 50), 200))
    records = await workouts_collection.find(
        {
            "video_source": "VIMEO",
            "vimeo_id": {"$exists": True, "$ne": ""},
        },
        sort=[("vimeo_synced_at", -1), ("updated_at", -1), ("_id", -1)],
    ).to_list(length=capped_limit)

    workouts = [
        {
            "id": str(record["_id"]),
            "title": str(record.get("title") or ""),
            "vimeoId": str(record.get("vimeo_id") or ""),
            "tag": str(record.get("tag") or ""),
            "visibility": str(record.get("visibility") or "Draft"),
            "providerVisibility": str(record.get("vimeo_provider_visibility") or "Draft"),
            "videoSource": str(record.get("video_source") or "VIMEO"),
            "vimeoSourceType": str(record.get("vimeo_source_type") or ""),
            "vimeoSourceUri": str(record.get("vimeo_source_uri") or ""),
            "vimeoSyncedAt": _as_utc(record.get("vimeo_synced_at")) if record.get("vimeo_synced_at") else None,
            "updatedAt": _as_utc(record.get("updated_at")) if record.get("updated_at") else None,
        }
        for record in records
    ]

    return AdminWorkoutSyncDebugResponse(total=len(workouts), workouts=workouts)





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





@app.delete("/journal/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)

async def delete_journal_entry(

    entry_id: str,

    user: dict = Depends(_require_access_user),

) -> Response:

    user_id = str(user["_id"])

    logger.info("journal_delete_attempt user_id=%s entry_id=%s", user_id, entry_id)

    try:

        object_id = ObjectId(entry_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid journal entry id") from exc



    delete_result = await journal_entries_collection.delete_one({"_id": object_id, "user_id": user_id})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="Journal entry not found")



    logger.info("journal_delete_success user_id=%s entry_id=%s", user_id, entry_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)





@app.patch("/journal/entries/{entry_id}", response_model=JournalEntryResponse)

async def update_journal_entry(

    entry_id: str,

    payload: JournalEntryUpdateRequest,

    user: dict = Depends(_require_access_user),

) -> JournalEntryResponse:

    user_id = str(user["_id"])

    logger.info("journal_update_attempt user_id=%s entry_id=%s", user_id, entry_id)

    try:

        object_id = ObjectId(entry_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid journal entry id") from exc



    existing_record = await journal_entries_collection.find_one({"_id": object_id, "user_id": user_id})

    if not existing_record:

        raise HTTPException(status_code=404, detail="Journal entry not found")



    now = datetime.now(timezone.utc)

    update_document = {

        "mood": payload.mood.strip(),

        "content": payload.content.strip(),

        "updated_at": now,

    }

    await journal_entries_collection.update_one(

        {"_id": object_id, "user_id": user_id},

        {"$set": update_document},

    )



    logger.info("journal_update_success user_id=%s entry_id=%s", user_id, entry_id)

    return JournalEntryResponse(

        id=str(existing_record["_id"]),

        user_id=existing_record["user_id"],

        mood=update_document["mood"],

        content=update_document["content"],

        created_at=existing_record["created_at"],

        updated_at=now,

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





@app.post("/journal/analyze/latest", response_model=JournalLatestAnalysisResponse)

async def analyze_latest_journal_entry(

    user: dict = Depends(_require_access_user),

) -> JournalLatestAnalysisResponse:

    user_id = str(user["_id"])

    logger.info("journal_analyze_latest_attempt user_id=%s", user_id)

    record = await journal_entries_collection.find_one(

        {"user_id": user_id},

        sort=[("created_at", -1)],

    )

    if not record:

        raise HTTPException(status_code=404, detail="No journal entries found")



    entry = JournalEntryResponse(

        id=str(record["_id"]),

        user_id=record["user_id"],

        mood=record["mood"],

        content=record["content"],

        created_at=record["created_at"],

        updated_at=record["updated_at"],

    )



    try:

        result = generate_journal_analysis(

            {

                "mood": entry.mood,

                "content": entry.content,

            }

        )

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Journal analysis unavailable: {exc}") from exc



    logger.info("journal_analyze_latest_success user_id=%s entry_id=%s", user_id, entry.id)

    return JournalLatestAnalysisResponse(entry=entry, analysis=result.analysis)





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


@app.post("/ai/meal-analysis", response_model=MealImageAnalysisResponse)

async def analyze_meal_image(

    payload: MealImageAnalysisRequest,

    user: dict = Depends(_require_meal_analysis_access_user),

) -> MealImageAnalysisResponse:

    user_id = str(user["_id"])

    logger.info("meal_image_analyze_attempt user_id=%s file_name=%s", user_id, payload.file_name or "")

    try:
        payload_data = payload.model_dump()
        if payload.image_base64:
            result = generate_meal_image_analysis(payload_data)
        else:
            extracted_text = payload.text_content
            if not extracted_text and payload.document_base64:
                extracted_text = _extract_meal_analysis_document_text(
                    payload.document_base64,
                    payload.mime_type,
                    payload.file_name,
                )
            if not extracted_text or not extracted_text.strip():
                raise HTTPException(status_code=422, detail="The uploaded document did not contain readable meal text.")

            result = generate_meal_document_analysis({
                "text_content": extracted_text.strip(),
                "file_name": payload.file_name,
            })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Meal image analysis unavailable: {exc}") from exc



    created_at = datetime.now(timezone.utc)

    saved_result = {

        **result.data,

        "file_name": payload.file_name,

        "created_at": created_at,

    }

    insert_result = await meal_analysis_entries_collection.insert_one(

        {

            "user_id": user_id,

            "analysis": saved_result,

            "created_at": created_at,

            "updated_at": created_at,

        }

    )

    saved_result["analysis_id"] = str(insert_result.inserted_id)

    logger.info("meal_image_analyze_success user_id=%s", user_id)

    return MealImageAnalysisResponse(**saved_result)





@app.get("/ai/meal-analysis", response_model=MealImageAnalysisListResponse)

async def list_meal_analyses(

    user: dict = Depends(_require_meal_analysis_access_user),

) -> MealImageAnalysisListResponse:

    user_id = str(user["_id"])

    records = await meal_analysis_entries_collection.find(

        {"user_id": user_id},

        sort=[("created_at", -1)],

    ).to_list(length=100)



    analyses: list[MealImageAnalysisResponse] = []

    for record in records:

        analysis_data = dict(record.get("analysis") or {})

        analysis_data["analysis_id"] = str(record["_id"])

        if not analysis_data.get("created_at"):

            analysis_data["created_at"] = record.get("created_at")

        analyses.append(MealImageAnalysisResponse(**analysis_data))



    return MealImageAnalysisListResponse(analyses=analyses)





@app.post("/ai/coach-victor/chat", response_model=CoachVictorChatResponse)

async def coach_victor_chat(

    payload: CoachVictorChatRequest,

    user: dict = Depends(_require_coach_victor_access_user),

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

    await _record_trial_engagement(user, "coach_message")

    return CoachVictorChatResponse(reply=result.reply, thread_id=thread_id)





@app.get("/ai/coach-victor/history", response_model=CoachVictorHistoryResponse)

async def coach_victor_history(

    user: dict = Depends(_require_coach_victor_access_user),

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

    background_tasks: BackgroundTasks,

    user: dict = Depends(_require_meal_plan_access_user),

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

        await _record_trial_engagement(user, "nutrition_plan")
        return NutritionPlanSaveResponse(plan=NutritionPlanResponse(**plan_data))



    await _enforce_nutrition_generation_limit(user)



    try:

        result = await asyncio.to_thread(generate_nutrition_plan, payload_data)

    except NutritionPlanRefusalError as exc:

        raise HTTPException(status_code=422, detail=f"Nutrition plan refused: {exc}") from exc

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Nutrition plan unavailable: {exc}") from exc



    plan = NutritionPlanResponse(**result.data, profile=payload.model_dump())

    background_tasks.add_task(

        _persist_nutrition_plan_record,

        str(user["_id"]),

        profile_hash,

        plan.model_dump(),

    )

    logger.info(

        "nutrition_plan_generated user_id=%s days=%s",

        str(user["_id"]),

        len(plan.days),

    )



    await _record_trial_engagement(user, "nutrition_plan")
    return NutritionPlanSaveResponse(plan=plan)





@app.post("/ai/nutrition/plan/jobs", response_model=NutritionPlanJobResponse, status_code=status.HTTP_202_ACCEPTED)

async def nutrition_plan_job(

    payload: NutritionPlanRequest,

    user: dict = Depends(_require_meal_plan_access_user),

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



    await _enforce_nutrition_generation_limit(user)



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

    user: dict = Depends(_require_meal_plan_access_user),

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





@app.get("/ai/nutrition/plan/latest", response_model=NutritionPlanResponse | None)

async def nutrition_latest_plan(

    user: dict = Depends(_require_meal_plan_access_user),

) -> NutritionPlanResponse | None:

    logger.info("nutrition_latest_attempt user_id=%s", str(user["_id"]))

    record = await nutrition_plans_collection.find_one(

        _standard_nutrition_filter(str(user["_id"])),

        sort=[("created_at", -1)],

    )

    if not record or not record.get("plan"):
        return None



    plan_data = dict(record["plan"])

    plan_data["plan_id"] = str(record["_id"])

    logger.info("nutrition_latest_success user_id=%s plan_id=%s", str(user["_id"]), plan_data["plan_id"])

    return NutritionPlanResponse(**plan_data)





@app.patch("/ai/nutrition/plan/latest/completions", response_model=NutritionPlanResponse)

async def nutrition_latest_plan_completion(

    payload: NutritionMealCompletionUpdateRequest,

    user: dict = Depends(_require_meal_plan_access_user),

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

    user: dict = Depends(_require_nutrition_tracker_access_user),

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





@app.post("/ai/nutrition/plan/progressive/jobs", response_model=NutritionPlanJobResponse, status_code=status.HTTP_202_ACCEPTED)

async def progressive_nutrition_plan_job(

    payload: NutritionPlanRequest,

    user: dict = Depends(_require_meal_plan_access_user),

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



    await _enforce_nutrition_generation_limit(user)



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



    return NutritionPlanJobResponse(

        job_id=job_id,

        status="queued",

        created_at=created_at,

        updated_at=created_at,

    )





@app.get("/ai/nutrition/plan/progressive/jobs/{job_id}", response_model=NutritionPlanJobResponse)

async def progressive_nutrition_plan_job_status(

    job_id: str,

    user: dict = Depends(_require_meal_plan_access_user),

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

    user: dict = Depends(_require_meal_plan_access_user),

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

    user: dict = Depends(_require_meal_plan_access_user),

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

    return [dict(item) for item in record.get("items") or [] if isinstance(item, dict)]





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

    }





def _serialize_app_subscription_plan_item(item: dict, now: datetime | None = None) -> dict:

    normalized = _serialize_admin_subscription_plan_item(item)

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

        "subscriptionTier": _normalize_subscription_plan_tier_key(normalized["tier"]),

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

    started_at = _trial_datetime(user.get("subscription_started_at"))
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
            "marketing_consent": bool(user.get("marketing_consent")),

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
        current_password_hash = str(existing_user.get("password_hash") or "").strip()
        password_matches_seed = bool(current_password_hash) and verify_password(settings.admin_password, current_password_hash)
        should_sync_password = settings.admin_seed_sync_password and not password_matches_seed

        logger.info(
            "admin_seed_validation email=%s exists=true password_hash_present=%s password_matches_seed=%s sync_password=%s",
            settings.admin_email,
            bool(current_password_hash),
            password_matches_seed,
            should_sync_password,
        )

        await users_collection.update_one(

            {"_id": existing_user["_id"]},

            {

                "$set": {

                    "name": existing_user.get("name") or settings.admin_name,

                    "email": settings.admin_email,

                    "role": "admin",

                    "is_admin": True,

                    "is_verified": True,

                    "subscription_tier": "INNER_CIRCLE",

                    "subscription_role": "INNER_CIRCLE",

                    "subscription_status": "ACTIVE",

                    "subscription_billing_cycle": "yearly",

                    "subscription_is_purchased": True,

                    "subscription_purchase_source": "admin_seed",

                    "password_hash": hash_password(settings.admin_password) if should_sync_password else current_password_hash,

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
            settings.admin_email,
            password_matches_seed or should_sync_password,
        )

        return



    await users_collection.insert_one(

        {

            "name": settings.admin_name,

            "email": settings.admin_email,

            "password_hash": hash_password(settings.admin_password),

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
        settings.admin_email,
    )
    logger.info("admin_seed_created email=%s", settings.admin_email)





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

    if status in {"ACTIVE", "PENDING_PAYMENT", "CANCELLED"}:

        return status

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

        "access": subscription.get("access") if isinstance(subscription.get("access"), list) and subscription.get("access") else _resolve_subscription_access(tier),

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

    }





async def _build_subscription_update_doc(existing_user: dict, payload: UpdateSubscriptionRequest, now: datetime) -> dict:

    tier = _normalize_subscription_tier(payload.subscription_tier)

    billing_cycle = _normalize_billing_cycle(payload.billing_cycle)

    subscription_status = "ACTIVE" if payload.confirm_payment and tier != "NONE" else "NONE"

    is_purchased = bool(payload.confirm_payment and tier != "NONE")

    checkout_plan = await _resolve_subscription_checkout_plan(tier, billing_cycle, payload.plan_id) if tier != "NONE" else None

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

    else:

        update_doc["subscription_started_at"] = existing_user.get("subscription_started_at") or now

        update_doc["subscription_confirmed_at"] = now if subscription_status == "ACTIVE" else existing_user.get("subscription_confirmed_at")



    return update_doc





async def _serialize_me_record(record: dict) -> dict:

    stats = await _calculate_user_fitness_stats(str(record["_id"]))

    subscription_summary = _build_subscription_summary(record)

    return {

        "id": str(record["_id"]),
        "created_at": record.get("created_at"),

        "name": str(record.get("name") or ""),

        "email": str(record.get("email") or ""),

        "is_verified": bool(record.get("is_verified")),

        "role": str(record.get("role") or ("admin" if record.get("is_admin") else "user")),

        "is_admin": bool(record.get("is_admin")),

        "country": str(record.get("country") or ""),

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

        "subscription_tier": subscription_summary["tier"],

        "subscription_role": subscription_summary["role"],

        "subscription_status": subscription_summary["status"],

        "subscription_started_at": subscription_summary["started_at"],

        "subscription_confirmed_at": subscription_summary["confirmed_at"],

        "subscription_billing_cycle": subscription_summary["billing_cycle"],

        "subscription_is_purchased": subscription_summary["is_purchased"],

        "subscription_purchase_source": subscription_summary["purchase_source"],

        "subscription_access": subscription_summary["access"],

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





@app.get("/admin/community/top-contributors")
async def admin_get_community_top_contributors(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    records = await community_posts_collection.find({}, sort=[("created_at", -1)]).to_list(length=500)
    posts = await _serialize_community_post_records(records, None, comment_limit_per_post=0, include_reactions=False)
    contributors: dict[str, dict[str, Any]] = {}
    for post in posts:
        author_id = str(post.get("author_id") or "")
        if not author_id:
            continue
        item = contributors.setdefault(author_id, {"userId": author_id, "name": str(post.get("author_name") or "Community member"), "profileImage": str(post.get("author_profile_image") or ""), "postCount": 0, "likeCount": 0})
        item["postCount"] += 1
        item["likeCount"] += max(int(post.get("like_count") or 0), 0)
    return {"contributors": sorted(contributors.values(), key=lambda item: (item["likeCount"], item["postCount"]), reverse=True)[:10]}


@app.get("/admin/community/trending")
async def admin_get_community_trending(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    records = await community_posts_collection.find({}, {"content": 1}).to_list(length=500)
    counts: dict[str, int] = {}
    for record in records:
        for tag in re.findall(r"#[A-Za-z0-9_]+", str(record.get("content") or "").lower()):
            counts[tag] = counts.get(tag, 0) + 1
    return {"hashtags": [{"tag": tag, "postCount": count} for tag, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]]}


@app.get("/admin/community/flags")
async def admin_get_community_flags(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    records = await community_posts_collection.find({"flagged": True}, sort=[("updated_at", -1)]).to_list(length=200)
    posts = await _serialize_community_post_records(records, None, comment_limit_per_post=0, include_reactions=False)
    return {"total": len(posts), "posts": posts}


@app.get("/admin/community/shortcuts")
async def admin_get_community_shortcuts(_: dict = Depends(_require_admin_user)) -> dict[str, Any]:
    flagged_count = await community_posts_collection.count_documents({"flagged": True})
    return {"items": [
        {"key": "flagged_posts", "label": "Review Flagged Posts", "route": "/community", "count": flagged_count},
        {"key": "pinned_announcements", "label": "Pinned Announcements", "route": "/community/announcements"},
        {"key": "community_guidelines", "label": "Community Guidelines", "route": "/community/guidelines"},
    ]}


@app.get("/admin/audit-logs")
async def admin_list_audit_logs(
    limit: int = 50,
    _: dict = Depends(_require_admin_user),
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    records = await admin_audit_logs_collection.find({}, sort=[("created_at", -1)]).to_list(length=safe_limit)
    return {"items": [{
        "id": str(record.get("_id") or ""),
        "adminEmail": str(record.get("admin_email") or ""),
        "action": str(record.get("action") or ""),
        "resource": str(record.get("resource") or ""),
        "resourceId": str(record.get("resource_id") or ""),
        "details": record.get("details") or {},
        "createdAt": record.get("created_at"),
    } for record in records]}


def _serialize_admin_workout_record(record: dict) -> dict:

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    updated_at = _as_utc(record.get("updated_at") or created_at)

    return {

        "id": str(record["_id"]),

        "title": str(record.get("title") or ""),

        "vimeoId": str(record.get("vimeo_id") or ""),

        "videoUrl": str(record.get("video_url") or ""),

        "videoSource": str(record.get("video_source") or "VIMEO"),

        "tag": str(record.get("tag") or ""),

        "visibility": str(record.get("visibility") or "Draft"),

        "providerVisibility": str(record.get("vimeo_provider_visibility") or "Published"),

        "thumbnail": str(record.get("thumbnail") or ""),

        "dateAdded": created_at,

        "updatedAt": updated_at,

    }





async def _sync_workout_library_from_challenge_plan(plan_days: list[dict], challenge_category: str) -> int:

    synced_count = 0

    now = datetime.now(timezone.utc)

    category_tag = str(challenge_category or "Challenge").strip() or "Challenge"



    for day in plan_days:

        for section in day.get("sections") or []:

            for exercise in section.get("exercises") or []:

                workout_id = str(exercise.get("workout_id") or "").strip()

                vimeo_id = str(exercise.get("workout_vimeo_id") or "").strip()

                video_url = str(exercise.get("workout_video_url") or "").strip()

                video_source = str(exercise.get("workout_video_source") or "VIMEO").strip().upper() or "VIMEO"

                if not workout_id and not vimeo_id and not video_url:

                    continue



                title = str(exercise.get("workout_title") or exercise.get("name") or "").strip()

                if not title:

                    title = f"{category_tag} Exercise"



                thumbnail = _normalize_challenge_thumbnail(exercise.get("workout_thumbnail"))

                existing = None

                if workout_id and ObjectId.is_valid(workout_id):

                    existing = await workouts_collection.find_one({"_id": ObjectId(workout_id)})

                if not existing and vimeo_id:

                    existing = await workouts_collection.find_one({"vimeo_id": vimeo_id})

                document = {

                    "title": title,

                    "vimeo_id": vimeo_id,

                    "video_url": video_url,

                    "video_source": video_source,

                    "tag": category_tag,

                    "visibility": "Published",

                    "thumbnail": thumbnail,

                    "updated_at": now,

                }



                if existing:

                    await workouts_collection.update_one({"_id": existing["_id"]}, {"$set": document})

                else:

                    document["created_at"] = now

                    await workouts_collection.insert_one(document)



                synced_count += 1



    return synced_count





def _difficulty_color(difficulty: str) -> str:

    mapping = {

        "BEGINNER": "#22C55E",

        "INTERMEDIATE": "#F59E0B",

        "ADVANCED": "#EF4444",

    }

    return mapping.get(str(difficulty or "").upper(), "#4F8EF7")





def _challenge_color(category: str, difficulty: str) -> str:

    category_key = str(category or "").strip().lower()

    category_map = {

        "strength": "#4F8EF7",

        "cardio": "#06B6D4",

        "mindfulness": "#22C55E",

        "nutrition": "#F59E0B",

        "family": "#A855F7",

    }

    return category_map.get(category_key, _difficulty_color(difficulty))





LEGACY_DEFAULT_CHALLENGE_THUMBNAIL = "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?q=80&w=300&auto=format&fit=crop"





def _normalize_challenge_thumbnail(value: str | None) -> str:

    thumbnail = str(value or "").strip()

    if thumbnail == LEGACY_DEFAULT_CHALLENGE_THUMBNAIL:

        return ""

    return thumbnail





def _slugify_challenge_plan_id(value: str, fallback: str) -> str:

    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")

    return slug[:60] or fallback





def _normalize_challenge_plan_days(
    raw_days: list[ChallengePlanDay] | list[dict] | None,
    duration_days: int | None = None
) -> list[dict]:

    if not raw_days:
        if duration_days and duration_days > 0:
            return [{"day_number": i, "title": f"Day {i}", "focus": "Challenge Activity", "sections": []} for i in range(1, duration_days + 1)]
        return []



    normalized_days: list[dict] = []

    seen_day_numbers: set[int] = set()



    for index, raw_day in enumerate(raw_days, start=1):

        if isinstance(raw_day, ChallengePlanDay):

            day_data = raw_day.model_dump()

        elif isinstance(raw_day, dict):

            day_data = dict(raw_day)

        else:

            continue



        day_number = max(int(day_data.get("day_number") or index), 1)

        if day_number in seen_day_numbers:

            day_number = max(seen_day_numbers) + 1

        seen_day_numbers.add(day_number)



        sections: list[dict] = []

        raw_sections = day_data.get("sections") if isinstance(day_data.get("sections"), list) else []

        for section_index, raw_section in enumerate(raw_sections, start=1):

            section_data = raw_section.model_dump() if hasattr(raw_section, "model_dump") else dict(raw_section or {})

            section_title = str(section_data.get("title") or f"Section {section_index}").strip() or f"Section {section_index}"

            section_id = _slugify_challenge_plan_id(

                str(section_data.get("id") or section_title),

                f"day-{day_number}-section-{section_index}",

            )

            exercises: list[dict] = []

            raw_exercises = section_data.get("exercises") if isinstance(section_data.get("exercises"), list) else []

            for exercise_index, raw_exercise in enumerate(raw_exercises, start=1):

                exercise_data = raw_exercise.model_dump() if hasattr(raw_exercise, "model_dump") else dict(raw_exercise or {})

                exercise_name = str(exercise_data.get("name") or f"Exercise {exercise_index}").strip() or f"Exercise {exercise_index}"

                exercise_id = _slugify_challenge_plan_id(

                    str(exercise_data.get("id") or exercise_name),

                    f"{section_id}-exercise-{exercise_index}",

                )

                exercises.append(

                    {

                        "id": exercise_id,

                        "name": exercise_name,

                        "details": str(exercise_data.get("details") or "Complete as assigned.").strip() or "Complete as assigned.",

                        "notes": str(exercise_data.get("notes") or "").strip(),

                        "workout_id": str(exercise_data.get("workout_id") or "").strip(),

                        "workout_title": str(exercise_data.get("workout_title") or "").strip(),

                        "workout_vimeo_id": str(exercise_data.get("workout_vimeo_id") or "").strip(),

                        "workout_video_url": str(exercise_data.get("workout_video_url") or "").strip(),

                        "workout_video_source": str(exercise_data.get("workout_video_source") or "VIMEO").strip().upper() or "VIMEO",

                        "workout_thumbnail": _normalize_challenge_thumbnail(exercise_data.get("workout_thumbnail")),

                    }

                )

            sections.append(

                {

                    "id": section_id,

                    "title": section_title,

                    "description": str(section_data.get("description") or "").strip(),

                    "estimated_minutes": max(int(section_data.get("estimated_minutes") or 0), 0),

                    "exercises": exercises,

                }

            )



        normalized_days.append(

            {

                "day_number": day_number,

                "title": str(day_data.get("title") or f"Day {day_number}").strip() or f"Day {day_number}",

                "focus": str(day_data.get("focus") or "").strip() or "Challenge work",

                "notes": str(day_data.get("notes") or "").strip(),

                "sections": sections,

            }

        )



    normalized_days.sort(key=lambda item: int(item.get("day_number") or 0))

    return normalized_days





def _build_challenge_plan_text(plan_days: list[dict]) -> str:

    if not plan_days:

        return ""



    lines: list[str] = []

    for day in plan_days:

        day_number = max(int(day.get("day_number") or 0), 0)

        title = str(day.get("title") or f"Day {day_number}").strip()

        focus = str(day.get("focus") or "").strip()

        notes = str(day.get("notes") or "").strip()

        lines.append(f"Day {day_number}: {title}")

        if focus:

            lines.append(f"Focus: {focus}")

        for section in day.get("sections") or []:

            lines.append(f"- {str(section.get('title') or 'Section').strip()}: {str(section.get('description') or '').strip()}")

            for exercise in section.get("exercises") or []:

                lines.append(

                    f"  - {str(exercise.get('name') or 'Exercise').strip()} - {str(exercise.get('details') or '').strip()}"

                )

        if notes:

            lines.append(f"Notes: {notes}")

        lines.append("")

    return "\n".join(lines).strip()





def _extract_plan_day_numbers(plan_days: list[dict]) -> list[int]:

    return [max(int(day.get("day_number") or 0), 0) for day in plan_days if int(day.get("day_number") or 0) > 0]





def _count_completed_plan_days(plan_progress: dict) -> int:

    total = 0

    for entry in plan_progress.values():

        if isinstance(entry, dict) and bool(entry.get("completed")):

            total += 1

    return total





def _count_completed_plan_days_from_start(plan_days: list[dict], plan_progress: dict) -> int:

    completed_days = 0

    for day in plan_days:

        day_number = max(int(day.get("day_number") or 0), 0)

        if day_number <= 0:

            continue

        entry = plan_progress.get(str(day_number), {}) if isinstance(plan_progress, dict) else {}

        if not (isinstance(entry, dict) and bool(entry.get("completed"))):

            break

        completed_days += 1

    return completed_days





def _has_completed_challenge_day_today(membership: dict) -> bool:

    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    today = datetime.now(timezone.utc).date()

    for entry in raw_progress.values():

        if not (isinstance(entry, dict) and bool(entry.get("completed"))):

            continue

        updated_at_raw = entry.get("updated_at")

        if not updated_at_raw:

            continue

        try:

            updated_at = datetime.fromisoformat(str(updated_at_raw).replace("Z", "+00:00"))

        except ValueError:

            continue

        if updated_at.tzinfo is None:

            updated_at = updated_at.replace(tzinfo=timezone.utc)

        else:

            updated_at = updated_at.astimezone(timezone.utc)

        if updated_at.date() == today:

            return True

    return False





def _build_challenge_completion_units(plan_days: list[dict]) -> list[dict[str, str | int]]:

    units: list[dict[str, str | int]] = []

    for day in plan_days:

        day_number = max(int(day.get("day_number") or 0), 0)

        for section in day.get("sections") or []:

            section_id = str(section.get("id") or "")

            exercises = section.get("exercises") if isinstance(section.get("exercises"), list) else []

            if exercises:

                for exercise in exercises:

                    exercise_id = str(exercise.get("id") or "")

                    if not exercise_id:

                        continue

                    units.append(

                        {

                            "day_number": day_number,

                            "section_id": section_id,

                            "exercise_id": exercise_id,

                        }

                    )

            elif section_id:

                units.append(

                    {

                        "day_number": day_number,

                        "section_id": section_id,

                        "exercise_id": "",

                    }

                )

    return units





def _calculate_challenge_completion_counts(plan_days: list[dict], membership: dict) -> tuple[int, int]:

    units = _build_challenge_completion_units(plan_days)

    total_unit_count = len(units)

    if total_unit_count == 0:

        return 0, 0



    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    completed_unit_count = 0

    for unit in units:

        day_progress = raw_progress.get(str(unit["day_number"]), {}) if isinstance(raw_progress, dict) else {}

        if not isinstance(day_progress, dict):

            continue

        completed_exercise_ids = {

            str(exercise_id)

            for exercise_id in day_progress.get("completed_exercise_ids", [])

            if isinstance(exercise_id, str) and exercise_id

        }

        completed_section_ids = {

            str(section_id)

            for section_id in day_progress.get("completed_section_ids", [])

            if isinstance(section_id, str) and section_id

        }

        unit_exercise_id = str(unit["exercise_id"] or "")

        unit_section_id = str(unit["section_id"] or "")

        if unit_section_id and unit_section_id in completed_section_ids:

            completed_unit_count += 1

        elif unit_exercise_id:

            if unit_exercise_id in completed_exercise_ids:

                completed_unit_count += 1



    return completed_unit_count, total_unit_count





def _calculate_challenge_completion_fraction(plan_days: list[dict], membership: dict) -> float:

    completed_unit_count, total_unit_count = _calculate_challenge_completion_counts(plan_days, membership)

    if total_unit_count <= 0:

        duration_days = max(_extract_plan_day_numbers(plan_days), default=max(int(membership.get("duration_days") or 0), 0))

        if duration_days > 0:

            progress_days_completed = _count_completed_plan_days_from_start(

                plan_days,

                membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {},

            ) if plan_days else max(int(membership.get("progress_days_completed") or 0), 0)

            return min(max(progress_days_completed / duration_days, 0.0), 1.0)

        return 0.0

    return min(max(completed_unit_count / total_unit_count, 0.0), 1.0)





def _calculate_challenge_points_earned(plan_days: list[dict], membership: dict, challenge_points: int) -> int:

    if challenge_points <= 0:

        return 0



    completed_unit_count, total_unit_count = _calculate_challenge_completion_counts(plan_days, membership)

    if total_unit_count <= 0 or completed_unit_count <= 0:

        return 0



    return round((challenge_points * completed_unit_count) / total_unit_count)





def _build_viewer_plan_progress(plan_days: list[dict], membership: dict) -> list[ChallengePlanDayProgressResponse]:

    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}

    progress_responses: list[ChallengePlanDayProgressResponse] = []



    for day in plan_days:

        day_number = max(int(day.get("day_number") or 0), 0)

        raw_day_progress = raw_progress.get(str(day_number), {}) if isinstance(raw_progress, dict) else {}

        completed_section_ids = [

            str(section_id)

            for section_id in raw_day_progress.get("completed_section_ids", [])

            if isinstance(section_id, str) and section_id

        ] if isinstance(raw_day_progress, dict) else []

        completed_exercise_ids = [

            str(exercise_id)

            for exercise_id in raw_day_progress.get("completed_exercise_ids", [])

            if isinstance(exercise_id, str) and exercise_id

        ] if isinstance(raw_day_progress, dict) else []

        progress_responses.append(

            ChallengePlanDayProgressResponse(

                day_number=day_number,

                completed=bool(isinstance(raw_day_progress, dict) and raw_day_progress.get("completed")),

                completed_section_ids=completed_section_ids,

                completed_exercise_ids=completed_exercise_ids,

            )

        )



    return progress_responses





def _serialize_challenge_plan_progress_response(challenge_id: str, membership: dict, plan_days: list[dict]) -> ChallengePlanProgressResponse:

    viewer_plan_progress = _build_viewer_plan_progress(plan_days, membership)

    challenge_points = max(int((membership.get("challenge_points") or membership.get("points") or 0)), 0)

    progress_days_completed = _count_completed_plan_days_from_start(plan_days, membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {})

    return ChallengePlanProgressResponse(

        challenge_id=challenge_id,

        viewer_membership_status=str(membership.get("status") or "ACTIVE"),

        viewer_progress_days_completed=progress_days_completed,

        viewer_points_earned=_calculate_challenge_points_earned(plan_days, membership, challenge_points),

        viewer_plan_progress=viewer_plan_progress,

    )





def _load_report_font(size: int, bold: bool = False) -> Any:

    _require_pillow()

    font_candidates = [

        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",

        "arialbd.ttf" if bold else "arial.ttf",

    ]

    for candidate in font_candidates:

        try:

            return ImageFont.truetype(candidate, size=size)

        except Exception:

            continue

    return ImageFont.load_default()





def _wrap_report_text(draw: Any, text: str, font: Any, max_width: int) -> list[str]:

    words = str(text or "").split()

    if not words:

        return [""]



    lines: list[str] = []

    current = words[0]

    for word in words[1:]:

        candidate = f"{current} {word}"

        bbox = draw.textbbox((0, 0), candidate, font=font)

        if bbox[2] - bbox[0] <= max_width:

            current = candidate

        else:

            lines.append(current)

            current = word

    lines.append(current)

    return lines





def _draw_centered_text(draw: Any, center_x: int, y: int, text: str, font: Any, fill: str) -> None:

    bbox = draw.textbbox((0, 0), text, font=font)

    width = bbox[2] - bbox[0]

    draw.text((center_x - width / 2, y), text, font=font, fill=fill)





def _build_report_completed_entries(thread: dict, membership: dict) -> list[dict[str, str]]:

    entries: list[dict[str, str]] = []

    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}



    for day in _normalize_challenge_plan_days(
        thread.get("plan_days") if isinstance(thread.get("plan_days"), list) else [],
        duration_days=max(int(thread.get("duration_days") or 0), 1)
    ):

        day_progress = raw_progress.get(str(day.get("day_number") or 0), {}) if isinstance(raw_progress, dict) else {}

        completed_exercise_ids = {

            str(exercise_id)

            for exercise_id in (day_progress.get("completed_exercise_ids") or [])

            if isinstance(exercise_id, str) and exercise_id

        } if isinstance(day_progress, dict) else set()

        completed_section_ids = {

            str(section_id)

            for section_id in (day_progress.get("completed_section_ids") or [])

            if isinstance(section_id, str) and section_id

        } if isinstance(day_progress, dict) else set()



        for section in day.get("sections") or []:

            section_title = str(section.get("title") or "Section").strip() or "Section"

            if str(section.get("id") or "") in completed_section_ids:

                for exercise in section.get("exercises") or []:

                    exercise_name = str(exercise.get("name") or "Exercise").strip() or "Exercise"

                    entries.append({

                        "title": exercise_name,

                        "detail": f"Day {int(day.get('day_number') or 0)} | {section_title}",

                    })

                if not section.get("exercises"):

                    entries.append({

                        "title": f"{section_title} completed",

                        "detail": f"Day {int(day.get('day_number') or 0)} | {str(day.get('title') or 'Day')}",

                    })

                continue



            for exercise in section.get("exercises") or []:

                exercise_id = str(exercise.get("id") or "")

                if exercise_id and exercise_id in completed_exercise_ids:

                    exercise_name = str(exercise.get("name") or "Exercise").strip() or "Exercise"

                    entries.append({

                        "title": exercise_name,

                        "detail": f"Day {int(day.get('day_number') or 0)} | {section_title}",

                    })



    return entries[:10]





def _build_challenge_progress_report_png(

    thread: dict,

    membership: dict,

    user_name: str,

) -> tuple[bytes, str]:

    _require_pillow()

    plan_days = _normalize_challenge_plan_days(
        thread.get("plan_days") if isinstance(thread.get("plan_days"), list) else [],
        duration_days=max(int(thread.get("duration_days") or 0), 1)
    )

    challenge_points = max(int(thread.get("points") or 0), 0)

    membership_with_points = dict(membership)

    membership_with_points["challenge_points"] = challenge_points

    completed_units, total_units = _calculate_challenge_completion_counts(plan_days, membership_with_points)

    completion_fraction = _calculate_challenge_completion_fraction(plan_days, membership_with_points)

    completion_percent = max(min(int(round(completion_fraction * 100)), 100), 0)

    viewer_points = _calculate_challenge_points_earned(plan_days, membership_with_points, challenge_points)

    entries = _build_report_completed_entries(thread, membership_with_points)



    width = 1080

    row_height = 76

    header_height = 430

    footer_height = 288

    rows = max(len(entries), 1)

    height = header_height + rows * row_height + footer_height



    image = Image.new("RGBA", (width, height), "#05111D")

    draw = ImageDraw.Draw(image)



    accent = "#00F0D0"

    accent2 = "#F59E0B"

    surface = "#081423"

    surface2 = "#0E1826"

    muted = "#8FA7C1"

    white = "#FFFFFF"



    draw.rounded_rectangle((36, 36, width - 36, height - 36), radius=42, fill=surface, outline=(255, 255, 255, 24), width=2)

    draw.ellipse((820, 32, 1100, 312), fill=(0, 240, 208, 14))

    draw.ellipse((900, 0, 1060, 160), fill=(255, 255, 255, 10))



    title_font = _load_report_font(40, bold=True)

    app_font = _load_report_font(24, bold=True)

    body_font = _load_report_font(20)

    small_font = _load_report_font(16)

    metric_font = _load_report_font(28, bold=True)

    section_font = _load_report_font(22, bold=True)



    draw.ellipse((84, 84, 172, 172), fill=accent)

    _draw_centered_text(draw, 128, 112, "VF", _load_report_font(30, bold=True), "#03131F")

    draw.text((196, 92), "VICTORY FITNESS", font=app_font, fill=accent)

    draw.text((196, 126), str(user_name or "Victory Member"), font=title_font, fill=white)

    draw.text((196, 166), f"Challenge report generated {datetime.now(timezone.utc).strftime('%b %d, %Y')}", font=small_font, fill=muted)



    challenge_name = str(thread.get("title") or "Challenge Progress")

    challenge_lines = _wrap_report_text(draw, challenge_name, title_font, 900)

    draw.multiline_text((84, 238), "\n".join(challenge_lines), font=title_font, fill=white, spacing=8)

    draw.text(

        (84, 300),

        f"{completion_percent}% complete | {completed_units}/{max(total_units, completed_units or 1)} exercises done",

        font=body_font,

        fill=muted,

    )



    draw.rounded_rectangle((84, 334, 940, 352), radius=9, fill=(255, 255, 255, 18))

    draw.rounded_rectangle((84, 334, 84 + int(856 * (completion_percent / 100)), 352), radius=9, fill=accent)



    metric_boxes = [

        ((84, 380, 336, 456), "DAYS COMPLETED", f"{max(int(membership.get('progress_days_completed') or 0), 0)}/{max(int(thread.get('duration_days') or 0), 1)}", accent),

        ((356, 380, 608, 456), "POINTS EARNED", f"{viewer_points}/{challenge_points}", accent2),

        ((628, 380, 940, 456), "EXERCISES DONE", f"{completed_units}", "#A78BFA"),

    ]

    for box, label, value, color in metric_boxes:

        draw.rounded_rectangle(box, radius=24, fill=surface2, outline=tuple(int(color[i:i+2], 16) for i in (1, 3, 5)) + (40,), width=2)

        draw.text((box[0] + 24, box[1] + 20), label, font=small_font, fill=color)

        draw.text((box[0] + 24, box[1] + 48), value, font=metric_font, fill=white)



    draw.text((84, 500), "Completed exercises", font=section_font, fill=white)

    y = 546

    if entries:

      content_entries = entries

    else:

      content_entries = [{"title": "No completed items yet", "detail": "Finish exercises to build your share card."}]

    for entry in content_entries:

        draw.rounded_rectangle((84, y, 996, y + 60), radius=18, fill="#0D1725", outline=(255, 255, 255, 12), width=1)

        draw.ellipse((102, y + 13, 130, y + 41), fill=accent)

        draw.line((108, y + 27, 116, y + 35), fill="#03131F", width=3)

        draw.line((116, y + 35, 124, y + 21), fill="#03131F", width=3)

        draw.text((150, y + 10), entry["title"], font=body_font, fill=white)

        draw.text((150, y + 34), entry["detail"], font=small_font, fill=muted)

        y += row_height



    footer_top = height - 238

    draw.text((84, footer_top), "Download Victory Fitness", font=app_font, fill=white)

    draw.text((84, footer_top + 32), "Train with the full app on Google Play and the App Store", font=small_font, fill=muted)



    def draw_store_card(x: int, title: str, subtitle: str, accent_color: str, symbol: str) -> None:

        draw.rounded_rectangle((x, height - 160, x + 396, height - 66), radius=28, fill="#0E1826", outline=(36, 50, 68, 255), width=2)

        if symbol == "play":

            draw.polygon([(x + 38, height - 128), (x + 38, height - 92), (x + 68, height - 110)], fill=accent_color)

            draw.polygon([(x + 68, height - 110), (x + 80, height - 121), (x + 80, height - 99)], fill="#60A5FA")

            draw.polygon([(x + 38, height - 128), (x + 61, height - 113), (x + 38, height - 92)], fill="#F59E0B")

        else:

            draw.rounded_rectangle((x + 30, height - 134, x + 78, height - 86), radius=14, fill=(255, 255, 255, 18))

            draw.ellipse((x + 38, height - 124, x + 70, height - 92), fill=white)

        draw.text((x + 104, height - 126), subtitle, font=small_font, fill=muted)

        draw.text((x + 104, height - 98), title, font=app_font, fill=white)



    draw_store_card(84, "Google Play", "Download on", accent, "play")

    draw_store_card(514, "App Store", "Download on the", white, "apple")



    output = BytesIO()

    image.save(output, format="PNG", optimize=True)

    png_bytes = output.getvalue()

    share_message = "\n".join([

        "Victory Fitness",

        f"Member: {user_name}",

        f"{challenge_name} progress report",

        f"Completed {completion_percent}% | {max(int(membership.get('progress_days_completed') or 0), 0)}/{max(int(thread.get('duration_days') or 0), 1)} days | {viewer_points}/{challenge_points} pts",

    ])

    return png_bytes, share_message





def _serialize_admin_challenge_record(

    record: dict,

    stats_map: dict[str, dict[str, int]] | None = None,

) -> dict:

    challenge_id = str(record["_id"])

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    updated_at = _as_utc(record.get("updated_at") or created_at)

    stats = (stats_map or {}).get(challenge_id, {})

    return {

        "id": challenge_id,

        "title": str(record.get("title") or ""),

        "description": str(record.get("description") or ""),

        "whyItMatters": str(record.get("why_it_matters") or ""),

        "planText": str(record.get("plan_text") or ""),

        "planDays": _normalize_challenge_plan_days(record.get("plan_days") if isinstance(record.get("plan_days"), list) else []),

        "category": str(record.get("category") or "Challenge"),

        "durationDays": max(int(record.get("duration_days") or 0), 0),

        "points": max(int(record.get("points") or 0), 0),

        "difficulty": str(record.get("difficulty") or "BEGINNER"),

        "status": str(record.get("status") or "DRAFT"),

        "thumbnail": _normalize_challenge_thumbnail(record.get("thumbnail")),

        "participantCount": int(stats.get("participants", 0)),

        "completionCount": int(stats.get("completions", 0)),

        "createdAt": created_at,

        "updatedAt": updated_at,

    }





def _serialize_challenge_chat_message(

    record: dict,

    author_record: dict | None = None,

    viewer_user_id: str | None = None,

    reactions: list[dict] | None = None,

) -> dict:

    created_at = _as_utc(record.get("created_at") or datetime.now(timezone.utc))

    updated_at = _as_utc(record.get("updated_at") or created_at)

    author_id = str(record.get("author_id") or "")

    author_name = str(record.get("author_name") or "Member")

    author_role = str(record.get("author_role") or "user")

    author_profile_image = str(record.get("author_profile_image") or "")

    if author_record:

        author_name = str(author_record.get("name") or "Member").strip() or "Member"

        author_role = str(author_record.get("role") or ("admin" if author_record.get("is_admin") else "user")).strip() or "user"

        author_profile_image = str(author_record.get("profile_image") or "").strip()



    return {

        "id": str(record.get("_id") or ""),

        "challenge_id": str(record.get("challenge_id") or ""),

        "author_id": author_id,

        "author_name": author_name,

        "author_role": author_role,

        "author_profile_image": author_profile_image,

        "message_type": str(record.get("message_type") or "message"),

        "content": str(record.get("content") or ""),

        "image_url": str(record.get("image_url") or ""),

        "reply_to_message_id": str(record.get("reply_to_message_id")) if record.get("reply_to_message_id") else None,

        "progress_payload": dict(record.get("progress_payload")) if isinstance(record.get("progress_payload"), dict) else None,

        "created_at": created_at,

        "updated_at": updated_at,

        "can_delete": bool(viewer_user_id) and viewer_user_id == author_id,

        "can_edit": bool(viewer_user_id) and viewer_user_id == author_id and author_id not in {"system", "coach_bot"} and not record.get("deleted_at"),

        "is_edited": bool(record.get("edited_at")),

        "is_deleted": bool(record.get("deleted_at")),

        "reactions": reactions or [],

    }





def _serialize_public_workout_record(record: dict) -> dict:

    return shared_serialize_public_workout_record(record)





async def _load_challenge_stats_map(challenge_ids: list[str]) -> dict[str, dict[str, int]]:

    if not challenge_ids:

        return {}



    participant_records = await challenge_memberships_collection.aggregate(

        [

            {"$match": {"challenge_id": {"$in": challenge_ids}}},

            {"$group": {"_id": "$challenge_id", "participants": {"$sum": 1}}},

        ]

    ).to_list(length=len(challenge_ids))

    completion_records = await challenge_memberships_collection.aggregate(

        [

            {"$match": {"challenge_id": {"$in": challenge_ids}, "status": "COMPLETED"}},

            {"$group": {"_id": "$challenge_id", "completions": {"$sum": 1}}},

        ]

    ).to_list(length=len(challenge_ids))



    stats_map: dict[str, dict[str, int]] = {challenge_id: {"participants": 0, "completions": 0} for challenge_id in challenge_ids}

    for item in participant_records:

        challenge_id = str(item.get("_id") or "")

        if challenge_id:

            stats_map.setdefault(challenge_id, {"participants": 0, "completions": 0})["participants"] = int(item.get("participants", 0))

    for item in completion_records:

        challenge_id = str(item.get("_id") or "")

        if challenge_id:

            stats_map.setdefault(challenge_id, {"participants": 0, "completions": 0})["completions"] = int(item.get("completions", 0))

    return stats_map





async def _get_challenge_or_404(challenge_id: str) -> dict:

    try:

        object_id = ObjectId(challenge_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge id") from exc



    challenge = await challenges_collection.find_one({"_id": object_id})

    if not challenge:

        raise HTTPException(status_code=404, detail="Challenge not found")

    return challenge





async def _get_challenge_membership_or_403(challenge_id: str, user_id: str) -> dict:

    membership = await challenge_memberships_collection.find_one(

        {"challenge_id": challenge_id, "user_id": user_id}

    )

    if not membership:

        raise HTTPException(status_code=403, detail="Start this challenge to access the chat")

    return membership





async def _get_challenge_message_or_404(challenge_id: str, message_id: str) -> dict:

    try:

        object_id = ObjectId(message_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid challenge chat message id") from exc



    message_record = await challenge_chat_messages_collection.find_one(

        {"_id": object_id, "challenge_id": challenge_id}

    )

    if not message_record:

        raise HTTPException(status_code=404, detail="Challenge chat message not found")

    return message_record





def _ensure_challenge_read_access(membership: dict, challenge: dict) -> None:

    membership_status = str(membership.get("status") or "").upper()

    challenge_status = str(challenge.get("status") or "").upper()

    if membership_status not in {"ACTIVE", "COMPLETED"}:

        raise HTTPException(status_code=403, detail="You do not have access to this challenge chat")

    if challenge_status == "DRAFT":

        raise HTTPException(status_code=403, detail="This challenge is not available")





def _ensure_challenge_write_access(membership: dict, challenge: dict) -> None:

    membership_status = str(membership.get("status") or "").upper()

    if membership_status != "ACTIVE":

        raise HTTPException(status_code=403, detail="Only active participants can post in this challenge chat")

    challenge_status = str(challenge.get("status") or "").upper()

    if challenge_status != "ACTIVE":

        if challenge_status == "UPCOMING":

            raise HTTPException(status_code=403, detail="This challenge has not started yet")

        if challenge_status == "ARCHIVED":

            raise HTTPException(status_code=403, detail="This challenge has been archived")

        raise HTTPException(status_code=403, detail="This challenge is not available")





def _ensure_challenge_chat_write_access(membership: dict, challenge: dict) -> None:

    membership_status = str(membership.get("status") or "").upper()

    if membership_status not in {"ACTIVE", "COMPLETED"}:

        raise HTTPException(status_code=403, detail="You do not have permission to post in this challenge chat")

    challenge_status = str(challenge.get("status") or "").upper()

    if challenge_status != "ACTIVE":

        if challenge_status == "UPCOMING":

            raise HTTPException(status_code=403, detail="This challenge has not started yet")

        if challenge_status == "ARCHIVED":

            raise HTTPException(status_code=403, detail="This challenge has been archived")

        raise HTTPException(status_code=403, detail="This challenge is not available")





async def _load_challenge_chat_author_records(records: list[dict]) -> dict[str, dict]:

    author_ids = {

        str(record.get("author_id") or "").strip()

        for record in records

        if str(record.get("author_id") or "").strip() and ObjectId.is_valid(str(record.get("author_id") or "").strip())

    }

    if not author_ids:

        return {}



    object_ids = [ObjectId(author_id) for author_id in author_ids]

    author_records = await users_collection.find({"_id": {"$in": object_ids}}).to_list(length=len(object_ids))

    return {str(author_record.get("_id") or ""): author_record for author_record in author_records}





async def _load_challenge_participants(challenge_id: str) -> list[ChallengeParticipantResponse]:

    memberships = await challenge_memberships_collection.find(

        {"challenge_id": challenge_id, "status": {"$in": ["ACTIVE", "COMPLETED"]}},

        sort=[("started_at", 1), ("joined_at", 1), ("_id", 1)],

    ).to_list(length=None)

    user_ids = [

        str(membership.get("user_id") or "").strip()

        for membership in memberships

        if str(membership.get("user_id") or "").strip() and ObjectId.is_valid(str(membership.get("user_id") or "").strip())

    ]

    user_records = await users_collection.find(

        {"_id": {"$in": [ObjectId(user_id) for user_id in user_ids]}}

    ).to_list(length=len(user_ids)) if user_ids else []

    users_by_id = {str(record.get("_id") or ""): record for record in user_records}



    participants: list[ChallengeParticipantResponse] = []

    seen_user_ids: set[str] = set()

    for membership in memberships:

        user_id = str(membership.get("user_id") or "").strip()

        if not user_id or user_id in seen_user_ids:

            continue

        seen_user_ids.add(user_id)

        user_record = users_by_id.get(user_id, {})

        participants.append(

            ChallengeParticipantResponse(

                user_id=user_id,

                name=str(user_record.get("name") or "Member").strip() or "Member",

                profile_image=str(user_record.get("profile_image") or "").strip(),

            )

        )

    return participants





async def _load_challenge_chat_messages(

    challenge_id: str,

    viewer_user_id: str | None,

    limit: int = 50,

) -> list[dict]:

    records = await challenge_chat_messages_collection.find(

        {"challenge_id": challenge_id},

        sort=[("created_at", -1), ("_id", -1)],

        limit=max(limit, 1),

    ).to_list(length=max(limit, 1))

    records.reverse()

    author_records_by_id = await _load_challenge_chat_author_records(records)

    reactions_by_message_id = await _load_challenge_message_reactions(records, viewer_user_id)

    return [

        _serialize_challenge_chat_message(

            record,

            author_records_by_id.get(str(record.get("author_id") or "")),

            viewer_user_id,

            reactions_by_message_id.get(str(record.get("_id") or ""), []),

        )

        for record in records

    ]





async def _count_unread_challenge_messages(

    challenge_id: str,

    viewer_user_id: str,

    membership: dict,

) -> int:

    last_read = membership.get("last_read_message_at")

    filter_doc: dict = {

        "challenge_id": challenge_id,

        "author_id": {"$ne": viewer_user_id},

    }

    if isinstance(last_read, datetime):

        filter_doc["created_at"] = {"$gt": _as_utc(last_read)}

    return await challenge_chat_messages_collection.count_documents(filter_doc)





async def _load_challenge_message_reactions(

    records: list[dict],

    viewer_user_id: str | None,

) -> dict[str, list[dict]]:

    message_ids = [str(record.get("_id") or "") for record in records if record.get("_id")]

    if not message_ids:

        return {}



    reactions = await challenge_message_reactions_collection.find(

        {"message_id": {"$in": message_ids}},

        sort=[("created_at", 1), ("_id", 1)],

    ).to_list(length=5000)

    grouped: dict[str, dict[str, dict]] = {}

    for reaction in reactions:

        message_id = str(reaction.get("message_id") or "")

        emoji = str(reaction.get("emoji") or "")

        if not message_id or not emoji:

            continue

        grouped.setdefault(message_id, {})

        bucket = grouped[message_id].setdefault(

            emoji,

            {"emoji": emoji, "count": 0, "viewer_reacted": False},

        )

        bucket["count"] = int(bucket.get("count", 0)) + 1

        if viewer_user_id and str(reaction.get("user_id") or "") == viewer_user_id:

            bucket["viewer_reacted"] = True



    return {

        message_id: list(emoji_map.values())

        for message_id, emoji_map in grouped.items()

    }





def _challenge_message_mentions_coach(content: str) -> bool:

    return bool(re.search(r"(?i)(?:^|\s)@coach\b", content or ""))





def _strip_challenge_coach_mentions(content: str) -> str:

    return re.sub(r"(?i)(?:^|\s)@coach\b", " ", content or "").strip()





async def _create_challenge_coach_reply(

    challenge: dict,

    membership: dict,

    user: dict,

    trigger_message: dict,

) -> dict | None:

    coach_prompt = _strip_challenge_coach_mentions(str(trigger_message.get("content") or ""))

    if not coach_prompt:

        return None



    recent_records = await challenge_chat_messages_collection.find(

        {"challenge_id": str(challenge.get("_id") or "")},

        sort=[("created_at", -1), ("_id", -1)],

        limit=12,

    ).to_list(length=12)

    recent_records.reverse()



    chat_history: list[dict[str, str]] = [

        {

            "role": "user",

            "content": (

                "Challenge context:\n"

                f"- Title: {str(challenge.get('title') or '')}\n"

                f"- Category: {str(challenge.get('category') or 'Challenge')}\n"

                f"- Duration days: {max(int(challenge.get('duration_days') or 0), 0)}\n"

                f"- Difficulty: {str(challenge.get('difficulty') or 'BEGINNER')}\n"

                f"- User progress days completed: {max(int(membership.get('progress_days_completed') or 0), 0)}\n"

                f"- User question: {coach_prompt}\n"

                "Respond as Coach Victor inside a group challenge chat. Keep it concise, practical, and supportive."

            ),

        }

    ]



    author_records_by_id = await _load_challenge_chat_author_records(recent_records)

    for record in recent_records:

        message_type = str(record.get("message_type") or "message")

        if message_type not in {"message", "progress_update", "ai_reply"}:

            continue



        author_id = str(record.get("author_id") or "")

        content = str(record.get("content") or "").strip()

        if not content:

            continue



        if author_id == "coach_bot":

            chat_history.append({"role": "assistant", "content": content})

            continue



        author_name = str(author_records_by_id.get(author_id, {}).get("name") or record.get("author_name") or "Member").strip() or "Member"

        chat_history.append({"role": "user", "content": f"{author_name}: {content}"})



    result = generate_coach_victor_reply(chat_history)

    reply = result.reply.strip()

    if not reply:

        return None



    now = datetime.now(timezone.utc)

    reply_document = {

        "_id": ObjectId(),

        "challenge_id": str(challenge.get("_id") or ""),

        "author_id": "coach_bot",

        "author_name": "Coach Victor",

        "author_role": "coach",

        "author_profile_image": "",

        "message_type": "ai_reply",

        "content": reply,

        "image_url": "",

        "reply_to_message_id": str(trigger_message.get("_id") or ""),

        "progress_payload": None,

        "created_at": now,

        "updated_at": now,

    }

    await challenge_chat_messages_collection.insert_one(reply_document)

    await _broadcast_challenge_chat_event(

        "message_created",

        str(challenge.get("_id") or ""),

        reply_document,

    )

    await notify_user(
        users_collection,
        user,
        "Coach Victor replied",
        "Coach Victor replied to your challenge message.",
        "challenge_coach_reply",
        {"type": "challenge_chat", "challengeId": str(challenge.get("_id") or ""), "route": f"/challenges/{challenge.get('_id')}"},
    )
    return reply_document





async def _serialize_single_challenge_chat_message(

    record: dict,

    viewer_user_id: str | None = None,

) -> dict:

    author_records_by_id = await _load_challenge_chat_author_records([record])

    reactions_by_message_id = await _load_challenge_message_reactions([record], viewer_user_id)

    return _serialize_challenge_chat_message(

        record,

        author_records_by_id.get(str(record.get("author_id") or "")),

        viewer_user_id,

        reactions_by_message_id.get(str(record.get("_id") or ""), []),

    )





async def _broadcast_challenge_chat_event(

    event: str,

    challenge_id: str,

    message_record: dict | None = None,

    message_id: str | None = None,

) -> None:

    payload = ChallengeChatEventResponse(

        event=event,

        challenge_id=challenge_id,

        message=ChallengeChatMessageResponse(**(await _serialize_single_challenge_chat_message(message_record, None))) if message_record else None,

        message_id=message_id,

    ).model_dump(mode="json")

    await challenge_chat_socket_manager.broadcast(challenge_id, payload)





async def _build_challenge_overview_response(user: dict) -> ChallengeOverviewResponse:

    user_id = str(user["_id"])

    memberships = await challenge_memberships_collection.find(

        {"user_id": user_id},

        projection=CHALLENGE_OVERVIEW_MEMBERSHIP_PROJECTION,

        sort=[("joined_at", -1), ("_id", -1)],

    ).to_list(length=None)

    challenge_ids = [membership.get("challenge_id") for membership in memberships if membership.get("challenge_id")]

    challenge_object_ids: list[ObjectId] = []

    for challenge_id in challenge_ids:

        try:

            challenge_object_ids.append(ObjectId(str(challenge_id)))

        except Exception:

            continue



    challenge_records = await challenges_collection.find(

        {"_id": {"$in": challenge_object_ids}},

        projection=CHALLENGE_OVERVIEW_CHALLENGE_PROJECTION,

    ).to_list(length=len(challenge_object_ids)) if challenge_object_ids else []

    challenges_by_id = {str(record["_id"]): record for record in challenge_records}



    for membership in memberships:

        if str(membership.get("status") or "").upper() == "ACTIVE":

            challenge_id = str(membership.get("challenge_id") or "")

            challenge = challenges_by_id.get(challenge_id)

            if not challenge:

                continue

            total_days = max(int(challenge.get("duration_days") or 0), 1)

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

                    if elapsed_days >= total_days:

                        now = datetime.now(timezone.utc)

                        await challenge_memberships_collection.update_one(

                            {"_id": membership["_id"]},

                            {"$set": {"status": "COMPLETED", "completed_at": now, "updated_at": now}}

                        )

                        membership["status"] = "COMPLETED"

                        membership["completed_at"] = now

                except ValueError:

                    pass



    active_memberships = [

        membership

        for membership in memberships

        if str(membership.get("status") or "").upper() == "ACTIVE"

        and str((challenges_by_id.get(str(membership.get("challenge_id") or "")) or {}).get("status") or "").upper() == "ACTIVE"

    ]

    completed_memberships = [membership for membership in memberships if str(membership.get("status") or "").upper() == "COMPLETED"]

    chat_memberships = [

        membership

        for membership in memberships

        if str(membership.get("status") or "").upper() in {"ACTIVE", "COMPLETED"}

        and str((challenges_by_id.get(str(membership.get("challenge_id") or "")) or {}).get("status") or "").upper() != "DRAFT"

    ]



    active_challenges: list[UserActiveChallengeResponse] = []

    active_challenge_ids: list[str] = []

    active_stats = await _load_challenge_stats_map([str(membership.get("challenge_id") or "") for membership in active_memberships if membership.get("challenge_id")])

    for membership in active_memberships:

        challenge_id = str(membership.get("challenge_id") or "")

        challenge = challenges_by_id.get(challenge_id)

        if not challenge:

            continue

        total_days = max(int(challenge.get("duration_days") or 0), 1)

        plan_days = _normalize_challenge_plan_days(

            challenge.get("plan_days") if isinstance(challenge.get("plan_days"), list) else [],

            duration_days=total_days

        )

        started_at_raw = membership.get("started_at")

        elapsed_days = 0

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

            except ValueError:

                pass

        days_left = max(total_days - elapsed_days, 0)

        progress_fraction = _calculate_challenge_completion_fraction(plan_days, membership)

        active_challenge_ids.append(challenge_id)

        active_challenges.append(

            UserActiveChallengeResponse(

                id=str(membership.get("_id") or challenge_id),
                created_at=membership.get("started_at") or challenge.get("created_at"),

                challenge_id=challenge_id,

                title=str(challenge.get("title") or ""),

                description=str(challenge.get("description") or ""),

                why_it_matters=str(challenge.get("why_it_matters") or ""),

                type=str(challenge.get("category") or "Challenge"),

                plan_text=str(challenge.get("plan_text") or ""),

                duration_days=total_days,

                days_left=days_left,

                total_days=total_days,

                progress=progress_fraction,

                points=max(int(challenge.get("points") or 0), 0),

                participants=int(active_stats.get(challenge_id, {}).get("participants", 0)),

                thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

                color=_challenge_color(str(challenge.get("category") or ""), str(challenge.get("difficulty") or "")),

            )

        )



    completed_challenges: list[UserCompletedChallengeResponse] = []

    for membership in completed_memberships:

        challenge_id = str(membership.get("challenge_id") or "")

        challenge = challenges_by_id.get(challenge_id)

        completed_at = membership.get("completed_at")

        if not challenge or not isinstance(completed_at, datetime):

            continue

        completed_challenges.append(

            UserCompletedChallengeResponse(

                id=str(membership.get("_id") or challenge_id),
                created_at=completed_at or challenge.get("created_at"),

                challenge_id=challenge_id,

                title=str(challenge.get("title") or ""),

                description=str(challenge.get("description") or ""),

                why_it_matters=str(challenge.get("why_it_matters") or ""),

                duration_days=max(int(challenge.get("duration_days") or 0), 0),

                type=str(challenge.get("category") or "Challenge"),

                earned_points=max(int(challenge.get("points") or 0), 0),

                participants=int(active_stats.get(challenge_id, {}).get("participants", 0)),

                thumbnail=_normalize_challenge_thumbnail(challenge.get("thumbnail")),

                completed_at=_as_utc(completed_at),

                color=_challenge_color(str(challenge.get("category") or ""), str(challenge.get("difficulty") or "")),

            )

        )



    chat_challenge_ids = list(dict.fromkeys(str(membership.get("challenge_id") or "") for membership in chat_memberships if membership.get("challenge_id")))

    active_chat_messages = await challenge_chat_messages_collection.aggregate(

        [

            {"$match": {"challenge_id": {"$in": chat_challenge_ids}}},

            {"$sort": {"created_at": -1}},

            {"$group": {"_id": "$challenge_id", "content": {"$first": "$content"}, "created_at": {"$first": "$created_at"}}},

        ]

    ).to_list(length=len(chat_challenge_ids)) if chat_challenge_ids else []

    chat_by_challenge = {str(item.get("_id") or ""): item for item in active_chat_messages}



    active_chats: list[ChallengeChatSummaryResponse] = []

    for membership in chat_memberships:

        challenge_id = str(membership.get("challenge_id") or "")

        if challenge_id not in challenges_by_id:

            continue

        unread_count = await _count_unread_challenge_messages(challenge_id, user_id, membership)

        active_chats.append(

            ChallengeChatSummaryResponse(

                id=f"chat-{challenge_id}",

                challenge_id=challenge_id,

                name=str(challenges_by_id[challenge_id].get("title") or ""),

                last_message=str(chat_by_challenge.get(challenge_id, {}).get("content") or "Coach: Stay consistent today."),

                last_message_at=_as_utc(chat_by_challenge[challenge_id]["created_at"]) if challenge_id in chat_by_challenge and isinstance(chat_by_challenge[challenge_id].get("created_at"), datetime) else None,

                unread_count=unread_count,

                avatar=_normalize_challenge_thumbnail(challenges_by_id[challenge_id].get("thumbnail")),

            )

        )



    excluded_challenge_ids = {str(membership.get("challenge_id") or "") for membership in memberships}

    ready_limit = _get_user_ready_challenge_limit(user)

    ready_records = await challenges_collection.find(

        {

            "status": {"$in": ["ACTIVE", "UPCOMING"]},

            "_id": {"$nin": [ObjectId(challenge_id) for challenge_id in excluded_challenge_ids if ObjectId.is_valid(challenge_id)]},

        },

        projection=CHALLENGE_OVERVIEW_CHALLENGE_PROJECTION,

        sort=[("created_at", -1), ("_id", -1)],

    ).limit(ready_limit).to_list(length=ready_limit)

    ready_stats = await _load_challenge_stats_map([str(record["_id"]) for record in ready_records])

    active_challenge_limit = _get_user_active_challenge_limit(user)

    can_start_more = active_challenge_limit is None or len(active_challenges) < active_challenge_limit

    ready_to_start = [

        UserReadyChallengeResponse(

            id=str(record["_id"]),
            created_at=record.get("created_at"),

            title=str(record.get("title") or ""),

            description=str(record.get("description") or ""),

            why_it_matters=str(record.get("why_it_matters") or ""),

            plan_text=str(record.get("plan_text") or ""),

            duration_days=max(int(record.get("duration_days") or 0), 0),

            type=str(record.get("category") or "Challenge"),

            points=max(int(record.get("points") or 0), 0),

            participants=int(ready_stats.get(str(record["_id"]), {}).get("participants", 0)),

            difficulty=str(record.get("difficulty") or "BEGINNER"),

            difficulty_color=_difficulty_color(str(record.get("difficulty") or "")),

            status=str(record.get("status") or "ACTIVE"),

            can_start=str(record.get("status") or "").upper() == "ACTIVE" and can_start_more,

            thumbnail=_normalize_challenge_thumbnail(record.get("thumbnail")),

        )

        for record in ready_records

    ]



    return ChallengeOverviewResponse(

        active_chats=active_chats,

        active_challenges=active_challenges,

        completed_challenges=completed_challenges,

        ready_to_start=ready_to_start,

    )





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

    return shared_as_utc(value)





async def _get_verified_user(authorization: str | None) -> dict:

    return await dependency_get_verified_user(authorization)





async def _get_verified_user_from_access_token(token: str) -> dict:

    return await dependency_get_verified_user_from_access_token(token)


def _build_challenge_progress_report_png(
    thread: dict,
    membership: dict,
    user_name: str,
) -> tuple[bytes, str]:
    """Render the downloadable report as the same victory postcard shown in the app."""
    _require_pillow()
    plan_days = _normalize_challenge_plan_days(
        thread.get("plan_days") if isinstance(thread.get("plan_days"), list) else [],
        duration_days=max(int(thread.get("duration_days") or 0), 1),
    )
    challenge_points = max(int(thread.get("points") or 0), 0)
    membership_with_points = dict(membership)
    membership_with_points["challenge_points"] = challenge_points
    entries = _build_report_completed_entries(thread, membership_with_points)
    completed_days = max(int(membership.get("progress_days_completed") or 0), 0)
    viewer_points = _calculate_challenge_points_earned(plan_days, membership_with_points, challenge_points)
    raw_progress = membership.get("plan_progress") if isinstance(membership.get("plan_progress"), dict) else {}
    completed_day_numbers = {
        int(day_number)
        for day_number, day_progress in raw_progress.items()
        if str(day_number).isdigit() and isinstance(day_progress, dict) and (
            bool(day_progress.get("completed"))
            or bool(day_progress.get("completed_section_ids"))
            or bool(day_progress.get("completed_exercise_ids"))
        )
    }
    latest_completed_day = next(
        (day for day in reversed(plan_days) if int(day.get("day_number") or 0) in completed_day_numbers),
        None,
    )
    challenge_name = str((latest_completed_day or {}).get("title") or thread.get("title") or "Challenge")
    width, height = 900, 1500
    image = Image.new("RGB", (width, height), "#03192A")
    draw = ImageDraw.Draw(image)
    cyan, white, muted, pink = "#00D9F5", "#F7F7F7", "#A9B8C8", "#FF4B70"
    dark, panel = "#031523", "#151918"
    title_font = _load_report_font(48, bold=True)
    heading_font = _load_report_font(34, bold=True)
    section_font = _load_report_font(22, bold=True)
    body_font = _load_report_font(18)
    small_font = _load_report_font(15)

    draw.rounded_rectangle((36, 120, width - 36, height - 28), radius=24, fill=dark, outline="#314A60", width=2)
    draw.rounded_rectangle((112, 176, width - 112, 1115), radius=32, outline="#00D9F5", width=8)
    for x in range(140, width - 140, 48):
        for y in range(205, 1090, 48):
            draw.ellipse((x, y, x + 3, y + 3), fill="#075477")

    def center_text(y: int, text: str, font, fill: str) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

    draw.rounded_rectangle((width // 2 - 31, 300, width // 2 + 31, 362), radius=4, outline="#758896", width=1)
    center_text(320, "VF", _load_report_font(25, bold=True), cyan)
    center_text(408, "DEINE VICTORY", title_font, white)
    center_text(492, "WORKOUT ABGESCHLOSSEN", section_font, cyan)
    draw.rounded_rectangle((150, 540, width - 150, 930), radius=24, fill=panel, outline="#5B6870", width=2)

    title_lines = _wrap_report_text(draw, challenge_name.upper(), heading_font, 550)[:3]
    title_y = 585
    for line in title_lines:
        center_text(title_y, line, heading_font, white)
        title_y += 48
    draw.line((188, title_y + 20, width - 188, title_y + 20), fill="#46504F", width=2)
    content = entries[:5] or [{"title": "Challenge day completed", "detail": "Keep building your streak"}]
    row_y = title_y + 48
    for entry in content:
        draw.ellipse((190, row_y + 5, 202, row_y + 17), fill=cyan)
        draw.text((222, row_y), str(entry.get("title") or "Completed"), font=body_font, fill=white)
        row_y += 34

    metric_top = 970
    for x, label, value, color in ((174, "STREAK", str(completed_days), cyan), (468, "INTENSITÄT", "Gut", pink)):
        draw.rounded_rectangle((x, metric_top, x + 258, metric_top + 106), radius=18, fill="#030606", outline="#27343A", width=2)
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((x + (258 - (box[2] - box[0])) / 2, metric_top + 18), label, font=small_font, fill=white)
        value_box = draw.textbbox((0, 0), value, font=heading_font)
        draw.text((x + (258 - (value_box[2] - value_box[0])) / 2, metric_top + 42), value, font=heading_font, fill=color)
    button_text = str(user_name or "Victory Member").upper()
    button_font = _load_report_font(22, bold=True)
    while draw.textbbox((0, 0), button_text, font=button_font)[2] > 390 and button_font.size > 14:
        button_font = _load_report_font(button_font.size - 2, bold=True)
    draw.rounded_rectangle((140, 1140, width - 140, 1230), radius=28, fill="#00C5F0")
    box = draw.textbbox((0, 0), button_text, font=button_font)
    draw.text(((width - (box[2] - box[0])) / 2, 1165), button_text, font=button_font, fill="#06131D")
    center_text(1300, "VICTORY-FITNESS.APP", section_font, "#B1BDCA")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    share_message = "\n".join([
        "Victory Fitness",
        f"{challenge_name} completed by {user_name or 'Victory Member'}",
        f"Streak: {completed_days} | Points: {viewer_points}/{challenge_points}",
    ])
    return output.getvalue(), share_message

HOMEPAGE_QUOTES_KEY = "homepage_quotes"


def _decode_homepage_quotes(record: dict | None) -> list[dict[str, Any]]:
    if not record:
        return []
    try:
        raw = json.loads(str(record.get("html_content") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return [
        {"id": str(item.get("id") or uuid4()), "text": str(item.get("text") or "").strip(), "author": str(item.get("author") or "").strip(), "active": bool(item.get("active", True))}
        for item in raw
        if isinstance(item, dict) and str(item.get("text") or "").strip() and str(item.get("author") or "").strip()
    ]


async def _load_homepage_quotes() -> list[dict[str, Any]]:
    items = _decode_homepage_quotes(await app_content_collection.find_one({"key": HOMEPAGE_QUOTES_KEY}))
    if items:
        return items
    defaults = [
        {"id": "quote-wisdom-listens", "text": "WISDOM LISTENS BEFORE IT LEADS.", "author": "Victor Akko", "active": True},
        {"id": "quote-only-limit", "text": "YOUR ONLY LIMIT IS YOUR MIND.", "author": "Focus", "active": True},
        {"id": "quote-victory-persevering", "text": "VICTORY BELONGS TO THE MOST PERSEVERING.", "author": "Napoleon", "active": True},
        {"id": "quote-strength-winning", "text": "STRENGTH DOES NOT COME FROM WINNING.", "author": "Arnold", "active": True},
    ]
    await _save_homepage_quotes(defaults)
    return defaults


async def _save_homepage_quotes(items: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc)
    await app_content_collection.update_one(
        {"key": HOMEPAGE_QUOTES_KEY},
        {"$set": {"key": HOMEPAGE_QUOTES_KEY, "title": "Homepage quotes", "html_content": json.dumps(items), "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


@app.get("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_list_homepage_quotes(_: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in await _load_homepage_quotes()])


@app.post("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_add_homepage_quote(payload: HomepageQuoteRequest, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = await _load_homepage_quotes()
    items.append({"id": str(uuid4()), "text": payload.text.strip(), "author": payload.author.strip(), "active": payload.active})
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])


@app.put("/admin/homepage/quotes", response_model=HomepageQuoteListResponse)
async def admin_replace_homepage_quotes(payload: HomepageQuoteListResponse, _: dict = Depends(_require_admin_user)) -> HomepageQuoteListResponse:
    items = [item.model_dump() for item in payload.items]
    await _save_homepage_quotes(items)
    return HomepageQuoteListResponse(items=[HomepageQuote(**item) for item in items])


@app.get("/content/homepage/quote", response_model=HomepageQuote | None)
async def get_homepage_quote() -> HomepageQuote | None:
    active_items = [item for item in await _load_homepage_quotes() if item.get("active")]
    if not active_items:
        return None
    return HomepageQuote(**active_items[datetime.now(timezone.utc).date().toordinal() % len(active_items)])


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


@app.get("/admin/analytics/trial-conversion", response_model=TrialConversionResponse)
async def admin_trial_conversion(_: dict = Depends(_require_admin_user)) -> TrialConversionResponse:
    now = datetime.now(timezone.utc)
    all_records = await users_collection.find({"is_admin": {"$ne": True}}).to_list(length=None)
    records = [record for record in all_records if record.get("subscription_started_at") is not None]
    users: list[TrialConversionUser] = []
    active_trials = continued = ended = 0
    for record in records:
        started = _trial_datetime(record.get("subscription_started_at"))
        if not started:
            continue
        ends = started + timedelta(days=5)
        purchased = bool(record.get("subscription_is_purchased"))
        is_paid = purchased or str(record.get("subscription_status") or "").upper() == "ACTIVE"
        if now < ends:
            state = "ACTIVE_TRIAL"
            active_trials += 1
        elif is_paid:
            state = "CONTINUED_AFTER_TRIAL"
            continued += 1
        else:
            state = "TRIAL_ENDED_NOT_CONTINUED"
            ended += 1
        users.append(TrialConversionUser(id=str(record.get("_id")), fullName=str(record.get("name") or "User"), email=str(record.get("email") or "unknown@example.com"), trialStartedAt=started, trialEndsAt=ends, status=state, subscriptionTier=str(record.get("subscription_tier") or "NONE"), subscriptionStatus=str(record.get("subscription_status") or "NONE"), subscriptionIsPurchased=purchased))
    users.sort(key=lambda item: item.trialStartedAt, reverse=True)
    total_decided = continued + ended
    total_subscriptions = sum(
        1 for record in all_records
        if bool(record.get("subscription_is_purchased"))
        or str(record.get("subscription_status") or "").upper() == "ACTIVE"
    )
    return TrialConversionResponse(
        totalUsers=len(all_records), totalSubscriptions=total_subscriptions,
        trialUsers=len(users), activeTrials=active_trials, continuedAfterTrial=continued,
        trialEndedNotContinued=ended, conversionRate=round((continued / total_decided * 100) if total_decided else 0, 1),
        chart=[
            {"name": "Active trial", "users": active_trials},
            {"name": "Continued", "users": continued},
            {"name": "Not continued", "users": ended},
            {"name": "Subscriptions", "users": total_subscriptions},
        ], users=users,
    )
def _upload_community_audio_to_s3(
    user_id: str,
    audio_base64: str,
    mime_type: str,
    file_name: str | None,
) -> str:
    return _upload_audio_to_s3("community-audio", user_id, audio_base64, mime_type, file_name)
