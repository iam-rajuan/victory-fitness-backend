from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


ALLOWED_CHALLENGE_DURATIONS = {3, 5, 7, 14, 21}


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    surname: str = Field(min_length=1, max_length=80)
    email: EmailStr
    mobile: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    marketing_consent: bool = False
    signup_source: str = Field(default="organic", max_length=120)
    beta_access_code: str | None = Field(default=None, min_length=3, max_length=120)

    @field_validator("name", "surname", "mobile")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("password")
    @classmethod
    def require_non_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{4}$")


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{4}$")


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(min_length=20)
    new_password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    session_token: str | None = None


class LogoutRequest(BaseModel):
    session_token: str | None = None


class GoogleAuthRequest(BaseModel):
    id_token: str | None = Field(default=None, min_length=20)
    access_token: str | None = Field(default=None, min_length=20)


class TokenResponse(BaseModel):
    access_token: str
    session_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict
    returning_user: dict | None = None


class SubscriptionSummaryResponse(BaseModel):
    tier: str = "NONE"
    role: str = "NONE"
    status: str = "NONE"
    started_at: datetime | None = None
    confirmed_at: datetime | None = None
    billing_cycle: str = "yearly"
    is_purchased: bool = False
    purchase_source: str = ""
    access: list[str] = Field(default_factory=list)


class GoldTrialSummaryResponse(BaseModel):
    tier_granted: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    outcome: str | None = None
    active: bool = False
    days_remaining: int = 0
    campaign_days_sent: list[int] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    trial_type: str | None = None
    is_beta_tester: bool = False


class MeResponse(BaseModel):
    id: str
    created_at: datetime | None = None
    name: str
    email: EmailStr
    is_verified: bool
    role: str = "user"
    is_admin: bool = False
    country: str = ""
    profileImage: str = ""
    points: int = 0
    workouts_completed: int = 0
    workouts_total: int = 0
    streak_days: int = 0
    rank: str = "Noob"
    next_rank: str = "Bronze"
    points_to_next_rank: int = 0
    rank_progress_fraction: float = 0
    subscription_tier: str = "NONE"
    subscription_role: str = "NONE"
    subscription_status: str = "NONE"
    subscription_started_at: datetime | None = None
    subscription_confirmed_at: datetime | None = None
    subscription_billing_cycle: str = "yearly"
    subscription_is_purchased: bool = False
    subscription_purchase_source: str = ""
    subscription_access: list[str] = Field(default_factory=list)
    subscription: SubscriptionSummaryResponse = Field(default_factory=SubscriptionSummaryResponse)
    trial_tier_granted: str | None = None
    trial_start_at: datetime | None = None
    trial_end_at: datetime | None = None
    trial_outcome: str | None = None
    gold_trial: GoldTrialSummaryResponse = Field(default_factory=GoldTrialSummaryResponse)
    marketing_consent: bool = False
    onboarding_completed: bool = False
    country_code: str | None = None
    identity_statement: str | None = None
    workout_unlock_label: str | None = None
    training_trigger_context: str | None = None


class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    country: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    profileImage: str | None = Field(default=None, max_length=500)
    onboarding_completed: bool | None = None
    identity_statement: str | None = Field(default=None, max_length=240)
    workout_unlock_label: str | None = Field(default=None, max_length=120)
    training_trigger_context: str | None = Field(default=None, max_length=240)


class PushTokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=500)
    platform: str = Field(default="unknown", max_length=20)


class AppNotificationItem(BaseModel):
    id: str
    type: str = "system"
    title: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read: bool = False


class AppNotificationListResponse(BaseModel):
    items: list[AppNotificationItem] = Field(default_factory=list)


class OnboardingPersonalProfileResponse(BaseModel):
    age: str = ""
    gender: str = ""
    height: str = ""
    heightUnit: str = "cm"
    weight: str = ""
    weightUnit: str = "kg"


class OnboardingAnamneseResponse(BaseModel):
    primaryGoal: str = ""
    activityLevel: str = ""
    healthConcerns: list[str] = Field(default_factory=list)
    healthNotes: str = ""
    daysPerWeek: str = ""
    timePerSession: str = ""
    equipmentAccess: str = ""


class OnboardingSuggestionResponse(BaseModel):
    tier: str = "GOLD"
    title: str = ""
    reason: str = ""
    note: str | None = None


class OnboardingStateResponse(BaseModel):
    userId: str
    currentStep: int = 0
    language: str = ""
    personalProfile: OnboardingPersonalProfileResponse = Field(default_factory=OnboardingPersonalProfileResponse)
    anamnese: OnboardingAnamneseResponse = Field(default_factory=OnboardingAnamneseResponse)
    suggestion: OnboardingSuggestionResponse | None = None
    updatedAt: datetime | None = None
    completed: bool = False


class UpdateOnboardingStateRequest(BaseModel):
    currentStep: int | None = Field(default=None, ge=0)
    language: str | None = Field(default=None, max_length=10)
    personalProfile: OnboardingPersonalProfileResponse | None = None
    anamnese: OnboardingAnamneseResponse | None = None
    suggestion: OnboardingSuggestionResponse | None = None
    completed: bool | None = None


class UpdateSubscriptionRequest(BaseModel):
    subscription_tier: str = Field(pattern=r"^(NONE|SILVER|GOLD|PLATINUM|INNER_CIRCLE)$")
    billing_cycle: str = Field(default="yearly", pattern=r"^(monthly|yearly)$")
    confirm_payment: bool = True
    plan_id: str | None = Field(default=None, max_length=120)


class StripeCheckoutSessionRequest(BaseModel):
    subscription_tier: str = Field(pattern=r"^(SILVER|GOLD|PLATINUM|INNER_CIRCLE)$")
    billing_cycle: str = Field(default="yearly", pattern=r"^(monthly|yearly)$")
    plan_id: str | None = Field(default=None, max_length=120)
    success_url: str | None = Field(default=None, max_length=1000)
    cancel_url: str | None = Field(default=None, max_length=1000)


class StripeCheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class StripeWebhookResponse(BaseModel):
    received: bool = True


