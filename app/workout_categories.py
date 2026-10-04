WORKOUT_CATEGORY_OPTIONS = (
    "Upper Body",
    "Core",
    "Strength",
    "Sport in Schwangerschaft",
    "Cardio",
    "Lower Body",
    "Full Body",
    "Pilates",
    "Yoga",
    "HIIT",
)

DEFAULT_WORKOUT_CATEGORY = WORKOUT_CATEGORY_OPTIONS[0]


def normalize_workout_categories(tag: str | None = None, purposes: list[str] | None = None) -> list[str]:
    candidates = list(purposes or [])
    if tag:
        candidates.append(tag)
    normalized: list[str] = []
    for item in candidates:
        raw = str(item or "").strip()
        canonical = next((option for option in WORKOUT_CATEGORY_OPTIONS if option.lower() == raw.lower()), "")
        if canonical and canonical not in normalized:
            normalized.append(canonical)
    return normalized


def normalize_workout_category(value: object, fallback: str = DEFAULT_WORKOUT_CATEGORY) -> str:
    return (normalize_workout_categories(str(value or ""), []) or [fallback])[0]
