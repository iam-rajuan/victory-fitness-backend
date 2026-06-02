import json
from dataclasses import dataclass
from urllib import error, request

from .config import settings


LONGEVITY_QUICK_ACTION_SYSTEM_PROMPT = (
    "You are the Longevity OS action planner inside the Victory Fitness app. "
    "Generate concise quick actions for the overview screen based on the user's latest synced health data. "
    "Return valid JSON only. "
    "Select up to 5 actions from these allowed ids only: recovery-reset, sleep-protocol, stress-reset, movement-boost, breath-lab. "
    "Each action must be specific to the data, not generic. "
    "Use short labels and one-sentence subtitles that explain why the action matters now."
)

LONGEVITY_QUICK_ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "label", "subtitle", "image", "color"],
                "properties": {
                    "id": {
                        "type": "string",
                        "enum": ["recovery-reset", "sleep-protocol", "stress-reset", "movement-boost", "breath-lab"],
                    },
                    "label": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "image": {"type": "string"},
                    "color": {"type": "string"},
                },
            },
        }
    },
}

QUICK_ACTION_TEMPLATES = {
    "recovery-reset": {
        "id": "recovery-reset",
        "label": "Recovery Reset",
        "subtitle": "Dial down intensity and give your body a cleaner recovery window.",
        "image": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80",
        "color": "#EC4899",
    },
    "sleep-protocol": {
        "id": "sleep-protocol",
        "label": "Sleep Protocol",
        "subtitle": "Protect sleep timing and depth to improve the next recovery cycle.",
        "image": "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=600&q=80",
        "color": "#4F8EF7",
    },
    "stress-reset": {
        "id": "stress-reset",
        "label": "Stress Reset",
        "subtitle": "Lower the pressure signal with a short downshift and calmer pacing.",
        "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600&q=80",
        "color": "#F97316",
    },
    "movement-boost": {
        "id": "movement-boost",
        "label": "Movement Boost",
        "subtitle": "Add a simple walk or light session to raise daily movement volume.",
        "image": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=600&q=80",
        "color": "#10B981",
    },
    "breath-lab": {
        "id": "breath-lab",
        "label": "Breath Lab",
        "subtitle": "Use slow breathing to help HRV, oxygen balance, and nervous-system recovery.",
        "image": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=600&q=80",
        "color": "#14B8A6",
    },
}

LONGEVITY_WEEKLY_PLAN_SYSTEM_PROMPT = (
    "You are the Longevity OS planning engine inside the Victory Fitness app. "
    "Generate a practical, personalized weekly health plan using the user's synced wearable data, "
    "completed habits, and priority health categories. "
    "Write like an elite health coach: direct, specific, realistic, and supportive. "
    "Do not mention that you are an AI model. "
    "Do not invent clinical diagnoses or unsafe medical advice. "
    "Return valid JSON only. "
    "Always include exactly these four sections in this order: "
    "heart_health, post_workout_recovery, mental_health_and_anxiety, immunity_and_infection. "
    "Each section must contain a short summary and exactly 3 concrete actions for this week. "
    "Use the user's actual metrics when relevant."
)

LONGEVITY_WEEKLY_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "sections"],
    "properties": {
        "summary": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "summary", "actions"],
                "properties": {
                    "id": {
                        "type": "string",
                        "enum": [
                            "heart_health",
                            "post_workout_recovery",
                            "mental_health_and_anxiety",
                            "immunity_and_infection",
                        ],
                    },
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "actions": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}

REQUEST_TIMEOUT_SECONDS = 90

SECTION_ORDER = [
    "heart_health",
    "post_workout_recovery",
    "mental_health_and_anxiety",
    "immunity_and_infection",
]

SECTION_TITLES = {
    "heart_health": "Heart Health",
    "post_workout_recovery": "Post Workout Recovery",
    "mental_health_and_anxiety": "Mental Health and Anxiety",
    "immunity_and_infection": "Immunity and Infection",
}


@dataclass
class LongevityWeeklyPlanSection:
    id: str
    title: str
    summary: str
    actions: list[str]


@dataclass
class LongevityWeeklyPlanResult:
    summary: str
    sections: list[LongevityWeeklyPlanSection]


