import math
from dataclasses import dataclass


DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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


def generate_strength_workout_plan(input_data: StrengthWorkoutPlanInput) -> dict:
    frequency = _safe_int(input_data.frequency, 4, minimum=3, maximum=5)
    preferred_days = _normalize_preferred_days(input_data.days)
    active_days = preferred_days[:frequency] if len(preferred_days) >= frequency else DAY_ORDER[:frequency]
    title_cycle = _strength_title_cycle(input_data.split, input_data.goal)
    exercise_pool = _strength_exercise_pool(input_data.goal, input_data.equipment)
    est_time = _strength_time_label(frequency, input_data.level)
    intensity = _strength_intensity_label(input_data.goal, input_data.level)

    days: list[dict] = []
    for index, day_name in enumerate(DAY_ORDER):
        if day_name not in active_days:
            days.append(
                {
                    "day": day_name,
                    "title": "Recovery / Mobility",
                    "est_time": "20 min",
                    "volume": "Light",
                    "intensity": "Recovery",
                    "exercises": [
                        {
                            "id": f"{day_name.lower()}-mobility-1",
                            "name": "Mobility Flow",
                            "sets": 2,
                            "reps": "5-8 min",
                            "rest": "30s",
                            "weight": "Bodyweight",
                            "type": "Recovery",
                        },
                        {
                            "id": f"{day_name.lower()}-mobility-2",
                            "name": "Brisk Walk",
                            "sets": 1,
                            "reps": "15-20 min",
                            "rest": "-",
                            "weight": "-",
                            "type": "Recovery",
                        },
                    ],
                }
            )
            continue

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


def _normalize_preferred_days(days: list[str]) -> list[str]:
    normalized = []
    for day in days:
        key = str(day or "").strip()[:3].title()
        if key in DAY_ORDER and key not in normalized:
            normalized.append(key)
    return normalized


def _strength_title_cycle(split: str, goal: str) -> list[str]:
    split_map = {
        "1": ["Full Body Strength", "Full Body Hypertrophy", "Full Body Power"],
        "2": ["Upper Body Strength", "Lower Body Strength", "Upper Body Volume", "Lower Body Power"],
        "3": ["Push Strength", "Pull Strength", "Leg Strength", "Push Hypertrophy", "Pull Hypertrophy"],
    }
    titles = split_map.get(str(split or "").strip(), split_map["2"])
    if str(goal or "") == "3":
        return [title.replace("Strength", "Power") for title in titles]
    return titles


def _strength_exercise_pool(goal: str, equipment: list[str]) -> list[list[dict]]:
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

    if str(goal or "") == "2":
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
    if str(goal or "") == "2":
        return "RPE 8.5"
    if str(goal or "") == "3":
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
