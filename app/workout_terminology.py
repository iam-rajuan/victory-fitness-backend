"""Canonical workout and exercise terminology module.

Enforces that workout titles, session titles, exercise names, and core fitness terminology
remain in canonical English regardless of the user's language (including German).
"""

from typing import Any

CANONICAL_EXERCISE_NAMES = [
    # Chest / Push
    "Bench Press",
    "Incline Dumbbell Press",
    "Dumbbell Floor Press",
    "Dumbbell Chest Flye",
    "Push-Up",
    "Diamond Push-Up",
    "Pike Push-Up",
    "Chair / Bench Dips",
    # Shoulders
    "Overhead Press",
    "Dumbbell Overhead Press",
    "Shoulder Press",
    "Lateral Raise",
    "Dumbbell Lateral Raise",
    "Cable Face Pull",
    # Back / Pull
    "Pull-Up",
    "Lat Pulldown",
    "Inverted Bodyweight Row",
    "Cable Row",
    "Dumbbell Row",
    "Weighted Row",
    "Chest-Supported Row",
    # Legs - Quads & Squats
    "Barbell Back Squat",
    "Bodyweight Tempo Squat",
    "Jump Squat",
    "Dumbbell Goblet Squat",
    "Dumbbell Bulgarian Split Squat",
    "Leg Press",
    "Leg Extension",
    "Reverse Lunge",
    "Walking Lunge",
    "Calf Raise",
    # Legs - Posterior Chain & Hinges
    "Deadlift",
    "Romanian Deadlift",
    "Dumbbell Romanian Deadlift",
    "Hamstring Curl",
    "Hip Thrust",
    "Glute Bridge",
    "Single-Leg Glute Bridge",
    # Arms
    "Dumbbell Curl",
    "Biceps Curl",
    "Hammer Curl",
    "Cable Curl",
    "Dumbbell Skull Crusher",
    "Triceps Pushdown",
    "Triceps Rope Pushdown",
    # Core
    "Plank",
    "Hollow Hold",
    "Mountain Climber",
    "Russian Twist",
    "Cable Crunch",
    "Farmer Carry",
]

CANONICAL_WORKOUT_TITLES = [
    "Upper Body",
    "Lower Body",
    "Full Body",
    "Push",
    "Pull",
    "Legs",
    "Upper Body Strength",
    "Lower Body Strength",
    "Full Body Strength",
    "Push Strength",
    "Pull Strength",
    "Leg Strength",
    "Upper Body Hypertrophy",
    "Lower Body Hypertrophy",
    "Full Body Hypertrophy",
    "Push Hypertrophy",
    "Pull Hypertrophy",
    "Upper Body Power",
    "Lower Body Power",
    "Full Body Power",
    "Upper Body Volume",
    "Lower Body Volume",
    "Full Body Volume",
    "Core",
    "Strength",
    "Cardio",
    "HIIT",
    "Pilates",
    "Yoga",
    "Mobility",
]

# German translated terms mapped directly back to Canonical English
GERMAN_TO_ENGLISH_MAP: dict[str, str] = {
    # Workouts & splits
    "oberkörper": "Upper Body",
    "unterkörper": "Lower Body",
    "ganzkörper": "Full Body",
    "drücken": "Push",
    "ziehen": "Pull",
    "beine": "Legs",
    "oberkörper kraft": "Upper Body Strength",
    "unterkörper kraft": "Lower Body Strength",
    "ganzkörper kraft": "Full Body Strength",
    "oberkörper hypertrophie": "Upper Body Hypertrophy",
    "unterkörper hypertrophie": "Lower Body Hypertrophy",
    "ganzkörper hypertrophie": "Full Body Hypertrophy",
    "oberkörper power": "Upper Body Power",
    "unterkörper power": "Lower Body Power",
    "ganzkörper power": "Full Body Power",
    "oberkörper volumen": "Upper Body Volume",
    "unterkörper volumen": "Lower Body Volume",
    # Exercises
    "bankdrücken": "Bench Press",
    "latzug": "Lat Pulldown",
    "lat-zug": "Lat Pulldown",
    "latziehen": "Lat Pulldown",
    "kreuzheben": "Deadlift",
    "rumänisches kreuzheben": "Romanian Deadlift",
    "kniebeuge": "Barbell Back Squat",
    "kniebeugen": "Barbell Back Squat",
    "langhantel kniebeuge": "Barbell Back Squat",
    "langhantel-kniebeuge": "Barbell Back Squat",
    "langhantel kniebeugen": "Barbell Back Squat",
    "tempo kniebeuge": "Bodyweight Tempo Squat",
    "tempo kniebeugen": "Bodyweight Tempo Squat",
    "sprung kniebeuge": "Jump Squat",
    "sprung-kniebeugen": "Jump Squat",
    "liegestütz": "Push-Up",
    "liegestütze": "Push-Up",
    "klimmzug": "Pull-Up",
    "klimmzüge": "Pull-Up",
    "schulterdrücken": "Shoulder Press",
    "überkopfdrücken": "Overhead Press",
    "kurzhantel überkopfdrücken": "Dumbbell Overhead Press",
    "seitheben": "Lateral Raise",
    "kurzhantel seitheben": "Dumbbell Lateral Raise",
    "bizepscurl": "Biceps Curl",
    "bizepscurls": "Biceps Curl",
    "kurzhantel curl": "Dumbbell Curl",
    "kurzhantel curls": "Dumbbell Curl",
    "trizepsdrücken": "Triceps Pushdown",
    "trizeps pushdown": "Triceps Pushdown",
    "trizeps seildrücken": "Triceps Rope Pushdown",
    "wadenheben": "Calf Raise",
    "beinbeuger": "Hamstring Curl",
    "beinstrecker": "Leg Extension",
    "beinpresse": "Leg Press",
    "beckenheben": "Glute Bridge",
    "gesäßbrücke": "Glute Bridge",
    "hüftstoß": "Hip Thrust",
    "rudern": "Row",
    "kurzhantel rudern": "Dumbbell Row",
    "kabelrudern": "Cable Row",
    "vorgebeugtes rudern": "Weighted Row",
    "bergsteiger": "Mountain Climber",
    "russische drehung": "Russian Twist",
    "bauchpresse": "Cable Crunch",
    "unterarmstütz": "Plank",
    "ausfallschritt": "Reverse Lunge",
    "ausfallschritte": "Reverse Lunge",
    "gehende ausfallschritte": "Walking Lunge",
    "kurzhantel bankdrücken": "Incline Dumbbell Press",
    "schrägbankdrücken": "Incline Dumbbell Press",
    "fliegende": "Dumbbell Chest Flye",
    "brustpresse": "Dumbbell Floor Press",
}

