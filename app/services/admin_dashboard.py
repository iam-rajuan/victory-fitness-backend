from calendar import month_abbr
from datetime import datetime, timedelta, timezone

from ..database import (
    challenge_memberships_collection,
    challenges_collection,
    users_collection,
    workouts_collection,
)
from ..models import (
    DashboardOverviewChartPoint,
    DashboardOverviewRecentUser,
    DashboardOverviewResponse,
)
from ..utils.datetime import as_utc
from ..vimeo_sync import get_vimeo_status


async def build_admin_dashboard_overview(year: int | None = None) -> DashboardOverviewResponse:
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
            createdAt=as_utc(record["created_at"]),
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
