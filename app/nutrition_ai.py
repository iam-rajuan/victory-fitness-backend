import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import time
from urllib import error, request

from pydantic import BaseModel, Field

from .config import settings
from .models import NutritionPlanResponse


NUTRITION_PLAN_SYSTEM_PROMPT = (
    "You are the senior nutrition coach inside the Victory Fitness app. "
    "Create accurate, practical, realistic nutrition plans that match the user's goal, body data, preferences, dietary pattern, allergies, activity level, and health context. "
    "The plan must feel like something a real person could actually buy, cook, and follow for a full week. "
    "Use foods and portions that are believable, balanced, and aligned with the goal. "
    "Make the meals specific, varied, and easy to understand. "
    "Each meal should include a clear meal name, a short useful description, realistic calories and macros, ingredients that match the meal, and concise step-by-step instructions. "
    "Keep the plan safe and moderate. "
    "Do not use extreme calorie restriction, extreme bulking, fake foods, impossible macros, or medically risky advice. "
    "If the user has allergies or health conditions, respect them carefully and avoid unsafe ingredients. "
    "If the user input is incomplete, infer a sensible practical plan instead of failing. "
    "The weekly summary should clearly describe the plan focus and how it supports the user's goal. "
    "The shopping list should be grouped logically and should match the actual meals in the plan. "
    "Return only valid JSON that matches the required schema exactly, with no markdown, no commentary, and no extra keys."
)

NUTRITION_ADVICE_SYSTEM_PROMPT = (
    "You are the senior nutrition coach inside the Victory Fitness app. "
    "Give accurate, practical, user-friendly nutrition guidance based on the user's context, goal, and meal question. "
    "Keep the advice specific, grounded, and easy to act on today. "
    "Prefer concrete suggestions such as food swaps, meal composition, protein targets, portion adjustments, hydration, timing, or consistency habits. "
    "Keep the tone direct and helpful. "
    "Avoid medical claims, extreme restrictions, or vague motivational filler. "
    "If the user mentions a medical condition, include a short caution and suggest professional guidance."
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

_NUTRITION_PLAN_MEMORY_CACHE: dict[str, dict] = {}


@dataclass
class NutritionResult:
    data: dict


@dataclass
class NutritionAdviceResult:
    reply: str


class NutritionPlanRefusalError(RuntimeError):
    pass


class StructuredNutritionMealItem(BaseModel):
    name: str = Field(description="Ingredient or shopping item name")
    qty: str = Field(description="Human-readable quantity or serving amount")


class StructuredNutritionShoppingSection(BaseModel):
    category: str = Field(description="Logical shopping category such as Proteins, Produce, or Pantry")
    items: list[StructuredNutritionMealItem] = Field(description="Shopping items for this category")


class StructuredNutritionMealEntry(BaseModel):
    name: str = Field(description="Meal name")
    desc: str = Field(description="Short practical meal description")
    kcal: int = Field(description="Approximate calories for the meal")
    p: int = Field(description="Approximate protein grams for the meal")
    c: int = Field(description="Approximate carb grams for the meal")
    f: int = Field(description="Approximate fat grams for the meal")
    ingredients: list[str] = Field(description="List of ingredients used for the meal")
    instructions: list[str] = Field(description="Short ordered preparation steps")


class StructuredNutritionDayPlan(BaseModel):
    day: str = Field(description="Day label using one of Mon Tue Wed Thu Fri Sat Sun")
    breakfast: StructuredNutritionMealEntry
    lunch: StructuredNutritionMealEntry
    dinner: StructuredNutritionMealEntry


class StructuredNutritionPlan(BaseModel):
    summary: str = Field(description="Short weekly summary of the nutrition plan")
    goal_label: str = Field(description="Readable goal label for the user")
    days: list[StructuredNutritionDayPlan] = Field(description="Seven day meal plan")
    shopping_list: list[StructuredNutritionShoppingSection] = Field(description="Grouped weekly shopping list")


def generate_nutrition_plan(payload: dict) -> NutritionResult:
    cache_key = build_nutrition_plan_signature(payload)
    cached_plan = _NUTRITION_PLAN_MEMORY_CACHE.get(cache_key)
    if cached_plan is not None:
        return NutritionResult(data=deepcopy(cached_plan))

    prompt = _build_nutrition_plan_prompt(payload)
    plan_text = _generate_nutrition_plan_json(prompt)
    plan = _parse_or_repair_nutrition_plan(plan_text)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid plan JSON")

    _NUTRITION_PLAN_MEMORY_CACHE[cache_key] = deepcopy(plan)
    return NutritionResult(data=plan)


def build_nutrition_plan_signature(payload: dict) -> str:
    normalized_profile = {
        "provider": "openai" if settings.openai_api_key else "anthropic" if settings.anthropic_api_key else "none",
        "openai_model": settings.openai_model,
        "anthropic_model": settings.anthropic_model,
        "goal": _normalize_text(payload.get("goal"), ""),
        "cuisine": _normalize_text(payload.get("cuisine"), ""),
        "favorite_meal": _normalize_text(payload.get("favorite_meal"), ""),
        "diet": _normalize_text(payload.get("diet"), ""),
        "allergies": _normalize_text(payload.get("allergies"), ""),
        "activity_level": _normalize_text(payload.get("activity_level"), ""),
        "age": _normalize_text(payload.get("age"), ""),
        "gender": _normalize_text(payload.get("gender"), ""),
        "height": _normalize_text(payload.get("height"), ""),
        "weight": _normalize_text(payload.get("weight"), ""),
        "health_conditions": sorted(
            {
                str(item).strip()
                for item in (payload.get("health_conditions") or [])
                if str(item).strip()
            }
        ),
    }
    payload_json = json.dumps(normalized_profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload_json.encode("utf-8")).hexdigest()


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


def _generate_nutrition_plan_json(prompt: str) -> str:
    candidates, provider_errors = _collect_nutrition_plan_candidates(prompt)
    for candidate in candidates:
        normalized = _parse_or_repair_nutrition_plan(candidate)
        if normalized is not None:
            return json.dumps(normalized, ensure_ascii=False)

    if provider_errors:
        raise RuntimeError("; ".join(provider_errors))

    raise RuntimeError("OPENAI_API_KEY or ANTHROPIC_API_KEY is not configured")


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


def _langchain_openai_nutrition_plan_json(prompt: str) -> str:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError("LangChain OpenAI package is not installed") from exc

    try:
        model = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.2,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        )
        structured_llm = model.with_structured_output(
            StructuredNutritionPlan,
            method="json_schema",
            include_raw=False,
            strict=True,
        )
        result = structured_llm.invoke(
            [
                ("system", NUTRITION_PLAN_SYSTEM_PROMPT),
                ("human", prompt),
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"LangChain OpenAI structured output failed: {exc}") from exc

    return _structured_plan_to_json(result)


def _langchain_anthropic_nutrition_plan_json(prompt: str) -> str:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise RuntimeError("LangChain Anthropic package is not installed") from exc

    try:
        model = ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.2,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        )
        structured_llm = model.with_structured_output(
            StructuredNutritionPlan,
            include_raw=False,
        )
        result = structured_llm.invoke(
            [
                ("system", NUTRITION_PLAN_SYSTEM_PROMPT),
                ("human", prompt),
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"LangChain Anthropic structured output failed: {exc}") from exc

    return _structured_plan_to_json(result)


def _structured_plan_to_json(result: object) -> str:
    if isinstance(result, StructuredNutritionPlan):
        return result.model_dump_json()

    if isinstance(result, BaseModel):
        return json.dumps(result.model_dump(), ensure_ascii=False)

    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)

    raise RuntimeError("Structured output did not return a usable nutrition plan object")


