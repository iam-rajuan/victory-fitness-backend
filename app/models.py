from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


ALLOWED_CHALLENGE_DURATIONS = {3, 5, 7, 14, 21}


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{4}$")


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


class GoogleAuthRequest(BaseModel):
    id_token: str | None = Field(default=None, min_length=20)
    access_token: str | None = Field(default=None, min_length=20)


class TokenResponse(BaseModel):
    access_token: str
    session_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


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


class MeResponse(BaseModel):
    id: str
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
    onboarding_completed: bool = False


class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    country: str | None = Field(default=None, max_length=120)
    profileImage: str | None = Field(default=None, max_length=500)
    onboarding_completed: bool | None = None


class UpdateSubscriptionRequest(BaseModel):
    subscription_tier: str = Field(pattern=r"^(NONE|SILVER|GOLD|PLATINUM|INNER_CIRCLE)$")
    billing_cycle: str = Field(default="yearly", pattern=r"^(monthly|yearly)$")
    confirm_payment: bool = True


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
    like_count: int = 0
    comment_count: int = 0
    viewer_has_liked: bool = False
    can_delete: bool = False
    comments: list[CommunityCommentResponse] = Field(default_factory=list)
    reactions: list[CommunityReactionUserResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CommunityPostListResponse(BaseModel):
    posts: list[CommunityPostResponse] = Field(default_factory=list)


class CommunityPostCreateRequest(BaseModel):
    content: str | None = Field(default=None, max_length=5000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
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


class UserCompletedChallengeResponse(BaseModel):
    id: str
    challenge_id: str
    title: str
    description: str = ""
    duration_days: int = 0
    type: str
    earned_points: int = 0
    participants: int = 0
    thumbnail: str = ""
    completed_at: datetime
    color: str = "#22C55E"


class UserReadyChallengeResponse(BaseModel):
    id: str
    title: str
    description: str
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

    @field_validator("durationDays")
    @classmethod
    def validate_duration_days(cls, value: int) -> int:
        if value not in ALLOWED_CHALLENGE_DURATIONS:
            raise ValueError("durationDays must be one of 3, 5, 7, 14, or 21")
        return value


class AdminChallengePlanGenerateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=80)
    difficulty: str = Field(pattern=r"^(BEGINNER|INTERMEDIATE|ADVANCED)$")
    durationDays: int = Field(default=7, ge=1, le=365)

    @field_validator("durationDays")
    @classmethod
    def validate_duration_days(cls, value: int) -> int:
        if value not in ALLOWED_CHALLENGE_DURATIONS:
            raise ValueError("durationDays must be one of 3, 5, 7, 14, or 21")
        return value


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
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class AdminCommunityPostUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    audience: str | None = Field(default=None, pattern=r"^(ALL|SILVER|GOLD|PLATINUM|INNER_CIRCLE)$")
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)
    clear_image: bool = False


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
    image_base64: str = Field(min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


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


class AdminSubscriptionPlanItem(BaseModel):
    id: str
    tier: str
    description: str = ""
    priceMonthly: int | None = Field(default=None, ge=0)
    priceYearly: int | None = Field(default=None, ge=0)
    isApplicationOnly: bool = False
    isMostPopular: bool = False
    iconType: str = ""
    features: list[str] = Field(default_factory=list)


class AdminSubscriptionPlanListResponse(BaseModel):
    items: list[AdminSubscriptionPlanItem] = Field(default_factory=list)


class AdminSubscriptionPlanRequest(BaseModel):
    tier: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    priceMonthly: int | None = Field(default=None, ge=0)
    priceYearly: int | None = Field(default=None, ge=0)
    isApplicationOnly: bool = False
    isMostPopular: bool = False
    iconType: str = Field(default="", max_length=80)
    features: list[str] = Field(default_factory=list)


class AdminMasterclassItem(BaseModel):
    id: str
    title: str
    category: str = ""
    duration: str = ""
    description: str = ""
    videoUrl: str = ""
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
    videoUrl: str = Field(min_length=1, max_length=1000)
    audioUrl: str = Field(default="", max_length=1000)
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
    vimeoId: str
    tag: str
    visibility: str
    thumbnail: str
    dateAdded: datetime
    updatedAt: datetime


class AdminWorkoutListResponse(BaseModel):
    total: int = 0
    workouts: list[AdminWorkoutItem] = Field(default_factory=list)


class AdminWorkoutRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    vimeoId: str = Field(min_length=1, max_length=80)
    tag: str = Field(min_length=1, max_length=80)
    visibility: str = Field(pattern=r"^(Published|Draft)$")
    thumbnail: str | None = Field(default=None, max_length=500)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class AdminWorkoutSyncResponse(BaseModel):
    status: str = "success"
    message: str
    syncedCount: int = 0


class WorkoutLibraryItem(BaseModel):
    id: str
    title: str
    vimeoId: str
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


class StrengthWorkoutDay(BaseModel):
    day: str
    title: str
    est_time: str
    volume: str
    intensity: str
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
    plan_id: str | None = None
    summary: str
    days: list[StrengthWorkoutDay] = Field(default_factory=list)
    created_at: datetime | None = None


class StrengthWorkoutPlanListResponse(BaseModel):
    items: list[StrengthWorkoutPlanResponse] = Field(default_factory=list)


class VideoWorkoutPlanItem(BaseModel):
    id: str
    title: str
    duration: str
    category: str
    image: str = ""
    tag: str = ""
    vimeo_id: str = ""


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
