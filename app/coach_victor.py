import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib import error, request

from .config import settings

DEFAULT_COUNTRY_NOTES = {
    "DE": "Use European metric conventions and food examples that fit Germany when relevant.",
    "GH": "Use practical guidance that fits Ghanaian food context and warm-climate training routines when relevant.",
    "IN": "Use practical guidance that fits Indian food context and busy urban routines when relevant.",
}

COACH_IDENTITY_LAYER = (
    "Layer 1 - Coach identity:\n"
    "You are Coach Victor, the in-app fitness coach inside the Victory Fitness app. "
    "Answer like a high-quality real coach: practical, direct, personalized, calm, and accountable."
)

MEDICAL_SCOPE_LAYER = (
    "Layer 7 - Medical and scope boundaries:\n"
    "Victory Fitness guidance is educational and fitness-focused. Do not invent diagnoses, do not prescribe medication, "
    "and do not give reckless or crash-diet advice. If the user mentions injury, pain, illness, medication, eating disorder risk, "
    "or medical conditions, include a short safety note and advise qualified medical guidance where appropriate."
)


@dataclass
class CoachVictorResult:
    reply: str


def _safe_text(value: object, default: str = "not provided") -> str:
    text = str(value or "").strip()
    return text or default


def _local_now_for_country(country_code: str | None) -> datetime:
    offsets = {"DE": 2.0, "GH": 0.0, "IN": 5.5}
    offset_minutes = int(offsets.get(str(country_code or "").upper(), 0.0) * 60)
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(minutes=offset_minutes)))


def build_coach_victor_system_prompt(
    *,
    user_context: dict[str, object] | None = None,
    recent_messages: list[dict[str, str]] | None = None,
) -> str:
    context = dict(user_context or {})
    recent_messages = [dict(item) for item in (recent_messages or []) if isinstance(item, dict)][-10:]
    onboarding = dict(context.get("onboarding") or {})
    personal_profile = dict(onboarding.get("personalProfile") or {})
    anamnese = dict(onboarding.get("anamnese") or {})
    nutrition_profile = dict(context.get("nutrition_profile") or {})
    progress = dict(context.get("progress") or {})
    habit_fields = dict(context.get("habit_fields") or {})
    longevity = dict(context.get("longevity") or {})
    medical = dict(context.get("medical") or {})
    country_code = _safe_text(context.get("country_code"), "").upper()
    country = _safe_text(context.get("country"), "not provided")
    local_now = _local_now_for_country(country_code)
    country_note = DEFAULT_COUNTRY_NOTES.get(
        country_code,
        "Use the user's local food, schedule, and unit conventions when possible.",
    )
    today_layer = (
        "Layer 5 - Today's context:\n"
        f"Current local date: {local_now.strftime('%A, %B %d, %Y')}.\n"
        f"Current local time window: {local_now.strftime('%H:%M')}.\n"
        f"User subscription tier: {_safe_text(context.get('subscription_tier'), 'NONE')}."
    )
    country_layer = (
        "Layer 2 - Country context:\n"
        f"User country: {country}.\n"
        f"User country code: {country_code or 'unknown'}.\n"
        f"Country adaptation note: {country_note}"
    )
    profile_layer = (
        "Layer 3 - User profile and personalization:\n"
        f"Age: {_safe_text(personal_profile.get('age'))}.\n"
        f"Gender: {_safe_text(personal_profile.get('gender'))}.\n"
        f"Height: {_safe_text(personal_profile.get('height'))} {_safe_text(personal_profile.get('heightUnit'), 'cm')}.\n"
        f"Weight: {_safe_text(personal_profile.get('weight'))} {_safe_text(personal_profile.get('weightUnit'), 'kg')}.\n"
        f"Primary goal: {_safe_text(anamnese.get('primaryGoal'))}.\n"
        f"Activity level: {_safe_text(anamnese.get('activityLevel'))}.\n"
        f"Days per week: {_safe_text(anamnese.get('daysPerWeek'))}.\n"
        f"Session time: {_safe_text(anamnese.get('timePerSession'))}.\n"
        f"Equipment access: {_safe_text(anamnese.get('equipmentAccess'))}.\n"
        f"Protein target: {_safe_text(nutrition_profile.get('protein_target_g') or nutrition_profile.get('daily_protein'), 'not set')}.\n"
        f"Favorite meals JSON: {json.dumps(nutrition_profile.get('favorite_meals_json') or nutrition_profile.get('favorite_meal') or [], ensure_ascii=False)}.\n"
        f"Allergies: {_safe_text(nutrition_profile.get('allergies'))}.\n"
        f"Health conditions: {json.dumps(nutrition_profile.get('health_conditions') or [], ensure_ascii=False)}.\n"
        f"Motivation statement: {_safe_text(context.get('motivation_statement'))}.\n"
        f"Section 20 habit fields - identity statement: {_safe_text(habit_fields.get('identity_statement'))}.\n"
        f"Section 20 habit fields - workout unlock label: {_safe_text(habit_fields.get('workout_unlock_label'))}.\n"
        f"Section 20 habit fields - training trigger context: {_safe_text(habit_fields.get('training_trigger_context'))}.\n"
        f"Section 20 habit fields - completed habits: {json.dumps(longevity.get('completed_habits') or [], ensure_ascii=False)}.\n"
        f"Section 20 habit fields - pending habits: {json.dumps(longevity.get('pending_habits') or [], ensure_ascii=False)}."
    )
    progress_layer = (
        "Layer 4 - Progress and adaptation data:\n"
        f"Current streak days: {_safe_text(progress.get('streak_days'), '0')}.\n"
        f"Workouts completed: {_safe_text(progress.get('workouts_completed'), '0')}.\n"
        f"Recent 14-day completed workouts: {_safe_text(progress.get('recent_completed_workouts'), '0')}.\n"
        f"Recent 7-day nutrition actions: {_safe_text(progress.get('recent_nutrition_actions'), '0')}.\n"
        f"Latest workout adaptation note: {_safe_text(progress.get('latest_workout_feedback_summary'))}.\n"
        f"Latest nutrition summary: {_safe_text(progress.get('latest_nutrition_summary'))}.\n"
        f"Latest longevity weekly plan focus: {_safe_text(progress.get('weekly_plan_focus'))}."
    )
    conversation_lines = []
    for index, item in enumerate(recent_messages, start=1):
        role = _safe_text(item.get("role"), "user")
        content = _safe_text(item.get("content"), "")
        if content:
            conversation_lines.append(f"{index}. {role}: {content}")
    conversation_layer = (
        "Layer 6 - Last 10 conversation messages:\n"
        + ("\n".join(conversation_lines) if conversation_lines else "No recent conversation history.")
    )
    guidance_layer = (
        "Response rules:\n"
        "Base your answer on the user's actual question, goals, limitations, progress, and recent conversation.\n"
        "Give the direct answer first, then brief reasoning if needed.\n"
        "Prefer concrete sets, reps, exercise choices, scheduling, protein guidance, meal ideas, recovery steps, or behavior changes.\n"
        "If context is incomplete, make a reasonable assumption and state it briefly instead of refusing.\n"
        "Keep answers concise by default and avoid generic filler."
    )
    medical_context_layer = (
        "Medical signals detected from stored profile:\n"
        f"Injury or health notes: {_safe_text(medical.get('health_notes'))}.\n"
        f"Application injury field: {_safe_text(medical.get('injury'))}."
    )
    return "\n\n".join(
        [
            COACH_IDENTITY_LAYER,
            country_layer,
            profile_layer,
            progress_layer,
            today_layer,
            conversation_layer,
            MEDICAL_SCOPE_LAYER,
            medical_context_layer,
            guidance_layer,
        ]
    )