def _build_nutrition_plan_prompt(payload: dict) -> str:
    return (
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


def _collect_nutrition_plan_candidates(prompt: str) -> tuple[list[str], list[str]]:
    candidates: list[str] = []
    provider_errors: list[str] = []

    if settings.openai_api_key:
        try:
            _append_candidate(candidates, _langchain_openai_nutrition_plan_json(prompt))
        except RuntimeError as exc:
            provider_errors.append(str(exc))

    if settings.anthropic_api_key:
        try:
            _append_candidate(candidates, _langchain_anthropic_nutrition_plan_json(prompt))
        except RuntimeError as exc:
            provider_errors.append(str(exc))

    return candidates, provider_errors


def _openai_structured_nutrition_plan_json(prompt: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    request_payload = {
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

    data = _openai_responses_json_with_retry(request_payload)
    try:
        return _extract_response_text(data, NutritionPlanRefusalError).strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI nutrition plan response was missing JSON text") from exc


def _anthropic_nutrition_plan_json(prompt: str) -> str:
    payload = {
        "model": settings.anthropic_model,
        "system": (
            f"{NUTRITION_PLAN_SYSTEM_PROMPT} Return only one valid JSON object. "
            "Do not include markdown fences, explanations, or commentary."
        ),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000,
        "temperature": 0.2,
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("Anthropic request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic request failed: {exc.reason}") from exc

    try:
        return "".join(
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Anthropic nutrition plan response was missing text") from exc


def _openai_chat_nutrition_plan_json(prompt: str) -> str:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"{NUTRITION_PLAN_SYSTEM_PROMPT} "
                    "Return exactly one valid JSON object that matches the required schema. "
                    "Do not include markdown fences, explanations, notes, or extra text."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 3000,
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI nutrition fallback request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI nutrition fallback request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI nutrition fallback request failed: {exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI nutrition fallback response was missing JSON text") from exc


def _repair_nutrition_plan_json(text: str) -> str | None:
    if not text.strip():
        return None

    if settings.openai_api_key:
        try:
            return _openai_repair_nutrition_plan_json(text)
        except RuntimeError:
            pass

    if settings.anthropic_api_key:
        try:
            return _anthropic_repair_nutrition_plan_json(text)
        except RuntimeError:
            pass

    return None


def _openai_repair_nutrition_plan_json(raw_text: str) -> str:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You repair malformed nutrition plan output into one valid JSON object. "
                    "Return exactly one valid JSON object that matches the required schema. "
                    "Do not add markdown, commentary, or extra keys. "
                    f"Schema requirement: {json.dumps(NUTRITION_PLAN_JSON_SCHEMA['schema'], ensure_ascii=False)}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Repair this text into valid nutrition plan JSON. "
                    "Preserve the intent and meal content when possible.\n\n"
                    f"{raw_text}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 3200,
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("OpenAI nutrition repair request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI nutrition repair request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI nutrition repair request failed: {exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI nutrition repair response was missing JSON text") from exc


def _anthropic_repair_nutrition_plan_json(raw_text: str) -> str:
    payload = {
        "model": settings.anthropic_model,
        "system": (
            "You repair malformed nutrition plan output into one valid JSON object. "
            "Return exactly one valid JSON object that matches the required schema. "
            "Do not add markdown, commentary, or extra keys. "
            f"Schema requirement: {json.dumps(NUTRITION_PLAN_JSON_SCHEMA['schema'], ensure_ascii=False)}"
        ),
        "messages": [
            {
                "role": "user",
                "content": (
                    "Repair this text into valid nutrition plan JSON. "
                    "Preserve the intended meals and weekly structure when possible.\n\n"
                    f"{raw_text}"
                ),
            }
        ],
        "max_tokens": 3200,
        "temperature": 0,
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
        with request.urlopen(req, timeout=OPENAI_REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError("Anthropic nutrition repair request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic nutrition repair request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic nutrition repair request failed: {exc.reason}") from exc

    try:
        return "".join(
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Anthropic nutrition repair response was missing text") from exc


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
                if isinstance(part.get("text"), str) and part.get("text"):
                    parts.append(part["text"])
                parsed_value = part.get("parsed") or part.get("json")
                if isinstance(parsed_value, dict):
                    parts.append(json.dumps(parsed_value, ensure_ascii=False))

        if parts:
            return "".join(parts)

    raise RuntimeError("OpenAI response was missing output text")


def _parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", cleaned, 0)

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(cleaned[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start:index + 1]
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
                break

    raise json.JSONDecodeError("No valid JSON object found", cleaned, 0)


def _normalize_nutrition_plan(plan: dict) -> dict:
    normalized_days = _normalize_plan_days(plan.get("days", []))
    shopping_list = plan.get("shopping_list", [])
    normalized_plan = {
        "summary": _normalize_text(plan.get("summary"), "A practical weekly nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "days": normalized_days,
        "shopping_list": _normalize_shopping_list(shopping_list, normalized_days),
    }
    return _validate_nutrition_plan(normalized_plan)


def _parse_or_repair_nutrition_plan(text: str) -> dict | None:
    try:
        return _normalize_nutrition_plan(_parse_json_object(text))
    except json.JSONDecodeError:
        pass

    repaired_text = _repair_nutrition_plan_json(text)
    if not repaired_text:
        return None

    try:
        return _normalize_nutrition_plan(_parse_json_object(repaired_text))
    except json.JSONDecodeError:
        return None


def _validate_nutrition_plan(plan: dict) -> dict:
    validated = NutritionPlanResponse(**plan)
    return validated.model_dump(exclude_none=True, exclude={"plan_id", "profile"})


def _append_candidate(candidates: list[str], text: str) -> None:
    cleaned = text.strip()
    if cleaned and cleaned not in candidates:
        candidates.append(cleaned)


def _compact_error(message: str) -> str:
    compact = " ".join(message.split())
    return compact[:220]


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


def _goal_label(goal: object) -> str:
    return {
        "g1": "Weight Loss",
        "g2": "Muscle Building",
        "g3": "Weight Maintenance",
        "g4": "Flexibility and Mobility",
        "g5": "Energy and Endurance",
    }.get(str(goal), "Personalized Nutrition Plan")