def generate_longevity_weekly_plan(payload: dict) -> LongevityWeeklyPlanResult:
    prompt = _build_prompt(payload)

    if settings.openai_api_key:
        try:
            return _openai_longevity_weekly_plan(prompt)
        except RuntimeError:
            pass

    return _fallback_longevity_weekly_plan(payload)


def generate_longevity_quick_actions(payload: dict) -> list[dict[str, str]]:
    prompt = _build_quick_action_prompt(payload)

    if settings.openai_api_key:
        try:
            return _openai_longevity_quick_actions(prompt)
        except RuntimeError:
            pass

    return _fallback_longevity_quick_actions(payload)


def _build_prompt(payload: dict) -> str:
    user_name = str(payload.get("user_name") or "the user").strip()
    overview = payload.get("overview") or {}
    summary = payload.get("summary") or {}
    focus_areas = [str(item).strip() for item in payload.get("focus_areas") or [] if str(item).strip()]
    habits = [str(item).strip() for item in payload.get("completed_habits") or [] if str(item).strip()]
    categories = [str(item).strip() for item in payload.get("heal_categories") or [] if str(item).strip()]

    return (
        "Create a 7-day longevity weekly plan.\n"
        f"User: {user_name}\n"
        f"Biological age: {overview.get('biological_age', 'N/A')}\n"
        f"Recovery score: {overview.get('recovery_score', 0)}\n"
        f"HRV: {overview.get('hrv_ms', 0)} ms\n"
        f"Sleep score: {overview.get('sleep_score', 0)}\n"
        f"Average sleep: {summary.get('sleep_hours', 0)} hours\n"
        f"Average resting heart rate: {summary.get('heart_rate_bpm', 0)} bpm\n"
        f"Average daily steps: {summary.get('steps', 0)}\n"
        f"Average blood oxygen: {summary.get('spo2_percent', 0)}%\n"
        f"Average stress score: {summary.get('stress_score', 0)}\n"
        f"Workout sessions logged: {summary.get('workouts', 0)}\n"
        f"Priority focus areas: {', '.join(focus_areas) or 'heart health, recovery, mental resilience, immunity'}\n"
        f"Completed habits: {', '.join(habits) or 'none yet'}\n"
        f"Current heal categories: {', '.join(categories) or 'heart health, post workout recovery, mental health and anxiety, immunity and infection'}\n"
        "Use the four required sections. Tailor each section to the data above."
    )


def _build_quick_action_prompt(payload: dict) -> str:
    overview = payload.get("overview") or {}
    summary = payload.get("summary") or {}
    focus_areas = [str(item).strip() for item in payload.get("focus_areas") or [] if str(item).strip()]

    return (
        "Create up to 5 quick actions for the Longevity OS overview screen.\n"
        f"Recovery score: {overview.get('recovery_score', 0)}\n"
        f"HRV: {overview.get('hrv_ms', 0)} ms\n"
        f"Sleep score: {overview.get('sleep_score', 0)}\n"
        f"Average sleep: {summary.get('sleep_hours', 0)} hours\n"
        f"Average resting heart rate: {summary.get('heart_rate_bpm', 0)} bpm\n"
        f"Average daily steps: {summary.get('steps', 0)}\n"
        f"Average blood oxygen: {summary.get('spo2', summary.get('spo2_percent', 0))}%\n"
        f"Average stress score: {summary.get('stress_score', 0)}\n"
        f"Workout sessions logged: {summary.get('workouts', 0)}\n"
        f"Priority focus areas: {', '.join(focus_areas) or 'heart health, recovery, mental resilience, immunity'}\n"
        "Choose only from these actions when they fit the data: recovery-reset, sleep-protocol, stress-reset, movement-boost, breath-lab.\n"
        "Return a short label and a one-sentence subtitle that explains why the action is relevant now."
    )


def _openai_longevity_weekly_plan(prompt: str) -> LongevityWeeklyPlanResult:
    request_payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": LONGEVITY_WEEKLY_PLAN_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "longevity_weekly_plan",
                "schema": LONGEVITY_WEEKLY_PLAN_SCHEMA,
                "strict": True,
            }
        },
        "max_output_tokens": 1400,
    }

    data = _openai_responses_json(request_payload)
    text = _extract_response_text(data).strip()
    if not text:
        raise RuntimeError("OpenAI longevity weekly plan response was empty")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI longevity weekly plan response was not valid JSON") from exc

    return _normalize_plan_payload(parsed)


