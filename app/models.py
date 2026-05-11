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
