from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/longevity-os/dashboard", response_model=LongevityDashboardResponse)

async def longevity_dashboard(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityDashboardResponse:

    profile = await _get_or_create_longevity_profile(user)

    return await _serialize_longevity_dashboard(profile)

@router.get("/longevity-os/heal/categories", response_model=LongevityHealCategoriesResponse)

async def longevity_heal_categories(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityHealCategoriesResponse:

    profile = await _get_or_create_longevity_profile(user)

    return LongevityHealCategoriesResponse(

        categories=[LongevityHealCategoryResponse(**item) for item in profile.get("heal_categories") or []]

    )

@router.post("/longevity-os/heal/weekly-plan", response_model=LongevityWeeklyPlanResponse)

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

@router.get("/longevity-os/habits", response_model=LongevityHabitsResponse)

async def longevity_habits(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityHabitsResponse:

    profile = await _get_or_create_longevity_profile(user)

    habits = [dict(item) for item in profile.get("habits") or []]

    return LongevityHabitsResponse(

        streak_days=_calculate_habit_streak(habits),

        habits=[LongevityHabitResponse(**item) for item in habits],

    )

@router.patch("/longevity-os/habits/{habit_id}", response_model=LongevityHabitsResponse)

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

@router.get("/longevity-os/masterclasses", response_model=LongevityMasterclassListResponse)

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

@router.get("/longevity-os/circles", response_model=LongevityCircleListResponse)

async def longevity_circles(

    user: dict = Depends(_require_longevity_access_user),

) -> LongevityCircleListResponse:

    profile = await _get_or_create_longevity_profile(user)

    return LongevityCircleListResponse(

        items=[LongevityCircleResponse(**item) for item in profile.get("circles") or []]

    )
