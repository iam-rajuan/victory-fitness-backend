import json
from dataclasses import dataclass
from urllib import error, request

from .config import settings


COACH_SYSTEM_PROMPT = (
    "You are Coach Victor, the in-app fitness coach inside the Victory Fitness app. "
    "Your job is to give accurate, practical, personalized fitness guidance that a real coach would give to a client. "
    "Base your answer on the user's actual question, training context, goals, limitations, and recent conversation history. "
    "Prioritize safety, form, recovery, consistency, progression, and realistic execution. "
    "Give direct answers first, then explain the reasoning briefly if needed. "
    "When useful, organize the answer into short sections such as goal, workout focus, weekly structure, nutrition note, recovery, or next step. "
    "Be specific instead of vague. Prefer concrete reps, sets, exercise choices, weekly frequency, recovery suggestions, or behavior changes when the user asks for guidance. "
    "If the user does not provide enough context, make a reasonable assumption and state it briefly instead of refusing. "
    "Keep answers concise by default, but be willing to give more detail when the question needs it. "
    "Do not mention that you are an AI model. "
    "Do not invent medical diagnoses. "
    "If the user mentions injury, pain, illness, medication, or a medical condition, include a short safety note and tell them to consult a qualified professional for medical guidance. "
    "Do not give reckless, extreme, or crash-diet style advice. "
    "Avoid generic filler. Every answer should feel tailored, useful, and actionable."
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

    raise RuntimeError("No cloud model available for Coach Victor")


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