def _openai_longevity_quick_actions(prompt: str) -> list[dict[str, str]]:
    request_payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": LONGEVITY_QUICK_ACTION_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "longevity_quick_actions",
                "schema": LONGEVITY_QUICK_ACTION_SCHEMA,
                "strict": True,
            }
        },
        "max_output_tokens": 900,
    }

    data = _openai_responses_json(request_payload)
    text = _extract_response_text(data).strip()
    if not text:
        raise RuntimeError("OpenAI longevity quick actions response was empty")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI longevity quick actions response was not valid JSON") from exc

    return _normalize_quick_action_payload(parsed)


def _fallback_longevity_weekly_plan(payload: dict) -> LongevityWeeklyPlanResult:
    overview = payload.get("overview") or {}
    summary = payload.get("summary") or {}
    recovery_score = int(overview.get("recovery_score") or 0)
    sleep_hours = float(summary.get("sleep_hours") or 0)
    hrv_ms = int(summary.get("hrv_ms") or overview.get("hrv_ms") or 0)
    steps = int(summary.get("steps") or 0)
    stress_score = int(summary.get("stress_score") or 0)
    spo2 = int(summary.get("spo2_percent") or 0)

    sections = [
        LongevityWeeklyPlanSection(
            id="heart_health",
            title="Heart Health",
            summary=(
                f"Use your current activity baseline of about {steps} steps per day and HRV around {hrv_ms} ms "
                "to build steadier cardiovascular output this week without spiking fatigue."
            ),
            actions=[
                "Complete 3 moderate cardio sessions of 25 to 35 minutes at conversational pace.",
                "Add one 10-minute brisk walk after your two largest meals to improve circulation and glucose handling.",
                "Keep one full lower-intensity day after your hardest training session to support heart-rate recovery.",
            ],
        ),
        LongevityWeeklyPlanSection(
            id="post_workout_recovery",
            title="Post Workout Recovery",
            summary=(
                f"Your recovery score is {recovery_score}% with average sleep near {sleep_hours:.1f} hours, "
                "so this week should prioritize sleep quality, tissue recovery, and workout spacing."
            ),
            actions=[
                "Finish each workout with 5 to 8 minutes of easy cooldown walking and nasal breathing.",
                "Aim for a consistent sleep window and protect the first 90 minutes before bed from hard training and screens.",
                "Use one active recovery session with mobility, light cycling, or walking instead of another intense workout.",
            ],
        ),
        LongevityWeeklyPlanSection(
            id="mental_health_and_anxiety",
            title="Mental Health and Anxiety",
            summary=(
                f"Your recent stress score is around {stress_score}, so this plan uses lower-friction routines "
                "to calm the nervous system and improve mental steadiness."
            ),
            actions=[
                "Do 5 minutes of slow breathing or box breathing after waking and again after your workday.",
                "Schedule one phone-free 20-minute walk outside on at least 4 days this week.",
                "Reduce late caffeine and create a short shutdown routine at night to lower background anxiety load.",
            ],
        ),
        LongevityWeeklyPlanSection(
            id="immunity_and_infection",
            title="Immunity and Infection",
            summary=(
                f"With sleep at {sleep_hours:.1f} hours and oxygen around {spo2}%, your immunity focus this week "
                "should be built around recovery consistency, hydration, and avoiding excessive training strain."
            ),
            actions=[
                "Keep hydration steady across the day and increase fluids around training sessions.",
                "Prioritize protein, colorful produce, and regular meal timing for the next 7 days.",
                "If sleep drops or fatigue rises, swap one hard session for mobility and extra recovery instead of pushing through.",
            ],
        ),
    ]

    return LongevityWeeklyPlanResult(
        summary="Your weekly longevity plan is ready and built from your latest synced recovery, sleep, movement, stress, and oxygen data.",
        sections=sections,
    )


