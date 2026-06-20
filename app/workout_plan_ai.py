import json
from dataclasses import dataclass
from urllib import error, request

from .config import settings


DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WORKOUT_PLAN_TIMEOUT_SECONDS = 60


@dataclass
class StrengthWorkoutPlanInput:
    goal: str
    level: str
    split: str
    height: str
    gender: str
    bench: str
    squat: str
    deadlift: str
    equipment: list[str]
    frequency: str
    days: list[str]
    age: str
    weight: str


@dataclass
class VideoWorkoutPlanInput:
    goal: str
    level: str
    days: str
    duration: str
    time: str
    notes: str
    equipment: str


def _normalize_strength_goal(goal: str) -> str:
    value = str(goal or "").strip().upper()
    goal_map = {
        "1": "HYPERTROPHY",
        "2": "PURE STRENGTH",
        "3": "POWER & SPEED",
        "4": "BODY RECOMP",
    }
    return goal_map.get(value, value)


def _normalize_strength_split(split: str) -> str:
    value = str(split or "").strip().upper()
    split_map = {
        "1": "FULL BODY",
        "2": "UPPER / LOWER",
        "3": "PUSH PULL LEGS",
    }
    return split_map.get(value, value)


def generate_strength_workout_plan(input_data: StrengthWorkoutPlanInput) -> dict:
    ai_plan = _generate_strength_workout_plan_with_ai(input_data)
    if _looks_like_strength_plan(ai_plan):
        return ai_plan

    frequency = _safe_int(input_data.frequency, 4, minimum=3, maximum=5)
    preferred_days = _normalize_preferred_days(input_data.days)
    active_days = preferred_days[:frequency] if preferred_days else DAY_ORDER[:frequency]
    title_cycle = _strength_title_cycle(input_data.split, input_data.goal)
    exercise_pool = _strength_exercise_pool(input_data.goal, input_data.equipment)
    est_time = _strength_time_label(frequency, input_data.level)
    intensity = _strength_intensity_label(input_data.goal, input_data.level)

    days: list[dict] = []
    for index, day_name in enumerate(active_days):
        session_title = title_cycle[index % len(title_cycle)]
        exercises = []
        for exercise_index, exercise in enumerate(exercise_pool[index % len(exercise_pool)]):
            exercises.append(
                {
                    "id": f"{day_name.lower()}-{exercise_index + 1}",
                    "name": exercise["name"],
                    "sets": exercise["sets"],
                    "reps": exercise["reps"],
                    "rest": exercise["rest"],
                    "weight": _exercise_weight_label(exercise["name"], input_data),
                    "type": exercise["type"],
                }
            )

        working_sets = sum(int(item["sets"]) for item in exercises)
        average_weight = max(_safe_int(input_data.weight, 75, minimum=40, maximum=180), 40)
        volume_value = working_sets * average_weight * 8
        days.append(
            {
                "day": day_name,
                "title": session_title,
                "est_time": est_time,
                "volume": f"{volume_value:,} kg",
                "intensity": intensity,
                "exercises": exercises,
            }
        )

    summary = (
        f"{input_data.level or 'Intermediate'} {input_data.goal or 'strength'} plan using a "
        f"{input_data.split or 'balanced'} split with {frequency} main training days."
    )
    return {"summary": summary, "days": days}


def _generate_strength_workout_plan_with_ai(input_data: StrengthWorkoutPlanInput) -> dict | None:
    if settings.anthropic_api_key:
        try:
            plan = _anthropic_strength_plan_json(input_data)
            if _looks_like_strength_plan(plan):
                return plan
        except RuntimeError:
            pass

    if settings.openai_api_key:
        try:
            plan = _openai_strength_plan_json(input_data)
            if _looks_like_strength_plan(plan):
                return plan
        except RuntimeError:
            pass

    return None


