from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ...core.legacy import *

router = APIRouter()

WEEKDAY_KEYS = [
    ("Mon", "M"),
    ("Tue", "T"),
    ("Wed", "W"),
    ("Thu", "T"),
    ("Fri", "F"),
    ("Sat", "S"),
    ("Sun", "S"),
]

COMPOUND_NAME_HINTS = (
    "squat",
    "deadlift",
    "press",
    "bench",
    "row",
    "pull",
    "push",
    "clean",
    "snatch",
    "lunge",
    "thruster",
    "burpee",
)


def _coerce_positive_int(value: Any, fallback: int = 0) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except Exception:
        return fallback
    return parsed if parsed > 0 else fallback


def _extract_minutes(value: Any, fallback: int = 0) -> int:
    match = re.search(r"\d+", str(value or ""))
    return max(int(match.group(0)), 1) if match else fallback


def _normalize_weekday_key(value: Any) -> str:
    text = str(value or "").strip().lower()[:3]
    aliases = {
        "mon": "Mon",
        "tue": "Tue",
        "wed": "Wed",
        "thu": "Thu",
        "fri": "Fri",
        "sat": "Sat",
        "sun": "Sun",
    }
    return aliases.get(text, "")


def _exercise_is_compound(exercise: dict[str, Any]) -> bool:
    kind = str(exercise.get("type") or exercise.get("kind") or "").lower()
    name = str(exercise.get("name") or "").lower()
    if "compound" in kind:
        return True
    return any(hint in name for hint in COMPOUND_NAME_HINTS)


def _flatten_strength_day_exercises(day: dict[str, Any]) -> list[dict[str, Any]]:
    exercises = [dict(item) for item in day.get("exercises") or [] if isinstance(item, dict)]
    if exercises:
        return exercises
    flattened: list[dict[str, Any]] = []
    for section in day.get("sections") or []:
        if not isinstance(section, dict):
            continue
        flattened.extend(dict(item) for item in section.get("exercises") or [] if isinstance(item, dict))
    return flattened


def _build_session_counts(exercises: list[dict[str, Any]]) -> dict[str, int]:
    set_count = sum(_coerce_positive_int(exercise.get("sets"), 1) for exercise in exercises)
    return {
        "exerciseCount": len(exercises),
        "setCount": set_count,
        "compoundCount": sum(1 for exercise in exercises if _exercise_is_compound(exercise)),
    }


def _week_start_utc(now: datetime) -> datetime:
    start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.weekday())


async def _completed_workout_dates_for_week(user_id: str, now: datetime) -> set[str]:
    if workout_logs_collection is None:
        return set()
    week_start = _week_start_utc(now)
    week_end = week_start + timedelta(days=7)
    cursor = workout_logs_collection.find(
        {
            "user_id": user_id,
            "status": "completed",
            "completed_at": {"$gte": week_start, "$lt": week_end},
        }
    )
    docs = await cursor.to_list(length=100)
    dates: set[str] = set()
    for doc in docs:
        completed_at = doc.get("completed_at") or doc.get("started_at")
        if isinstance(completed_at, datetime):
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            dates.add(completed_at.astimezone(timezone.utc).date().isoformat())
    return dates


