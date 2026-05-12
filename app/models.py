from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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


class RefreshRequest(BaseModel):
    session_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    session_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class MeResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    is_verified: bool
    role: str = "user"
    is_admin: bool = False
    country: str = ""
    profileImage: str = ""


class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    country: str | None = Field(default=None, max_length=120)
    profileImage: str | None = Field(default=None, max_length=500)


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


class CommunityCommentResponse(BaseModel):
    id: str
    post_id: str
    author_name: str
    author_role: str
    author_profile_image: str = ""
    content: str
    created_at: datetime


class CommunityPostResponse(BaseModel):
    id: str
    author_name: str
    author_role: str
    author_profile_image: str = ""
    audience: str = "ALL"
    content: str
    image_url: str = ""
    like_count: int = 0
    comment_count: int = 0
    viewer_has_liked: bool = False
    comments: list[CommunityCommentResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CommunityPostListResponse(BaseModel):
    posts: list[CommunityPostResponse] = Field(default_factory=list)


class CommunityPostCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    image_base64: str | None = Field(default=None, min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class CommunityCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommunityReactionToggleResponse(BaseModel):
    post_id: str
    like_count: int = 0
    viewer_has_liked: bool = False


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


class MealImageAnalysisRequest(BaseModel):
    image_base64: str = Field(min_length=32, max_length=20000000)
    mime_type: str = Field(default="image/jpeg", max_length=120)
    file_name: str | None = Field(default=None, max_length=255)


class MealImageAnalysisResponse(BaseModel):
    meal_name_guess: str
    summary: str
    estimated_calories: int = Field(ge=0, le=3000)
    estimated_protein: int = Field(ge=0, le=300)
    estimated_carbs: int = Field(ge=0, le=500)
    estimated_fat: int = Field(ge=0, le=200)
    confidence: str
    notes: list[str] = Field(default_factory=list)


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
    vimeoApiStatus: str
    userChart: list[DashboardOverviewChartPoint] = Field(default_factory=list)
    recentUsers: list[DashboardOverviewRecentUser] = Field(default_factory=list)


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
    pass


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
