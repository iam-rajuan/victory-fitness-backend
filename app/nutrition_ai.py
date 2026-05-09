import json
from dataclasses import dataclass
import time
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

OPENAI_REQUEST_TIMEOUT_SECONDS = 120
OPENAI_REQUEST_RETRIES = 2
PLAN_DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MEAL_ENTRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "desc", "kcal", "p", "c", "f", "ingredients", "instructions"],
    "properties": {
        "name": {"type": "string"},
        "desc": {"type": "string"},
        "kcal": {"type": "integer", "minimum": 0, "maximum": 3000},
        "p": {"type": "integer", "minimum": 0, "maximum": 300},
        "c": {"type": "integer", "minimum": 0, "maximum": 500},
        "f": {"type": "integer", "minimum": 0, "maximum": 200},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "instructions": {"type": "array", "items": {"type": "string"}},
    },
}

NUTRITION_PLAN_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "nutrition_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "goal_label", "days", "shopping_list"],
        "properties": {
            "summary": {"type": "string"},
            "goal_label": {"type": "string"},
            "days": {
                "type": "array",
                "minItems": 7,
                "maxItems": 7,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["day", "breakfast", "lunch", "dinner"],
                    "properties": {
                        "day": {
                            "type": "string",
                            "enum": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                        },
                        "breakfast": MEAL_ENTRY_SCHEMA,
                        "lunch": MEAL_ENTRY_SCHEMA,
                        "dinner": MEAL_ENTRY_SCHEMA,
                    },
                },
            },
            "shopping_list": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["category", "items"],
                    "properties": {
                        "category": {"type": "string"},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "qty"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "qty": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


@dataclass
class NutritionResult:
    data: dict


@dataclass
class NutritionAdviceResult:
    reply: str


class NutritionPlanRefusalError(RuntimeError):
    pass


def generate_nutrition_plan(payload: dict) -> NutritionResult:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    prompt = (
        "Create a 7-day nutrition plan in JSON with this exact top-level structure:\n"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        '"days": [{"day":"Mon|Tue|Wed|Thu|Fri|Sat|Sun","breakfast":{...},"lunch":{...},"dinner":{...}}], '
        '"shopping_list": [{"category": string, "items": [{"name": string, "qty": string}]}]'
        "}\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        "ingredients must be an array of strings. instructions must be an array of strings.\n"
        "Use concise meal names, realistic portions, and keep the plan practical.\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )

    responses_payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": NUTRITION_PLAN_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "text": {"format": NUTRITION_PLAN_JSON_SCHEMA},
        "max_output_tokens": 2200,
    }

    try:
        data = _openai_responses_json_with_retry(responses_payload)
        text = _extract_response_text(data, NutritionPlanRefusalError)
    except NutritionPlanRefusalError:
        raise
    except RuntimeError:
        text = _fallback_nutrition_plan_json(prompt)

    try:
        return NutritionResult(data=_normalize_nutrition_plan(json.loads(text)))
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI nutrition plan response was invalid JSON") from exc


def generate_nutrition_advice(payload: dict) -> NutritionAdviceResult:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    prompt = (
        "Give 3 to 5 short bullet-style nutrition suggestions based on this context. "
        "Do not use markdown headings. Keep it concise and useful.\n"
        f"Context: {json.dumps(payload, ensure_ascii=False)}"
    )

    request_payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": NUTRITION_ADVICE_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "max_output_tokens": 400,
    }

    data = _openai_responses_json_with_retry(request_payload)
    try:
        reply = _extract_response_text(data).strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI nutrition advice response was missing text") from exc

    return NutritionAdviceResult(reply=reply)


def _openai_responses_json_with_retry(payload: dict) -> dict:
    last_error: Exception | None = None

    for attempt in range(OPENAI_REQUEST_RETRIES):
        try:
            return _openai_responses_json(payload)
        except TimeoutError as exc:
            last_error = exc
        except RuntimeError as exc:
            last_error = exc

        if attempt < OPENAI_REQUEST_RETRIES - 1:
            time.sleep(1.5)

    if isinstance(last_error, RuntimeError):
        raise last_error

    raise RuntimeError("OpenAI request timed out") from last_error


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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc


def _fallback_nutrition_plan_json(prompt: str) -> str:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": NUTRITION_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 2200,
    }

    data = _openai_chat_json_with_retry(payload)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI nutrition plan fallback response was missing JSON text") from exc


def _openai_chat_json_with_retry(payload: dict) -> dict:
    last_error: Exception | None = None

    for attempt in range(OPENAI_REQUEST_RETRIES):
        try:
            return _openai_chat_json(payload)
        except TimeoutError as exc:
            last_error = exc
        except RuntimeError as exc:
            last_error = exc

        if attempt < OPENAI_REQUEST_RETRIES - 1:
            time.sleep(1.5)

    if isinstance(last_error, RuntimeError):
        raise last_error

    raise RuntimeError("OpenAI request timed out") from last_error


def _openai_chat_json(payload: dict) -> dict:
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc


