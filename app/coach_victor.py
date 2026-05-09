import json
from dataclasses import dataclass
from urllib import error, request

from .config import settings


COACH_SYSTEM_PROMPT = (
    "You are Coach Victor, an expert fitness coach inside the Victory Fitness app. "
    "Give concise, practical, high-signal fitness guidance. "
    "Prioritize form, safety, consistency, and realistic next steps. "
    "Keep answers short unless the user asks for detail. "
    "Do not mention that you are an AI model. "
    "If the user asks for medical advice, injuries, or anything risky, tell them to consult a qualified professional."
)


@dataclass
class CoachVictorResult:
    reply: str


def generate_coach_victor_reply(messages: list[dict[str, str]]) -> CoachVictorResult:
    if settings.anthropic_api_key:
        reply = _generate_anthropic_reply(messages)
        if reply:
            return CoachVictorResult(reply=reply)

    if settings.openai_api_key:
        reply = _generate_openai_reply(messages)
        if reply:
            return CoachVictorResult(reply=reply)

    return CoachVictorResult(reply=_fallback_coach_reply(messages))


def _generate_openai_reply(messages: list[dict[str, str]]) -> str | None:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
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


def _generate_anthropic_reply(messages: list[dict[str, str]]) -> str | None:
    payload = {
        "model": settings.anthropic_model,
        "system": COACH_SYSTEM_PROMPT,
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


def _fallback_coach_reply(messages: list[dict[str, str]]) -> str:
    user_message = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user_message = message.get("content", "").lower()
            break

    if any(term in user_message for term in ("pain", "injury", "hurt", "ache")):
        return (
            "If you are dealing with pain or an injury, pause the movement and get guidance from a qualified "
            "professional. For now, keep training light, avoid anything that triggers pain, and focus on gentle "
            "mobility and recovery."
        )

    if any(term in user_message for term in ("diet", "meal", "food", "protein", "calorie", "nutrition")):
        return (
            "Start with the basics: include protein in each meal, drink enough water, and build most plates around "
            "lean protein, vegetables, and a steady carb source. Keep it consistent for 7 days before changing too much."
        )

    if any(term in user_message for term in ("workout", "exercise", "train", "gym", "muscle", "strength")):
        return (
            "For a solid session today, do 5 minutes of warm-up, then 3 sets each of squats, push-ups or presses, "
            "rows, and planks. Keep 1 to 2 reps in reserve and focus on clean form."
        )

    if any(term in user_message for term in ("weight loss", "lose weight", "fat loss", "cut")):
        return (
            "For fat loss, keep the plan simple: walk daily, lift 3 to 4 times per week, prioritize protein, and "
            "keep portions controlled. Progress comes from consistency, not extreme restriction."
        )

    return (
        "I can help with training, nutrition, recovery, and consistency. Tell me your goal, your current fitness "
        "level, and how many days per week you can train, and I will suggest a practical next step."
    )