def generate_video_workout_plan(input_data: VideoWorkoutPlanInput, workouts: list[dict]) -> dict:
    training_days = _video_training_days(input_data.days)
    duration_label = _video_duration_label(input_data.time)
    items_per_day = 3 if "45+" in input_data.time else 2 if "25-45" in input_data.time else 1
    goal_categories = _video_goal_categories(input_data.goal)
    published_workouts = workouts[:]
    if not published_workouts:
        published_workouts = [
            {"id": "fallback-1", "title": "Bodyweight Conditioning", "tag": "Full Body", "thumbnail": ""},
            {"id": "fallback-2", "title": "Core and Mobility Flow", "tag": "Mobility", "thumbnail": ""},
            {"id": "fallback-3", "title": "Low Impact Cardio", "tag": "Cardio", "thumbnail": ""},
        ]

    days: list[dict] = []
    cursor = 0
    for day_name in DAY_ORDER:
        if day_name not in training_days:
            days.append(
                {
                    "day": day_name,
                    "duration_label": "Recovery",
                    "workouts_count": 0,
                    "workouts": [],
                }
            )
            continue

        daily_workouts = []
        for item_index in range(items_per_day):
            source = published_workouts[(cursor + item_index) % len(published_workouts)]
            category = goal_categories[(cursor + item_index) % len(goal_categories)]
            daily_workouts.append(
                {
                    "id": str(source.get("id") or f"{day_name.lower()}-{item_index + 1}"),
                    "title": str(source.get("title") or "Workout"),
                    "duration": _video_workout_duration(input_data.time, item_index),
                    "category": category,
                    "image": str(source.get("thumbnail") or ""),
                    "tag": str(source.get("tag") or "Recommended"),
                    "vimeo_id": str(source.get("vimeoId") or source.get("vimeo_id") or ""),
                    "video_url": str(source.get("videoUrl") or source.get("video_url") or ""),
                    "video_source": str(source.get("videoSource") or source.get("video_source") or "VIMEO"),
                }
            )
        cursor += items_per_day
        days.append(
            {
                "day": day_name,
                "duration_label": duration_label,
                "workouts_count": len(daily_workouts),
                "workouts": daily_workouts,
            }
        )

    summary = (
        f"{input_data.goal or 'General fitness'} video plan with {len(training_days)} active days, "
        f"built for {input_data.level or 'your current level'} and {input_data.equipment or 'available equipment'}."
    )
    return {"summary": summary, "days": days}


def _looks_like_strength_plan(plan: dict | None) -> bool:
    if not isinstance(plan, dict):
        return False
    days = plan.get("days")
    return isinstance(days, list) and len(days) > 0


def _strength_plan_prompt(input_data: StrengthWorkoutPlanInput) -> str:
    return (
        "Create a custom strength plan as one JSON object only.\n"
        "The plan must match the user's actual inputs and feel like a real coach wrote it.\n"
        "Requirements:\n"
        "- Return only the actual training days the user selected. Do not include recovery days unless they were selected.\n"
        "- Day values must use Mon Tue Wed Thu Fri Sat Sun.\n"
        "- Training days must align with preferred training days and frequency when possible.\n"
        "- Each day needs: day, title, est_time, volume, intensity, exercises.\n"
        "- Each exercise needs: id, name, sets, reps, rest, weight, type.\n"
        "- Weight should be realistic based on the user's lifts when provided, otherwise estimate conservatively.\n"
        "- Split, goal, experience level, equipment, and frequency must visibly affect the plan.\n"
        "- Keep exercise ids stable and machine-friendly.\n"
        f"User inputs: {json.dumps(input_data.__dict__, ensure_ascii=False)}"
    )


