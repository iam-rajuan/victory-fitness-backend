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
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

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
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    try:
        reply = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI response was missing message content") from exc

    return CoachVictorResult(reply=reply)
