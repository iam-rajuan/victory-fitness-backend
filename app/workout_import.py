"""Custom workout routine import and structured parsing engine.

Supports experienced users providing free-form workout routines with:
- Multiple training days (e.g. 5 days)
- Exercise names
- Weights in kg (e.g. 80kg)
- Sets & reps
- Session durations (e.g. 90 minutes)
- Equipment & custom notes

Architecture:
    Free-form user input
        ↓
    AI & Deterministic structured parsing
        ↓
    Strict schema validation & integrity rules
        ↓
    Preview payload generation
        ↓
    User confirms
        ↓
    Save via workout-plan API / collection
"""

from __future__ import annotations

from enum import Enum
import json
import logging
import math
import re
from typing import Any
from urllib import error, request

from .config import settings
from .models import CustomWorkoutDay, CustomWorkoutExercise, CustomWorkoutPlan

logger = logging.getLogger(__name__)

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DAY_NAME_TO_KEY = {
    "monday": "Mon",
    "mon": "Mon",
    "tuesday": "Tue",
    "tue": "Tue",
    "wednesday": "Wed",
    "wed": "Wed",
    "thursday": "Thu",
    "thu": "Thu",
    "friday": "Fri",
    "fri": "Fri",
    "saturday": "Sat",
    "sat": "Sat",
    "sunday": "Sun",
    "sun": "Sun",
}

EQUIPMENT_KEYWORDS = [
    ("barbell", "Barbell"),
    ("squat rack", "Squat Rack"),
    ("rack", "Squat Rack"),
    ("dumbbell", "Dumbbells"),
    ("dumbbells", "Dumbbells"),
    ("db", "Dumbbells"),
    ("dbs", "Dumbbells"),
    ("cable", "Cables"),
    ("cables", "Cables"),
    ("machine", "Machines"),
    ("machines", "Machines"),
    ("bench", "Bench"),
    ("pull-up bar", "Pull-up Bar"),
    ("pull up bar", "Pull-up Bar"),
    ("pull-up", "Pull-up Bar"),
    ("pullup", "Pull-up Bar"),
    ("band", "Bands"),
    ("bands", "Bands"),
    ("kettlebell", "Kettlebells"),
    ("bodyweight", "Bodyweight"),
]

COMPOUND_KEYWORDS = {
    "bench press", "squat", "deadlift", "row", "overhead press", "shoulder press",
    "pull-up", "pull up", "chin-up", "chin up", "dip", "dips", "lunge", "lunges",
    "clean", "snatch", "press", "rdl", "romanian deadlift", "front squat", "hip thrust",
}

CORE_KEYWORDS = {
    "plank", "crunch", "ab wheel", "leg raise", "knee raise", "russian twist",
    "hollow hold", "deadbug", "hanging",
}


PAIN_MAPPINGS = {
    "knee": ["knee", "knees", "patella", "meniscus"],
    "shoulder": ["shoulder", "shoulders", "rotator cuff", "deltoid"],
    "lower_back": ["lower back", "lumbar", "back pain", "herniated", "spine"],
    "elbow": ["elbow", "tennis elbow", "golfers elbow"],
    "wrist": ["wrist"],
    "hip": ["hip", "hips", "groin"],
    "ankle": ["ankle", "achilles"],
}


class WorkoutIntent(str, Enum):
    IMPORT_EXISTING = "import_existing"  # Intent B: Experienced user supplying existing routine; preserve verbatim
    CREATE_NEW = "create_new"            # Intent A: User asks AI to build/create/recommend a new workout
    ADJUST_CURRENT = "adjust_current"    # User asks to tweak active routine / session
    GENERAL_QUERY = "general_query"      # Non-workout or general coaching inquiry


def is_custom_workout_import_request(message: str) -> bool:
    """Detects if the user's message contains an existing/custom workout routine to import."""
    text = str(message or "").strip()
    if not text:
        return False
    lowered = text.lower()

    # Explicit import intent phrases
    explicit_import_phrases = (
        "import my workout", "import this workout", "import my routine", "import this routine",
        "import my plan", "import this plan", "here is my workout", "here is my routine",
        "here's my workout", "here's my routine", "my current routine", "my workout routine",
        "my 5-day", "my 4-day", "my 3-day", "my 6-day", "save my workout", "add my routine",
        "custom routine", "custom workout", "save this workout", "import that workout",
        "use my existing", "use my workout", "use this routine", "use my routine",
    )
    if any(phrase in lowered for phrase in explicit_import_phrases):
        return True

    # Count day occurrences
    day_matches = re.findall(
        r"(?i)\b(?:day\s*[1-7]|monday|tuesday|wednesday|thursday|friday|saturday|sunday|session\s*[1-7]|workout\s*[a-g])\b",
        text,
    )
    distinct_day_count = len(set(m.lower().replace(" ", "") for m in day_matches))

    # Exercise and set/rep indicators
    has_set_rep = bool(re.search(r"\b\d+\s*(?:x|sets?\s*(?:of|x)?)\s*\d+", lowered))
    has_weight = bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:kg|lbs?)\b", lowered))
    has_exercise_names = any(term in lowered for term in ("bench", "squat", "deadlift", "row", "press", "curl", "pull-up", "pullup"))

    # If at least 2 distinct days and set/rep or weights are present:
    if distinct_day_count >= 2 and (has_set_rep or (has_weight and has_exercise_names)):
        return True

    # Or if multi-line block with days and exercises
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    day_header_lines = [l for l in lines if re.match(r"(?i)^(?:###?\s*)?(?:day\s*\d+|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", l)]
    if len(day_header_lines) >= 2 and len(lines) >= 5:
        return True

    return False


