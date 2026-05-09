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
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 1024,
        "system": COACH_SYSTEM_PROMPT,
        "messages": messages,
    }

    req = request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic request failed: {exc.reason}") from exc

    try:
        content = data["content"]
        reply = next(
            block["text"]
            for block in content
            if block.get("type") == "text" and block.get("text")
        ).strip()
    except (KeyError, IndexError, AttributeError, TypeError, StopIteration) as exc:
        raise RuntimeError("Anthropic response was missing message content") from exc

    return CoachVictorResult(reply=reply)
