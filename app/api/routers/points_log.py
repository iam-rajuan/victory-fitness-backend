from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status

from ...core.legacy import *

router = APIRouter()

_DEFAULT_TIERS = [
    ("Bronze", 0),
    ("Silver", 500),
    ("Gold", 1500),
    ("Platinum", 3000),
    ("Diamond", 5000),
    ("Master", 8000),
    ("Champion", 12000),
    ("Titan", 18000),
    ("Legend", 25000),
    ("Immortal", 35000),
]


def _resolve_tier_progression(points: int) -> dict:
    curr_tier = _DEFAULT_TIERS[0][0]
    next_tier = _DEFAULT_TIERS[1][0]
    points_to_next = _DEFAULT_TIERS[1][1] - points
    floor = 0
    ceiling = _DEFAULT_TIERS[1][1]

    for i in range(len(_DEFAULT_TIERS)):
        tier_name, threshold = _DEFAULT_TIERS[i]
        if points >= threshold:
            curr_tier = tier_name
            floor = threshold
            if i + 1 < len(_DEFAULT_TIERS):
                next_tier, ceiling = _DEFAULT_TIERS[i + 1]
                points_to_next = max(ceiling - points, 0)
            else:
                next_tier = curr_tier
                ceiling = threshold
                points_to_next = 0

    span = max(ceiling - floor, 1)
    progress_fraction = 1.0 if next_tier == curr_tier else min(max((points - floor) / span, 0.0), 1.0)

    return {
        "current_tier": curr_tier,
        "next_tier": next_tier,
        "points_to_next_tier": points_to_next,
        "rank_progress_fraction": round(progress_fraction, 3),
    }


@router.post("/points-log", status_code=status.HTTP_201_CREATED)
async def create_points_entry(
    payload: _PointsLogRequest,
    user: dict = Depends(dependency_require_access_user),
) -> dict[str, str]:
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if points_log_collection is None:
        return {"status": "noop"}
    try:
        await points_log_collection.insert_one({
            "user_id": user_id,
            "points": payload.points,
            "reason": payload.reason,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"points_log insert failed: {exc}")
    return {"status": "ok"}


@router.get("/me/points/breakdown")
async def get_my_points_breakdown(
    user: dict = Depends(dependency_require_access_user),
) -> dict:
    """Returns total points, tier progression, and 7-day category breakdown."""
    user_id = str(user.get("_id") or user.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    total_points = int(user.get("points") or 0)
    progression = _resolve_tier_progression(total_points)

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=6)
    start_date = seven_days_ago.replace(hour=0, minute=0, second=0, microsecond=0)

    # Prepare daily slots
    days_map: dict[str, dict] = {}
    for i in range(7):
        d = (start_date + timedelta(days=i)).date()
        date_str = d.isoformat()
        day_name = d.strftime("%a")
        days_map[date_str] = {
            "date": date_str,
            "day_name": day_name,
            "workouts": 0,
            "nutrition": 0,
            "habits": 0,
            "streaks": 0,
            "total": 0,
        }

    category_totals = {
        "workouts": 0,
        "nutrition": 0,
        "habits": 0,
        "streaks": 0,
        "total": 0,
    }

    if points_log_collection is not None:
        try:
            cursor = points_log_collection.find({
                "user_id": user_id,
                "created_at": {"$gte": start_date},
            }).sort("created_at", 1)
            entries = await cursor.to_list(length=1000)

            for entry in entries:
                pts = int(entry.get("points") or 0)
                reason = str(entry.get("reason") or "").lower()
                created_at = entry.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except Exception:
                        created_at = now
                elif not isinstance(created_at, datetime):
                    created_at = now

                date_str = created_at.date().isoformat()
                if date_str not in days_map:
                    continue

                if any(w in reason for w in ("workout", "exercise", "strength", "lift", "training")):
                    category = "workouts"
                elif any(w in reason for w in ("meal", "nutrition", "food", "protein", "macro", "diet")):
                    category = "nutrition"
                elif any(w in reason for w in ("streak", "checkin", "check-in", "bonus", "milestone")):
                    category = "streaks"
                else:
                    category = "habits"

                days_map[date_str][category] += pts
                days_map[date_str]["total"] += pts
                category_totals[category] += pts
                category_totals["total"] += pts
        except Exception:
            pass

    return {
        "total_points": total_points,
        "current_tier": progression["current_tier"],
        "next_tier": progression["next_tier"],
        "points_to_next_tier": progression["points_to_next_tier"],
        "rank_progress_fraction": progression["rank_progress_fraction"],
        "seven_day_breakdown": list(days_map.values()),
        "category_totals_7d": category_totals,
    }