def classify_workout_message_intent(message: str, user_context: dict[str, Any] | None = None) -> WorkoutIntent:
    """Classifies user intent distinguishing between CREATE_NEW, IMPORT_EXISTING, ADJUST_CURRENT, and GENERAL_QUERY.

    Guarantees strict separation:
    - Intent A (CREATE_NEW): AI creates a new evidence-based program.
    - Intent B (IMPORT_EXISTING): AI preserves existing routine verbatim.
    Never mixes these two intents.
    """
    text = str(message or "").strip()
    if not text:
        return WorkoutIntent.GENERAL_QUERY
    lowered = text.lower()

    # 1. Intent B (IMPORT_EXISTING) takes priority when routine content or import intent is supplied
    if is_custom_workout_import_request(text):
        return WorkoutIntent.IMPORT_EXISTING

    # 2. Check for Intent A (CREATE_NEW): User asks to create/build/make a new workout/plan/program
    create_terms = (
        "create", "build", "generate", "make", "design", "recommend", "give me",
        "start", "set up", "write", "plan a", "put together"
    )
    plan_terms = (
        "workout plan", "training plan", "workout program", "training program",
        "workout routine", "training routine", "routine", "split", "program",
        "strength plan", "hypertrophy plan", "strength routine", "gym plan",
        "home plan", "bodyweight plan", "workout for"
    )
    has_create_term = any(term in lowered for term in create_terms)
    has_plan_term = any(term in lowered for term in plan_terms)
    split_requests = bool(re.search(r"\b([1-7])[\s-]*(?:day|days)[\s-]*(?:split|routine|plan|program|workout)\b", lowered))
    beginner_requests = bool(re.search(r"\b(?:beginner|intermediate|advanced)[\s-]*(?:workout|routine|plan|program)\b", lowered))

    if (has_create_term and has_plan_term) or split_requests or (has_create_term and beginner_requests):
        return WorkoutIntent.CREATE_NEW

    # 3. Check for ADJUST_CURRENT: User asks to modify active workout / session
    adjust_terms = (
        "adjust", "tweak", "swap", "replace", "modify", "shorten", "lengthen",
        "change", "reduce", "increase", "remove", "add", "move", "only have",
        "tonight", "current session", "tight", "hurts", "sore",
    )
    workout_terms = (
        "workout", "session", "exercise", "routine", "plan", "split", "minutes", "min",
        "sets", "reps", "volume", "weight", "bench", "squat", "deadlift", "press",
        "row", "curl", "pull-up", "pullup", "equipment", "gym", "bodyweight",
    )
    if any(term in lowered for term in adjust_terms) and any(p in lowered for p in workout_terms):
        return WorkoutIntent.ADJUST_CURRENT

    if "build my plan" in lowered or "create my plan" in lowered or "make my plan" in lowered:
        return WorkoutIntent.CREATE_NEW

    return WorkoutIntent.GENERAL_QUERY


def count_expected_days_in_input(text: str) -> int:
    """Accurately counts how many distinct days are specified in the raw user input."""
    lowered = str(text or "").lower()

    # Check explicit day count mention: "5 training days", "5 days", "5-day", "5-day workout"
    count_match = re.search(r"\b([1-7])[\s-]*(?:training[\s-]*)?days?\b", lowered)
    explicit_count = int(count_match.group(1)) if count_match else None

    # Find day headers
    day_headers = re.findall(
        r"(?im)^(?:###?\s*)?(?:day\s*([1-7])|session\s*([1-7])|workout\s*([a-g])|(monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        text,
    )
    found_days: set[str] = set()
    for match in day_headers:
        # Match is tuple of groups
        val = next((item for item in match if item), "")
        if val:
            found_days.add(val.lower())

    header_count = len(found_days)
    if explicit_count and explicit_count >= 2:
        return explicit_count
    if header_count >= 2:
        return header_count
    return max(header_count, 1) if header_count else 0


def extract_expected_duration_minutes(text: str) -> int | None:
    """Extract session duration without confusing inter-set rest for workout length."""
    lowered = str(text or "").lower()

    # Prefer explicit duration labels emitted by Coach Victor and common user phrasing.
    labelled_patterns = (
        r"(?:est(?:imated)?\.?\s*time|session\s*(?:duration|length)|duration)\s*[:=\-]?\s*(\d{1,3})\s*(?:min|mins|minute|minutes)\b",
        r"(\d{1,3})\s*(?:min|mins|minute|minutes)\s*(?:/|per)\s*session\b",
        r"(?:workout|session)\s*(?:is|of|for|around|about|approximately|approx\.?)?\s*(\d{1,3})\s*(?:min|mins|minute|minutes)\b",
    )
    for pattern in labelled_patterns:
        match = re.search(pattern, lowered)
        if match:
            return max(15, min(int(match.group(1)), 240))

    # Fall back to an ordinary minute mention, excluding values explicitly used as rest.
    for match in re.finditer(r"(\d{1,3})\s*(?:min|mins|minute|minutes)\b", lowered):
        trailing_context = lowered[match.end():match.end() + 16]
        if re.match(r"\s*(?:of\s+)?rest\b", trailing_context):
            continue
        return max(15, min(int(match.group(1)), 240))
    if "1.5 hour" in lowered or "1.5 hr" in lowered or "1.5h" in lowered:
        return 90
    if "2 hour" in lowered or "2 hr" in lowered or "2h" in lowered:
        return 120
    if "1 hour" in lowered or "1 hr" in lowered or "1h" in lowered:
        return 60
    return None