def _build_week_summary(
    *,
    now: datetime,
    completed_dates: set[str],
    training_days: list[str],
) -> dict[str, Any]:
    today = now.astimezone(timezone.utc).date()
    week_start = _week_start_utc(now).date()
    scheduled_days = {_normalize_weekday_key(day) for day in training_days if _normalize_weekday_key(day)}
    if not scheduled_days:
        scheduled_days = {"Mon", "Wed", "Fri"}

    pips: list[dict[str, str]] = []
    done_count = 0
    remaining_after_today = 0
    today_completed = today.isoformat() in completed_dates
    for index, (key, label) in enumerate(WEEKDAY_KEYS):
        day_date = week_start + timedelta(days=index)
        date_key = day_date.isoformat()
        is_today = day_date == today
        is_scheduled = key in scheduled_days
        is_done = date_key in completed_dates
        if is_done:
            done_count += 1
        if is_done:
            state = "done"
        elif is_today:
            state = "today"
        elif is_scheduled:
            state = "optional" if day_date > today else "missed"
        else:
            state = "rest"
        if day_date > today and is_scheduled and not is_done:
            remaining_after_today += 1
        pips.append({"label": label, "key": key, "state": state})

    left_label = "session" if remaining_after_today == 1 else "sessions"
    note_bits = [f"{done_count} done", "today done" if today_completed else "today"]
    note_bits.append(f"{remaining_after_today} light {left_label} left")
    if "Sun" not in scheduled_days:
        note_bits.append("Sunday optional")
    return {
        "pips": pips,
        "note": " · ".join(note_bits),
        "doneCount": done_count,
        "targetCount": len(scheduled_days),
        "remainingLightSessions": remaining_after_today,
        "todayCompleted": today_completed,
    }


@router.get("/workouts/home-plan-summary")
async def workout_home_plan_summary(user: dict = Depends(dependency_require_access_user)) -> dict[str, Any]:
    user_id = str(user.get("_id") or user.get("id") or "")
    now = datetime.now(timezone.utc)
    completed_dates = await _completed_workout_dates_for_week(user_id, now)

    strength_record = None
    if strength_workout_plans_collection is not None:
        strength_record = await strength_workout_plans_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)],
        )

    if strength_record and isinstance(strength_record.get("plan"), dict):
        plan = dict(strength_record.get("plan") or {})
        days = [day for day in plan.get("days") or [] if isinstance(day, dict)]
        progress = [item for item in strength_record.get("progress") or [] if isinstance(item, dict)]
        completed_day_keys = {str(item.get("day") or "") for item in progress if item.get("completed")}
        selected_day = next((day for day in days if str(day.get("day") or "") not in completed_day_keys), None) or (days[0] if days else {})
        exercises = _flatten_strength_day_exercises(selected_day)
        counts = _build_session_counts(exercises)
        training_days = [str(day) for day in (strength_record.get("input") or {}).get("days") or []]
        if not training_days:
            training_days = [str(day.get("day") or "") for day in days]
        duration_minutes = _extract_minutes(selected_day.get("est_time"), 40)
        title = str(selected_day.get("title") or "Workout").strip() or "Workout"
        return {
            "source": "strength_plan",
            "planId": str(strength_record.get("_id") or ""),
            "title": title,
            "dayKicker": f"{str(selected_day.get('day') or 'TODAY').upper()} · {duration_minutes} MIN",
            "planSource": "BUILT BY YOUR COACH",
            "durationMinutes": duration_minutes,
            "equipment": ", ".join(str(item) for item in (strength_record.get("input") or {}).get("equipment") or []),
            "week": _build_week_summary(now=now, completed_dates=completed_dates, training_days=training_days),
            "session": counts,
        }

    records = await list_public_workout_records({"visibility": "Published"})
    workout = shared_serialize_public_workout_record(records[0]) if records else {}
    movements = [dict(item) for item in workout.get("movements") or [] if isinstance(item, dict)]
    counts = _build_session_counts(movements)
    duration_minutes = _coerce_positive_int(workout.get("durationMinutes"), 0)
    return {
        "source": "workout_library",
        "planId": "",
        "title": str(workout.get("title") or "Workout"),
        "dayKicker": f"TODAY · {duration_minutes or 0} MIN",
        "planSource": "VIDEO · FROM THE LIBRARY",
        "durationMinutes": duration_minutes,
        "equipment": str(workout.get("equipment") or ""),
        "week": _build_week_summary(now=now, completed_dates=completed_dates, training_days=["Mon", "Wed", "Fri"]),
        "session": counts,
    }

@router.get("/workouts/library", response_model=WorkoutLibraryResponse)

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

    workouts = [WorkoutLibraryItem(**shared_serialize_public_workout_record(record)) for record in records]

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