def generate_coach_victor_reply(
    messages: list[dict[str, str]],
    *,
    user_context: dict[str, object] | None = None,
    recent_messages: list[dict[str, str]] | None = None,
) -> CoachVictorResult:
    system_prompt = build_coach_victor_system_prompt(
        user_context=user_context,
        recent_messages=recent_messages or messages,
    )
    if settings.anthropic_api_key:
        reply = _generate_anthropic_reply(messages, system_prompt=system_prompt)
        if reply:
            return CoachVictorResult(reply=reply)

    if settings.openai_api_key:
        reply = _generate_openai_reply(messages, system_prompt=system_prompt)
        if reply:
            return CoachVictorResult(reply=reply)

    raise RuntimeError("No cloud model available for Coach Victor")


def _generate_openai_reply(messages: list[dict[str, str]], *, system_prompt: str) -> str | None:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "temperature": 0.7,
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
        with request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (TimeoutError, error.HTTPError, error.URLError):
        return None

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError):
        return None


def _generate_anthropic_reply(messages: list[dict[str, str]], *, system_prompt: str) -> str | None:
    payload = {
        "model": settings.anthropic_model,
        "system": system_prompt,
        "messages": _normalize_anthropic_messages(messages),
        "max_tokens": 500,
        "temperature": 0.7,
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
        with request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (TimeoutError, error.HTTPError, error.URLError):
        return None

    try:
        parts = [
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ]
        reply = "".join(parts).strip()
    except (KeyError, TypeError):
        reply = ""

    return reply or None


def _normalize_anthropic_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            anthropic_role = "assistant"
        elif role == "user":
            anthropic_role = "user"
        else:
            continue

        content = message.get("content", "").strip()
        if not content:
            continue

        if normalized and normalized[-1]["role"] == anthropic_role:
            normalized[-1]["content"] += f"\n\n{content}"
        else:
            normalized.append({"role": anthropic_role, "content": content})

    if not normalized or normalized[0]["role"] != "user":
        normalized.insert(0, {"role": "user", "content": "Hello Coach Victor."})

    return normalized