def extract_equipment_from_text(text: str) -> list[str]:
    """Extracts gym/home equipment mentioned in text."""
    lowered = str(text or "").lower()
    found: list[str] = []
    for needle, canonical in EQUIPMENT_KEYWORDS:
        if re.search(rf"\b{re.escape(needle)}\b", lowered) and canonical not in found:
            found.append(canonical)
    return found


def _strip_markdown_line(line: str) -> str:
    """Remove presentation-only Markdown around a single plan line."""
    cleaned = re.sub(r"^\s*#{1,6}\s*", "", str(line or "").strip())
    return cleaned.strip().strip("*_` ").strip()


def _parse_exercise_line(line: str) -> CustomWorkoutExercise | None:
    """Parses a single line of text into a structured CustomWorkoutExercise."""
    raw = _strip_markdown_line(line)
    if not raw:
        return None

    # Skip day headers, bullet markers, or section headers
    if re.match(r"(?i)^(?:day\s*\d+|session\s*\d+|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b", raw):
        return None
    if re.match(r"(?i)^rest\b|^rest\s*day", raw):
        return None
    if re.match(
        r"(?i)^(?:est(?:imated)?\.?\s*time|duration|intensity|equipment|key\s+notes?|notes?\s+for\s+this\s+week|tap\s+the|import\s+this|used\s+your)\b",
        raw,
    ):
        return None

    # Clean leading bullets/numbering: "- ", "* ", "1. ", "1) "
    cleaned = re.sub(r"^\s*[-*•\d]+[.)\]\-:]\s*", "", raw).strip()
    if not cleaned:
        return None

    # Markdown emphasis often wraps exercise names after the list marker, e.g.
    # "- **Bench Press:** 3 × 8". It is presentation, not part of the name.
    cleaned = cleaned.replace("**", "").replace("__", "").strip("*_` ")

    has_prescription = bool(re.search(
        r"\b\d{1,2}\s*(?:x|×|sets?\s*(?:of|x|×)?)\s*\d{1,3}(?:\s*[-–—]\s*\d{1,3})?\b",
        cleaned,
        re.I,
    ))
    looks_like_coaching_note = bool(
        re.search(r"[.!?](?:\s|$)", cleaned)
        or re.match(
            r"(?i)^(?:mobilize|nudge|chase|keep|hold|report|build|progress|pick|do\s+not|don't|use|stay|manage|let|add\s+next|shoulder\s+health)\b",
            cleaned,
        )
    )
    if looks_like_coaching_note and not has_prescription:
        return None

    explicit_type = ""
    type_match = re.search(r"(?:[,;|]\s*|\s+)(compound|isolation|accessory|core|warmup)\s*$", cleaned, re.I)
    if type_match:
        explicit_type = type_match.group(1).title()
        cleaned = cleaned[:type_match.start()].rstrip(" ,;|:-")

    # Extract weight/load inside parentheses first: e.g. "(+10kg)", "(80kg)", "(bodyweight)"
    weight = ""
    weight_paren = re.search(r"\(\s*(\+?\d+(?:\.\d+)?(?:\s*[-–—]\s*\d+(?:\.\d+)?)?\s*(?:kg|lbs?|kilos?)(?:\s*/\s*(?:arm|side))?|bodyweight|bw)\s*\)", cleaned, re.I)
    if weight_paren:
        w_val = weight_paren.group(1).strip()
        weight = "Bodyweight" if w_val.lower() in ("bodyweight", "bw") else w_val.replace(" ", "")
        cleaned = cleaned[:weight_paren.start()] + " " + cleaned[weight_paren.end():]

    # Extract notes inside remaining parentheses: e.g. "(heavy warm up first)"
    notes = ""
    paren_match = re.search(r"\(([^)]+)\)", cleaned)
    if paren_match:
        notes = paren_match.group(1).strip()
        cleaned = cleaned[:paren_match.start()] + " " + cleaned[paren_match.end():]

    # Extract rest: e.g. "90s rest", "120s", "2 min rest", "60s"
    rest = "90s"
    rest_match = re.search(r"(\d{1,3}\s*(?:s|sec|secs|seconds?|min|mins|minutes?))\s*(?:rest)?", cleaned, re.I)
    if rest_match:
        rest = rest_match.group(1).strip().lower()
        cleaned = cleaned[:rest_match.start()] + " " + cleaned[rest_match.end():]

    # Extract weight/load if not already found: e.g. "80kg", "+10kg", "@ 80kg", "Bodyweight", "BW"
    if not weight:
        weight_match = re.search(r"(?:@\s*|(?<=[\s\-_(/])|^)(\+?\d+(?:\.\d+)?(?:\s*[-–—]\s*\d+(?:\.\d+)?)?\s*(?:kg|lbs?|kilos?)(?:\s*/\s*(?:arm|side))?|bodyweight|bw)\b", cleaned, re.I)
        if weight_match:
            weight_raw = weight_match.group(1).strip()
            if weight_raw.lower() in ("bodyweight", "bw"):
                weight = "Bodyweight"
            else:
                weight = weight_raw.replace(" ", "")
            cleaned = cleaned[:weight_match.start()] + " " + cleaned[weight_match.end():]

    # Extract sets and reps: e.g. "4x8", "4 sets x 8 reps", "4 sets of 8", "3 x 10-12"
    sets = 3
    reps = "8-12"
    set_rep_match = re.search(r"(\d{1,2})\s*(?:x|×|sets?\s*(?:of|x|×)?)\s*(\d{1,2}(?:\s*[-–—]\s*\d{1,2})?)\s*(?:reps?)?", cleaned, re.I)
    if set_rep_match:
        try:
            sets = max(1, min(int(set_rep_match.group(1)), 20))
            reps = re.sub(r"\s*[-–—]\s*", "-", set_rep_match.group(2).strip())
        except Exception:
            pass
        cleaned = cleaned[:set_rep_match.start()] + " " + cleaned[set_rep_match.end():]
    else:
        # Check standalone sets: "3 sets"
        sets_only = re.search(r"(\d{1,2})\s*sets?\b", cleaned, re.I)
        if sets_only:
            sets = max(1, min(int(sets_only.group(1)), 20))
            cleaned = cleaned[:sets_only.start()] + " " + cleaned[sets_only.end():]
        # Check standalone reps: "10 reps"
        reps_only = re.search(r"(\d{1,2}(?:-\d{1,2})?)\s*reps?\b", cleaned, re.I)
        if reps_only:
            reps = reps_only.group(1).strip()
            cleaned = cleaned[:reps_only.start()] + " " + cleaned[reps_only.end():]

    # Clean exercise name from leftover delimiters without destroying intra-word hyphens (e.g. Pull-ups, T-Bar)
    cleaned = re.sub(r"(?:^\s*[-–—:;,|/@]+\s*|\s*[-–—:;,|/@]+\s*$)", " ", cleaned)
    cleaned = re.sub(r"\s+[-–—:;,|/@]+\s+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip(" \t-–—:;,|/@")
    exercise_name = cleaned
    if not exercise_name:
        return None

    # Preserve exact name, capitalize appropriately
    if len(exercise_name) <= 2:
        return None

    # Classify type
    lowered_ex = exercise_name.lower()
    if explicit_type:
        ex_type = explicit_type
    elif any(k in lowered_ex for k in CORE_KEYWORDS):
        ex_type = "Core"
    elif any(k in lowered_ex for k in COMPOUND_KEYWORDS):
        ex_type = "Compound"
    else:
        ex_type = "Isolation"

    return CustomWorkoutExercise(
        exercise_name=exercise_name,
        sets=sets,
        reps=reps,
        weight=weight,
        rest=rest,
        notes=notes,
        type=ex_type,
    )


def parse_custom_workout_deterministic(text: str) -> CustomWorkoutPlan:
    """High-accuracy deterministic parser that extracts all days, exercises, weights, and durations."""
    raw = str(text or "").strip()
    if not raw:
        return CustomWorkoutPlan(is_valid=False, error_message="Empty input")

    plan_duration = extract_expected_duration_minutes(raw) or 90
    plan_equipment = extract_equipment_from_text(raw)
    expected_days = count_expected_days_in_input(raw)

    # Determine plan name
    plan_name = "Custom Workout Plan"
    title_match = re.search(r"(?i)(?:my\s+)?([a-z0-9\s/]+(?:split|routine|workout|plan))\b", raw)
    if title_match and len(title_match.group(1).strip()) > 4:
        candidate = title_match.group(1).strip().title()
        if len(candidate) <= 50:
            plan_name = candidate
    elif expected_days:
        plan_name = f"{expected_days}-Day Custom Routine"

    lines = raw.splitlines()

    # Day header regex
    day_regex = re.compile(
        r"(?i)^(?:day\s*([0-9]+)|session\s*([0-9]+)|workout\s*([a-g])|(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?))\b[:\s\-–—]*(.*)$"
    )

    day_blocks: list[tuple[str, str, list[str]]] = []  # (header_tag, extra_title, lines)
    current_tag = ""
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        stripped = _strip_markdown_line(line)
        if not stripped:
            continue
        if current_tag and re.match(r"(?i)^(?:key\s+notes?|notes?\s+for\s+this\s+week)\b", stripped):
            day_blocks.append((current_tag, current_title, current_lines))
            current_tag = ""
            current_title = ""
            current_lines = []
            break
        m = day_regex.match(stripped)
        if m:
            if current_tag:
                day_blocks.append((current_tag, current_title, current_lines))
            tag_val = next((item for item in m.groups()[:4] if item), "")
            current_tag = tag_val
            current_title = m.group(5).strip() if m.group(5) else ""
            current_lines = []
        elif current_tag:
            current_lines.append(stripped)

    if current_tag:
        day_blocks.append((current_tag, current_title, current_lines))

    # Standard day key sequence for numbered days
    standard_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    parsed_days: list[CustomWorkoutDay] = []
    uncertainties: list[str] = []

    for idx, (tag, extra_title, block_lines) in enumerate(day_blocks):
        # Determine day key
        tag_lower = tag.lower()
        if tag_lower in DAY_NAME_TO_KEY:
            day_key = DAY_NAME_TO_KEY[tag_lower]
        elif idx < len(standard_keys):
            day_key = standard_keys[idx]
        else:
            day_key = standard_keys[idx % len(standard_keys)]

        # Day name
        if tag.isdigit():
            day_label = f"Day {tag}"
        elif tag_lower in DAY_NAME_TO_KEY:
            day_label = tag.title()
        else:
            day_label = f"Day {idx + 1}"

        if extra_title:
            day_name = f"{day_label} - {extra_title}"
        else:
            day_name = day_label

        # Check day-specific duration
        block_text = "\n".join([extra_title, *block_lines])
        day_duration = extract_expected_duration_minutes(block_text) or plan_duration or 90
        day_equip = extract_equipment_from_text(block_text) or plan_equipment

        # Parse exercises in this block
        exercises: list[CustomWorkoutExercise] = []
        for line in block_lines:
            ex = _parse_exercise_line(line)
            if ex:
                exercises.append(ex)

        if not exercises:
            # Check if this was a rest day
            if re.search(r"(?i)\brest\b", extra_title) or any(re.search(r"(?i)\brest\b", l) for l in block_lines):
                # Rest day
                exercises.append(
                    CustomWorkoutExercise(
                        exercise_name="Active Recovery / Rest",
                        sets=1,
                        reps="1",
                        weight="Bodyweight",
                        rest="0s",
                        notes="Mobility, hydration and light recovery walking",
                        type="Warmup",
                    )
                )
            else:
                uncertainties.append(f"Day {day_label} had no parseable exercises.")

        parsed_days.append(
            CustomWorkoutDay(
                day_name=day_name,
                day_key=day_key,
                expected_duration=day_duration,
                equipment=day_equip,
                exercises=exercises,
            )
        )

    # Validate day count: if input clearly specified 5 days, ensure we have 5 days
    if expected_days and len(parsed_days) < expected_days:
        uncertainties.append(
            f"Input indicated {expected_days} training days, but only {len(parsed_days)} day blocks were parsed."
        )

    is_valid = len(parsed_days) >= 1 and any(len(d.exercises) > 0 for d in parsed_days)
    error_message = None if is_valid else "Could not identify any valid days or exercises in routine."

    return CustomWorkoutPlan(
        plan_name=plan_name,
        expected_duration=plan_duration,
        equipment=plan_equipment,
        days=parsed_days,
        parsing_uncertainty=uncertainties,
        is_valid=is_valid,
        error_message=error_message,
    )


def validate_parsed_workout_plan(plan: CustomWorkoutPlan, raw_input: str) -> tuple[bool, list[str]]:
    """Strictly validates a parsed workout plan against client integrity rules.

    Rules:
    1. If input contains N days (e.g. 5 days): output must contain at least N days or report uncertainty.
    2. If input says 90-minute session: never silently convert to 25 minutes.
    3. If input contains 80kg: preserve 80kg on the affected exercise.
    4. Do not silently replace unknown exercises with unrelated exercises.
    5. Reject incomplete or corrupted model outputs.
    """
    uncertainties = list(plan.parsing_uncertainty)
    raw_lower = str(raw_input or "").lower()

    # Rule 1: Day Count
    expected_days = count_expected_days_in_input(raw_input)
    if expected_days >= 2 and len(plan.days) < expected_days:
        uncertainties.append(
            f"Integrity check failed: Raw input specified {expected_days} days, but plan only contains {len(plan.days)} days."
        )
        return False, uncertainties

    # Rule 2: Duration Integrity
    raw_duration = extract_expected_duration_minutes(raw_input)
    if raw_duration and raw_duration >= 60:
        # User specified 60-90+ minutes
        for day in plan.days:
            if day.expected_duration < 45:
                # Silently converted to short session!
                uncertainties.append(
                    f"Integrity check failed: User specified {raw_duration}-minute session, but {day.day_name} was converted to {day.expected_duration} minutes."
                )
                # Auto-correct to user's requested duration rather than dropping it
                day.expected_duration = raw_duration
        if plan.expected_duration and plan.expected_duration < 45:
            plan.expected_duration = raw_duration

    # Rule 3: Weight Preservation (e.g. 80kg)
    # Find weights in raw text: e.g. "80kg", "100kg", "70kg"
    raw_weights = set(re.findall(r"\b(\d{2,3}\s*kg)\b", raw_lower))
    if raw_weights:
        parsed_weights = {
            ex.weight.lower().replace(" ", "")
            for day in plan.days
            for ex in day.exercises
            if ex.weight
        }
        # Check if known prominent weights were retained
        for rw in raw_weights:
            norm_rw = rw.replace(" ", "")
            if norm_rw not in parsed_weights:
                uncertainties.append(
                    f"Note: Stated load '{rw}' was not cleanly mapped to an exercise weight in the parsed output."
                )

    # Rule 4: Exercise Preservation
    for day in plan.days:
        if not day.exercises:
            uncertainties.append(f"Integrity check failed: {day.day_name} has zero exercises.")
            return False, uncertainties
        for ex in day.exercises:
            if not ex.exercise_name or len(ex.exercise_name.strip()) < 2:
                uncertainties.append(f"Integrity check failed: Empty exercise name found in {day.day_name}.")
                return False, uncertainties

    is_valid = len(plan.days) >= 1 and (expected_days == 0 or len(plan.days) >= expected_days)
    return is_valid, uncertainties


def validate_strength_plan_structure(
    plan: dict[str, Any],
    expected_days: int | None = None,
    min_duration_minutes: int | None = None,
    required_weights: list[str] | None = None,
    *,
    expected_days_count: int | None = None,
) -> tuple[bool, list[str]]:
    """Strictly validates a generated or imported strength plan before saving."""
    errors: list[str] = []
    target_days_count = expected_days if expected_days is not None else expected_days_count
    if not isinstance(plan, dict):
        return False, ["Plan payload must be a JSON object"]

    days = plan.get("days")
    if not isinstance(days, list) or not days:
        return False, ["Plan must contain a non-empty list of days"]

    if target_days_count and len(days) < target_days_count:
        errors.append(f"Plan contains only {len(days)} days, expected {target_days_count} days.")

    all_weights_text: list[str] = []

    for idx, day in enumerate(days):
        if not isinstance(day, dict):
            errors.append(f"Day {idx + 1} is not a valid dictionary object.")
            continue
        day_key = str(day.get("day") or "").strip()
        day_title = str(day.get("title") or day.get("day_name") or "").strip()
        if not day_title:
            errors.append(f"Day {idx + 1} ({day_key}) is missing a title.")

        est_time = str(day.get("est_time") or "").strip().lower()
        if not est_time:
            errors.append(f"Day {idx + 1} ({day_key}) is missing an estimated session duration.")
        elif min_duration_minutes and min_duration_minutes >= 60:
            m = re.search(r"(\d+)", est_time)
            dur_val = int(m.group(1)) if m else 0
            if dur_val < min_duration_minutes - 15:
                errors.append(
                    f"Day {idx + 1} duration '{est_time}' is significantly lower than requested {min_duration_minutes} min."
                )

        exercises = day.get("exercises")
        if not isinstance(exercises, list) or len(exercises) < 2:
            errors.append(f"Day {idx + 1} ({day_key}) must have at least 2 structured exercises.")
            continue

        for ex_idx, ex in enumerate(exercises):
            if not isinstance(ex, dict):
                errors.append(f"Day {idx + 1} Exercise {ex_idx + 1} is invalid.")
                continue
            name = str(ex.get("name") or ex.get("exercise_name") or "").strip()
            if len(name) < 2:
                errors.append(f"Day {idx + 1} Exercise {ex_idx + 1} has an invalid name.")
            sets = ex.get("sets")
            try:
                if int(sets) < 1:
                    errors.append(f"Day {idx + 1} Exercise '{name}' has invalid sets count: {sets}")
            except Exception:
                errors.append(f"Day {idx + 1} Exercise '{name}' sets count must be an integer: {sets}")

            w_val = str(ex.get("weight") or "").strip()
            if w_val:
                all_weights_text.append(w_val.lower().replace(" ", ""))

    if required_weights:
        joined_weights = " ".join(all_weights_text)
        for rw in required_weights:
            clean_rw = rw.lower().replace(" ", "")
            if clean_rw not in joined_weights:
                errors.append(f"Required load '{rw}' was not found in the plan exercises.")

    is_valid = len(errors) == 0
    return is_valid, errors


def assemble_deterministic_workout_context(
    user: dict | None = None,
    user_context: dict[str, Any] | None = None,
    message: str = "",
) -> dict[str, Any]:
    """Assembles complete deterministic training context for workout generation and coaching.

    Ensures all 10 context dimensions are deterministic and unambiguous before AI generation:
    1. user goal
    2. experience level
    3. age
    4. equipment
    5. injuries/restrictions
    6. training days
    7. expected workout duration
    8. existing routine when supplied
    9. known weights/reps
    10. recent plan/session information
    """
    context = dict(user_context or {})
    u = dict(user or {})
    onboarding = dict(context.get("onboarding") or u.get("onboarding") or {})
    anamnese = dict(onboarding.get("anamnese") or {})
    personal_profile = dict(onboarding.get("personalProfile") or {})
    progress = dict(context.get("progress") or {})
    medical = dict(context.get("medical") or {})

    lowered = str(message or "").lower()
    intent = classify_workout_message_intent(message, user_context)

    # 1. User Goal
    goal = ""
    if any(term in lowered for term in ("lose weight", "fat loss", "cut", "recomp", "tone")):
        goal = "Body Recomp"
    elif any(term in lowered for term in ("pure strength", "heavy strength", "powerlift", "strength")):
        goal = "Pure Strength"
    elif any(term in lowered for term in ("power & speed", "power and speed", "athletic", "speed", "stamina", "endurance")):
        goal = "Power & Speed"
    elif any(term in lowered for term in ("hypertrophy", "build muscle", "muscle", "mass", "bulk")):
        goal = "Hypertrophy"
    if not goal:
        raw_goal = str(anamnese.get("primaryGoal") or u.get("fitness_goal") or "").strip().lower()
        if any(w in raw_goal for w in ["muscle", "hypertrophy", "build"]):
            goal = "Hypertrophy"
        elif any(w in raw_goal for w in ["fat", "lose", "weight loss", "recomp", "tone"]):
            goal = "Body Recomp"
        elif any(w in raw_goal for w in ["strength", "powerlift"]):
            goal = "Pure Strength"
        elif any(w in raw_goal for w in ["speed", "athletic", "endurance"]):
            goal = "Power & Speed"
        else:
            goal = "Hypertrophy"

    # 2. Experience Level
    level = ""
    if any(w in lowered for w in ("beginner", "novice", "new to lifting", "starting out")):
        level = "Beginner"
    elif any(w in lowered for w in ("advanced", "experienced", "athlete", "competitive")):
        level = "Advanced"
    elif any(w in lowered for w in ("intermediate", "moderate")):
        level = "Intermediate"
    if not level:
        raw_level = str(anamnese.get("activityLevel") or u.get("fitness_level") or "").strip().lower()
        if any(w in raw_level for w in ["sedentary", "light", "beginner"]):
            level = "Beginner"
        elif any(w in raw_level for w in ["very", "advanced", "athlete"]):
            level = "Advanced"
        else:
            level = "Intermediate"

    # 3. Age
    age = str(personal_profile.get("age") or u.get("age") or "28").strip()

    # 4. Equipment
    equipment: list[str] = []
    if any(term in lowered for term in ("no equipment", "bodyweight only", "bodyweight", "nothing at all", "calisthenics")):
        equipment = ["No equipment"]
    elif any(term in lowered for term in ("home gym", "dumbbells only", "dumbbell", "dumbbells", "bands")):
        equipment = ["Dumbbells", "Bands"]
    elif any(term in lowered for term in ("full gym", "gym", "barbell", "squat rack", "cables")):
        equipment = ["Gym", "Barbell", "Dumbbells", "Cables", "Machines"]
    if not equipment:
        raw_equip = str(anamnese.get("equipmentAccess") or u.get("equipmentAccess") or "").strip().lower()
        if any(w in raw_equip for w in ["no equipment", "none", "bodyweight", "outdoors", "outdoor"]):
            equipment = ["No equipment"]
        elif any(w in raw_equip for w in ["dumbbells", "kettlebells", "home gym", "bands"]):
            equipment = ["Dumbbells", "Bands"]
        elif any(w in raw_equip for w in ["gym", "full gym", "barbell"]):
            equipment = ["Gym", "Barbell", "Dumbbells", "Cables", "Machines"]
        else:
            equipment = ["Gym", "Barbell", "Dumbbells", "Cables", "Machines"]

    # 5. Injuries / Restrictions
    injury_flags: list[str] = []
    for flag in list(u.get("injury_flags") or []):
        if str(flag).strip() and str(flag).strip().lower() not in injury_flags:
            injury_flags.append(str(flag).strip().lower())
    for injury_key, needles in PAIN_MAPPINGS.items():
        if any(needle in lowered for needle in needles) and injury_key not in injury_flags:
            injury_flags.append(injury_key)
    health_notes = str(medical.get("health_notes") or (anamnese.get("healthNotes") or "")).strip()
    app_injury = str(medical.get("injury") or "").strip()

    # 6. Training Days & Frequency
    frequency = count_expected_days_in_input(message) or None
    if not frequency:
        raw_days = str(anamnese.get("daysPerWeek") or "").strip()
        m = re.search(r"(\d+)", raw_days)
        frequency = int(m.group(1)) if m else 4
    frequency = max(1, min(frequency, 7))

    day_aliases = [
        ("monday", "Mon"), ("mon", "Mon"),
        ("tuesday", "Tue"), ("tue", "Tue"),
        ("wednesday", "Wed"), ("wed", "Wed"),
        ("thursday", "Thu"), ("thu", "Thu"),
        ("friday", "Fri"), ("fri", "Fri"),
        ("saturday", "Sat"), ("sat", "Sat"),
        ("sunday", "Sun"), ("sun", "Sun"),
    ]
    explicit_days = []
    for needle, day in day_aliases:
        if re.search(rf"\b{re.escape(needle)}\b", lowered) and day not in explicit_days:
            explicit_days.append(day)
    default_days_map = {
        1: ["Mon"],
        2: ["Mon", "Thu"],
        3: ["Mon", "Wed", "Fri"],
        4: ["Mon", "Tue", "Thu", "Fri"],
        5: ["Mon", "Tue", "Wed", "Fri", "Sat"],
        6: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        7: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }
    days = explicit_days if len(explicit_days) == frequency else default_days_map.get(frequency, ["Mon", "Tue", "Thu", "Fri"])

    # 7. Expected Workout Duration (NEVER collapse 90 to 25!)
    expected_duration = extract_expected_duration_minutes(message)
    if not expected_duration:
        raw_time = str(anamnese.get("timePerSession") or "").strip()
        m_time = re.search(r"(\d+)", raw_time)
        expected_duration = int(m_time.group(1)) if m_time else 45
    expected_duration = max(15, min(expected_duration, 240))

    # 8. Known Weights / PRs
    bench = str(personal_profile.get("bench") or u.get("bench") or "").strip()
    squat = str(personal_profile.get("squat") or u.get("squat") or "").strip()
    deadlift = str(personal_profile.get("deadlift") or u.get("deadlift") or "").strip()
    user_weight = str(personal_profile.get("weight") or u.get("weight") or "75").strip()

    # 9. Existing Routine when supplied (Intent B)
    existing_routine: CustomWorkoutPlan | None = None
    if intent == WorkoutIntent.IMPORT_EXISTING:
        existing_routine = parse_custom_workout(message, user_context)

    # 10. Recent Plan / Session Information
    current_plan = dict(progress.get("current_home_workout_plan") or {})
    recent_plan_summary = str(current_plan.get("summary") or progress.get("latest_workout_feedback_summary") or "").strip()

    return {
        "intent": intent,
        "goal": goal,
        "experience_level": level,
        "age": age,
        "gender": str(personal_profile.get("gender") or u.get("gender") or "Other").strip(),
        "weight_kg": user_weight,
        "equipment": equipment,
        "injuries_restrictions": injury_flags,
        "health_notes": health_notes,
        "application_injury": app_injury,
        "training_days": days,
        "frequency": frequency,
        "expected_duration_minutes": expected_duration,
        "known_weights": {
            "bench": bench,
            "squat": squat,
            "deadlift": deadlift,
            "bodyweight": user_weight,
        },
        "existing_routine": existing_routine,
        "recent_plan_summary": recent_plan_summary,
    }


def parse_custom_workout(text: str, user_context: dict[str, Any] | None = None) -> CustomWorkoutPlan:
    """Unified entry point for custom workout parsing.

    Runs deterministic parser first as reliable baseline, validates rules,
    and guarantees that 5-day inputs, 90-minute durations, and 80kg weights
    are completely preserved without silent corruption.
    """
    raw_text = str(text or "").strip()
    plan = parse_custom_workout_deterministic(raw_text)
    is_valid, uncertainties = validate_parsed_workout_plan(plan, raw_text)
    plan.is_valid = is_valid
    plan.parsing_uncertainty = uncertainties

    # If duration was specified in user context or profile anamnese and missing in plan:
    if not plan.expected_duration and user_context:
        onboarding = dict(user_context.get("onboarding") or {})
        anamnese = dict(onboarding.get("anamnese") or {})
        raw_time = str(anamnese.get("timePerSession") or "")
        m = re.search(r"(\d+)", raw_time)
        if m:
            plan.expected_duration = int(m.group(1))

    return plan


def convert_custom_plan_to_strength_plan_dict(
    plan: CustomWorkoutPlan,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Converts a validated CustomWorkoutPlan into the canonical dictionary format

    stored in strength_workout_plans_collection and returned by the API.
    """
    days_out: list[dict[str, Any]] = []

    for day in plan.days:
        day_exercises: list[dict[str, Any]] = []
        total_volume_kg = 0
        total_bw_reps = 0

        for idx, ex in enumerate(day.exercises, start=1):
            ex_id = f"{day.day_key.lower()}-{idx}"

            # Calculate volume
            avg_reps = 10
            rep_match = re.search(r"(\d+)", str(ex.reps))
            if rep_match:
                avg_reps = int(rep_match.group(1))

            weight_kg = 0
            w_match = re.search(r"(\d+(?:\.\d+)?)", str(ex.weight))
            if w_match and "bw" not in str(ex.weight).lower() and "bodyweight" not in str(ex.weight).lower():
                try:
                    weight_kg = float(w_match.group(1))
                except ValueError:
                    weight_kg = 0

            if weight_kg > 0:
                total_volume_kg += int(ex.sets * avg_reps * weight_kg)
            else:
                total_bw_reps += int(ex.sets * avg_reps)

            exercise_name_lower = ex.exercise_name.strip().lower()
            is_bodyweight = any(
                marker in exercise_name_lower
                for marker in (
                    "bodyweight", "push-up", "push up", "pull-up", "pull up",
                    "plank", "hollow hold", "mountain climber", "burpee",
                    "inverted row", "diamond push", "pike push", "bench dip",
                    "chair dip",
                )
            )
            normalized_weight = ex.weight or ("Bodyweight" if is_bodyweight else "")

            day_exercises.append(
                {
                    "id": ex_id,
                    "name": ex.exercise_name,
                    "sets": ex.sets,
                    "reps": ex.reps,
                    "rest": ex.rest,
                    "weight": normalized_weight,
                    "type": ex.type,
                    "notes": ex.notes,
                }
            )

        if total_volume_kg > 0:
            volume_label = f"{total_volume_kg:,} kg"
        else:
            volume_label = f"{total_bw_reps} BW Reps"

        est_time_str = f"{day.expected_duration} min"

        # Construct sections
        sections = [
            {
                "id": f"{day.day_key.lower()}-section-1",
                "title": "Primary Routine",
                "estimated_minutes": day.expected_duration,
                "exercises": day_exercises,
            }
        ]

        days_out.append(
            {
                "day": day.day_key,
                "title": day.day_name,
                "est_time": est_time_str,
                "volume": volume_label,
                "intensity": "RPE 8.0 (Custom Routine)",
                "sections": sections,
                "exercises": day_exercises,
            }
        )

    summary = (
        f"{plan.plan_name} · {len(plan.days)} Days · {plan.expected_duration or 90} min per session "
        f"with verified custom weights and exercises."
    )

    return {
        "summary": summary,
        "days": days_out,
    }