def _fallback_longevity_quick_actions(payload: dict) -> list[dict[str, str]]:
    overview = payload.get("overview") or {}
    summary = payload.get("summary") or {}
    recovery_score = int(overview.get("recovery_score") or 0)
    sleep_hours = float(summary.get("sleep_hours") or 0)
    hrv_ms = int(summary.get("hrv_ms") or overview.get("hrv_ms") or 0)
    steps = int(summary.get("steps") or 0)
    stress_score = int(summary.get("stress_score") or 0)
    spo2 = int(summary.get("spo2") or summary.get("spo2_percent") or 0)

    selected_ids: list[str] = []
    if recovery_score < 75:
        selected_ids.append("recovery-reset")
    if sleep_hours < 7:
        selected_ids.append("sleep-protocol")
    if stress_score > 38:
        selected_ids.append("stress-reset")
    if steps < 9000:
        selected_ids.append("movement-boost")
    if hrv_ms < 40 or (spo2 and spo2 < 97):
        selected_ids.append("breath-lab")
    if not selected_ids:
        selected_ids.extend(["movement-boost", "sleep-protocol", "breath-lab"])

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for action_id in selected_ids:
        if action_id in seen:
            continue
        seen.add(action_id)
        template = QUICK_ACTION_TEMPLATES.get(action_id)
        if template:
            deduped.append(dict(template))
    return deduped[:5]


def _normalize_plan_payload(parsed: dict) -> LongevityWeeklyPlanResult:
    raw_sections = parsed.get("sections") if isinstance(parsed, dict) else None
    raw_summary = parsed.get("summary") if isinstance(parsed, dict) else ""
    mapped: dict[str, LongevityWeeklyPlanSection] = {}

    if isinstance(raw_sections, list):
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            section_id = str(item.get("id") or "").strip()
            if section_id not in SECTION_ORDER:
                continue
            actions = [
                str(action).strip()
                for action in item.get("actions") or []
                if str(action).strip()
            ][:3]
            while len(actions) < 3:
                actions.append("Stay consistent with the plan and review your recovery signals daily.")
            mapped[section_id] = LongevityWeeklyPlanSection(
                id=section_id,
                title=str(item.get("title") or SECTION_TITLES[section_id]).strip() or SECTION_TITLES[section_id],
                summary=str(item.get("summary") or "").strip(),
                actions=actions,
            )

    sections = [
        mapped.get(section_id) or LongevityWeeklyPlanSection(
            id=section_id,
            title=SECTION_TITLES[section_id],
            summary=f"This week's {SECTION_TITLES[section_id].lower()} plan is ready.",
            actions=[
                "Review your current wearable recovery signals before training.",
                "Follow the lowest-friction action that supports this category today.",
                "Reassess this category again after your next data sync.",
            ],
        )
        for section_id in SECTION_ORDER
    ]

    summary_text = str(raw_summary or "").strip() or "Your weekly longevity plan is ready."
    return LongevityWeeklyPlanResult(summary=summary_text, sections=sections)


def _normalize_quick_action_payload(parsed: dict) -> list[dict[str, str]]:
    raw_items = parsed.get("items") if isinstance(parsed, dict) else None
    mapped: list[dict[str, str]] = []

    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            action_id = str(item.get("id") or "").strip()
            template = QUICK_ACTION_TEMPLATES.get(action_id)
            if not template:
                continue
            mapped.append(
                {
                    "id": action_id,
                    "label": str(item.get("label") or template["label"]).strip() or template["label"],
                    "subtitle": str(item.get("subtitle") or template["subtitle"]).strip() or template["subtitle"],
                    "image": str(item.get("image") or template["image"]).strip() or template["image"],
                    "color": str(item.get("color") or template["color"]).strip() or template["color"],
                }
            )

    if not mapped:
        return _fallback_longevity_quick_actions(parsed if isinstance(parsed, dict) else {})

    deduped: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in mapped:
        action_id = str(item.get("id") or "")
        if action_id and action_id not in seen_ids:
            seen_ids.add(action_id)
            deduped.append(item)

    return deduped[:5]


def _openai_responses_json(payload: dict) -> dict:
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI longevity weekly plan request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI longevity weekly plan request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI longevity weekly plan request failed: {exc.reason}") from exc


def _extract_response_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = data.get("output", [])
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text" and part.get("text"):
                    parts.append(str(part["text"]))
                elif isinstance(part.get("text"), str) and part.get("text"):
                    parts.append(part["text"])
        if parts:
            return "".join(parts)

    raise RuntimeError("OpenAI longevity weekly plan response was missing text")