def _extract_response_text(data: dict, refusal_error_cls: type[Exception] = RuntimeError) -> str:
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
                if part.get("type") == "refusal":
                    raise refusal_error_cls(str(part.get("refusal", "Model refused the request")))
                if part.get("type") == "output_text":
                    text = part.get("text", "")
                    if text:
                        parts.append(text)

        if parts:
            return "".join(parts)

    raise RuntimeError("OpenAI response was missing output text")


def _normalize_nutrition_plan(plan: dict) -> dict:
    normalized_days = _normalize_plan_days(plan.get("days", []))
    shopping_list = plan.get("shopping_list", [])

    return {
        "summary": _normalize_text(plan.get("summary"), "A practical weekly nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "days": normalized_days,
        "shopping_list": _normalize_shopping_list(shopping_list, normalized_days),
    }


def _normalize_plan_days(days: object) -> list[dict]:
    by_day: dict[str, dict] = {}
    if isinstance(days, list):
        for raw_day in days:
            if not isinstance(raw_day, dict):
                continue
            normalized_day = _normalize_day_plan(raw_day)
            day_name = normalized_day["day"]
            if day_name not in by_day:
                by_day[day_name] = normalized_day

    return [by_day.get(day_name, _default_day_plan(day_name)) for day_name in PLAN_DAY_ORDER]


def _normalize_day_plan(day: dict) -> dict:
    day_name = str(day.get("day", "")).strip().title()[:3]
    if day_name not in PLAN_DAY_ORDER:
        day_name = PLAN_DAY_ORDER[0]

    return {
        "day": day_name,
        "breakfast": _normalize_meal_entry(day.get("breakfast", {})),
        "lunch": _normalize_meal_entry(day.get("lunch", {})),
        "dinner": _normalize_meal_entry(day.get("dinner", {})),
    }


def _normalize_meal_entry(entry: dict) -> dict:
    ingredients = entry.get("ingredients", [])
    instructions = entry.get("instructions", [])
    normalized_name = _normalize_text(entry.get("name"), "Balanced Meal")
    normalized_desc = _normalize_text(entry.get("desc"), "A practical meal tailored to your plan.")
    normalized_ingredients = _normalize_string_list(ingredients)
    normalized_instructions = _normalize_string_list(instructions)

    if not normalized_ingredients:
        normalized_ingredients = ["Ingredients tailored to your nutrition goal."]

    if not normalized_instructions:
        normalized_instructions = ["Prepare the ingredients and portion the meal to match your plan."]

    return {
        "name": normalized_name,
        "desc": normalized_desc,
        "kcal": _normalize_int(entry.get("kcal"), 450, 0, 3000),
        "p": _normalize_int(entry.get("p"), 30, 0, 300),
        "c": _normalize_int(entry.get("c"), 35, 0, 500),
        "f": _normalize_int(entry.get("f"), 15, 0, 200),
        "ingredients": normalized_ingredients,
        "instructions": normalized_instructions,
    }


def _normalize_shopping_section(section: dict) -> dict:
    items = section.get("items", [])
    return {
        "category": section.get("category", ""),
        "items": [
            {
                "name": item.get("name", ""),
                "qty": item.get("qty", ""),
            }
            for item in items
            if isinstance(item, dict)
        ],
    }


def _normalize_shopping_list(shopping_list: object, days: list[dict]) -> list[dict]:
    if isinstance(shopping_list, list):
        normalized = [_normalize_shopping_section(section) for section in shopping_list if isinstance(section, dict)]
        normalized = [section for section in normalized if section["category"] and section["items"]]
        if normalized:
            return normalized

    fallback_items: list[dict[str, str]] = []
    seen: set[str] = set()
    for day in days:
        for meal_key in ("breakfast", "lunch", "dinner"):
            meal = day.get(meal_key, {})
            for ingredient in meal.get("ingredients", []):
                label = ingredient.strip()
                lowered = label.lower()
                if label and lowered not in seen:
                    seen.add(lowered)
                    fallback_items.append({"name": label, "qty": "1 serving"})

    return [{"category": "Weekly Ingredients", "items": fallback_items[:40]}] if fallback_items else []


def _normalize_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return [part for part in parts if part]

    return []


def _normalize_text(value: object, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _normalize_int(value: object, fallback: int, min_value: int, max_value: int) -> int:
    try:
        normalized = int(float(str(value).strip()))
    except (TypeError, ValueError):
        normalized = fallback

    return max(min_value, min(max_value, normalized))


def _default_day_plan(day_name: str) -> dict:
    return {
        "day": day_name,
        "breakfast": _default_meal_entry(f"{day_name} Breakfast"),
        "lunch": _default_meal_entry(f"{day_name} Lunch"),
        "dinner": _default_meal_entry(f"{day_name} Dinner"),
    }


def _default_meal_entry(name: str) -> dict:
    return {
        "name": name,
        "desc": "A balanced meal placeholder used to complete your weekly plan.",
        "kcal": 450,
        "p": 30,
        "c": 35,
        "f": 15,
        "ingredients": ["Ingredients tailored to your nutrition goal."],
        "instructions": ["Prepare the ingredients and portion the meal to match your plan."],
    }
