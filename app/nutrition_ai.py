import json
from dataclasses import dataclass
from urllib import error, request

from .config import settings


NUTRITION_PLAN_SYSTEM_PROMPT = (
    "You are a senior nutrition coach inside the Victory Fitness app. "
    "Create practical, realistic meal plans that match the user's goal and preferences. "
    "Return only valid JSON, with no markdown or extra commentary. "
    "Keep the nutrition advice safe, specific, and easy to follow."
)

NUTRITION_ADVICE_SYSTEM_PROMPT = (
    "You are a senior nutrition coach inside the Victory Fitness app. "
    "Give short, practical, high-signal nutrition guidance. "
    "Keep the advice grounded and user-friendly. "
    "Avoid medical claims and tell the user to consult a professional for medical conditions."
)


@dataclass
class NutritionResult:
    data: dict


@dataclass
class NutritionAdviceResult:
    reply: str


def generate_nutrition_plan(payload: dict) -> NutritionResult:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    prompt = (
        "Create a 7-day nutrition plan in JSON with this exact top-level structure:\n"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        '"days": [{"day":"Mon|Tue|Wed|Thu|Fri|Sat|Sun","breakfast":{...},"lunch":{...},"dinner":{...}}], '
        '"shopping_list": [{"category": string, "items": [{"name": string, "qty": string}]}]'
        "}\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        "Use concise meal names, realistic portions, and keep the plan practical.\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )

    request_payload = {
        "model": settings.anthropic_model,
        "max_tokens": 2048,
        "system": NUTRITION_PLAN_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    data = _anthropic_json(request_payload)
    try:
        content = data["content"]
        text = next(
            block["text"]
            for block in content
            if block.get("type") == "text" and block.get("text")
        ).strip()
        return NutritionResult(data=json.loads(text))
    except (KeyError, IndexError, AttributeError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        raise RuntimeError("Anthropic nutrition plan response was invalid JSON") from exc


def generate_nutrition_advice(payload: dict) -> NutritionAdviceResult:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    prompt = (
        "Give 3 to 5 short bullet-style nutrition suggestions based on this context. "
        "Do not use markdown headings. Keep it concise and useful.\n"
        f"Context: {json.dumps(payload, ensure_ascii=False)}"
    )

    request_payload = {
        "model": settings.anthropic_model,
        "max_tokens": 512,
        "system": NUTRITION_ADVICE_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    data = _anthropic_json(request_payload)
    try:
        content = data["content"]
        reply = next(
            block["text"]
            for block in content
            if block.get("type") == "text" and block.get("text")
        ).strip()
    except (KeyError, IndexError, AttributeError, TypeError, StopIteration) as exc:
        raise RuntimeError("Anthropic nutrition advice response was missing text") from exc

    return NutritionAdviceResult(reply=reply)


def _anthropic_json(payload: dict) -> dict:
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
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic request failed: {exc.reason}") from exc
