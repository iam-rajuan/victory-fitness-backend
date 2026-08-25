from fastapi import APIRouter

from ...core.legacy import *
from ...models import (
    StrengthWorkoutAdaptiveRecommendationResponse,
    StrengthWorkoutSessionFeedbackRequest,
)

router = APIRouter()


def _adjust_strength_volume_label(volume_label: str, adjustment_pct: int) -> str:
    text = str(volume_label or "").strip()
    if not text or adjustment_pct == 0:
        return text
    match = re.match(r"^\s*([\d,]+(?:\.\d+)?)\s*(.*)$", text)
    if not match:
        return text
    try:
        numeric_value = float(match.group(1).replace(",", ""))
    except ValueError:
        return text
    adjusted_value = max(numeric_value * (1 + (adjustment_pct / 100.0)), 0)
    suffix = match.group(2).strip()
    rounded_value = int(round(adjusted_value))
    formatted = f"{rounded_value:,}" if rounded_value >= 1 else f"{adjusted_value:.1f}".rstrip("0").rstrip(".")
    return f"{formatted} {suffix}".strip()


def _adjust_strength_intensity_label(intensity_label: str, adjustment_pct: int) -> str:
    text = str(intensity_label or "").strip()
    if not text or adjustment_pct == 0:
        return text
    rpe_match = re.search(r"RPE\s*([0-9]+(?:\.[0-9])?)", text, re.IGNORECASE)
    if rpe_match:
        try:
            current_value = float(rpe_match.group(1))
        except ValueError:
            return text
        delta = 0.5 if adjustment_pct > 0 else -0.5
        next_value = min(max(current_value + delta, 5.0), 10.0)
        return re.sub(
            r"RPE\s*[0-9]+(?:\.[0-9])?",
            f"RPE {next_value:.1f}",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    replacements = {
        "moderate": "moderately hard" if adjustment_pct > 0 else "controlled",
        "hard": "very hard" if adjustment_pct > 0 else "moderate",
        "controlled": "moderate" if adjustment_pct > 0 else "easy",
    }
    lowered = text.lower()
    for source, target in replacements.items():
        if source in lowered:
            pattern = re.compile(re.escape(source), re.IGNORECASE)
            return pattern.sub(target, text, count=1)
    return text


def _adaptive_workout_adjustment(payload: StrengthWorkoutSessionFeedbackRequest) -> tuple[int, str, str]:
    perceived = str(payload.perceived_difficulty or "").lower()
    energy = str(payload.energy or "").lower()
    soreness = str(payload.soreness or "").lower()
    if perceived == "hard" or energy == "low" or soreness == "high":
        return (-10, "decrease", "Reduce the next workout slightly so recovery stays ahead of fatigue.")
    if perceived == "easy" and energy == "high" and soreness == "low":
        return (5, "increase", "You handled this session well, so the next workout can progress slightly.")
    return (0, "maintain", "Keep the next workout steady and reinforce consistency before changing load again.")

@router.get("/ai/workout-plan/strength/{plan_id}/report", response_model=StrengthWorkoutPlanCompletionReportResponse)
async def workout_strength_plan_completion_report(
    plan_id: str,
    day: str = "",
    full_plan: bool = False,
    user: dict = Depends(_require_workout_plan_access_user),
) -> StrengthWorkoutPlanCompletionReportResponse:
    if not ObjectId.is_valid(plan_id):
        raise HTTPException(status_code=404, detail="Strength workout plan not found")
    record = await strength_workout_plans_collection.find_one({"_id": ObjectId(plan_id), "user_id": str(user["_id"])})
    if not record or not isinstance(record.get("plan"), dict):
        raise HTTPException(status_code=404, detail="Strength workout plan not found")
    plan = _serialize_strength_workout_plan_record(record)
    plan_is_complete = bool(plan.days) and all(next((item.completed for item in plan.progress if item.day == workout_day.day), False) for workout_day in plan.days)
    png_bytes, share_message = _build_strength_workout_completion_png(
        plan,
        str(user.get("name") or "Victory Member"),
        day,
        full_plan=full_plan and plan_is_complete,
    )
    return StrengthWorkoutPlanCompletionReportResponse(
        file_name="victory-fitness-strength-completion.png",
        mime_type="image/png",
        image_base64=base64.b64encode(png_bytes).decode("ascii"),
        share_message=share_message,
    )

@router.post("/ai/workout-plan/strength", response_model=StrengthWorkoutPlanResponse)

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

@router.get("/ai/workout-plan/strength/latest", response_model=StrengthWorkoutPlanResponse)

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

@router.get("/ai/workout-plan/strength", response_model=StrengthWorkoutPlanListResponse)

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

@router.patch("/ai/workout-plan/strength/{plan_id}/progress", response_model=StrengthWorkoutPlanResponse)

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


@router.post("/ai/workout-plan/strength/{plan_id}/feedback", response_model=StrengthWorkoutAdaptiveRecommendationResponse)
async def workout_strength_plan_feedback(
    plan_id: str,
    payload: StrengthWorkoutSessionFeedbackRequest,
    user: dict = Depends(_require_workout_plan_access_user),
) -> StrengthWorkoutAdaptiveRecommendationResponse:
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

    plan_data = dict(record.get("plan") or {})
    plan_days = [dict(item) for item in plan_data.get("days") or [] if isinstance(item, dict)]
    selected_index = next(
        (index for index, day in enumerate(plan_days) if str(day.get("day") or "").strip() == day_key),
        -1,
    )
    if selected_index < 0:
        raise HTTPException(status_code=400, detail="Workout day not found")

    adjustment_pct, direction, summary = _adaptive_workout_adjustment(payload)
    next_intensity_target = ""
    if selected_index + 1 < len(plan_days):
        next_day = dict(plan_days[selected_index + 1])
        next_day["volume"] = _adjust_strength_volume_label(str(next_day.get("volume") or ""), adjustment_pct)
        next_day["intensity"] = _adjust_strength_intensity_label(str(next_day.get("intensity") or ""), adjustment_pct)
        next_intensity_target = str(next_day.get("intensity") or "")
        plan_days[selected_index + 1] = next_day
        plan_data["days"] = plan_days

    now = datetime.now(timezone.utc)
    raw_feedback = record.get("session_feedback") or []
    session_feedback = [item for item in raw_feedback if isinstance(item, dict)]
    session_feedback.append(
        {
            "day": day_key,
            "perceived_difficulty": payload.perceived_difficulty,
            "energy": payload.energy,
            "soreness": payload.soreness,
            "notes": str(payload.notes or "").strip(),
            "adjustment_pct": adjustment_pct,
            "next_volume_direction": direction,
            "created_at": now,
        }
    )
    session_feedback = session_feedback[-60:]

    await strength_workout_plans_collection.update_one(
        {"_id": record["_id"]},
        {
            "$set": {
                "plan": plan_data,
                "session_feedback": session_feedback,
                "updated_at": now,
            }
        },
    )

    record["plan"] = plan_data
    record["session_feedback"] = session_feedback
    record["updated_at"] = now

    return StrengthWorkoutAdaptiveRecommendationResponse(
        plan=_serialize_strength_workout_plan_record(record),
        adjustment_pct=adjustment_pct,
        next_volume_direction=direction,
        next_intensity_target=next_intensity_target,
        summary=summary,
        updated_at=now,
    )

@router.delete("/ai/workout-plan/strength/latest")

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

@router.delete("/ai/workout-plan/strength/{plan_id}")

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

@router.post("/ai/workout-plan/video", response_model=VideoWorkoutPlanResponse)

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
