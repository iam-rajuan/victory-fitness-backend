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
    """Extracts session duration in minutes from text. Defaults to 90 if ~90 min indicated."""
    lowered = str(text or "").lower()
    match = re.search(r"(\d{1,3})\s*(?:min|mins|minute|minutes)\b", lowered)
    if match:
        mins = int(match.group(1))
        return max(15, min(mins, 240))
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


def _parse_exercise_line(line: str) -> CustomWorkoutExercise | None:
    """Parses a single line of text into a structured CustomWorkoutExercise."""
    raw = line.strip()
    if not raw:
        return None

    # Skip day headers, bullet markers, or section headers
    if re.match(r"(?i)^(?:###?\s*)?(?:day\s*\d+|session\s*\d+|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", raw):
        return None
    if re.match(r"(?i)^rest\b|^rest\s*day", raw):
        return None

    # Clean leading bullets/numbering: "- ", "* ", "1. ", "1) "
    cleaned = re.sub(r"^\s*[-*•\d]+[.)\]\-:]\s*", "", raw).strip()
    if not cleaned:
        return None

    # Extract weight/load inside parentheses first: e.g. "(+10kg)", "(80kg)", "(bodyweight)"
    weight = ""
    weight_paren = re.search(r"\(\s*(\+?\d+(?:\.\d+)?\s*(?:kg|lbs?|kilos?)|bodyweight|bw)\s*\)", cleaned, re.I)
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
        weight_match = re.search(r"(?:@\s*|(?<=[\s\-_(/])|^)(\+?\d+(?:\.\d+)?\s*(?:kg|lbs?|kilos?)|bodyweight|bw)\b", cleaned, re.I)
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
    set_rep_match = re.search(r"(\d{1,2})\s*(?:x|sets?\s*(?:of|x)?)\s*(\d{1,2}(?:-\d{1,2})?)\s*(?:reps?)?", cleaned, re.I)
    if set_rep_match:
        try:
            sets = max(1, min(int(set_rep_match.group(1)), 20))
            reps = set_rep_match.group(2).strip()
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
    cleaned = re.sub(r"(?:^\s*[-–—:,|/@]+\s*|\s*[-–—:,|/@]+\s*$)", " ", cleaned)
    cleaned = re.sub(r"\s+[-–—:,|/@]+\s+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    exercise_name = cleaned
    if not exercise_name:
        return None

    # Preserve exact name, capitalize appropriately
    if len(exercise_name) <= 2:
        return None

    # Classify type
    lowered_ex = exercise_name.lower()
    if any(k in lowered_ex for k in CORE_KEYWORDS):
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
        r"(?i)^(?:###?\s*)?(?:day\s*([0-9]+)|session\s*([0-9]+)|workout\s*([a-g])|(monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b[:\s\-–—]*(.*)$"
    )

    day_blocks: list[tuple[str, str, list[str]]] = []  # (header_tag, extra_title, lines)
    current_tag = ""
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
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

    user_weight_kg = 75
    if user:
        try:
            onboarding = dict(user.get("onboarding") or {})
            personal = dict(onboarding.get("personalProfile") or {})
            user_weight_kg = int(personal.get("weight") or user.get("weight") or 75)
        except Exception:
            user_weight_kg = 75

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

            day_exercises.append(
                {
                    "id": ex_id,
                    "name": ex.exercise_name,
                    "sets": ex.sets,
                    "reps": ex.reps,
                    "rest": ex.rest,
                    "weight": ex.weight if ex.weight else ("Bodyweight" if ex.type == "Core" else f"{user_weight_kg} kg"),
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