class ProfileImageUploadRequest(BaseModel):
    image_base64: str = Field(min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class ProfileImageUploadResponse(BaseModel):
    image_url: str


class AdminProfileResponse(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    role: str = "admin"
    country: str = ""
    contactNumber: str = ""
    profileImage: str = ""
    isVerified: bool = True


class UpdateAdminProfileRequest(BaseModel):
    fullName: str | None = Field(default=None, min_length=2, max_length=100)
    country: str | None = Field(default=None, max_length=120)
    contactNumber: str | None = Field(default=None, max_length=40)


class AdminChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class BodyMetricsResponse(BaseModel):
    age: str = ""
    height: str = ""
    weight: str = ""
    gender: str = ""


class UpdateBodyMetricsRequest(BaseModel):
    age: str | None = Field(default=None, max_length=20)
    height: str | None = Field(default=None, max_length=20)
    weight: str | None = Field(default=None, max_length=20)
    gender: str | None = Field(default=None, max_length=40)


class LongevityOverviewResponse(BaseModel):
    biological_age: str = "N/A"
    chronological_age: str = "N/A"
    trending_years_younger: float = 0
    recovery_score: int = 0
    hrv_ms: int = 0
    sleep_score: int = 0


class LongevityQuickActionResponse(BaseModel):
    id: str
    label: str
    subtitle: str = ""
    image: str = ""
    color: str = ""


class LongevityWearableDeviceResponse(BaseModel):
    id: str
    name: str
    status: str = "CONNECT"
    active: bool = False
    image: str = ""
    device_name: str = ""
    source_device: str = ""
    platform: str = ""


class LongevityWearablesResponse(BaseModel):
    devices: list[LongevityWearableDeviceResponse] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    has_data: bool = False
    sync_message: str = ""


class IntegrationConnectionResponse(BaseModel):
    provider: str
    display_name: str
    connection_type: str = "native"
    status: str = "not_connected"
    connected: bool = False
    needs_permission: bool = False
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_error: str = ""
    last_sync_message: str = ""
    permission_granted: bool = False
    device_name: str = ""
    source_device: str = ""
    platform: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _map_mongo_id(cls, value: Any) -> Any:
        if isinstance(value, dict) and "id" not in value and "_id" in value:
            mapped = dict(value)
            mapped["id"] = str(mapped.get("_id") or "")
            value = mapped
        if isinstance(value, dict):
            mapped = dict(value)
            metadata = dict(mapped.get("metadata") or {})
            device_name = str(mapped.get("device_name") or mapped.get("source_device") or metadata.get("device_name") or metadata.get("source_device") or "")
            mapped["device_name"] = device_name
            mapped["source_device"] = str(mapped.get("source_device") or device_name)
            mapped["permission_granted"] = bool(mapped.get("permission_granted") or metadata.get("permission_granted") or False)
            return mapped
        return value


class IntegrationListResponse(BaseModel):
    items: list[IntegrationConnectionResponse] = Field(default_factory=list)


class IntegrationConnectStartResponse(BaseModel):
    provider: str
    connection_type: str
    authorization_url: str | None = None
    state: str | None = None
    expires_at: datetime | None = None
    message: str = ""


class NativeIntegrationConnectedRequest(BaseModel):
    provider: str
    source_device: str = ""
    permission_granted: bool = True
    platform: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NativeIntegrationSamplesRequest(BaseModel):
    provider: str
    source_device: str = Field(default="", max_length=160)
    batch_id: str | None = Field(default=None, max_length=120)
    platform: str = ""
    metrics: list[dict[str, Any]] = Field(default_factory=list, min_length=1)


class IntegrationImportQrRequest(BaseModel):
    qr_payload: str = Field(min_length=1)
    source_device: str = Field(default="", max_length=160)


class IntegrationImportFileRequest(BaseModel):
    provider: str = "qr-import"
    file_name: str = Field(default="", max_length=200)
    content_base64: str = Field(min_length=1)
    source_device: str = Field(default="", max_length=160)


class LongevityHabitResponse(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    icon: str = ""
    done: bool = False


class LongevityHabitsResponse(BaseModel):
    streak_days: int = 0
    habits: list[LongevityHabitResponse] = Field(default_factory=list)


class LongevityHabitUpdateRequest(BaseModel):
    done: bool


class LongevityHealCategoryResponse(BaseModel):
    id: str
    label: str
    image: str = ""
    color: str = ""


class LongevityHealCategoriesResponse(BaseModel):
    categories: list[LongevityHealCategoryResponse] = Field(default_factory=list)


class LongevityWeeklyPlanSectionResponse(BaseModel):
    id: str
    title: str
    summary: str = ""
    actions: list[str] = Field(default_factory=list)


class LongevityWeeklyPlanResponse(BaseModel):
    status: str = "success"
    message: str
    plan_sections: list[LongevityWeeklyPlanSectionResponse] = Field(default_factory=list)
    generated_at: datetime


class LongevityMasterclassResponse(BaseModel):
    id: str
    title: str
    description: str = ""
    thumbnail: str = ""
    videoUrl: str = ""
    videoSource: str = "VIMEO"
    audioUrl: str = ""
    category: str = ""
    duration: str = ""
    educationalContent: str = ""


class LongevityMasterclassListResponse(BaseModel):
    items: list[LongevityMasterclassResponse] = Field(default_factory=list)


class LongevityCircleResponse(BaseModel):
    id: str
    name: str
    member_count: int = 0
    description: str = ""


class LongevityCircleListResponse(BaseModel):
    items: list[LongevityCircleResponse] = Field(default_factory=list)


class LongevityDashboardResponse(BaseModel):
    overview: LongevityOverviewResponse
    quick_actions: list[LongevityQuickActionResponse] = Field(default_factory=list)
    wearables: LongevityWearablesResponse
    habits: LongevityHabitsResponse
    heal_categories: list[LongevityHealCategoryResponse] = Field(default_factory=list)
    weekly_plan: LongevityWeeklyPlanResponse | None = None
    masterclasses: list[LongevityMasterclassResponse] = Field(default_factory=list)
    circles: list[LongevityCircleResponse] = Field(default_factory=list)


class PrivacyPolicyResponse(BaseModel):
    key: str = "privacy_policy"
    title: str
    html_content: str
    plain_text: str
    updated_at: datetime


class UpdatePrivacyPolicyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    html_content: str = Field(min_length=1, max_length=200000)


class TermsConditionResponse(BaseModel):
    key: str = "terms_condition"
    title: str
    html_content: str
    plain_text: str
    updated_at: datetime


class UpdateTermsConditionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    html_content: str = Field(min_length=1, max_length=200000)


class AboutUsResponse(BaseModel):
    key: str = "about_us"
    title: str
    html_content: str
    plain_text: str
    updated_at: datetime


class UpdateAboutUsRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    html_content: str = Field(min_length=1, max_length=200000)


class OnboardingSlideResponse(BaseModel):
    id: str
    badge: str = ""
    title_lines: list[str] = Field(default_factory=list)
    title_accent_index: int | None = None
    description: str = ""
    show_skip: bool = False
    button_label: str = ""
    button_arrow: str = ""
    has_secondary: bool = False
    secondary_label: str = ""
    has_footer: bool = False
    footer_text: str = ""


class OnboardingContentResponse(BaseModel):
    slides: list[OnboardingSlideResponse] = Field(default_factory=list)


class CoachingApplicationCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone_number: str | None = Field(default=None, max_length=40)
    goal: str = Field(min_length=1, max_length=200)
    obstacle: str = Field(min_length=1, max_length=200)
    investment: str = Field(min_length=1, max_length=200)
    commitment: str = Field(min_length=1, max_length=200)
    injury: str = Field(min_length=1, max_length=80)
    additional_notes: str | None = Field(default=None, max_length=4000)
    agreement_accepted: bool = True


class CoachingApplicationResponse(BaseModel):
    id: str
    user_id: str = ""
    first_name: str
    last_name: str
    full_name: str
    email: EmailStr
    phone_number: str = ""
    goal: str
    obstacle: str
    investment: str
    commitment: str
    injury: str
    additional_notes: str = ""
    agreement_accepted: bool = True
    status: str = "NEW"
    admin_notes: str = ""
    created_at: datetime
    updated_at: datetime


class CoachingApplicationListResponse(BaseModel):
    applications: list[CoachingApplicationResponse] = Field(default_factory=list)


class AdminCoachingApplicationUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    admin_notes: str | None = Field(default=None, max_length=2000)


class SupportMessageCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)


class SupportMessageResponse(BaseModel):
    id: str
    user_id: str = ""
    user_name: str
    user_email: EmailStr
    subject: str
    message: str
    status: str = "OPEN"
    admin_notes: str = ""
    created_at: datetime
    updated_at: datetime


class SupportMessageListResponse(BaseModel):
    messages: list[SupportMessageResponse] = Field(default_factory=list)


class AdminSupportMessageUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    admin_notes: str | None = Field(default=None, max_length=2000)


class CommunityCommentResponse(BaseModel):
    id: str
    post_id: str
    author_name: str
    author_role: str
    author_profile_image: str = ""
    content: str
    created_at: datetime


class CommunityReactionUserResponse(BaseModel):
    user_id: str
    user_name: str
    user_role: str
    user_profile_image: str = ""
    created_at: datetime


class CommunityPostResponse(BaseModel):
    id: str
    author_id: str = ""
    author_name: str
    author_role: str
    author_profile_image: str = ""
    audience: str = "ALL"
    content: str
    image_url: str = ""
    video_url: str = ""
    audio_url: str = ""
    like_count: int = 0
    comment_count: int = 0
    viewer_has_liked: bool = False
    can_delete: bool = False
    comments: list[CommunityCommentResponse] = Field(default_factory=list)
    reactions: list[CommunityReactionUserResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    flagged: bool = False
    flag_reason: str = ""
    moderation_status: str = "published"
    moderator_notes: str = ""


class CommunityPostListResponse(BaseModel):
    posts: list[CommunityPostResponse] = Field(default_factory=list)
    page: int = 1
    limit: int = 100
    total: int = 0
    has_more: bool = False


class CommunityPostCreateRequest(BaseModel):
    content: str | None = Field(default=None, max_length=5000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    video_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    external_video_url: str | None = Field(default=None, max_length=2000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class CommunityCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommunityReactionToggleResponse(BaseModel):
    post_id: str
    like_count: int = 0
    viewer_has_liked: bool = False


class ChallengePlanExercise(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    details: str = Field(min_length=1, max_length=240)
    notes: str = Field(default="", max_length=400)
    workout_id: str = Field(default="", max_length=80)
    workout_title: str = Field(default="", max_length=160)
    workout_vimeo_id: str = Field(default="", max_length=80)
    workout_video_url: str = Field(default="", max_length=2000)
    workout_video_source: str = Field(default="VIMEO", pattern=r"^(VIMEO|YOUTUBE|UPLOAD)$")
    workout_thumbnail: str = Field(default="", max_length=20000000)


class ChallengePlanSection(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=400)
    estimated_minutes: int = Field(default=10, ge=0, le=240)
    exercises: list[ChallengePlanExercise] = Field(default_factory=list)


class ChallengePlanDay(BaseModel):
    day_number: int = Field(ge=1, le=365)
    title: str = Field(min_length=1, max_length=160)
    focus: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=1200)
    sections: list[ChallengePlanSection] = Field(default_factory=list)


class ChallengePlanDayProgressResponse(BaseModel):
    day_number: int
    completed: bool = False
    completed_section_ids: list[str] = Field(default_factory=list)
    completed_exercise_ids: list[str] = Field(default_factory=list)


class ChallengePlanProgressResponse(BaseModel):
    challenge_id: str
    viewer_membership_status: str
    viewer_progress_days_completed: int = 0
    viewer_points_earned: int = 0
    viewer_plan_progress: list[ChallengePlanDayProgressResponse] = Field(default_factory=list)


class ChallengeProgressReportResponse(BaseModel):
    file_name: str
    mime_type: str = "image/png"
    image_base64: str = Field(min_length=32, max_length=20000000)
    share_message: str = Field(min_length=1, max_length=5000)


class ChallengePlanCompletionRequest(BaseModel):
    completed: bool = True


class ChallengeChatSummaryResponse(BaseModel):
    id: str
    challenge_id: str
    name: str
    last_message: str = ""
    last_message_at: datetime | None = None
    unread_count: int = 0
    avatar: str = ""


class ChallengeParticipantResponse(BaseModel):
    user_id: str
    name: str
    profile_image: str = ""


class UserActiveChallengeResponse(BaseModel):
    id: str
    challenge_id: str
    title: str
    description: str = ""
    why_it_matters: str = ""
    type: str
    plan_text: str = ""
    duration_days: int = 0
    days_left: int = 0
    total_days: int = 0
    progress: float = 0
    points: int = 0
    participants: int = 0
    thumbnail: str = ""
    color: str = "#4F8EF7"
    created_at: datetime | None = None


class UserCompletedChallengeResponse(BaseModel):
    id: str
    challenge_id: str
    title: str
    description: str = ""
    why_it_matters: str = ""
    duration_days: int = 0
    type: str
    earned_points: int = 0
    participants: int = 0
    thumbnail: str = ""
    completed_at: datetime
    color: str = "#22C55E"
    created_at: datetime | None = None


class UserReadyChallengeResponse(BaseModel):
    id: str
    title: str
    description: str
    why_it_matters: str = ""
    plan_text: str = ""
    duration_days: int = 0
    type: str
    points: int = 0
    participants: int = 0
    difficulty: str
    difficulty_color: str = "#22C55E"
    status: str
    can_start: bool = False
    thumbnail: str = ""
    created_at: datetime | None = None


class ChallengeOverviewResponse(BaseModel):
    active_chats: list[ChallengeChatSummaryResponse] = Field(default_factory=list)
    active_challenges: list[UserActiveChallengeResponse] = Field(default_factory=list)
    completed_challenges: list[UserCompletedChallengeResponse] = Field(default_factory=list)
    ready_to_start: list[UserReadyChallengeResponse] = Field(default_factory=list)


class StartChallengeResponse(BaseModel):
    status: str = "success"
    membership_id: str


class ChallengeDetailResponse(BaseModel):
    challenge_id: str
    title: str
    description: str
    why_it_matters: str = ""
    plan_text: str = ""
    plan_days: list[ChallengePlanDay] = Field(default_factory=list)
    category: str
    duration_days: int
    points: int = 0
    difficulty: str
    status: str
    thumbnail: str = ""
    participant_count: int = 0
    participants: list[ChallengeParticipantResponse] = Field(default_factory=list)
    viewer_membership_status: str = "NOT_JOINED"
    viewer_progress_days_completed: int = 0
    viewer_points_earned: int = 0
    viewer_plan_progress: list[ChallengePlanDayProgressResponse] = Field(default_factory=list)
    unread_count: int = 0
    can_start: bool = False
    can_post: bool = False
    has_joined: bool = False
    current_day_number: int | None = None
    can_complete_today: bool = False
    completed_today: bool = False
    messages: list["ChallengeChatMessageResponse"] = Field(default_factory=list)
    started_at: datetime | None = None




class ChallengeChatMessageResponse(BaseModel):
    id: str
    challenge_id: str
    author_id: str = ""
    author_name: str
    author_role: str
    author_profile_image: str = ""
    message_type: str
    content: str = ""
    image_url: str = ""
    reply_to_message_id: str | None = None
    progress_payload: dict | None = None
    created_at: datetime
    updated_at: datetime
    can_delete: bool = False
    can_edit: bool = False
    is_edited: bool = False
    is_deleted: bool = False
    reactions: list[dict] = Field(default_factory=list)


class ChallengeChatThreadResponse(BaseModel):
    challenge_id: str
    title: str
    description: str
    why_it_matters: str = ""
    plan_text: str = ""
    plan_days: list[ChallengePlanDay] = Field(default_factory=list)
    category: str
    duration_days: int
    points: int = 0
    difficulty: str
    status: str
    thumbnail: str = ""
    participant_count: int = 0
    participants: list[ChallengeParticipantResponse] = Field(default_factory=list)
    viewer_membership_status: str
    viewer_progress_days_completed: int = 0
    viewer_points_earned: int = 0
    viewer_plan_progress: list[ChallengePlanDayProgressResponse] = Field(default_factory=list)
    unread_count: int = 0
    messages: list[ChallengeChatMessageResponse] = Field(default_factory=list)
    started_at: datetime | None = None



class ChallengeChatMessageCreateRequest(BaseModel):
    content: str | None = Field(default=None, max_length=4000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)
    reply_to_message_id: str | None = Field(default=None, max_length=80)


class ChallengeChatMessageUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ChallengeProgressUpdateRequest(BaseModel):
    completed_day: int = Field(ge=1, le=365)
    note: str | None = Field(default=None, max_length=2000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class ChallengeChatReactionToggleRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class ChallengeChatEventResponse(BaseModel):
    event: str
    challenge_id: str
    message: ChallengeChatMessageResponse | None = None
    message_id: str | None = None


class AdminChallengeItem(BaseModel):
    id: str
    title: str
    description: str
    whyItMatters: str = ""
    planText: str = ""
    planDays: list[ChallengePlanDay] = Field(default_factory=list)
    category: str
    durationDays: int
    points: int = 0
    difficulty: str
    status: str
    thumbnail: str = ""
    participantCount: int = 0
    completionCount: int = 0
    createdAt: datetime
    updatedAt: datetime


class AdminChallengeListResponse(BaseModel):
    total: int = 0
    challenges: list[AdminChallengeItem] = Field(default_factory=list)


class AdminChallengeRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    whyItMatters: str | None = Field(default=None, max_length=4000)
    planText: str | None = Field(default=None, max_length=30000)
    planDays: list[ChallengePlanDay] = Field(default_factory=list)
    category: str = Field(min_length=1, max_length=80)
    durationDays: int = Field(ge=1, le=365)
    points: int = Field(ge=0, le=100000)
    difficulty: str = Field(pattern=r"^(BEGINNER|INTERMEDIATE|ADVANCED)$")
    status: str = Field(pattern=r"^(ACTIVE|UPCOMING|DRAFT|ARCHIVED)$")
    thumbnail: str | None = Field(default=None, max_length=20000000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class AdminChallengePlanGenerateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=80)
    difficulty: str = Field(pattern=r"^(BEGINNER|INTERMEDIATE|ADVANCED)$")
    durationDays: int = Field(default=7, ge=1, le=365)


class AdminChallengePlanGenerateResponse(BaseModel):
    title: str
    description: str
    planText: str = ""
    planDays: list[ChallengePlanDay] = Field(default_factory=list)
    durationDays: int = 0


class AdminCommunityPostCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    audience: str = Field(default="ALL", pattern=r"^(ALL|SILVER|GOLD|PLATINUM|INNER_CIRCLE)$")
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    video_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    audio_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    external_video_url: str | None = Field(default=None, max_length=2000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class AdminCommunityPostUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    audience: str | None = Field(default=None, pattern=r"^(ALL|SILVER|GOLD|PLATINUM|INNER_CIRCLE)$")
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    video_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    audio_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    external_video_url: str | None = Field(default=None, max_length=2000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)
    clear_image: bool = False
    clear_media: bool = False
    flagged: bool | None = None
    flag_reason: str | None = Field(default=None, max_length=500)
    moderation_status: str | None = Field(default=None, pattern=r"^(published|reviewing|approved|removed)$")
    moderator_notes: str | None = Field(default=None, max_length=1000)


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    is_verified: bool
    created_at: datetime


class CoachVictorMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class CoachVictorThreadMessage(CoachVictorMessage):
    id: str
    created_at: datetime


class CoachVictorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CoachVictorChatResponse(BaseModel):
    reply: str
    thread_id: str | None = None


class CoachVictorHistoryResponse(BaseModel):
    thread_id: str | None = None
    messages: list[CoachVictorThreadMessage] = Field(default_factory=list)


class JournalEntryCreateRequest(BaseModel):
    mood: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=10000)


class JournalEntryUpdateRequest(BaseModel):
    mood: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=10000)


class JournalEntryResponse(BaseModel):
    id: str
    user_id: str
    mood: str
    content: str
    created_at: datetime
    updated_at: datetime


class JournalEntryListResponse(BaseModel):
    entries: list[JournalEntryResponse] = Field(default_factory=list)


class JournalAnalysisRequest(BaseModel):
    mood: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=10000)


class JournalAnalysisResponse(BaseModel):
    analysis: str


class JournalLatestAnalysisResponse(BaseModel):
    entry: JournalEntryResponse
    analysis: str


class MealImageAnalysisRequest(BaseModel):
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    document_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    text_content: str | None = Field(default=None, min_length=1, max_length=200000)
    mime_type: str = Field(default="application/octet-stream", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_analysis_source(self):
        if self.image_base64 or self.document_base64 or self.text_content:
            return self
        raise ValueError("One of image_base64, document_base64, or text_content is required")


class MealImageAnalysisResponse(BaseModel):
    analysis_id: str | None = None
    meal_name_guess: str
    summary: str
    estimated_calories: int = Field(ge=0, le=3000)
    estimated_protein: int = Field(ge=0, le=300)
    estimated_carbs: int = Field(ge=0, le=500)
    estimated_fat: int = Field(ge=0, le=200)
    confidence: str
    notes: list[str] = Field(default_factory=list)
    file_name: str | None = None
    created_at: datetime | None = None


class MealImageAnalysisListResponse(BaseModel):
    analyses: list[MealImageAnalysisResponse] = Field(default_factory=list)


class NutritionMealItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    qty: str = Field(min_length=1, max_length=80)


class NutritionShoppingSection(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    items: list[NutritionMealItem] = Field(default_factory=list)


class NutritionMealEntry(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    desc: str = Field(min_length=1, max_length=300)
    kcal: int = Field(ge=0, le=3000)
    p: int = Field(ge=0, le=300)
    c: int = Field(ge=0, le=500)
    f: int = Field(ge=0, le=200)
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)


class NutritionDayPlan(BaseModel):
    day: str = Field(pattern=r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)$")
    breakfast: NutritionMealEntry
    lunch: NutritionMealEntry
    dinner: NutritionMealEntry


class NutritionPlanRequest(BaseModel):
    goal: str | None = None
    cuisine: str | None = None
    favorite_meal: str | None = None
    diet: str | None = None
    allergies: str | None = None
    activity_level: str | None = None
    age: str | None = None
    gender: str | None = None
    height: str | None = None
    weight: str | None = None
    health_conditions: list[str] = Field(default_factory=list)


class NutritionPlanResponse(BaseModel):
    plan_id: str | None = None
    summary: str
    goal_label: str
    days: list[NutritionDayPlan]
    shopping_list: list[NutritionShoppingSection] = Field(default_factory=list)
    meal_completions: dict[str, dict[str, bool]] = Field(default_factory=dict)
    profile: dict | None = None


class NutritionAdviceRequest(BaseModel):
    goal: str | None = None
    meal_query: str | None = None
    daily_calories: int | None = None
    daily_protein: int | None = None
    daily_carbs: int | None = None
    daily_fat: int | None = None
    cuisine: str | None = None
    favorite_meal: str | None = None
    allergies: str | None = None


class NutritionAdviceResponse(BaseModel):
    reply: str


class NutritionPlanSaveResponse(BaseModel):
    status: str = "success"
    plan: NutritionPlanResponse


class NutritionPlanJobResponse(BaseModel):
    job_id: str
    status: str
    plan_id: str | None = None
    plan: NutritionPlanResponse | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class NutritionMealCompletionUpdateRequest(BaseModel):
    day: str = Field(pattern=r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)$")
    meal_key: str = Field(pattern=r"^(breakfast|lunch|dinner)$")
    completed: bool = True


class StrengthWorkoutPlanProgressUpdateRequest(BaseModel):
    day: str = Field(min_length=1, max_length=40)
    section_id: str | None = Field(default=None, max_length=120)
    exercise_id: str | None = Field(default=None, max_length=120)
    started: bool | None = None
    completed: bool | None = None


class DashboardOverviewChartPoint(BaseModel):
    month: str
    userCount: int = 0
    agentCount: int = 0


class DashboardOverviewRecentUser(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    status: str
    createdAt: datetime
    profileImage: str = ""


class DashboardOverviewResponse(BaseModel):
    totalUsers: int = 0
    workoutsThisWeek: int = 0
    challengeCompletions: int = 0
    activeChallenges: int = 0
    readyChallenges: int = 0
    vimeoApiStatus: str
    userChart: list[DashboardOverviewChartPoint] = Field(default_factory=list)
    recentUsers: list[DashboardOverviewRecentUser] = Field(default_factory=list)


class FAQItemResponse(BaseModel):
    id: str
    question: str
    answer: str


class FAQListResponse(BaseModel):
    items: list[FAQItemResponse] = Field(default_factory=list)


class FAQRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=10000)


class HomepageQuote(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=1000)
    author: str = Field(min_length=1, max_length=200)
    active: bool = True


class HomepageQuoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    author: str = Field(min_length=1, max_length=200)
    active: bool = True


class HomepageQuoteListResponse(BaseModel):
    items: list[HomepageQuote] = Field(default_factory=list)


class AdminNotificationItem(BaseModel):
    id: str
    title: str
    message: str = ""
    read: bool = False
    createdAt: datetime


class AdminNotificationListResponse(BaseModel):
    items: list[AdminNotificationItem] = Field(default_factory=list)


class AdminNotificationUpdateRequest(BaseModel):
    read: bool = True


class AdminTestNotificationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class AdminSubscriptionPlanItem(BaseModel):
    id: str
    tier: str
    description: str = ""
    priceMonthly: int | None = Field(default=None, ge=0)
    priceYearly: int | None = Field(default=None, ge=0)
    discountPercentage: int | None = Field(default=None, ge=0, le=100)
    discountStartDate: datetime | None = None
    discountEndDate: datetime | None = None
    isApplicationOnly: bool = False
    isMostPopular: bool = False
    iconType: str = ""
    features: list[str] = Field(default_factory=list)
    featureAccess: list[str] = Field(default_factory=list)


class AdminSubscriptionPlanListResponse(BaseModel):
    items: list[AdminSubscriptionPlanItem] = Field(default_factory=list)


class AdminSubscriptionPlanRequest(BaseModel):
    tier: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    priceMonthly: int | None = Field(default=None, ge=0)
    priceYearly: int | None = Field(default=None, ge=0)
    discountPercentage: int | None = Field(default=None, ge=0, le=100)
    discountStartDate: datetime | None = None
    discountEndDate: datetime | None = None
    isApplicationOnly: bool = False
    isMostPopular: bool = False
    iconType: str = Field(default="", max_length=80)
    features: list[str] = Field(default_factory=list)
    featureAccess: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_discount_window(self):
        if self.discountStartDate and self.discountEndDate and self.discountEndDate < self.discountStartDate:
            raise ValueError("discountEndDate must be after discountStartDate")
        if self.isApplicationOnly:
            self.priceMonthly = None
            self.priceYearly = None
        return self


class AppSubscriptionPlanItem(BaseModel):
    id: str
    subscriptionTier: str
    title: str
    description: str = ""
    priceMonthly: int | None = Field(default=None, ge=0)
    priceYearly: int | None = Field(default=None, ge=0)
    discountedPriceMonthly: int | None = Field(default=None, ge=0)
    discountedPriceYearly: int | None = Field(default=None, ge=0)
    discountPercentage: int | None = Field(default=None, ge=0, le=100)
    discountStartDate: datetime | None = None
    discountEndDate: datetime | None = None
    isDiscountActive: bool = False
    isApplicationOnly: bool = False
    isMostPopular: bool = False
    iconType: str = ""
    features: list[str] = Field(default_factory=list)
    featureAccess: list[str] = Field(default_factory=list)


class AppSubscriptionPlanListResponse(BaseModel):
    items: list[AppSubscriptionPlanItem] = Field(default_factory=list)


class AdminMasterclassItem(BaseModel):
    id: str
    title: str
    category: str = ""
    duration: str = ""
    description: str = ""
    videoUrl: str = ""
    videoSource: str = "VIMEO"
    audioUrl: str = ""
    educationalContent: str = ""
    thumbnailUrl: str = ""


class AdminMasterclassListResponse(BaseModel):
    items: list[AdminMasterclassItem] = Field(default_factory=list)


class AdminMasterclassRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=120)
    duration: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=4000)
    videoUrl: str = Field(default="", max_length=2000)
    videoSource: str = Field(default="VIMEO", pattern=r"^(VIMEO|YOUTUBE|UPLOAD)$")
    video_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    video_mime_type: str = Field(default="video/mp4", max_length=120)
    video_file_name: str | None = Field(default=None, max_length=255)
    audioUrl: str = Field(default="", max_length=1000)
    audio_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    audio_mime_type: str = Field(default="audio/mpeg", max_length=120)
    audio_file_name: str | None = Field(default=None, max_length=255)
    clear_audio: bool = False
    educationalContent: str = Field(default="", max_length=10000)
    thumbnailUrl: str = Field(default="", max_length=20000000)


class AdminUserListItem(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    role: str
    status: str
    isVerified: bool
    contactNumber: str = ""
    country: str = ""
    country_code: str | None = None
    tier: str | None = None
    identity_statement: str | None = None
    workout_unlock_label: str | None = None
    training_trigger_context: str | None = None
    createdAt: datetime
    updatedAt: datetime
    profileImage: str = ""


class AdminUserDetailResponse(AdminUserListItem):
    subscription_tier: str = "NONE"
    subscription_role: str = "NONE"
    subscription_status: str = "NONE"
    subscription_started_at: datetime | None = None
    subscription_confirmed_at: datetime | None = None
    subscription_billing_cycle: str = "yearly"
    subscription_is_purchased: bool = False
    subscription_purchase_source: str = ""
    subscription_access: list[str] = Field(default_factory=list)
    trial_type: str | None = None
    is_beta_tester: bool = False
    trial_start_at: datetime | None = None
    trial_end_at: datetime | None = None
    trial_days_remaining: int = 0
    trial_status: str | None = None


class PhaseOneBetaCountryItem(BaseModel):
    code: str | None = None
    label: str
    count: int = 0
    activeUsers: int = 0
    aiUsers: int = 0
    nutritionUsers: int = 0
    workoutUsers: int = 0


class PhaseOneBetaUserActivity(BaseModel):
    aiConversations: int | None = None
    aiMessages: int | None = None
    nutritionPlans: int | None = None
    nutritionLogs: int | None = None
    workoutsStarted: int | None = None
    workoutsCompleted: int | None = None
    challengesJoined: int | None = None
    challengesCompleted: int | None = None
    communityPosts: int | None = None
    communityComments: int | None = None
    communityReactions: int | None = None
    lastActiveAt: datetime | None = None
    usedAiCoach: bool = False
    usedNutrition: bool = False
    usedWorkout: bool = False
    usedChallenge: bool = False
    usedCommunity: bool = False
    usedAnyTrackedFeature: bool = False


class PhaseOneBetaFeatureAdoptionMetric(BaseModel):
    users: int = 0
    total: int = 0
    averagePerActiveUser: float = 0
    neverUsedUsers: int = 0


class PhaseOneBetaFeatureAdoptionResponse(BaseModel):
    aiCoach: PhaseOneBetaFeatureAdoptionMetric = Field(default_factory=PhaseOneBetaFeatureAdoptionMetric)
    nutrition: PhaseOneBetaFeatureAdoptionMetric = Field(default_factory=PhaseOneBetaFeatureAdoptionMetric)
    workouts: PhaseOneBetaFeatureAdoptionMetric = Field(default_factory=PhaseOneBetaFeatureAdoptionMetric)
    challenges: PhaseOneBetaFeatureAdoptionMetric = Field(default_factory=PhaseOneBetaFeatureAdoptionMetric)
    community: PhaseOneBetaFeatureAdoptionMetric = Field(default_factory=PhaseOneBetaFeatureAdoptionMetric)


class PhaseOneBetaCrossFeatureResponse(BaseModel):
    aiOnly: int = 0
    nutritionOnly: int = 0
    workoutOnly: int = 0
    aiAndNutrition: int = 0
    aiAndWorkout: int = 0
    nutritionAndWorkout: int = 0
    usedThreePlusFeatures: int = 0
    usedNoTrackedFeature: int = 0


class PhaseOneBetaCheckpointItem(BaseModel):
    day: int
    eligibleUsers: int = 0
    activeUsers: int = 0
    aiUsers: int = 0
    nutritionUsers: int = 0
    workoutUsers: int = 0
    challengeUsers: int = 0
    communityUsers: int = 0
    anyFeatureUsers: int = 0


class PhaseOneBetaParticipationResponse(BaseModel):
    enrollmentProgressPct: float = 0
    activeRatePct: float = 0
    expiredRatePct: float = 0
    neverActiveUsers: int = 0
    usersActiveToday: int = 0
    usersActiveThisWeek: int = 0


class PhaseOneBetaCampaignHealthResponse(BaseModel):
    zeroActivityUsers: int = 0
    endingSoonUsers: int = 0
    usersWithoutAiCoach: int = 0
    usersWithoutNutrition: int = 0


class PhaseOneBetaSupportReferenceResponse(BaseModel):
    betaUsersWithMessages: int = 0
    totalSupportMessages: int = 0


class AdminUserListResponse(BaseModel):
    total: int = 0
    page: int = 1
    limit: int = 10
    users: list[AdminUserListItem] = Field(default_factory=list)


class AdminUserChartPoint(BaseModel):
    month: str
    userCount: int = 0
    activeUserCount: int = 0


class AdminUserSummaryResponse(BaseModel):
    totalUsers: int = 0
    activeUsers: int = 0
    pendingUsers: int = 0
    userChart: list[AdminUserChartPoint] = Field(default_factory=list)


class AdminUserManagementOverviewResponse(BaseModel):
    summary: AdminUserSummaryResponse
    table: AdminUserListResponse


class AdminTrialCohortItem(BaseModel):
    cohort: str
    signupSource: str = "organic"
    totalUsers: int = 0
    convertedUsers: int = 0
    dropoutUsers: int = 0
    conversionRate: float = 0
    engagedUsersByDay: dict[str, int] = Field(default_factory=dict)


class AdminTrialCohortResponse(BaseModel):
    cohorts: list[AdminTrialCohortItem] = Field(default_factory=list)


class AdminTrialDropoutItem(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    signupSource: str = "organic"
    cohort: str
    trialStartedAt: datetime
    marketingConsent: bool = False
    lastEngagedDay: int | None = None
    coachMessages: int = 0
    nutritionPlanCreated: bool = False
    campaignDaysSent: list[int] = Field(default_factory=list)


class AdminTrialDropoutResponse(BaseModel):
    total: int = 0
    users: list[AdminTrialDropoutItem] = Field(default_factory=list)


class PhaseOneBetaUserItem(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    country: str = ""
    countryCode: str | None = None
    plan: str = "GOLD"
    status: str = "ACTIVE"
    trialType: str = "beta_trial"
    isBetaTester: bool = True
    trialStartedAt: datetime | None = None
    trialExpiresAt: datetime | None = None
    daysRemaining: int = 0
    price: float = 0
    currency: str = "EUR"
    paymentRequired: bool = False
    activity: PhaseOneBetaUserActivity = Field(default_factory=PhaseOneBetaUserActivity)


class PhaseOneBetaSummaryResponse(BaseModel):
    totalBetaUsers: int = 0
    activeBetaUsers: int = 0
    expiredBetaUsers: int = 0
    goldBetaUsers: int = 0
    limit: int = 300
    remainingSlots: int = 0
    averageDaysRemaining: float = 0
    countriesRepresented: int = 0
    participation: PhaseOneBetaParticipationResponse = Field(default_factory=PhaseOneBetaParticipationResponse)
    featureAdoption: PhaseOneBetaFeatureAdoptionResponse = Field(default_factory=PhaseOneBetaFeatureAdoptionResponse)
    crossFeatureAdoption: PhaseOneBetaCrossFeatureResponse = Field(default_factory=PhaseOneBetaCrossFeatureResponse)
    checkpoints: list[PhaseOneBetaCheckpointItem] = Field(default_factory=list)
    campaignHealth: PhaseOneBetaCampaignHealthResponse = Field(default_factory=PhaseOneBetaCampaignHealthResponse)
    support: PhaseOneBetaSupportReferenceResponse = Field(default_factory=PhaseOneBetaSupportReferenceResponse)
    countries: list[PhaseOneBetaCountryItem] = Field(default_factory=list)
    users: list[PhaseOneBetaUserItem] = Field(default_factory=list)


class GoldTrialMessageConfig(BaseModel):
    day: int = Field(ge=0, le=5)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=1000)
    channels: list[str] = Field(default_factory=list)
    video_url: str = Field(default="", max_length=2000)
    active: bool = True


class GoldTrialConfigResponse(BaseModel):
    tierLabel: str = "Try Gold free for 5 days"
    trialTierGranted: str = "gold"
    durationDays: int = 5
    messages: list[GoldTrialMessageConfig] = Field(default_factory=list)
    fallbackRule: str = "skip_to_next_channel_and_notify_admin"
    updatedAt: datetime | None = None


class GoldTrialConfigUpdateRequest(BaseModel):
    tierLabel: str | None = Field(default=None, min_length=1, max_length=120)
    messages: list[GoldTrialMessageConfig] | None = None


class GoldTrialOutcomeBreakdownResponse(BaseModel):
    totalTrials: int = 0
    activeTrials: int = 0
    convertedGold: int = 0
    downgradedSilver: int = 0
    lapsed: int = 0
    pendingDecision: int = 0
    conversionRate: float = 0
    downgradeRate: float = 0
    lapsedRate: float = 0


class GoldTrialStartResponse(BaseModel):
    status: str = "active"
    trial: GoldTrialSummaryResponse


class GoldTrialDecisionOption(BaseModel):
    tier: str
    label: str
    priceYearly: int | None = None
    includes: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    demonstratedUsage: dict[str, Any] = Field(default_factory=dict)


class GoldTrialDecisionResponse(BaseModel):
    trial: GoldTrialSummaryResponse
    usage: dict[str, Any] = Field(default_factory=dict)
    options: list[GoldTrialDecisionOption] = Field(default_factory=list)
    guardrail: str = "No paid plan is activated without explicit user action."


class AdminSubscriberItem(BaseModel):
    id: str
    fullName: str
    email: EmailStr
    subscriptionTier: str = "NONE"
    contactNumber: str = ""
    country: str = ""
    status: str = "NONE"
    joinedDate: datetime
    profileImage: str = ""
    subscriptionRole: str = "NONE"
    subscriptionBillingCycle: str = "yearly"
    subscriptionStartedAt: datetime | None = None
    subscriptionConfirmedAt: datetime | None = None
    subscriptionIsPurchased: bool = False
    subscriptionAccess: list[str] = Field(default_factory=list)


class AdminSubscriberListResponse(BaseModel):
    total: int = 0
    page: int = 1
    limit: int = 10
    users: list[AdminSubscriberItem] = Field(default_factory=list)


class AdminUserUpdateRequest(BaseModel):
    fullName: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    role: str | None = Field(default=None, min_length=1, max_length=50)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|INACTIVE|PENDING)$")
    isVerified: bool | None = None
    contactNumber: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, max_length=80)
    profileImage: str | None = Field(default=None, max_length=500)


class AdminWorkoutItem(BaseModel):
    id: str
    title: str
    vimeoId: str = ""
    videoUrl: str = ""
    videoSource: str = "VIMEO"
    tag: str
    visibility: str
    providerVisibility: str = "Published"
    thumbnail: str
    dateAdded: datetime
    updatedAt: datetime


class AdminWorkoutListResponse(BaseModel):
    total: int = 0
    workouts: list[AdminWorkoutItem] = Field(default_factory=list)


class AdminWorkoutRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    vimeoId: str = Field(default="", max_length=80)
    videoUrl: str = Field(default="", max_length=2000)
    videoSource: str = Field(default="VIMEO", pattern=r"^(VIMEO|YOUTUBE|UPLOAD)$")
    tag: str = Field(min_length=1, max_length=80)
    visibility: str = Field(pattern=r"^(Published|Draft)$")
    thumbnail: str | None = Field(default=None, max_length=500)
    video_base64: str | None = Field(default=None, min_length=32, max_length=40000000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    video_mime_type: str = Field(default="video/mp4", max_length=120)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    video_file_name: str | None = Field(default=None, max_length=255)
    file_name: str | None = Field(default=None, max_length=255)


class AdminDirectUploadRequest(BaseModel):
    uploadType: str = Field(pattern=r"^(WORKOUT_VIDEO|COMMUNITY_VIDEO)$")
    contentType: str = Field(min_length=1, max_length=120)
    fileName: str | None = Field(default=None, max_length=255)


class AdminDirectUploadResponse(BaseModel):
    uploadUrl: str
    fileUrl: str
    headers: dict[str, str] = Field(default_factory=dict)


class AdminWorkoutSyncVideoResponse(BaseModel):
    title: str
    vimeoId: str = ""
    tag: str = ""
    visibility: str = "Draft"
    providerVisibility: str = "Draft"
    alreadyInLibrary: bool = False


class AdminWorkoutSyncResponse(BaseModel):
    status: str = "success"
    message: str
    syncedCount: int = 0
    modulesSynced: int = 0
    videosDiscovered: int = 0
    syncedVideos: list[AdminWorkoutSyncVideoResponse] = Field(default_factory=list)


class AdminWorkoutSyncDebugItem(BaseModel):
    id: str
    title: str
    vimeoId: str = ""
    tag: str = ""
    visibility: str = "Draft"
    providerVisibility: str = "Draft"
    videoSource: str = "VIMEO"
    vimeoSourceType: str = ""
    vimeoSourceUri: str = ""
    vimeoSyncedAt: datetime | None = None
    updatedAt: datetime | None = None


class AdminWorkoutSyncDebugResponse(BaseModel):
    total: int = 0
    workouts: list[AdminWorkoutSyncDebugItem] = Field(default_factory=list)


class WorkoutLibraryItem(BaseModel):
    id: str
    title: str
    vimeoId: str = ""
    videoUrl: str = ""
    videoSource: str = "VIMEO"
    tag: str
    thumbnail: str
    dateAdded: datetime


class WorkoutLibraryCategory(BaseModel):
    id: str
    name: str
    count: int = 0
    image: str = ""


class WorkoutLibraryResponse(BaseModel):
    featuredWorkout: WorkoutLibraryItem | None = None
    workouts: list[WorkoutLibraryItem] = Field(default_factory=list)
    categories: list[WorkoutLibraryCategory] = Field(default_factory=list)


class StrengthWorkoutExercise(BaseModel):
    id: str
    name: str
    sets: int = Field(ge=1, le=10)
    reps: str
    rest: str
    weight: str = ""
    type: str


class StrengthWorkoutSection(BaseModel):
    id: str
    title: str
    estimated_minutes: int = Field(default=0, ge=0, le=180)
    exercises: list[StrengthWorkoutExercise] = Field(default_factory=list)


class StrengthWorkoutDay(BaseModel):
    day: str
    title: str
    est_time: str
    volume: str
    intensity: str
    sections: list[StrengthWorkoutSection] = Field(default_factory=list)
    exercises: list[StrengthWorkoutExercise] = Field(default_factory=list)


class StrengthWorkoutPlanRequest(BaseModel):
    goal: str | None = None
    level: str | None = None
    split: str | None = None
    height: str | None = None
    gender: str | None = None
    bench: str | None = None
    squat: str | None = None
    deadlift: str | None = None
    equipment: list[str] = Field(default_factory=list)
    frequency: str | None = None
    days: list[str] = Field(default_factory=list)
    age: str | None = None
    weight: str | None = None


class StrengthWorkoutPlanResponse(BaseModel):
    class DayProgress(BaseModel):
        day: str
        started: bool = False
        completed: bool = False
        completed_section_ids: list[str] = Field(default_factory=list)
        completed_exercise_ids: list[str] = Field(default_factory=list)
        started_at: datetime | None = None
        completed_at: datetime | None = None

    plan_id: str | None = None
    summary: str
    days: list[StrengthWorkoutDay] = Field(default_factory=list)
    progress: list[DayProgress] = Field(default_factory=list)
    created_at: datetime | None = None


class StrengthWorkoutPlanListResponse(BaseModel):
    items: list[StrengthWorkoutPlanResponse] = Field(default_factory=list)


class StrengthWorkoutPlanCompletionReportResponse(BaseModel):
    file_name: str
    mime_type: str = "image/png"
    image_base64: str = Field(min_length=32, max_length=20000000)
    share_message: str = Field(min_length=1, max_length=5000)


class VideoWorkoutPlanItem(BaseModel):
    id: str
    title: str
    duration: str
    category: str
    image: str = ""
    tag: str = ""
    vimeo_id: str = ""
    video_url: str = ""
    video_source: str = "VIMEO"


class VideoWorkoutPlanDay(BaseModel):
    day: str
    duration_label: str
    workouts_count: int = 0
    workouts: list[VideoWorkoutPlanItem] = Field(default_factory=list)


class VideoWorkoutPlanRequest(BaseModel):
    goal: str | None = None
    level: str | None = None
    days: str | None = None
    duration: str | None = None
    time: str | None = None
    notes: str | None = None
    countryCode: str | None = None
    phone: str | None = None
    equipment: str | None = None


class VideoWorkoutPlanResponse(BaseModel):
    summary: str
    days: list[VideoWorkoutPlanDay] = Field(default_factory=list)

# =====================================================================
# Admin Intelligence & Marketing Analytics (Section 18)
# =====================================================================


class AnalyticsRangeResponse(BaseModel):
    preset: str
    market: str
    fromDate: datetime
    toDate: datetime
    prevFromDate: datetime
    prevToDate: datetime


class UserTierBreakdown(BaseModel):
    tier: str
    count: int
    color: str | None = None


class TopUserItem(BaseModel):
    rank: int
    userId: str
    name: str
    tier: str | None = None
    points: int
    workouts: int = 0


class UserStatsResponse(BaseModel):
    totalRegistered: int
    totalRegisteredChangePct: float
    newUsers: int
    newUsersChangePct: float
    activeUsers: int
    activeUsersChangePct: float
    trialConversionRate: float
    trialConversionColor: str
    churnedUsers: int
    churnedChangePct: float
    usersByTier: list[UserTierBreakdown] = Field(default_factory=list)
    top10Users: list[TopUserItem] = Field(default_factory=list)


class TopWorkoutItem(BaseModel):
    workoutId: str | None = None
    title: str
    count: int
    avgDurationSeconds: int = 0


class WorkoutStatsResponse(BaseModel):
    totalCompleted: int
    totalCompletedChangePct: float
    completionRate: float
    completionRateColor: str
    topWorkout: TopWorkoutItem | None = None
    aiGeneratedWorkouts: int


class PopularChallengeItem(BaseModel):
    challengeId: str | None = None
    title: str
    category: str | None = None
    participants: int
    completionRate: float


class InviteAbVariant(BaseModel):
    variant: str
    acceptances: int
    total: int


class ChallengeStatsResponse(BaseModel):
    mostPopular: PopularChallengeItem | None = None
    invitesSent: int
    invitesSentChangePct: float
    inviteConversionRate: float
    abTestResult: list[InviteAbVariant] = Field(default_factory=list)


class MarketFoodItem(BaseModel):
    foodId: str | None = None
    foodName: str
    count: int


class NutritionStatsResponse(BaseModel):
    aiMealPlans: int
    aiMealPlansChangePct: float
    proteinTargetHitRate: float
    mostLoggedByMarket: dict[str, "MarketFoodItem | None"] = Field(default_factory=dict)


class RevenueTierItem(BaseModel):
    tier: str
    amount: float


class MarketRevenue(BaseModel):
    market: str
    currency: str
    amount: float


class MrrTrendPoint(BaseModel):
    date: str
    value: float


class RevenueStatsResponse(BaseModel):
    mrr: dict[str, float] = Field(default_factory=dict)
    revenueByTier: list[RevenueTierItem] = Field(default_factory=list)
    revenueByMarket: list[MarketRevenue] = Field(default_factory=list)
    arpu: float
    mrrTrend: list[MrrTrendPoint] = Field(default_factory=list)
    trendGranularity: str = "weekly"


class AccountabilityStatsResponse(BaseModel):
    newAccountabilityPairs: int
    newPairsChangePct: float


class RetentionComparison(BaseModel):
    habitRetainedPct: float
    nonHabitRetainedPct: float


class HabitAdoptionResponse(BaseModel):
    identityStatementSet: int
    identityStatementPct: float
    workoutUnlockSet: int
    workoutUnlockPct: float
    ifThenTriggerSet: int
    ifThenTriggerPct: float
    retentionComparison: RetentionComparison


class FunnelStep(BaseModel):
    label: str
    count: int
    dropOffPct: float


class TrialFunnelResponse(BaseModel):
    steps: list[FunnelStep] = Field(default_factory=list)
    largestDropOff: str | None = None


class SparklinePoint(BaseModel):
    date: str
    value: float


class ViralCoefficientWidgetResponse(BaseModel):
    current: float
    color: str
    sublabel: str
    sparkline: list[SparklinePoint] = Field(default_factory=list)


class MarketShareSplit(BaseModel):
    ghana: int = 0
    germany: int = 0
    india: int = 0


class WhatsAppTrackerWidgetResponse(BaseModel):
    todayCount: int
    thisWeekCount: int
    thisWeekChangePct: float
    dailySeries: list[SparklinePoint] = Field(default_factory=list)
    marketSplit: MarketShareSplit


class DailyWinEvent(BaseModel):
    type: str
    label: str
    count: int = 1
    createdAt: datetime


class DailyWinsFeedResponse(BaseModel):
    events: list[DailyWinEvent] = Field(default_factory=list)
    lastUpdated: datetime


class RetentionCohortRow(BaseModel):
    weekStart: str
    newUsers: int
    day7Pct: float | None = None
    day14Pct: float | None = None
    day30Pct: float | None = None
    paidDay30Pct: float | None = None


class RetentionCohortResponse(BaseModel):
    cohorts: list[RetentionCohortRow] = Field(default_factory=list)


class MarketBreakdownRow(BaseModel):
    name: str
    activeUsers: int
    newUsersThisWeek: int
    trialConversionRate: float
    revenueLocal: float
    whatsappShares: int
    day7RetentionPct: float
    viralCoefficient: float


class MarketBreakdownResponse(BaseModel):
    markets: list[MarketBreakdownRow] = Field(default_factory=list)