_EXACT_ENGLISH_SET = {item.strip().lower(): item for item in CANONICAL_EXERCISE_NAMES + CANONICAL_WORKOUT_TITLES}


def is_canonical_fitness_text(text: str) -> bool:
    cleaned = str(text or "").strip().lower()
    if not cleaned:
        return False
    if cleaned in _EXACT_ENGLISH_SET:
        return True
    if cleaned in GERMAN_TO_ENGLISH_MAP:
        return True
    import re
    # Check for known exercise terms in English with word boundaries
    known_fitness_patterns = [
        r"\bbench\s+press\b", r"\bsquat[s]?\b", r"\bdeadlift[s]?\b", r"\bpulldown[s]?\b",
        r"\bpush[\s-]?up[s]?\b", r"\bpull[\s-]?up[s]?\b", r"\boverhead\s+press\b",
        r"\blateral\s+raise[s]?\b", r"\bcurl[s]?\b", r"\brow[s]?\b", r"\blunge[s]?\b",
        r"\bplank[s]?\b", r"\bdip[s]?\b", r"\bhip\s+thrust[s]?\b", r"\bglute\s+bridge[s]?\b",
        r"\bcalf\s+raise[s]?\b", r"\bupper\s+body\b", r"\blower\s+body\b",
        r"\bfull\s+body\b", r"\bhypertrophy\b",
    ]
    return any(re.search(pat, cleaned) for pat in known_fitness_patterns)


def canonicalize_fitness_text(text: str) -> str:
    original = str(text or "").strip()
    if not original:
        return ""
    cleaned = original.lower()
    # 1. Exact German -> English mapping
    if cleaned in GERMAN_TO_ENGLISH_MAP:
        return GERMAN_TO_ENGLISH_MAP[cleaned]
    # 2. Exact Canonical English casing match
    if cleaned in _EXACT_ENGLISH_SET:
        return _EXACT_ENGLISH_SET[cleaned]
    # 3. Handle German compound word patterns
    for ger, eng in GERMAN_TO_ENGLISH_MAP.items():
        if ger in cleaned:
            # Replace German occurrence with English
            import re
            pattern = re.compile(re.escape(ger), re.IGNORECASE)
            return pattern.sub(eng, original).strip()
    return original


def canonicalize_strength_plan_dict(plan: dict[str, Any]) -> dict[str, Any]:
    """Sanitizes any AI-generated or stored plan dict so that day titles, section titles, and exercise names are canonical English."""
    if not isinstance(plan, dict):
        return plan

    days = plan.get("days")
    if isinstance(days, list):
        for day in days:
            if isinstance(day, dict):
                if "title" in day:
                    day["title"] = canonicalize_fitness_text(str(day.get("title") or ""))
                exercises = day.get("exercises")
                if isinstance(exercises, list):
                    for ex in exercises:
                        if isinstance(ex, dict) and "name" in ex:
                            ex["name"] = canonicalize_fitness_text(str(ex.get("name") or ""))
                sections = day.get("sections")
                if isinstance(sections, list):
                    for sec in sections:
                        if isinstance(sec, dict):
                            if "title" in sec:
                                sec["title"] = canonicalize_fitness_text(str(sec.get("title") or ""))
                            sec_exercises = sec.get("exercises")
                            if isinstance(sec_exercises, list):
                                for ex in sec_exercises:
                                    if isinstance(ex, dict) and "name" in ex:
                                        ex["name"] = canonicalize_fitness_text(str(ex.get("name") or ""))

    return plan
