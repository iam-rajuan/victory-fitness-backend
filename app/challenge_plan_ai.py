import json
import re
from dataclasses import dataclass
from urllib import error, request

from .config import settings


OPENAI_REQUEST_TIMEOUT_SECONDS = 45


@dataclass
class ChallengePlanGenerationInput:
    title: str
    description: str
    category: str
    difficulty: str
    duration_days: int


def generate_challenge_plan(input_data: ChallengePlanGenerationInput) -> dict:
    if settings.openai_api_key:
        try:
            candidate = _openai_challenge_plan_json(input_data)
            if _looks_like_plan(candidate):
                return candidate
        except RuntimeError:
            pass

    if settings.anthropic_api_key:
        try:
            candidate = _anthropic_challenge_plan_json(input_data)
            if _looks_like_plan(candidate):
                return candidate
        except RuntimeError:
            pass

    return _build_fallback_plan(input_data)


def _looks_like_plan(value: dict | None) -> bool:
    if not isinstance(value, dict):
        return False
    plan_days = value.get("plan_days")
    return isinstance(plan_days, list) and len(plan_days) > 0


def _challenge_plan_prompt(input_data: ChallengePlanGenerationInput) -> str:
    return (
        "Create a structured fitness challenge plan.\n"
        f"Title: {input_data.title}\n"
        f"Description: {input_data.description}\n"
        f"Category: {input_data.category}\n"
        f"Difficulty: {input_data.difficulty}\n"
        f"Duration days: {input_data.duration_days}\n\n"
        "Requirements:\n"
        "- Return one JSON object only.\n"
        "- Include exactly one plan day per calendar day.\n"
        "- Every day needs a title, focus, notes, and 2-4 sections.\n"
        "- Every section needs 2-5 exercises.\n"
        "- Exercise details must include sets/reps/time in plain text.\n"
        "- Vary intensity across the week and include recovery where appropriate.\n"
        "- Keep the plan realistic for the specified difficulty.\n"
        "- Use stable machine-friendly ids for sections and exercises.\n"
    )