def _strength_plan_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "days"],
        "properties": {
            "summary": {"type": "string"},
            "days": {
                "type": "array",
                "minItems": 1,
                "maxItems": 7,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["day", "title", "est_time", "volume", "intensity", "exercises"],
                    "properties": {
                        "day": {"type": "string", "enum": DAY_ORDER},
                        "title": {"type": "string"},
                        "est_time": {"type": "string"},
                        "volume": {"type": "string"},
                        "intensity": {"type": "string"},
                        "exercises": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "name", "sets", "reps", "rest", "weight", "type"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "sets": {"type": "integer"},
                                    "reps": {"type": "string"},
                                    "rest": {"type": "string"},
                                    "weight": {"type": "string"},
                                    "type": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _openai_strength_plan_json(input_data: StrengthWorkoutPlanInput) -> dict:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You generate personalized strength plans. "
                    "Return exactly one valid JSON object matching the required schema. "
                    "No markdown, no explanations."
                ),
            },
            {
                "role": "user",
                "content": _strength_plan_prompt(input_data),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 4000,
    }

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=WORKOUT_PLAN_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI strength plan request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI strength plan request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI strength plan request failed: {exc.reason}") from exc

    try:
        content = data["choices"][0]["message"]["content"].strip()
        return json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError("OpenAI strength plan response was missing valid JSON") from exc


def _anthropic_strength_plan_json(input_data: StrengthWorkoutPlanInput) -> dict:
    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 4000,
        "system": (
            "You generate personalized strength plans. "
            "Return exactly one valid JSON object matching the provided schema. "
            "No markdown, no explanations.\n"
            f"Schema: {json.dumps(_strength_plan_schema(), ensure_ascii=False)}"
        ),
        "messages": [
            {
                "role": "user",
                "content": _strength_plan_prompt(input_data),
            }
        ],
    }

    req = request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=WORKOUT_PLAN_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("Anthropic strength plan request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic strength plan request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic strength plan request failed: {exc.reason}") from exc

    try:
        content = "".join(
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
        return json.loads(content)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Anthropic strength plan response was missing valid JSON") from exc


def _normalize_preferred_days(days: list[str]) -> list[str]:
    normalized = []
    for day in days:
        key = str(day or "").strip()[:3].title()
        if key in DAY_ORDER and key not in normalized:
            normalized.append(key)
    return normalized


def _strength_title_cycle(split: str, goal: str) -> list[str]:
    split_map = {
        "FULL BODY": ["Full Body Strength", "Full Body Hypertrophy", "Full Body Power"],
        "UPPER / LOWER": ["Upper Body Strength", "Lower Body Strength", "Upper Body Volume", "Lower Body Power"],
        "PUSH PULL LEGS": ["Push Strength", "Pull Strength", "Leg Strength", "Push Hypertrophy", "Pull Hypertrophy"],
    }
    normalized_split = _normalize_strength_split(split)
    normalized_goal = _normalize_strength_goal(goal)
    titles = split_map.get(normalized_split, split_map["UPPER / LOWER"])
    if normalized_goal == "POWER & SPEED":
        return [title.replace("Strength", "Power") for title in titles]
    return titles


def _strength_exercise_pool(goal: str, equipment: list[str]) -> list[list[dict]]:
    normalized_goal = _normalize_strength_goal(goal)
    bodyweight_only = "bodyweight" in {str(item).strip().lower() for item in equipment}
    if bodyweight_only:
        return [
            [
                {"name": "Tempo Squat", "sets": 4, "reps": "10-12", "rest": "75s", "type": "Compound"},
                {"name": "Push-Up", "sets": 4, "reps": "8-15", "rest": "60s", "type": "Compound"},
                {"name": "Reverse Lunge", "sets": 3, "reps": "10/side", "rest": "60s", "type": "Accessory"},
                {"name": "Plank", "sets": 3, "reps": "45s", "rest": "45s", "type": "Core"},
            ],
            [
                {"name": "Single-Leg Glute Bridge", "sets": 4, "reps": "12/side", "rest": "60s", "type": "Accessory"},
                {"name": "Pike Push-Up", "sets": 4, "reps": "8-12", "rest": "60s", "type": "Compound"},
                {"name": "Bodyweight Row", "sets": 3, "reps": "10-12", "rest": "60s", "type": "Compound"},
                {"name": "Hollow Hold", "sets": 3, "reps": "30-40s", "rest": "45s", "type": "Core"},
            ],
        ]

    if normalized_goal == "PURE STRENGTH":
        return [
            [
                {"name": "Barbell Back Squat", "sets": 5, "reps": "4-6", "rest": "180s", "type": "Compound"},
                {"name": "Bench Press", "sets": 5, "reps": "4-6", "rest": "180s", "type": "Compound"},
                {"name": "Weighted Row", "sets": 4, "reps": "6-8", "rest": "120s", "type": "Compound"},
                {"name": "Farmer Carry", "sets": 3, "reps": "30m", "rest": "75s", "type": "Accessory"},
            ],
            [
                {"name": "Deadlift", "sets": 4, "reps": "3-5", "rest": "210s", "type": "Compound"},
                {"name": "Overhead Press", "sets": 4, "reps": "5-6", "rest": "120s", "type": "Compound"},
                {"name": "Pull-Up", "sets": 4, "reps": "6-8", "rest": "90s", "type": "Compound"},
                {"name": "Split Squat", "sets": 3, "reps": "8/side", "rest": "75s", "type": "Accessory"},
            ],
        ]

    return [
        [
            {"name": "Barbell Back Squat", "sets": 4, "reps": "6-8", "rest": "180s", "type": "Compound"},
            {"name": "Romanian Deadlift", "sets": 3, "reps": "8-10", "rest": "120s", "type": "Compound"},
            {"name": "Leg Press", "sets": 3, "reps": "10-12", "rest": "90s", "type": "Accessory"},
            {"name": "Leg Extension", "sets": 3, "reps": "12-15", "rest": "60s", "type": "Isolation"},
        ],
        [
            {"name": "Bench Press", "sets": 4, "reps": "6-8", "rest": "150s", "type": "Compound"},
            {"name": "Incline Dumbbell Press", "sets": 3, "reps": "8-10", "rest": "90s", "type": "Accessory"},
            {"name": "Cable Row", "sets": 3, "reps": "10-12", "rest": "75s", "type": "Compound"},
            {"name": "Lateral Raise", "sets": 3, "reps": "12-15", "rest": "45s", "type": "Isolation"},
        ],
        [
            {"name": "Deadlift", "sets": 4, "reps": "5-6", "rest": "180s", "type": "Compound"},
            {"name": "Pull-Up", "sets": 4, "reps": "6-10", "rest": "90s", "type": "Compound"},
            {"name": "Walking Lunge", "sets": 3, "reps": "10/side", "rest": "75s", "type": "Accessory"},
            {"name": "Cable Crunch", "sets": 3, "reps": "12-15", "rest": "45s", "type": "Core"},
        ],
    ]


def _strength_time_label(frequency: int, level: str) -> str:
    base = 55 if str(level or "").upper() == "BEGINNER" else 65 if str(level or "").upper() == "INTERMEDIATE" else 75
    if frequency >= 5:
        base -= 5
    return f"{base} min"


def _strength_intensity_label(goal: str, level: str) -> str:
    normalized_goal = _normalize_strength_goal(goal)
    if normalized_goal == "PURE STRENGTH":
        return "RPE 8.5"
    if normalized_goal == "POWER & SPEED":
        return "RPE 8.0"
    return "RPE 7.5" if str(level or "").upper() == "BEGINNER" else "RPE 8.0"


def _exercise_weight_label(exercise_name: str, input_data: StrengthWorkoutPlanInput) -> str:
    name = exercise_name.lower()
    if "bench" in name:
        value = _safe_int(input_data.bench, 60, minimum=20, maximum=250)
        return f"{max(int(round(value * 0.72)), 15)}kg"
    if "squat" in name or "leg press" in name:
        value = _safe_int(input_data.squat, 90, minimum=30, maximum=320)
        multiplier = 0.7 if "squat" in name else 1.25
        return f"{max(int(round(value * multiplier)), 20)}kg"
    if "deadlift" in name or "romanian" in name:
        value = _safe_int(input_data.deadlift, 100, minimum=40, maximum=350)
        multiplier = 0.68 if "romanian" in name else 0.82
        return f"{max(int(round(value * multiplier)), 20)}kg"
    if "pull-up" in name:
        return "Bodyweight"
    if "plank" in name or "hold" in name or "carry" in name:
        return "-"
    weight = _safe_int(input_data.weight, 75, minimum=40, maximum=180)
    return f"{max(int(round(weight * 0.45)), 10)}kg"


def _video_training_days(days_value: str) -> list[str]:
    mapping = {
        "1": ["Mon", "Wed", "Fri"],
        "2": ["Mon", "Tue", "Thu", "Sat"],
        "3": ["Mon", "Tue", "Wed", "Fri", "Sat"],
        "4": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    }
    return mapping.get(str(days_value or "").strip(), mapping["2"])


def _video_duration_label(time_value: str) -> str:
    mapping = {
        "1": "20-25 min",
        "2": "30-40 min",
        "3": "45-60 min",
    }
    return mapping.get(str(time_value or "").strip(), "30-40 min")


def _video_workout_duration(time_value: str, item_index: int) -> str:
    if str(time_value or "") == "1":
        values = ["18 Min.", "20 Min.", "22 Min."]
    elif str(time_value or "") == "3":
        values = ["18 Min.", "22 Min.", "28 Min."]
    else:
        values = ["15 Min.", "20 Min.", "25 Min."]
    return values[item_index % len(values)]


def _video_goal_categories(goal: str) -> list[str]:
    mapping = {
        "1": ["Upper Body", "Lower Body", "Full Body"],
        "2": ["HIIT", "Core", "Full Body"],
        "3": ["Cardio", "Conditioning", "Mobility"],
        "4": ["Mobility", "Stretch", "Core"],
    }
    return mapping.get(str(goal or "").strip(), ["Full Body", "Core", "Mobility"])


def _safe_int(value: str | int | None, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))
