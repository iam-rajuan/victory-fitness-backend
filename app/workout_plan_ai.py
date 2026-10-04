import json
import re
from dataclasses import dataclass, field
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
    muscle_group: str = ""
    duration_minutes: str = ""
    language: str = "en"
    injury_flags: list[str] = field(default_factory=list)
    custom_notes: str = ""


@dataclass
class VideoWorkoutPlanInput:
    goal: str
    level: str
    days: str
    duration: str
    time: str
    notes: str
    equipment: str
    language: str = "en"


KNEE_AGGRAVATING_TERMS = [
    "squat", "lunge", "leg press", "leg extension", "step-up", "step up",
    "box jump", "jump squat", "pistol", "split squat", "bulgarian",
]
SHOULDER_AGGRAVATING_TERMS = [
    "overhead press", "military press", "incline press", "upright row",
    "arnold press", "behind neck", "dip",
]
LOWER_BACK_AGGRAVATING_TERMS = [
    "back squat", "good morning", "heavy deadlift", "deficit deadlift",
    "barbell row", "pendlay row",
]

EXERCISE_CATALOG = [
    {"name": "Bodyweight Tempo Squat", "muscles": ["legs", "quads", "glutes"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Reverse Lunge", "muscles": ["legs", "quads", "glutes"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Walking Lunge", "muscles": ["legs", "quads", "glutes"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Single-Leg Glute Bridge", "muscles": ["legs", "glutes", "hamstrings"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Jump Squat", "muscles": ["legs", "quads", "glutes"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Push-Up", "muscles": ["chest", "triceps", "shoulders"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Pike Push-Up", "muscles": ["shoulders", "triceps"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Diamond Push-Up", "muscles": ["chest", "triceps"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Inverted Bodyweight Row", "muscles": ["back", "biceps"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Chair / Bench Dips", "muscles": ["triceps", "chest"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Plank", "muscles": ["core"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Core"},
    {"name": "Hollow Hold", "muscles": ["core"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Core"},
    {"name": "Mountain Climber", "muscles": ["core", "conditioning"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Core"},
    {"name": "Russian Twist", "muscles": ["core"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Core"},
    {"name": "Dumbbell Goblet Squat", "muscles": ["legs", "quads", "glutes"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Dumbbell Bulgarian Split Squat", "muscles": ["legs", "quads", "glutes"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Dumbbell Romanian Deadlift", "muscles": ["legs", "hamstrings", "glutes"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Dumbbell Floor Press", "muscles": ["chest", "triceps"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Dumbbell Chest Flye", "muscles": ["chest"], "equipment": ["dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Dumbbell Row", "muscles": ["back", "biceps"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Dumbbell Overhead Press", "muscles": ["shoulders", "triceps"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Dumbbell Lateral Raise", "muscles": ["shoulders"], "equipment": ["dumbbells_only", "full_gym"], "type": "Isolation"},
    {"name": "Dumbbell Curl", "muscles": ["biceps", "arms"], "equipment": ["dumbbells_only", "full_gym"], "type": "Isolation"},
    {"name": "Dumbbell Skull Crusher", "muscles": ["triceps", "arms"], "equipment": ["dumbbells_only", "full_gym"], "type": "Isolation"},
    {"name": "Barbell Back Squat", "muscles": ["legs", "quads", "glutes"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Romanian Deadlift", "muscles": ["legs", "hamstrings", "glutes"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Deadlift", "muscles": ["legs", "back", "hamstrings", "glutes"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Leg Press", "muscles": ["legs", "quads", "glutes"], "equipment": ["full_gym"], "type": "Accessory"},
    {"name": "Leg Extension", "muscles": ["legs", "quads"], "equipment": ["full_gym"], "type": "Isolation"},
    {"name": "Hamstring Curl", "muscles": ["legs", "hamstrings"], "equipment": ["full_gym"], "type": "Isolation"},
    {"name": "Calf Raise", "muscles": ["legs", "calves"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Isolation"},
    {"name": "Hip Thrust", "muscles": ["legs", "glutes", "hamstrings"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Glute Bridge", "muscles": ["legs", "glutes"], "equipment": ["bodyweight_only", "dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Bench Press", "muscles": ["chest", "triceps"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Incline Dumbbell Press", "muscles": ["chest", "shoulders", "triceps"], "equipment": ["dumbbells_only", "full_gym"], "type": "Accessory"},
    {"name": "Cable Row", "muscles": ["back", "biceps"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Weighted Row", "muscles": ["back", "biceps"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Chest-Supported Row", "muscles": ["back", "biceps"], "equipment": ["dumbbells_only", "full_gym"], "type": "Compound"},
    {"name": "Pull-Up", "muscles": ["back", "biceps"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Overhead Press", "muscles": ["shoulders", "triceps"], "equipment": ["full_gym"], "type": "Compound"},
    {"name": "Lateral Raise", "muscles": ["shoulders"], "equipment": ["dumbbells_only", "full_gym"], "type": "Isolation"},
    {"name": "Cable Face Pull", "muscles": ["shoulders", "back"], "equipment": ["full_gym"], "type": "Accessory"},
    {"name": "Cable Crunch", "muscles": ["core"], "equipment": ["full_gym"], "type": "Core"},
    {"name": "Farmer Carry", "muscles": ["core", "traps"], "equipment": ["dumbbells_only", "full_gym"], "type": "Accessory"},
]

EXERCISE_BY_NAME = {str(item["name"]).lower(): item for item in EXERCISE_CATALOG}


def _replacement_for_injury(exercise_name: str, injury_flags: list[str]) -> str | None:
    name = str(exercise_name or "").lower()
    flags = [str(flag).lower() for flag in injury_flags if str(flag).strip()]
    if "knee" in flags and any(term in name for term in KNEE_AGGRAVATING_TERMS):
        return "Romanian Deadlift" if any(term in name for term in ["squat", "press", "step", "jump"]) else "Glute Bridge"
    if "shoulder" in flags and any(term in name for term in SHOULDER_AGGRAVATING_TERMS):
        return "Cable Face Pull"
    if "lower_back" in flags and any(term in name for term in LOWER_BACK_AGGRAVATING_TERMS):
        return "Chest-Supported Row"
    return None


def sanitize_workout_plan_for_injuries(plan: dict, injury_flags: list[str]) -> tuple[dict, bool]:
    if not plan or not isinstance(plan, dict):
        return plan, False
    flags = [str(f).lower() for f in injury_flags if str(f).strip()]
    if not flags:
        return plan, False

    modified = False

    def sanitize_exercises(exercises: list) -> list:
        nonlocal modified
        sanitized = []
        for ex in exercises or []:
            if not isinstance(ex, dict):
                sanitized.append(ex)
                continue
            replacement = _replacement_for_injury(str(ex.get("name") or ""), flags)
            if replacement:
                ex = {**ex, "name": replacement}
                if "type" in ex:
                    ex["type"] = "Compound" if replacement in {"Romanian Deadlift", "Glute Bridge"} else "Accessory"
                modified = True
            sanitized.append(ex)
        return sanitized

    if isinstance(plan.get("exercises"), list):
        plan["exercises"] = sanitize_exercises(plan.get("exercises") or [])
    for section in plan.get("sections", []) or []:
        if isinstance(section, dict) and isinstance(section.get("exercises"), list):
            section["exercises"] = sanitize_exercises(section.get("exercises") or [])

    for day in plan.get("days", []) or []:
        if not isinstance(day, dict):
            continue
        if isinstance(day.get("exercises"), list):
            day["exercises"] = sanitize_exercises(day.get("exercises") or [])
        for section in day.get("sections", []) or []:
            if isinstance(section, dict) and isinstance(section.get("exercises"), list):
                section["exercises"] = sanitize_exercises(section.get("exercises") or [])

    return plan, modified


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


def _sanitize_plan_injuries(plan: dict, injury_flags: list[str]) -> dict:
    sanitized, _ = sanitize_workout_plan_for_injuries(plan, injury_flags)
    return sanitized


def generate_strength_workout_plan(input_data: StrengthWorkoutPlanInput) -> dict:
    ai_plan = _generate_strength_workout_plan_with_ai(input_data)
    if _looks_like_strength_plan(ai_plan):
        sanitized = _sanitize_plan_injuries(ai_plan, getattr(input_data, "injury_flags", []))
        return _validate_and_correct_strength_plan(sanitized, input_data)

    return _build_strength_workout_plan(input_data)


def _build_strength_workout_plan(input_data: StrengthWorkoutPlanInput) -> dict:
    frequency = _safe_int(input_data.frequency, 4, minimum=1, maximum=7)
    preferred_days = _normalize_preferred_days(input_data.days)
    active_days = preferred_days[:frequency] if preferred_days else DAY_ORDER[:frequency]
    title_cycle = _strength_title_cycle(input_data.split, input_data.goal, input_data.muscle_group)
    exercise_pool = _strength_exercise_pool(input_data.goal, input_data.equipment, input_data.muscle_group, input_data.duration_minutes, input_data.level)

    frequency = _safe_int(input_data.frequency, 4, minimum=1, maximum=7)

    injury_list = [str(item).lower() for item in getattr(input_data, "injury_flags", []) if str(item).strip()]
    if "knee" in injury_list:
        safe_pool = []
        for day_exercises in exercise_pool:
            safe_day = []
            for ex in day_exercises:
                ex_name = ex["name"]
                alt_name = _replacement_for_injury(ex_name, injury_list)
                if alt_name:
                    safe_day.append({**ex, "name": alt_name, "type": "Compound" if "Deadlift" in alt_name else "Isolation"})
                else:
                    safe_day.append(ex)
            safe_pool.append(safe_day)
        exercise_pool = safe_pool

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
        exercises = _fit_exercises_to_duration(exercises, input_data.duration_minutes)

        working_sets = sum(int(item["sets"]) for item in exercises)
        average_weight = max(_safe_int(input_data.weight, 75, minimum=40, maximum=180), 40)
        equip_type = _classify_equipment(input_data.equipment)
        if equip_type == "bodyweight_only":
            volume_value = working_sets * 12 # total bodyweight reps
            volume_label = f"{volume_value} BW Reps"
        else:
            volume_value = working_sets * average_weight * 8
            volume_label = f"{volume_value:,} kg"

        day_est_time = _calculate_day_est_time(exercises)
        days.append(
            {
                "day": day_name,
                "title": session_title,
                "est_time": day_est_time,
                "volume": volume_label,
                "intensity": intensity,
                "exercises": exercises,
            }
        )

    focus = _normalize_muscle_group(input_data.muscle_group)
    focus_label = "full-body" if focus == "full_body" else focus.replace("_", " ")
    duration = _requested_duration_minutes(input_data.duration_minutes)
    duration_text = f" around {duration} minutes per session" if duration else ""
    summary = (
        f"{input_data.level or 'Intermediate'} {input_data.goal or 'strength'} plan focused on {focus_label}, using a "
        f"{input_data.split or 'balanced'} split with {frequency} main training days{duration_text}."
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
            {"id": "fallback-1", "title": "Bodyweight Full Body", "tag": "Full Body", "thumbnail": ""},
            {"id": "fallback-2", "title": "Core Pilates Flow", "tag": "Pilates", "thumbnail": ""},
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
    lang = getattr(input_data, "language", "en") or "en"
    lang_line = f"- Language: Write the summary, day titles, and exercise notes in {lang}. Keep day keys as Mon, Tue, etc.\n" if lang not in ("en", "en-gh") else ""
    injury_list = [str(item).lower() for item in getattr(input_data, "injury_flags", []) if str(item).strip()]
    injury_line = ""
    if "knee" in injury_list:
        injury_line = (
            "- CRITICAL INJURY GUARDRAIL: User has active KNEE PAIN. You MUST NOT include squats, lunges, leg press, leg extensions, step-ups, split squats, box jumps, jump squats, or pistol squats. "
            "Prescribe only knee-safe posterior chain movements (e.g. Romanian Deadlift, Hip Thrust, Glute Bridge, Hamstring Curls, Calf Raises) or core/upper movements.\n"
        )
    elif injury_list:
        injury_line = f"- CRITICAL INJURY GUARDRAIL: Strictly avoid exercises that aggravate user's active pain flags: {', '.join(injury_list)}.\n"
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
        "- Split, goal, experience level, selected muscle group, available duration, equipment, and frequency must visibly affect the plan.\n"
        "- If custom_notes are present, treat them as the user's direct plan instructions and reflect them unless they conflict with injury, duration, or equipment constraints.\n"
        "- STRICT MUSCLE GROUP CONSTRAINT: If muscle_group is not full body, every exercise must train that selected muscle group or a directly supporting sub-muscle. Do not include unrelated chest, back, shoulder, or arm work in a legs-focused plan.\n"
        "- STRICT DURATION CONSTRAINT: Estimate each session inside the requested duration window by adjusting exercise count, sets, and rest. Do not return longer sessions than requested.\n"
        "- STRICT EQUIPMENT CONSTRAINT: If equipment includes 'no equipment', 'bodyweight', or 'outdoors', you MUST ONLY prescribe calisthenics/bodyweight exercises. NEVER include Barbell, Dumbbell, Cable, Machine, or Leg Press lifts. Weight must be 'Bodyweight'.\n"
        "- If equipment is 'home gym' or 'dumbbells', use only dumbbells and bodyweight. NEVER prescribe barbells or cable machines.\n"
        f"{injury_line}"
        "- Keep exercise ids stable and machine-friendly.\n"
        f"{lang_line}"
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


def _strength_title_cycle(split: str, goal: str, muscle_group: str = "") -> list[str]:
    focus = _normalize_muscle_group(muscle_group)
    if focus != "full_body":
        label = focus.replace("_", " ").title()
        normalized_goal = _normalize_strength_goal(goal)
        if normalized_goal == "POWER & SPEED":
            return [f"{label} Power", f"{label} Speed", f"{label} Athletic Strength"]
        if normalized_goal == "PURE STRENGTH":
            return [f"{label} Strength", f"{label} Heavy Strength", f"{label} Strength Practice"]
        if normalized_goal == "BODY RECOMP":
            return [f"{label} Recomp", f"{label} Conditioning Strength", f"{label} Volume"]
        return [f"{label} Hypertrophy", f"{label} Volume", f"{label} Strength"]

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


def _strength_intensity_label(goal: str, level: str) -> str:
    norm_goal = _normalize_strength_goal(goal)
    norm_level = str(level or "").strip().lower()
    if norm_goal == "PURE STRENGTH":
        return "RPE 8.5 (High)"
    if norm_goal == "POWER & SPEED":
        return "RPE 8.0 (Dynamic)"
    if norm_level == "advanced":
        return "RPE 8.5 (High)"
    if norm_level == "beginner":
        return "RPE 7.0 (Controlled)"
    return "RPE 7.5 (Moderate)"


def _classify_equipment(equipment: list[str]) -> str:
    """Classifies user equipment into: 'bodyweight_only', 'dumbbells_only', or 'full_gym'."""
    if not equipment:
        return "bodyweight_only"
    normalized_items = [str(item).strip().lower() for item in equipment if str(item).strip()]
    if not normalized_items:
        return "bodyweight_only"
    normalized_text = " ".join(normalized_items)

    has_no_equip = any(term in normalized_text for term in ["no equipment", "none", "bodyweight", "bodyweight only", "outdoors"])
    has_gym_equip = any(
        term in normalized_text
        for term in [
            "barbell",
            "squat rack",
            "squat_rack",
            "cable",
            "machine",
            "machines",
            "smith",
            "crossfit",
            "full gym",
            "gym",
        ]
    )
    has_dumbbells = any(term in normalized_text for term in ["dumbbell", "kettlebell", "home gym", "band", "bench", "pull-up", "pullup"])

    if has_no_equip and not has_gym_equip and not has_dumbbells:
        return "bodyweight_only"
    if has_gym_equip:
        return "full_gym"
    if has_dumbbells:
        return "dumbbells_only"
    return "bodyweight_only"


def _calculate_day_est_time(exercises: list[dict]) -> str:
    """Calculates realistic workout duration based on sets, rep cadence (35s), and rest seconds."""
    total_sec = 0
    for ex in exercises:
        sets = max(int(ex.get("sets") or 3), 1)
        rest_str = str(ex.get("rest") or "60s").strip().lower()
        m = re.search(r"(\d+)", rest_str)
        r_sec = int(m.group(1)) * 60 if m and "min" in rest_str else int(m.group(1)) if m else 60
        total_sec += (sets * 35) + (max(0, sets - 1) * r_sec)
    # Total minutes + 5-7 min warm-up & cool-down
    mins = max(int((total_sec + 59) // 60) + 6, 25)
    return f"{mins} min"


def _normalize_muscle_group(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()
    if not text:
        return "full_body"
    if any(term in text for term in ["full", "total", "whole", "general"]):
        return "full_body"
    if any(term in text for term in ["leg", "lower", "quad", "hamstring", "glute", "calf"]):
        return "legs"
    if "chest" in text or "pec" in text:
        return "chest"
    if any(term in text for term in ["back", "lat", "pull"]):
        return "back"
    if any(term in text for term in ["shoulder", "delt"]):
        return "shoulders"
    if any(term in text for term in ["arm", "bicep", "tricep"]):
        return "arms"
    if any(term in text for term in ["core", "abs", "abdominal"]):
        return "core"
    return text.replace(" ", "_")


def _requested_duration_minutes(value: str | int | None) -> int:
    if isinstance(value, int):
        return max(20, min(value, 90))
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        return 45
    return max(20, min(int(match.group(1)), 90))


def _target_exercise_count(duration_minutes: str | int | None) -> int:
    duration = _requested_duration_minutes(duration_minutes)
    if duration <= 30:
        return 3
    if duration <= 45:
        return 4
    if duration <= 60:
        return 5
    return 6


def _estimated_minutes_value(exercises: list[dict]) -> int:
    match = re.search(r"(\d+)", _calculate_day_est_time(exercises))
    return int(match.group(1)) if match else 45


def _fit_exercises_to_duration(exercises: list[dict], duration_minutes: str | int | None) -> list[dict]:
    duration = _requested_duration_minutes(duration_minutes)
    fitted = [dict(exercise) for exercise in exercises]
    while len(fitted) > 3 and _estimated_minutes_value(fitted) > duration + 5:
        fitted.pop()
    if _estimated_minutes_value(fitted) <= duration + 5:
        return fitted
    for exercise in fitted:
        exercise["sets"] = min(max(int(exercise.get("sets") or 3), 1), 3)
        rest_match = re.search(r"(\d+)", str(exercise.get("rest") or "60s"))
        rest_value = int(rest_match.group(1)) if rest_match else 60
        exercise["rest"] = f"{min(rest_value, 90)}s"
    return fitted


def _allowed_focuses(focus: str) -> set[str]:
    if focus == "arms":
        return {"arms", "biceps", "triceps"}
    if focus == "legs":
        return {"legs", "quads", "hamstrings", "glutes", "calves"}
    if focus == "full_body":
        return {"legs", "quads", "hamstrings", "glutes", "calves", "chest", "back", "shoulders", "arms", "biceps", "triceps", "core"}
    return {focus}


def _exercise_matches_constraints(exercise_name: str, input_data: StrengthWorkoutPlanInput) -> bool:
    metadata = EXERCISE_BY_NAME.get(str(exercise_name or "").strip().lower())
    if not metadata:
        return False
    equip_type = _classify_equipment(input_data.equipment)
    if equip_type not in metadata.get("equipment", []):
        return False
    focus = _normalize_muscle_group(input_data.muscle_group)
    if focus == "full_body":
        return True
    muscles = {str(item).lower() for item in metadata.get("muscles", [])}
    return bool(muscles & _allowed_focuses(focus))


def _catalog_candidates(goal: str, equipment: list[str], focus: str) -> list[dict]:
    equip_type = _classify_equipment(equipment)
    allowed = _allowed_focuses(focus)
    candidates = []
    for item in EXERCISE_CATALOG:
        if equip_type not in item.get("equipment", []):
            continue
        muscles = {str(value).lower() for value in item.get("muscles", [])}
        if focus != "full_body" and not muscles & allowed:
            continue
        candidates.append(item)
    candidates.sort(key=lambda item: _exercise_priority(item, equip_type, goal))
    return candidates


def _exercise_priority(item: dict, equip_type: str, goal: str) -> tuple[int, int, str]:
    name = str(item.get("name") or "").lower()
    metadata_equipment = set(item.get("equipment") or [])
    type_rank = 0 if item.get("type") == "Compound" else 1
    normalized_goal = _normalize_strength_goal(goal)
    if equip_type == "full_gym":
        if metadata_equipment == {"full_gym"}:
            equipment_rank = 0
        elif "full_gym" in metadata_equipment and "dumbbells_only" in metadata_equipment:
            equipment_rank = 1
        else:
            equipment_rank = 2
        if normalized_goal == "POWER & SPEED" and any(term in name for term in ["jump", "carry"]):
            type_rank = -1
        return (equipment_rank, type_rank, name)
    if equip_type == "dumbbells_only":
        equipment_rank = 0 if any(term in name for term in ["dumbbell", "farmer"]) else 1
        return (equipment_rank, type_rank, name)
    return (0, type_rank, name)


def _rotate_candidates(candidates: list[dict], day_index: int, count: int) -> list[dict]:
    if not candidates:
        return []
    ordered = candidates[day_index:] + candidates[:day_index]
    while len(ordered) < count:
        ordered.extend(candidates)
    return ordered[:count]


def _prescribe_exercise(source: dict, goal: str, level: str, duration_minutes: str | int | None) -> dict:
    exercise = dict(source)
    normalized_goal = _normalize_strength_goal(goal)
    normalized_level = str(level or "").strip().lower()
    duration = _requested_duration_minutes(duration_minutes)
    is_compound = str(exercise.get("type") or "").lower() == "compound"

    if normalized_goal == "PURE STRENGTH":
        sets = 5 if is_compound else 3
        reps = "3-5" if is_compound else "6-8"
        rest = "180s" if is_compound else "90s"
    elif normalized_goal == "POWER & SPEED":
        sets = 4 if is_compound else 3
        reps = "3-6 explosive" if is_compound else "8-10"
        rest = "120s" if is_compound else "75s"
    elif normalized_goal == "BODY RECOMP":
        sets = 3
        reps = "10-15"
        rest = "60s"
    else:
        sets = 4 if is_compound else 3
        reps = "8-12" if is_compound else "12-15"
        rest = "75s" if is_compound else "60s"

    if normalized_level == "beginner":
        sets = min(sets, 3)
        rest = "60s" if rest != "180s" else "120s"
    elif normalized_level == "advanced":
        sets = min(sets + (1 if is_compound and duration >= 45 else 0), 5)

    if duration <= 30:
        sets = min(sets, 3)
        rest = "90s" if normalized_goal == "PURE STRENGTH" and is_compound else "60s"

    exercise.update({"sets": sets, "reps": reps, "rest": rest})
    return exercise


def _shape_pool_for_constraints(pool: list[list[dict]], goal: str, level: str, duration_minutes: str | int | None) -> list[list[dict]]:
    target_count = _target_exercise_count(duration_minutes)
    shaped = []
    for day in pool:
        shaped.append([
            _prescribe_exercise(exercise, goal, level, duration_minutes)
            for exercise in day[:target_count]
        ])
    return shaped


def _validate_and_correct_strength_plan(plan: dict, input_data: StrengthWorkoutPlanInput) -> dict:
    frequency = _safe_int(input_data.frequency, 4, minimum=1, maximum=7)
    preferred_days = _normalize_preferred_days(input_data.days)
    active_days = preferred_days[:frequency] if preferred_days else DAY_ORDER[:frequency]
    fallback = _build_strength_workout_plan(input_data)
    fallback_by_day = {str(day.get("day")): day for day in fallback.get("days", []) if isinstance(day, dict)}
    incoming_by_day = {str(day.get("day")): day for day in plan.get("days", []) if isinstance(day, dict)}

    corrected_days = []
    for day_index, day_name in enumerate(active_days):
        incoming = dict(incoming_by_day.get(day_name) or {})
        fallback_day = dict(fallback_by_day.get(day_name) or fallback["days"][day_index % len(fallback["days"])])
        clean_exercises = []
        seen_names = set()
        for raw_exercise in incoming.get("exercises") or []:
            if not isinstance(raw_exercise, dict):
                continue
            name = str(raw_exercise.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            if not _exercise_matches_constraints(name, input_data):
                continue
            metadata = EXERCISE_BY_NAME[name.lower()]
            prescribed = _prescribe_exercise(metadata, input_data.goal, input_data.level, input_data.duration_minutes)
            clean_exercises.append(
                {
                    "id": str(raw_exercise.get("id") or f"{day_name.lower()}-{len(clean_exercises) + 1}"),
                    "name": metadata["name"],
                    "sets": prescribed["sets"],
                    "reps": prescribed["reps"],
                    "rest": prescribed["rest"],
                    "weight": _exercise_weight_label(metadata["name"], input_data),
                    "type": str(raw_exercise.get("type") or prescribed["type"]),
                }
            )
            seen_names.add(name.lower())

        target_count = _target_exercise_count(input_data.duration_minutes)
        for fallback_exercise in fallback_day.get("exercises") or []:
            if len(clean_exercises) >= target_count:
                break
            name = str(fallback_exercise.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            clean_exercises.append({**fallback_exercise, "id": f"{day_name.lower()}-{len(clean_exercises) + 1}"})
            seen_names.add(name.lower())

        corrected_day = {
            "day": day_name,
            "title": str(incoming.get("title") or fallback_day.get("title") or f"{day_name} Strength"),
            "est_time": _calculate_day_est_time(_fit_exercises_to_duration(clean_exercises, input_data.duration_minutes)),
            "volume": str(fallback_day.get("volume") or incoming.get("volume") or ""),
            "intensity": _strength_intensity_label(input_data.goal, input_data.level),
            "exercises": _fit_exercises_to_duration(clean_exercises, input_data.duration_minutes),
        }
        corrected_days.append(corrected_day)

    summary = str(plan.get("summary") or fallback.get("summary") or "").strip() or fallback["summary"]
    return {"summary": summary, "days": corrected_days}


def _strength_exercise_pool(
    goal: str,
    equipment: list[str],
    muscle_group: str = "",
    duration_minutes: str | int = "",
    level: str = "",
) -> list[list[dict]]:
    normalized_goal = _normalize_strength_goal(goal)
    equip_type = _classify_equipment(equipment)
    focus = _normalize_muscle_group(muscle_group)
    if focus != "full_body":
        candidates = _catalog_candidates(goal, equipment, focus)
        if not candidates:
            candidates = _catalog_candidates(goal, equipment, "full_body")
        target_count = _target_exercise_count(duration_minutes)
        return [
            [
                _prescribe_exercise(candidate, goal, level, duration_minutes)
                for candidate in _rotate_candidates(candidates, day_index, target_count)
            ]
            for day_index in range(5)
        ]

    # 1. BODYWEIGHT / NO EQUIPMENT SPLIT
    if equip_type == "bodyweight_only":
        return _shape_pool_for_constraints([
            # Day 1: Full Body / Lower Focus
            [
                {"name": "Bodyweight Tempo Squat", "sets": 4, "reps": "12-15", "rest": "60s", "type": "Compound"},
                {"name": "Push-Up", "sets": 4, "reps": "10-15", "rest": "60s", "type": "Compound"},
                {"name": "Reverse Lunge", "sets": 3, "reps": "10/side", "rest": "60s", "type": "Accessory"},
                {"name": "Single-Leg Glute Bridge", "sets": 3, "reps": "12/side", "rest": "45s", "type": "Accessory"},
                {"name": "Plank", "sets": 3, "reps": "45s", "rest": "45s", "type": "Core"},
            ],
            # Day 2: Upper / Calisthenics Focus
            [
                {"name": "Pike Push-Up", "sets": 4, "reps": "8-12", "rest": "75s", "type": "Compound"},
                {"name": "Inverted Bodyweight Row", "sets": 4, "reps": "10-12", "rest": "60s", "type": "Compound"},
                {"name": "Bulgarian Split Squat", "sets": 3, "reps": "10/side", "rest": "60s", "type": "Compound"},
                {"name": "Chair / Bench Dips", "sets": 3, "reps": "12-15", "rest": "60s", "type": "Accessory"},
                {"name": "Hollow Hold", "sets": 3, "reps": "30-40s", "rest": "45s", "type": "Core"},
            ],
            # Day 3: Hypertrophy & Conditioning
            [
                {"name": "Jump Squat", "sets": 4, "reps": "10-12", "rest": "60s", "type": "Compound"},
                {"name": "Diamond Push-Up", "sets": 3, "reps": "8-12", "rest": "60s", "type": "Compound"},
                {"name": "Walking Lunge", "sets": 3, "reps": "12/side", "rest": "60s", "type": "Accessory"},
                {"name": "Mountain Climber", "sets": 3, "reps": "30s", "rest": "45s", "type": "Core"},
            ],
        ], goal, level, duration_minutes)

    # 2. HOME GYM / DUMBBELLS SPLIT
    if equip_type == "dumbbells_only":
        return _shape_pool_for_constraints([
            [
                {"name": "Dumbbell Goblet Squat", "sets": 4, "reps": "10-12", "rest": "75s", "type": "Compound"},
                {"name": "Dumbbell Floor Press", "sets": 4, "reps": "8-12", "rest": "75s", "type": "Compound"},
                {"name": "Dumbbell Romanian Deadlift", "sets": 3, "reps": "10-12", "rest": "75s", "type": "Compound"},
                {"name": "Dumbbell Row", "sets": 3, "reps": "10-12", "rest": "60s", "type": "Compound"},
                {"name": "Plank", "sets": 3, "reps": "45s", "rest": "45s", "type": "Core"},
            ],
            [
                {"name": "Dumbbell Overhead Press", "sets": 4, "reps": "8-10", "rest": "75s", "type": "Compound"},
                {"name": "Dumbbell Bulgarian Split Squat", "sets": 3, "reps": "8-10/side", "rest": "75s", "type": "Compound"},
                {"name": "Dumbbell Chest Flye", "sets": 3, "reps": "10-12", "rest": "60s", "type": "Accessory"},
                {"name": "Dumbbell Lateral Raise", "sets": 3, "reps": "12-15", "rest": "45s", "type": "Isolation"},
                {"name": "Russian Twist", "sets": 3, "reps": "20 total", "rest": "45s", "type": "Core"},
            ],
        ], goal, level, duration_minutes)

    # 3. FULL GYM SPLIT
    if normalized_goal == "PURE STRENGTH":
        return _shape_pool_for_constraints([
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
        ], goal, level, duration_minutes)

    return _shape_pool_for_constraints([
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
    ], goal, level, duration_minutes)


def _exercise_weight_label(exercise_name: str, input_data: StrengthWorkoutPlanInput) -> str:
    name = exercise_name.lower()
    equip_type = _classify_equipment(input_data.equipment)

    # If bodyweight only or exercise is bodyweight
    if equip_type == "bodyweight_only" or any(bw_word in name for bw_word in [
        "push-up", "pull-up", "bodyweight", "tempo squat", "lunge", "glute bridge",
        "plank", "dip", "hold", "mountain climber", "burpee", "jump"
    ]):
        if "carry" in name or "plank" in name or "hold" in name:
            return "-"
        return "Bodyweight"

    # If dumbbells only
    if equip_type == "dumbbells_only" or "dumbbell" in name:
        if "squat" in name or "deadlift" in name or "rdl" in name:
            return "12-16kg DB"
        if "press" in name or "row" in name:
            return "10-14kg DB"
        return "6-10kg DB"

    # Full Gym Barbell / Machine Lifts
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
        "3": ["Cardio", "HIIT", "Pilates"],
        "4": ["Yoga", "Pilates", "Core"],
    }
    return mapping.get(str(goal or "").strip(), ["Full Body", "Core", "Yoga"])


def _safe_int(value: str | int | None, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))