def _challenge_plan_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "plan_days"],
        "properties": {
            "summary": {"type": "string"},
            "plan_days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["day_number", "title", "focus", "notes", "sections"],
                    "properties": {
                        "day_number": {"type": "integer"},
                        "title": {"type": "string"},
                        "focus": {"type": "string"},
                        "notes": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "title", "description", "estimated_minutes", "exercises"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "estimated_minutes": {"type": "integer"},
                                    "exercises": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["id", "name", "details", "notes"],
                                            "properties": {
                                                "id": {"type": "string"},
                                                "name": {"type": "string"},
                                                "details": {"type": "string"},
                                                "notes": {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _openai_challenge_plan_json(input_data: ChallengePlanGenerationInput) -> dict:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You generate structured fitness challenge plans. "
                    "Return exactly one valid JSON object that matches the required schema. "
                    "Do not include markdown fences or extra text."
                ),
            },
            {
                "role": "user",
                "content": _challenge_plan_prompt(input_data),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 12000,
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI challenge plan request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI challenge plan request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI challenge plan request failed: {exc.reason}") from exc

    try:
        content = data["choices"][0]["message"]["content"].strip()
        return json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError("OpenAI challenge plan response was missing valid JSON") from exc


def _anthropic_challenge_plan_json(input_data: ChallengePlanGenerationInput) -> dict:
    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 12000,
        "system": (
            "You generate structured fitness challenge plans. "
            "Return exactly one valid JSON object that matches the provided schema. "
            "Do not include markdown fences or extra text.\n"
            f"Schema: {json.dumps(_challenge_plan_schema(), ensure_ascii=False)}"
        ),
        "messages": [
            {
                "role": "user",
                "content": _challenge_plan_prompt(input_data),
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("Anthropic challenge plan request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic challenge plan request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic challenge plan request failed: {exc.reason}") from exc

    try:
        content = "".join(
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
        return json.loads(content)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Anthropic challenge plan response was missing valid JSON") from exc


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:60] or fallback


def _build_fallback_plan(input_data: ChallengePlanGenerationInput) -> dict:
    category = input_data.category.strip().lower()
    difficulty = input_data.difficulty.strip().upper()
    days: list[dict] = []

    strength_library = [
        ("Warm-Up", ["Jumping jacks", "World's greatest stretch", "Glute bridge"], "2 rounds, controlled pace"),
        ("Main Strength", ["Goblet squat", "Push-up", "Bent-over row"], "3-4 sets x 8-12 reps"),
        ("Conditioning", ["Mountain climbers", "High knees", "Burpees"], "30-40 sec work x 3 rounds"),
        ("Recovery", ["Walk", "Hip opener stretch", "Box breathing"], "10-15 minutes easy pace"),
    ]
    cardio_library = [
        ("Warm-Up", ["Brisk walk", "Leg swings", "Arm circles"], "5-8 minutes"),
        ("Intervals", ["Jog", "Fast run", "Walk recovery"], "1 min hard / 2 min easy x 6-8 rounds"),
        ("Endurance", ["Steady run", "Bike", "Row"], "20-40 minutes moderate pace"),
        ("Recovery", ["Easy walk", "Calf stretch", "Hamstring stretch"], "10-15 minutes"),
    ]
    mindfulness_library = [
        ("Centering", ["Box breathing", "Neck release", "Cat-cow"], "5-8 minutes"),
        ("Mobility", ["Thoracic rotation", "Hip flow", "Ankle mobility"], "2-3 sets x 45 sec"),
        ("Reflection", ["Journal prompt", "Gratitude list", "Body scan"], "10 minutes"),
        ("Recovery", ["Slow walk", "Guided stretch", "Breath downshift"], "10-15 minutes"),
    ]
    nutrition_library = [
        ("Planning", ["Hydration target", "Protein check", "Meal prep block"], "20-30 minutes"),
        ("Action", ["Balanced breakfast", "Vegetable serving", "Snack prep"], "Complete today"),
        ("Education", ["Label check", "Portion review", "Mindful eating pause"], "10-15 minutes"),
        ("Recovery", ["Evening tea", "Kitchen reset", "Sleep routine"], "10 minutes"),
    ]

    library_map = {
        "strength": strength_library,
        "cardio": cardio_library,
        "mindfulness": mindfulness_library,
        "nutrition": nutrition_library,
    }
    library = library_map.get(category, strength_library)
    week_focuses = [
        "Build the base",
        "Increase consistency",
        "Progress the workload",
        "Finish with control",
        "Lock in the habit",
    ]
    intensity_sets = {
        "BEGINNER": [0, 1, 3],
        "INTERMEDIATE": [0, 1, 2],
        "ADVANCED": [0, 1, 2],
    }

    for day_number in range(1, input_data.duration_days + 1):
        week_index = min((day_number - 1) // 7, len(week_focuses) - 1)
        section_indexes = intensity_sets.get(difficulty, [0, 1, 3])
        if day_number % 7 == 0:
            section_indexes = [0, 3]
        elif day_number % 5 == 0 and difficulty != "BEGINNER":
            section_indexes = [0, 2, 3]

        sections: list[dict] = []
        for section_position, library_index in enumerate(section_indexes, start=1):
            section_title, exercise_names, default_details = library[library_index]
            section_id = _slugify(f"day-{day_number}-{section_title}", f"day-{day_number}-section-{section_position}")
            exercises = []
            for exercise_index, exercise_name in enumerate(exercise_names, start=1):
                exercise_id = _slugify(
                    f"{section_id}-{exercise_name}",
                    f"{section_id}-exercise-{exercise_index}",
                )
                notes = ""
                if section_title == "Main Strength":
                    notes = "Keep 1-2 reps in reserve and focus on form."
                elif section_title == "Intervals":
                    notes = "Recover fully enough to keep quality on the next interval."
                elif section_title == "Recovery":
                    notes = "This is intentionally low stress. Keep the habit without forcing intensity."
                exercises.append(
                    {
                        "id": exercise_id,
                        "name": exercise_name,
                        "details": default_details,
                        "notes": notes,
                    }
                )
            sections.append(
                {
                    "id": section_id,
                    "title": section_title,
                    "description": f"{section_title} block for day {day_number}.",
                    "estimated_minutes": 10 if section_title in {"Warm-Up", "Recovery", "Centering", "Reflection"} else 20,
                    "exercises": exercises,
                }
            )

        days.append(
            {
                "day_number": day_number,
                "title": f"Day {day_number} - {week_focuses[week_index]}",
                "focus": f"{input_data.category} focus with {input_data.difficulty.lower()} pacing.",
                "notes": (
                    "Stay consistent, adjust intensity if soreness is high, and log progress in challenge chat."
                ),
                "sections": sections,
            }
        )

    return {
        "summary": (
            f"{input_data.duration_days}-day {input_data.category.lower()} challenge for "
            f"{input_data.difficulty.lower()} members. Each day includes multiple sections and exercises."
        ),
        "plan_days": days,
    }
