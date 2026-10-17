import pytest
from bson import ObjectId
from app.workout_terminology import (
    canonicalize_fitness_text,
    canonicalize_strength_plan_dict,
    is_canonical_fitness_text,
)
from app.workout_plan_ai import _strength_plan_prompt, StrengthWorkoutPlanInput
from app.serializers.workouts import serialize_public_workout_record
from app.core.legacy import _serialize_strength_workout_plan_record


def test_canonical_workout_terminology_mapping():
    """Validates that German workout titles and exercise names map to canonical English."""
    # Workout Titles
    assert canonicalize_fitness_text("Oberkörper") == "Upper Body"
    assert canonicalize_fitness_text("Unterkörper") == "Lower Body"
    assert canonicalize_fitness_text("Ganzkörper") == "Full Body"
    assert canonicalize_fitness_text("Oberkörper Kraft") == "Upper Body Strength"
    assert canonicalize_fitness_text("Unterkörper Kraft") == "Lower Body Strength"
    assert canonicalize_fitness_text("Upper Body") == "Upper Body"
    assert canonicalize_fitness_text("Lower Body") == "Lower Body"

    # Exercise Names
    assert canonicalize_fitness_text("Bankdrücken") == "Bench Press"
    assert canonicalize_fitness_text("Latzug") == "Lat Pulldown"
    assert canonicalize_fitness_text("Schulterdrücken") == "Shoulder Press"
    assert canonicalize_fitness_text("Kniebeugen") == "Barbell Back Squat"
    assert canonicalize_fitness_text("Kreuzheben") == "Deadlift"
    assert canonicalize_fitness_text("Liegestütze") == "Push-Up"
    assert canonicalize_fitness_text("Klimmzüge") == "Pull-Up"
    assert canonicalize_fitness_text("Bizepscurl") == "Biceps Curl"
    assert canonicalize_fitness_text("Trizepsdrücken") == "Triceps Pushdown"

    # English canonical names stay unmodified
    assert canonicalize_fitness_text("Bench Press") == "Bench Press"
    assert canonicalize_fitness_text("Lat Pulldown") == "Lat Pulldown"
    assert canonicalize_fitness_text("Shoulder Press") == "Shoulder Press"


def test_non_workout_ui_terms_not_falsely_claimed():
    """Validates normal UI terms are not falsely classified as fitness terms."""
    assert not is_canonical_fitness_text("Zurück")
    assert not is_canonical_fitness_text("Einstellungen")
    assert not is_canonical_fitness_text("Fertig")
    assert not is_canonical_fitness_text("Profil bearbeiten")
    assert not is_canonical_fitness_text("Speichern")


def test_ai_strength_plan_prompt_enforces_english_terminology():
    """Validates that prompt enforces English workout titles and exercise names even with lang='de'."""
    prompt_input = StrengthWorkoutPlanInput(
        goal="Hypertrophy",
        level="Intermediate",
        split="Upper / Lower",
        height="180",
        gender="Male",
        bench="80",
        squat="100",
        deadlift="120",
        equipment=["Dumbbells", "Barbell"],
        frequency="4",
        days=["Mon", "Tue", "Thu", "Fri"],
        age="30",
        weight="80",
        duration_minutes="45",
        language="de",
    )
    prompt = _strength_plan_prompt(prompt_input)

    # Confirms language instruction specifies English for titles/exercises
    assert "MUST ALWAYS remain in English" in prompt
    assert "NEVER translate workout titles" in prompt
    assert "CRITICAL CLIENT REQUIREMENT" in prompt


def test_serialize_public_workout_record_canonicalizes_content():
    """Validates that workout serializer always outputs canonical English titles and movements."""
    raw_doc = {
        "_id": ObjectId(),
        "title": "Oberkörper Kraft",
        "tag": "Oberkörper",
        "purposes": ["Upper Body"],
        "equipment": "Dumbbells",
        "level": "Intermediate",
        "duration_minutes": 35,
        "movements": [
            {"id": "m1", "name": "Bankdrücken", "sets": "3", "reps": "8-10"},
            {"id": "m2", "name": "Latzug", "sets": "3", "reps": "10-12"},
        ],
    }

    serialized = serialize_public_workout_record(raw_doc)
    assert serialized["title"] == "Upper Body Strength"
    assert serialized["movements"][0]["name"] == "Bench Press"
    assert serialized["movements"][1]["name"] == "Lat Pulldown"


def test_serialize_strength_workout_plan_record_canonicalizes_plan():
    """Validates that strength plan serializer sanitizes stored German plan data to canonical English."""
    record = {
        "_id": ObjectId(),
        "created_at": None,
        "progress": [],
        "plan": {
            "summary": "Ein personalisierter Trainingsplan.",
            "days": [
                {
                    "day": "Day 1",
                    "title": "Oberkörper Kraft",
                    "est_time": "45 min",
                    "volume": "Moderate",
                    "intensity": "High",
                    "sections": [
                        {
                            "id": "sec-1",
                            "title": "Oberkörper Kraft",
                            "exercises": [
                                {"id": "ex-1", "name": "Bankdrücken", "sets": 3, "reps": "8", "weight": "60kg", "rest": "90s", "type": "compound"},
                                {"id": "ex-2", "name": "Latzug", "sets": 3, "reps": "10", "weight": "50kg", "rest": "60s", "type": "compound"},
                            ],
                        }
                    ],
                }
            ],
        },
    }

    serialized = _serialize_strength_workout_plan_record(record)
    assert serialized.days[0].title == "Upper Body Strength"
    assert serialized.days[0].sections[0].title == "Upper Body Strength"
    assert serialized.days[0].sections[0].exercises[0].name == "Bench Press"
    assert serialized.days[0].sections[0].exercises[1].name == "Lat Pulldown"
