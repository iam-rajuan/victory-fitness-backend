import json
import re
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import time
from typing import Any
from urllib import error, request
import base64
import io
from PIL import Image

from pydantic import BaseModel, Field

from .config import settings
from .country_food_data import (
    build_country_food_prompt_context,
    country_food_dataset_version,
    get_country_food_dataset,
)
from .models import NutritionPlanResponse, build_meal_specific_prep_steps


NUTRITION_PLAN_SYSTEM_PROMPT = (
    "You are the senior professional nutrition coach inside the Victory Fitness app. "
    "You behave like an experienced nutrition coach who designs personalized, balanced, safe 7-day meal plans. "
    "Meal-plan generation must strictly follow this priority order (favourite foods must NEVER outrank safety, goals, or targets):\n"
    "1. Allergies / safety / dietary restrictions (HARD SAFETY EXCEPTION: If a favourite food conflicts with an allergy or medical restriction, it must NEVER be recommended).\n"
    "2. User fitness goal (weight loss calorie deficit, muscle building surplus/recovery, or maintenance).\n"
    "3. Calorie target.\n"
    "4. Macro and protein requirements (strictly meet the calculated protein target: ~1.6g/kg for maintenance, ~2.0-2.2g/kg for muscle gain/weight reduction).\n"
    "5. Country-approved / culturally appropriate foods (prioritize approved country dataset when active; country priority does NOT mean repeating one dish every day).\n"
    "6. Nutritional quality.\n"
    "7. Weekly meal variety (diverse meals across the week; avoid repetitive meals across consecutive days).\n"
    "8. Favourite-food health/suitability preference ('Healthy for me' vs 'Not healthy for me' are personal user contexts, not medical diagnoses):\n"
    "   - Favourite + 'Not healthy for me': User loves it but wants it limited. Allow occasionally (approximately 1–3 meals across the 7-day plan, ~1–2 for weight loss, ~2–3 for maintenance/muscle gain). NEVER recommend it daily. Control portions, choose better pairings, and offer healthier variety on other days.\n"
    "   - Favourite + 'Healthy for me': User loves and considers it suitable. Prioritize more regularly when appropriate, but STILL maintain weekly variety and nutritional targets. Do not recommend it every day.\n"
    "   - Favourite + unspecified: Treat as general preference; include occasionally (approx 2–3 meals/week) when fitting macros; do not repeat daily.\n"
    "9. Favourite-food preference (a preference, NOT something that appears every day).\n"
    "10. Budget / preparation time / practical preferences.\n"
    "Each meal must include: name, desc, kcal, p, c, f, ingredients, instructions. "
    "Kcal must equal (p * 4) + (c * 4) + (f * 9) within ±5 kcal. "
    "Return only valid JSON that matches the required schema exactly, with no markdown, no commentary, and no extra keys."
)

NUTRITION_ADVICE_SYSTEM_PROMPT = (
    "You are the senior nutrition coach inside the Victory Fitness app. "
    "Give accurate, practical, user-friendly nutrition guidance based on the user's context, goal, and meal question. "
    "Your output is rendered directly in the frontend as short action cards. "
    "Keep the advice specific, grounded, and easy to act on today. "
    "Prefer concrete suggestions such as food swaps, meal composition, protein targets, portion adjustments, hydration, timing, or consistency habits. "
    "Keep the tone direct and helpful. "
    "Do not write paragraphs, headings, introductions, conclusions, markdown, or explanatory filler. "
    "Return one short actionable instruction per line. "
    "Each line should stand alone and read cleanly inside a mobile card. "
    "Avoid medical claims, extreme restrictions, or vague motivational filler. "
    "If the user mentions a medical condition, include a short caution and suggest professional guidance."
)

MEAL_IMAGE_ANALYSIS_SYSTEM_PROMPT = (
    "You are the senior nutrition coach inside the Victory Fitness app. "
    "Analyze the provided meal photo and estimate what the dish is, how balanced it looks, and rough macros. "
    "Be practical and conservative with estimates. "
    "If the image is unclear, say so and keep the estimate cautious. "
    "Return only valid JSON that matches the required schema exactly, with no markdown, no commentary, and no extra keys."
)

MEAL_DOCUMENT_ANALYSIS_SYSTEM_PROMPT = (
    "You are the senior nutrition coach inside the Victory Fitness app. "
    "Analyze the provided meal document, meal notes, typed description, nutrition label text, or food log. "
    "Infer what the person likely ate, estimate rough macros conservatively, and keep the summary practical. "
    "If the text is incomplete, messy, or ambiguous, say so clearly and keep the estimate cautious. "
    "Return only valid JSON that matches the required schema exactly, with no markdown, no commentary, and no extra keys."
)

OPENAI_REQUEST_TIMEOUT_SECONDS = 300
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
                    "required": ["day", "breakfast", "lunch", "pre_workout", "post_workout", "dinner"],
                    "properties": {
                        "day": {
                            "type": "string",
                            "enum": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                        },
                        "breakfast": MEAL_ENTRY_SCHEMA,
                        "lunch": MEAL_ENTRY_SCHEMA,
                        "pre_workout": MEAL_ENTRY_SCHEMA,
                        "post_workout": MEAL_ENTRY_SCHEMA,
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

NUTRITION_PLAN_MONDAY_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "nutrition_plan_monday",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "goal_label", "day"],
        "properties": {
            "summary": {"type": "string"},
            "goal_label": {"type": "string"},
            "day": {
                "type": "object",
                "additionalProperties": False,
                "required": ["day", "breakfast", "lunch", "pre_workout", "post_workout", "dinner"],
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": ["Mon"],
                    },
                    "breakfast": MEAL_ENTRY_SCHEMA,
                    "lunch": MEAL_ENTRY_SCHEMA,
                    "pre_workout": MEAL_ENTRY_SCHEMA,
                    "post_workout": MEAL_ENTRY_SCHEMA,
                    "dinner": MEAL_ENTRY_SCHEMA,
                },
            },
        },
    },
}

NUTRITION_PLAN_DAY_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "nutrition_plan_day",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "goal_label", "day"],
        "properties": {
            "summary": {"type": "string"},
            "goal_label": {"type": "string"},
            "day": {
                "type": "object",
                "additionalProperties": False,
                "required": ["day", "breakfast", "lunch", "pre_workout", "post_workout", "dinner"],
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": PLAN_DAY_ORDER,
                    },
                    "breakfast": MEAL_ENTRY_SCHEMA,
                    "lunch": MEAL_ENTRY_SCHEMA,
                    "pre_workout": MEAL_ENTRY_SCHEMA,
                    "post_workout": MEAL_ENTRY_SCHEMA,
                    "dinner": MEAL_ENTRY_SCHEMA,
                },
            },
        },
    },
}

MEAL_IMAGE_ANALYSIS_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "meal_image_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "meal_name_guess",
            "summary",
            "estimated_calories",
            "estimated_protein",
            "estimated_carbs",
            "estimated_fat",
            "confidence",
            "notes",
        ],
        "properties": {
            "meal_name_guess": {"type": "string"},
            "summary": {"type": "string"},
            "estimated_calories": {"type": "integer", "minimum": 0, "maximum": 3000},
            "estimated_protein": {"type": "integer", "minimum": 0, "maximum": 300},
            "estimated_carbs": {"type": "integer", "minimum": 0, "maximum": 500},
            "estimated_fat": {"type": "integer", "minimum": 0, "maximum": 200},
            "confidence": {"type": "string"},
            "notes": {"type": "array", "items": {"type": "string"}},
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


@dataclass
class MealImageAnalysisResult:
    data: dict


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
    preparation_steps: list[str] = Field(default_factory=list, description="Short ordered preparation steps")


class StructuredNutritionDayPlan(BaseModel):
    day: str = Field(description="Day label using one of Mon Tue Wed Thu Fri Sat Sun")
    breakfast: StructuredNutritionMealEntry
    lunch: StructuredNutritionMealEntry
    dinner: StructuredNutritionMealEntry
    pre_workout: StructuredNutritionMealEntry = Field(description="Pre-workout fuel meal (60-90m before workout, carb-forward)")
    post_workout: StructuredNutritionMealEntry = Field(description="Post-workout recovery meal (within 45m after workout, high protein)")


class StructuredNutritionPlan(BaseModel):
    summary: str = Field(description="Short weekly summary of the nutrition plan")
    goal_label: str = Field(description="Readable goal label for the user")
    days: list[StructuredNutritionDayPlan] = Field(description="Seven day meal plan")
    shopping_list: list[StructuredNutritionShoppingSection] = Field(description="Grouped weekly shopping list")


def generate_nutrition_plan(payload: dict) -> NutritionResult:
    cache_key = build_nutrition_plan_signature(payload)
    if not payload.get("regenerate") and not payload.get("force_refresh"):
        cached_plan = _NUTRITION_PLAN_MEMORY_CACHE.get(cache_key)
        if cached_plan is not None:
            return NutritionResult(data=deepcopy(cached_plan))

    prompt = _build_nutrition_plan_prompt(payload)
    plan_text = _generate_nutrition_plan_json(prompt)
    plan = _parse_or_repair_nutrition_plan(plan_text, payload=payload)
    if plan is None:
        plan = _build_fallback_nutrition_plan(payload)

    _NUTRITION_PLAN_MEMORY_CACHE[cache_key] = deepcopy(plan)
    return NutritionResult(data=plan)


def generate_progressive_nutrition_plan_monday(payload: dict) -> NutritionResult:
    prompt = _build_progressive_nutrition_plan_monday_prompt(payload)
    plan_text = _generate_nutrition_plan_monday_json(prompt)
    plan = _parse_or_repair_nutrition_plan_monday(plan_text, payload=payload)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid Monday plan JSON")

    return NutritionResult(data=plan)


def generate_progressive_nutrition_plan_completion(payload: dict, monday_plan: dict) -> NutritionResult:
    prompt = _build_progressive_nutrition_plan_completion_prompt(payload, monday_plan)
    plan_text = _generate_nutrition_plan_completion_json(prompt)
    plan = _parse_or_repair_nutrition_plan(plan_text, payload=payload)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid completion plan JSON")

    monday_days = _normalize_plan_days(monday_plan.get("days", []), day_order=["Mon"])
    if monday_days:
        remaining_days = [day for day in plan["days"] if day.get("day") != "Mon"]
        plan["days"] = monday_days + remaining_days

    return NutritionResult(data=_normalize_nutrition_plan(plan, payload=payload))


def generate_progressive_nutrition_plan_day(
    payload: dict,
    day_name: str,
    previous_days: list[dict],
) -> NutritionResult:
    normalized_day = str(day_name).strip().title()[:3]
    if normalized_day not in PLAN_DAY_ORDER:
        normalized_day = PLAN_DAY_ORDER[0]

    prompt = _build_progressive_nutrition_plan_day_prompt(payload, normalized_day, previous_days)
    plan_text = _generate_nutrition_plan_day_json(prompt)
    plan = _parse_or_repair_nutrition_day_plan(plan_text, normalized_day, payload=payload)
    if plan is None:
        raise RuntimeError(f"The nutrition model did not return valid {normalized_day} plan JSON")

    return NutritionResult(data=plan)


def build_nutrition_plan_signature(payload: dict) -> str:
    favorite_meals = [
        str(item).strip()
        for item in (payload.get("favorite_meals") or payload.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    fav_prefs = payload.get("favorite_meals_preferences") or {}
    if not fav_prefs and payload.get("favorite_foods_details"):
        fav_prefs = {
            item.get("name"): item.get("health_preference", "unspecified")
            for item in payload.get("favorite_foods_details")
            if isinstance(item, dict) and item.get("name")
        }
    normalized_prefs = sorted(
        [(str(k).strip().lower(), str(v).strip().lower()) for k, v in fav_prefs.items()]
    )
    normalized_profile = {
        "provider": "openai" if settings.openai_api_key else "anthropic" if settings.anthropic_api_key else "none",
        "openai_model": settings.openai_model,
        "anthropic_model": settings.anthropic_model,
        "goal": _normalize_text(payload.get("goal"), ""),
        "cuisine": _normalize_text(payload.get("cuisine"), ""),
        "country": _normalize_text(payload.get("country") or payload.get("user_country"), ""),
        "country_code": _normalize_text(payload.get("country_code") or payload.get("countryCode") or payload.get("user_country_code"), "").upper(),
        "country_food_dataset_version": country_food_dataset_version(payload),
        "favorite_meal": _normalize_text(payload.get("favorite_meal"), ""),
        "favorite_meals": favorite_meals,
        "favorite_meals_preferences": normalized_prefs,
        "diet": _normalize_text(payload.get("diet"), ""),
        "allergies": _normalize_text(payload.get("allergies"), ""),
        "activity_level": _normalize_text(payload.get("activity_level"), ""),
        "age": _normalize_text(payload.get("age"), ""),
        "gender": _normalize_text(payload.get("gender"), ""),
        "height": _normalize_text(payload.get("height"), ""),
        "weight": _normalize_text(payload.get("weight"), ""),
        "cooking_time_weekday": _normalize_text(payload.get("cooking_time_weekday"), ""),
        "people_cooking_for": _normalize_text(payload.get("people_cooking_for"), ""),
        "weekly_food_budget": _normalize_text(payload.get("weekly_food_budget"), ""),
        "weekly_food_budget_amount": payload.get("weekly_food_budget_amount"),
        "weekly_food_budget_currency": _normalize_text(payload.get("weekly_food_budget_currency"), "").upper(),
        "language": _normalize_text(payload.get("language") or payload.get("preferred_language"), "en").lower(),
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


def _parse_weight_kg(weight: Any) -> float:
    if weight is None:
        return 70.0
    s = str(weight).strip().lower()
    if not s:
        return 70.0
    try:
        if "lb" in s:
            num = float(re.sub(r"[^\d.]", "", s))
            return num * 0.45359237
        num = float(re.sub(r"[^\d.]", "", s))
        return num if num > 0 else 70.0
    except Exception:
        return 70.0


def calculate_protein_target(weight: Any, goal: str | None = None) -> tuple[int, float]:
    weight_kg = _parse_weight_kg(weight)
    goal_code = str(goal or "").strip().lower()

    # Maintenance / normal goal: minimum approximately 1.6 g protein per kg bodyweight
    if (
        goal_code in {"g3", "maintenance", "normal", "weight maintenance", "weight_maintenance"}
        or "maintenance" in goal_code
        or "normal" in goal_code
    ):
        multiplier = 1.6
    # Weight-reduction goal: approximately 2.2 g/kg according to client requested product logic
    elif (
        goal_code in {"g1", "weight reduction", "weight_reduction", "weight loss", "weight_loss", "fat loss", "fat_loss", "cutting", "deficit"}
        or any(term in goal_code for term in ["weight reduction", "weight_reduction", "weight loss", "weight_loss", "lose weight", "fat loss", "fat_loss", "cutting", "deficit"])
    ):
        multiplier = 2.2
    # Muscle-growth goal: target up to approximately 2.2 g/kg
    elif (
        goal_code in {"g2", "muscle gain", "muscle_gain", "muscle building", "muscle_building", "muscle growth", "muscle_growth", "hypertrophy"}
        or any(term in goal_code for term in ["muscle", "hypertrophy", "mass gain", "mass_gain", "build muscle"])
    ):
        multiplier = 2.2
    else:
        multiplier = 1.6

    daily_protein = max(int(round(weight_kg * multiplier)), 60)
    return daily_protein, multiplier


def _favorite_meals_instruction(payload: dict) -> str:
    favorite_meals = [
        str(item).strip()
        for item in (payload.get("favorite_meals") or payload.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    if payload.get("favorite_meal") and str(payload.get("favorite_meal")).strip():
        fav = str(payload.get("favorite_meal")).strip()
        if fav not in favorite_meals:
            favorite_meals.insert(0, fav)

    fav_prefs = payload.get("favorite_meals_preferences") or {}
    if not fav_prefs and payload.get("favorite_foods_details"):
        fav_prefs = {
            item.get("name"): item.get("health_preference", "unspecified")
            for item in payload.get("favorite_foods_details")
            if isinstance(item, dict) and item.get("name")
        }

    cuisine = str(payload.get("cuisine") or "").strip()
    country_dataset = get_country_food_dataset(payload)

    instructions = [
        "CRITICAL FAVOURITE MEALS & CULINARY MANDATE:",
        "- The 7-day meal plan must balance the user's declared favourite meals with professional nutrition coaching.",
        "- STRICT HIERARCHY OF PRIORITIES:",
        "  1. Allergies / safety / dietary restrictions. HARD SAFETY EXCEPTION: If a favourite food conflicts with an allergy or medical restriction, it must NEVER appear.",
        "  2. User fitness goal (calorie deficit for weight loss, surplus/protein for muscle gain, maintenance).",
        "  3. Calorie target.",
        "  4. Macro and protein requirements (strictly meet protein target).",
        "  5. Country-approved / culturally appropriate foods.",
        "  6. Nutritional quality.",
        "  7. Weekly meal variety (diverse dishes, no identical meals on consecutive days).",
        "  8. Favourite-food health/suitability preference.",
        "  9. Favourite-food preference (a preference, NOT something that appears every day).",
        "  10. Budget / prep time / practical preferences.",
    ]

    if country_dataset:
        instructions.append(
            f"- Approved {country_dataset['country']} Food Dataset is ACTIVE. Prioritize authentic dishes from this approved dataset. Country priority does NOT mean repeating one favourite dish every day. Provide variety across the week."
        )
    else:
        instructions.append(
            "- STRICTLY FORBIDDEN: NEVER fall back to or introduce country-of-origin, geographic, or regional defaults when favourite meals or cuisine are specified. For example, if a user is located in or from Ghana but lists Italian cuisine and favourites such as pasta, pizza, or risotto, every main meal must stay Italian or inspired by those favourites."
        )

    if favorite_meals:
        instructions.append(f"- User's Explicit Favourite Meals: {', '.join(favorite_meals)}.")
        instructions.append("- USER DECLARED FAVOURITE FOODS AND SPECIFIC FREQUENCY INSTRUCTIONS:")
        for meal in favorite_meals:
            pref = fav_prefs.get(meal) or fav_prefs.get(meal.lower()) or "unspecified"
            pref = str(pref).strip().lower()
            if pref == "not_healthy_for_me":
                instructions.append(
                    f"  * Favourite Food: '{meal}'\n"
                    f"    - User status: Favourite, marked 'Not healthy for me'.\n"
                    f"    - Coaching interpretation: The user enjoys this food, but it should be limited.\n"
                    f"    - Frequency constraint: Include it approximately 1–3 meals across the 7-day plan (normally 1–2 meals for weight loss, 2–3 for maintenance/muscle gain). ONLY when compatible with calories, macros, and restrictions.\n"
                    f"    - STRICT COACHING RULES: Do NOT recommend it every day. Do NOT recommend on consecutive days. Control portions, choose better pairings, and recommend healthier alternatives across the rest of the week."
                )
            elif pref == "healthy_for_me":
                instructions.append(
                    f"  * Favourite Food: '{meal}'\n"
                    f"    - User status: Favourite, marked 'Healthy for me'.\n"
                    f"    - Coaching interpretation: Preferred and suitable food.\n"
                    f"    - Frequency constraint: May be recommended more regularly where appropriate (e.g. 3–4 meals/week), while STILL maintaining weekly meal variety, macro balance, and country-food diversity. Do not recommend it every day."
                )
            else:
                instructions.append(
                    f"  * Favourite Food: '{meal}'\n"
                    f"    - User status: Favourite (health preference unspecified / unknown).\n"
                    f"    - Coaching interpretation: General preference.\n"
                    f"    - Frequency constraint: Include occasionally (approx 2–3 meals/week) when compatible with calorie and protein targets. Do not recommend every day."
                )

    if cuisine:
        instructions.append(f"- User's Target Cuisine: {cuisine}. Keep all meal recipes authentic to this cuisine style.")
    return "\n".join(instructions) + "\n"


def _workout_nutrient_timing_instruction(payload: dict) -> str:
    workout_time = str(payload.get("workout_time") or "17:30").strip()
    target_protein, multiplier = calculate_protein_target(payload.get("weight"), payload.get("goal"))
    return (
        "WORKOUT NUTRIENT TIMING & MEAL SCHEDULING REQUIREMENTS:\n"
        f"- User's planned workout time is {workout_time} (or on scheduled workout training days).\n"
        "- Generate SEPARATE DISTINCT MEALS for: 'breakfast', 'lunch', 'pre_workout', 'post_workout', 'dinner'.\n"
        "- PRE-WORKOUT MEAL ('pre_workout'): Scheduled 60–90 minutes BEFORE workout (e.g. at 16:00 for a 17:30 workout). "
        "It MUST be CARB-FORWARD (high complex carbohydrates 45–60g+, moderate protein 15–22g, low fat <= 6g) to maximize glycogen and stamina.\n"
        "- POST-WORKOUT MEAL ('post_workout'): Scheduled within 45 minutes AFTER workout ends (e.g. by 18:45). "
        "It MUST be PROTEIN-FORWARD (high complete protein >= 30–40g, moderate carbs 30–45g, low fat) to trigger muscle protein synthesis.\n"
        f"- All 5 meals must sum accurately to the daily calorie and protein targets ({multiplier}g/kg ±5g, ~{target_protein}g protein/day). No calculation should be missed.\n"
        "- In the meal description ('desc'), explicitly note the timing and purpose.\n"
    )


def _protein_target_instruction(payload: dict) -> str:
    weight_val = (
        payload.get("weight")
        or (payload.get("profile") if isinstance(payload.get("profile"), dict) else {}).get("weight")
        or payload.get("baseline_weight")
    )
    weight_kg = _parse_weight_kg(weight_val)
    goal = (
        payload.get("goal")
        or (payload.get("profile") if isinstance(payload.get("profile"), dict) else {}).get("goal")
        or payload.get("goal_label")
    )
    target_protein, multiplier = calculate_protein_target(weight_kg, goal)
    return (
        f"CRITICAL DETERMINISTIC PROTEIN CONSTRAINT:\n"
        f"- The daily protein target for this {weight_kg}kg user is EXACTLY {target_protein}g/day ({multiplier}g/kg bodyweight).\n"
        f"- Do NOT alter, arbitrarily calculate, or guess a different protein requirement.\n"
        f"PROTEIN ACCURACY TARGET: Daily protein across the 7-day plan must hit approximately {target_protein}g ({multiplier}g/kg ±5g, tolerance range {target_protein - 5}g–{target_protein + 5}g). "
        f"For this {weight_kg}kg user, ensure the daily total across all 5 meals (breakfast, lunch, pre_workout, post_workout, dinner) strictly hits approximately {target_protein}g/day. "
        f"Distribute across all 5 meals: ~{int(round(target_protein * 0.20))}g breakfast, ~{int(round(target_protein * 0.25))}g lunch, ~{int(round(target_protein * 0.15))}g pre_workout, ~{int(round(target_protein * 0.25))}g post_workout, ~{int(round(target_protein * 0.15))}g dinner. "
        "Strict Macro Math: For each meal, kcal must equal (p * 4) + (c * 4) + (f * 9) within ±5 kcal. All meals must sum accurately to the daily calorie and protein totals.\n"
    )


def _meal_plan_practical_constraints_instruction(payload: dict) -> str:
    cooking_time = str(payload.get("cooking_time_weekday") or "").strip()
    people = str(payload.get("people_cooking_for") or "").strip()
    budget_amount = payload.get("weekly_food_budget_amount")
    budget_currency = str(payload.get("weekly_food_budget_currency") or "").strip().upper()
    budget = (
        f"{budget_amount} {budget_currency}"
        if budget_amount is not None and budget_currency
        else str(payload.get("weekly_food_budget") or "").strip()
    )
    instructions = ["PRACTICAL WEEKLY PLANNING CONSTRAINTS:"]
    if cooking_time:
        instructions.append(f"- Weekday cooking/prep time target: {cooking_time}. Keep weekday meals at or below this where possible.")
    if people:
        instructions.append(f"- Scale recipes and shopping quantities for {people} people/portions.")
    if budget:
        instructions.append(f"- Weekly food budget: {budget}. Prefer cost-aware ingredients and reuse staples across meals.")
    if len(instructions) == 1:
        return ""
    instructions.append("- Reflect these constraints in the summary, meal choices, preparation steps, and shopping list quantities.")
    return "\n".join(instructions) + "\n"


def _format_approved_meal(item: dict) -> str:
    sides = ", ".join(str(side) for side in item.get("with", []) if str(side).strip())
    return f"{item.get('dish', 'Ghanaian meal')} with {sides}" if sides else str(item.get("dish") or "Ghanaian meal")


def _ghanaian_fallback_meals(payload: dict) -> dict[str, list[str]] | None:
    dataset = get_country_food_dataset(payload)
    if not dataset or dataset.get("country") != "Ghana":
        return None

    favorite_meals = [
        str(item).strip().lower()
        for item in (payload.get("favorite_meals") or payload.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    cuisine = _normalize_text(payload.get("cuisine"), "").lower()
    approved_terms = {
        str(item.get("dish") or "").lower()
        for items in dataset["meals"].values()
        for item in items
    }
    explicitly_non_ghanaian = bool(favorite_meals) and "ghana" not in cuisine and not any(
        any(term and term in meal for term in approved_terms)
        for meal in favorite_meals
    )
    if explicitly_non_ghanaian:
        return None

    return {
        meal_period: [_format_approved_meal(item) for item in items]
        for meal_period, items in dataset["meals"].items()
    }


COUNTRY_NATIONALITY_MAP: dict[str, str] = {
    "ghana": "Ghanaian",
    "gh": "Ghanaian",
    "germany": "German",
    "de": "German",
    "italy": "Italian",
    "it": "Italian",
    "nigeria": "Nigerian",
    "ng": "Nigerian",
    "india": "Indian",
    "in": "Indian",
    "mexico": "Mexican",
    "mx": "Mexican",
    "turkey": "Turkish",
    "tr": "Turkish",
    "spain": "Spanish",
    "es": "Spanish",
    "france": "French",
    "fr": "French",
    "japan": "Japanese",
    "jp": "Japanese",
    "china": "Chinese",
    "cn": "Chinese",
    "uk": "British",
    "gb": "British",
    "united kingdom": "British",
    "us": "American",
    "usa": "American",
    "united states": "American",
    "bangladesh": "Bangladeshi",
    "bd": "Bangladeshi",
}


def build_concise_nutrition_summary(plan: dict, payload: dict | None = None) -> str:
    """
    Build a structured, concise 2-line nutrition plan summary without large AI introductory essays.
    Example:
    '7-day Ghanaian maintenance plan • ~2,100 kcal/day • 112g protein/day.
    Nut allergy respected. Meals prioritize authentic Ghanaian options and your stated preferences.'
    """
    payload = payload or {}
    profile = plan.get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    days = plan.get("days") or []
    day_count = 7 if (not days or len(days) <= 1 or len(days) == 7) else len(days)

    # 1. Dynamic Calorie Target
    total_kcal = sum(
        sum(meal.get("kcal", 0) for k, meal in d.items() if k != "day" and isinstance(meal, dict))
        for d in days
    ) if days else 0
    avg_kcal = int(round((total_kcal / max(len(days), 1)) / 50.0) * 50) if days and total_kcal > 0 else 2100

    # 2. Dynamic Protein Target
    daily_protein = plan.get("daily_protein_target")
    if not daily_protein and days:
        daily_protein = sum(
            sum(meal.get("p", 0) for k, meal in d.items() if k != "day" and isinstance(meal, dict))
            for d in days
        ) // max(len(days), 1)
    if not daily_protein:
        daily_protein = 120

    # 3. Primary Goal
    goal_code = str(profile.get("goal") or payload.get("goal") or "").lower()
    goal_label = str(plan.get("goal_label") or profile.get("goal_label") or payload.get("goal_label") or "").strip()
    goal_map = {
        "g1": "weight loss",
        "g2": "muscle building",
        "g3": "maintenance",
        "g4": "flexibility",
        "g5": "endurance",
    }
    if goal_code in goal_map:
        goal_text = goal_map[goal_code]
    elif goal_label and goal_label.lower() not in {"personalized nutrition plan", "nutrition plan", "custom plan"}:
        goal_text = goal_label.lower().replace("weight maintenance", "maintenance")
    else:
        goal_text = "balanced nutrition"

    # 4. Country / Cuisine Context
    raw_cuisine = str(
        profile.get("cuisine")
        or payload.get("cuisine")
        or profile.get("country")
        or payload.get("country")
        or ""
    ).strip()

    is_ghanaian = (
        "ghana" in raw_cuisine.lower()
        or str(payload.get("country_code", "")).upper() == "GH"
        or str(profile.get("country_code", "")).upper() == "GH"
        or any(
            any(
                k != "day"
                and isinstance(m, dict)
                and any(
                    dish in str(m.get("name", "")).lower()
                    for dish in ["waakye", "fufu", "banku", "kenkey", "jollof", "red red", "nkate nkwan"]
                )
                for k, m in d.items()
            )
            for d in days[:2]
        )
    )

    if is_ghanaian:
        cuisine_label = "Ghanaian"
    elif raw_cuisine.lower() in COUNTRY_NATIONALITY_MAP:
        cuisine_label = COUNTRY_NATIONALITY_MAP[raw_cuisine.lower()]
    elif raw_cuisine and raw_cuisine.lower() not in {"balanced", "custom", "none", "standard"}:
        cuisine_label = raw_cuisine.capitalize()
    else:
        cuisine_label = ""

    cuisine_prefix = f"{cuisine_label} " if cuisine_label else ""
    line1 = f"{day_count}-day {cuisine_prefix}{goal_text} plan • ~{avg_kcal:,} kcal/day • {daily_protein}g protein/day."

    # 5. Major Dietary Restrictions / Allergies
    allergies = str(profile.get("allergies") or payload.get("allergies") or "").strip().lower()
    diet = str(profile.get("diet") or payload.get("diet") or "").strip().lower()

    dietary_notes = []
    if allergies and allergies not in {"none", "no", "n/a", ""}:
        clean_allergies = allergies.replace("allergies", "").replace("allergy", "").strip()
        dietary_notes.append(f"{clean_allergies.title()} allergy respected.")

    diet_labels = {
        "d2": "Vegetarian diet respected.",
        "vegetarian": "Vegetarian diet respected.",
        "d3": "Vegan diet respected.",
        "vegan": "Vegan diet respected.",
        "d4": "Keto/low-carb diet respected.",
        "keto": "Keto diet respected.",
        "low-carb": "Low-carb diet respected.",
    }
    if diet in diet_labels:
        dietary_notes.append(diet_labels[diet])

    diet_part = " ".join(dietary_notes)
    if diet_part:
        diet_part += " "

    # 6. Cuisine & Preference Priority
    if is_ghanaian:
        pref_part = (
            "Meals prioritize authentic Ghanaian options and your stated preferences. "
            "It prioritizes the approved Ghanaian food dataset and preserves local dish combinations."
        )
    elif cuisine_label:
        pref_part = f"Meals prioritize authentic {cuisine_label} options and your stated preferences."
    else:
        pref_part = "Meals prioritize balanced options and your stated preferences."

    line2 = f"{diet_part}{pref_part}".strip()
    return f"{line1}\n{line2}"


def _build_fallback_nutrition_plan(payload: dict) -> dict:
    goal_code = _normalize_text(payload.get("goal"), "").lower()
    diet_code = _normalize_text(payload.get("diet"), "").lower()
    cuisine = _normalize_text(payload.get("cuisine"), "").strip()
    workout_time = _normalize_text(payload.get("workout_time"), "17:30").strip()
    favorite_meals = [
        str(item).strip()
        for item in (payload.get("favorite_meals") or payload.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    if payload.get("favorite_meal") and str(payload.get("favorite_meal")).strip():
        fav = str(payload.get("favorite_meal")).strip()
        if fav not in favorite_meals:
            favorite_meals.insert(0, fav)

    favorite_meal = favorite_meals[0] if favorite_meals else ("balanced meals" if not cuisine else f"{cuisine} meals")
    allergies = _normalize_text(payload.get("allergies"), "").lower()
    health_conditions = _normalize_string_list(payload.get("health_conditions"))
    ghanaian_meals = _ghanaian_fallback_meals(payload)

    goal_label_map = {
        "g1": "Weight Loss",
        "g2": "Muscle Building",
        "g3": "Weight Maintenance",
        "g4": "Flexibility & Mobility",
        "g5": "Energy & Endurance",
    }
    goal_label = goal_label_map.get(goal_code, "Personalized Nutrition Plan")

    protein_name = "Chicken breast"
    breakfast_protein = "Greek yogurt"
    if diet_code in {"d2", "vegetarian"}:
        protein_name = "Paneer and lentils"
        breakfast_protein = "Greek yogurt"
    elif diet_code in {"d3", "vegan"}:
        protein_name = "Tofu and chickpeas"
        breakfast_protein = "Soy yogurt"
    elif diet_code in {"d4", "keto / low-carb", "keto", "low-carb"}:
        protein_name = "Eggs and salmon"
        breakfast_protein = "Eggs"

    if "nut" in allergies or "peanut" in allergies:
        breakfast_side = "berries"
    else:
        breakfast_side = "berries and seeds"

    # User favorite meals remain important; approved Ghanaian data is used when Ghana/Ghanaian context is active.
    has_explicit_favs = len(favorite_meals) > 0
    display_cuisine = cuisine if cuisine else ("Italian" if any("pasta" in f.lower() or "pizza" in f.lower() or "risotto" in f.lower() for f in favorite_meals) else "balanced")

    weight_kg = _parse_weight_kg(payload.get("weight"))
    daily_protein, multiplier = calculate_protein_target(payload.get("weight"), goal_code)

    breakfast_p = max(int(round(daily_protein * 0.20)), 12)
    lunch_p = max(int(round(daily_protein * 0.25)), 18)
    pre_p = max(int(round(daily_protein * 0.15)), 12)
    post_p = max(int(round(daily_protein * 0.25)), 25)
    dinner_p = max(daily_protein - (breakfast_p + lunch_p + pre_p + post_p), 12)

    is_low_carb = diet_code in {"d4", "keto / low-carb", "keto", "low-carb"} or goal_code == "g1"
    base_carb = 24 if is_low_carb else 42

    fav_prefs = payload.get("favorite_meals_preferences") or {}
    if not fav_prefs and payload.get("favorite_foods_details"):
        fav_prefs = {
            item.get("name"): item.get("health_preference", "unspecified")
            for item in payload.get("favorite_foods_details")
            if isinstance(item, dict) and item.get("name")
        }

    safe_favs: list[tuple[str, str]] = []
    for f in favorite_meals:
        f_norm = f.strip().lower()
        if ("nut" in allergies or "peanut" in allergies) and ("peanut" in f_norm or "groundnut" in f_norm or "nut" in f_norm):
            continue
        if ("shellfish" in allergies or "shrimp" in allergies) and ("shrimp" in f_norm or "prawn" in f_norm or "crab" in f_norm or "lobster" in f_norm):
            continue
        p_val = fav_prefs.get(f) or fav_prefs.get(f.lower()) or "unspecified"
        safe_favs.append((f, str(p_val).lower()))

    # Filter ghanaian_meals by allergies to avoid unsafe defaults
    if ghanaian_meals:
        safe_ghana_dinners = []
        for d in ghanaian_meals["dinner"]:
            d_str = str(d).lower()
            if ("nut" in allergies or "peanut" in allergies) and ("groundnut" in d_str or "peanut" in d_str):
                continue
            if ("shellfish" in allergies or "shrimp" in allergies) and ("crab" in d_str or "shrimp" in d_str or "prawn" in d_str):
                continue
            safe_ghana_dinners.append(d)
        if not safe_ghana_dinners:
            safe_ghana_dinners = ghanaian_meals["dinner"]

        non_fufu_dinners = [d for d in safe_ghana_dinners if "fufu" not in str(d).lower()]
        fufu_dinners = [d for d in safe_ghana_dinners if "fufu" in str(d).lower()]
        if not non_fufu_dinners:
            non_fufu_dinners = safe_ghana_dinners
    else:
        safe_ghana_dinners = []
        non_fufu_dinners = []
        fufu_dinners = []

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days: list[dict] = []

    for index, day_name in enumerate(day_names):
        base_kcal = 380 + (index % 3) * 20
        carb_target = base_carb + (0 if is_low_carb else (index % 2) * 6)

        if ghanaian_meals:
            breakfast_name = ghanaian_meals["breakfast"][index % len(ghanaian_meals["breakfast"])]
            lunch_dish = ghanaian_meals["lunch"][index % len(ghanaian_meals["lunch"])]
            # Default to diverse authentic Ghanaian dinners (avoid repeating Fufu every day)
            dinner_dish = non_fufu_dinners[index % len(non_fufu_dinners)]

            if safe_favs:
                top_fav, top_pref = safe_favs[0]
                if top_pref == "not_healthy_for_me":
                    if goal_code in {"g1", "weight loss", "weight_loss", "fat loss", "fat_loss", "weight reduction"}:
                        if index == 1:
                            lunch_dish = top_fav
                    else:
                        if index == 1:
                            lunch_dish = top_fav
                        elif index == 4:
                            dinner_dish = top_fav
                elif top_pref == "healthy_for_me":
                    if index == 0:
                        lunch_dish = top_fav
                    elif index == 2:
                        dinner_dish = top_fav
                    elif index == 5:
                        lunch_dish = top_fav
                else:
                    if index == 1:
                        lunch_dish = top_fav
                    elif index == 4:
                        dinner_dish = top_fav
            else:
                if index == 1 and len(fufu_dinners) > 1:
                    dinner_dish = fufu_dinners[1]
                elif index == 4 and fufu_dinners:
                    dinner_dish = fufu_dinners[0]
        elif safe_favs:
            breakfast_name = f"{display_cuisine.capitalize()} Protein Breakfast Bowl" if index % 2 == 0 else f"{display_cuisine.capitalize()} Scrambled Eggs & Toast"
            top_fav, top_pref = safe_favs[0]
            if top_pref == "not_healthy_for_me":
                if goal_code in {"g1", "weight loss", "weight_loss", "fat loss", "fat_loss", "weight reduction"}:
                    lunch_dish = top_fav if index == 1 else f"{display_cuisine.capitalize()} Grilled Chicken & Rice"
                    dinner_dish = f"Herb Roasted {protein_name} & Vegetables" if index != 1 else f"Baked Fish & Steamed Greens"
                else:
                    lunch_dish = top_fav if index == 1 else (f"{display_cuisine.capitalize()} Grilled Salmon Plate" if index == 3 else f"{display_cuisine.capitalize()} Chicken Bowl")
                    dinner_dish = top_fav if index == 4 else f"Roasted {protein_name} & Vegetables"
            elif top_pref == "healthy_for_me":
                lunch_dish = top_fav if index in {0, 5} else f"{display_cuisine.capitalize()} Grilled Chicken & Rice"
                dinner_dish = top_fav if index == 2 else f"Herb Roasted {protein_name} & Vegetables"
            else:
                lunch_dish = top_fav if index == 1 else f"{display_cuisine.capitalize()} Grilled Chicken & Rice"
                dinner_dish = top_fav if index == 4 else f"Roasted {protein_name} & Vegetables"
        else:
            lunch_dish = f"{display_cuisine.capitalize()} Rice & Protein Plate"
            dinner_dish = f"Roasted {protein_name} & Vegetables"
            breakfast_name = "Protein Oats Bowl" if index % 2 == 0 else "Egg & Toast Plate"

        pre_workout_timing = f"Scheduled 60–90 mins before {workout_time} workout (e.g. 16:00)"
        post_workout_timing = "Scheduled within 45 mins after workout (e.g. 18:45)"

        pre_dish = "Rolled Oats & Banana Energy Fuel" if ghanaian_meals else f"{display_cuisine.capitalize()} Energy Oats Bowl"
        post_dish = "Grilled Chicken Breast with White Rice" if ghanaian_meals else f"Roasted {protein_name} Recovery Plate"

        lunch_c = max(carb_target + 10, 52)
        pre_c = max(carb_target + 18, 55)
        post_c = 36
        dinner_c = max(18, carb_target - 8)

        b_kcal = (breakfast_p * 4) + (carb_target * 4) + (10 * 9)
        l_kcal = (lunch_p * 4) + (lunch_c * 4) + (11 * 9)
        pre_kcal = (pre_p * 4) + (pre_c * 4) + (5 * 9)
        post_kcal = (post_p * 4) + (post_c * 4) + (7 * 9)
        d_kcal = (dinner_p * 4) + (dinner_c * 4) + (12 * 9)

        if ghanaian_meals:
            breakfast_ingredients = [breakfast_name, "Portion adjusted to match calories and protein", "Water or unsweetened tea"]
            lunch_ingredients = [lunch_dish, "Lean protein portion adjusted to target", "Vegetable or salad side where suitable"]
            dinner_ingredients = [dinner_dish, "Soup/stew pairing preserved from approved Ghana dataset", "Extra fish, egg, chicken, beans, or wagashi as needed for protein"]
            pre_ingredients = [pre_dish, "Small carb-forward portion", "Water"]
            post_ingredients = [post_dish, "Protein-forward recovery portion", "Water"]
        else:
            breakfast_ingredients = [
                breakfast_protein,
                "Oats or whole grain bread",
                breakfast_side,
                "Cinnamon or light seasoning",
            ]
            lunch_ingredients = [
                protein_name,
                "Pasta, rice, or grains matching favorite dish",
                "Steamed vegetables or salad",
                "1 tsp olive oil",
                "Herbs and spices",
            ]
            dinner_ingredients = [
                protein_name,
                "Seasonal vegetables",
                "Light complex carbs",
                "Garlic and olive oil",
                "Fresh herbs",
            ]
            pre_ingredients = [
                "Whole-grain banana toast or oats with honey",
                "Light whey or plant protein shake",
                "1 medium banana or dates",
            ]
            post_ingredients = [
                protein_name,
                "Steamed jasmine rice or sweet potato",
                "Steamed greens with sea salt",
                "Electrolyte water",
            ]

        days.append(
            {
                "day": day_name,
                "breakfast": {
                    "name": breakfast_name,
                    "desc": f"Morning energy anchor built around {breakfast_protein.lower()} and {breakfast_side}.",
                    "kcal": b_kcal,
                    "p": breakfast_p,
                    "c": carb_target,
                    "f": 10,
                    "timing": "Morning (07:30–08:30)",
                    "ingredients": [
                        *breakfast_ingredients,
                    ],
                    "instructions": [
                        "Prepare the base protein and whole grains.",
                        "Top with fruit or light seasoning.",
                        "Enjoy with water or black coffee.",
                    ],
                },
                "lunch": {
                    "name": lunch_dish,
                    "desc": f"Midday fuel meal featuring {lunch_dish} with balanced macronutrients (Pre-workout 60–90 mins before training).",
                    "kcal": l_kcal,
                    "p": lunch_p,
                    "c": lunch_c,  # Carb-forward substantial
                    "f": 11,
                    "timing": "Midday (12:30–13:30)",
                    "ingredients": [
                        *lunch_ingredients,
                    ],
                    "instructions": [
                        "Cook grains or pasta al dente.",
                        "Sear or grill protein with aromatic herbs.",
                        "Plate together with fresh greens.",
                    ],
                },
                "pre_workout": {
                    "name": f"Pre-Workout: {pre_dish}",
                    "desc": f"Pre-workout fuel ({pre_workout_timing}): Carb-forward energy snack to saturate glycogen stores.",
                    "kcal": pre_kcal,
                    "p": pre_p,
                    "c": pre_c,  # High carb-forward
                    "f": 5,  # Low fat
                    "timing": f"60–90m before workout ({workout_time})",
                    "ingredients": [
                        *pre_ingredients,
                    ],
                    "instructions": [
                        "Consume 60 to 90 minutes before your workout.",
                        "Drink 350-500ml water for optimal cellular hydration.",
                    ],
                },
                "post_workout": {
                    "name": f"Post-Workout: {post_dish}",
                    "desc": f"Post-workout recovery ({post_workout_timing}): High complete protein to trigger muscle repair.",
                    "kcal": post_kcal,
                    "p": post_p,  # High protein-forward
                    "c": post_c,
                    "f": 7,
                    "timing": "Within 45m of workout end",
                    "ingredients": [
                        *post_ingredients,
                    ],
                    "instructions": [
                        "Consume within 45 minutes of completing your workout.",
                        "Rehydrate with water and essential electrolytes.",
                    ],
                },
                "dinner": {
                    "name": dinner_dish,
                    "desc": f"Balanced evening recovery dinner featuring {dinner_dish} providing sustained overnight amino acids and micronutrients.",
                    "kcal": d_kcal,
                    "p": dinner_p,  # Recovery protein
                    "c": dinner_c,
                    "f": 12,
                    "timing": "Evening (19:30–20:30)",
                    "ingredients": [
                        *dinner_ingredients,
                    ],
                    "instructions": [
                        "Cook protein through to lock in amino acids.",
                        "Steam or roast fresh greens.",
                        "Enjoy as a restful evening recovery meal.",
                    ],
                },
            }
        )

    if ghanaian_meals:
        shopping_list = [
            {
                "category": "Ghanaian Staples",
                "items": [
                    {"name": "Waakye rice and beans / rice", "qty": "3-5 servings"},
                    {"name": "Banku, fufu, kenkey, yam, or ampesi staples", "qty": "7-10 portions"},
                    {"name": "Gari and talia", "qty": "1 pack each"},
                ],
            },
            {
                "category": "Proteins",
                "items": [
                    {"name": "Fish, tilapia, smoked herring, or fried fish", "qty": "6-8 portions"},
                    {"name": "Chicken, goat, eggs, or wagashi", "qty": "7-10 portions"},
                    {"name": "Crab, wele, mushrooms, or beans where suitable", "qty": "3-5 portions"},
                ],
            },
            {
                "category": "Soups, Sauces & Produce",
                "items": [
                    {"name": "Shito, kpakpo shito, pepper sauce", "qty": "1 batch/jar"},
                    {"name": "Kontomire, okro, ayoyo, or soup vegetables", "qty": "7 servings"},
                    {"name": "Plantain, avocado, salad vegetables, milk, bread", "qty": "as needed for the selected meals"},
                ],
            },
        ]
    else:
        shopping_list = [
            {
                "category": "Proteins",
                "items": [
                    {"name": breakfast_protein, "qty": "5-7 servings"},
                    {"name": protein_name, "qty": "7-10 servings"},
                    {"name": "Eggs or plant protein backup", "qty": "1 carton/pack"},
                ],
            },
            {
                "category": "Carbohydrates & Grains",
                "items": [
                    {"name": "Oats / Whole-grain bread", "qty": "1 pack"},
                    {"name": "Pasta, Rice or specialty grains for favorite meals", "qty": "1-2 kg"},
                ],
            },
            {
                "category": "Produce & Fresh",
                "items": [
                    {"name": "Fresh vegetables for sides", "qty": "7-10 cups"},
                    {"name": "Leafy greens", "qty": "4 bags"},
                    {"name": "Fresh berries or fruit", "qty": "7 servings"},
                ],
            },
        ]

    summary = build_concise_nutrition_summary(
        {
            "days": days,
            "goal_label": goal_label,
            "daily_protein_target": daily_protein,
        },
        payload=payload,
    )

    return _normalize_nutrition_plan(
        {
            "summary": summary,
            "goal_label": goal_label,
            "daily_protein_target": daily_protein,
            "protein_per_kg": multiplier,
            "baseline_weight": weight_kg,
            "days": days,
            "shopping_list": shopping_list,
        },
        payload=payload,
    )


def generate_nutrition_advice(payload: dict) -> NutritionAdviceResult:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    is_tracker_request = not _normalize_text(payload.get("meal_query"), "")
    prompt = (
        "The frontend will split your response by line breaks and show each line as a separate practical action.\n"
        "Return only plain text lines.\n"
    )
    if is_tracker_request:
        prompt += (
            "This is the nutrition tracker coaching panel.\n"
            "Return 4 to 6 short practical actions for the rest of today based on the user's goal and daily totals.\n"
            "No intro text. No summary. One action per line.\n"
        )
    else:
        prompt += (
            "This is a direct nutrition advice response.\n"
            "Return 3 to 5 short practical actions answering the user's meal question.\n"
            "No intro text. No summary. One action per line.\n"
        )
    prompt += f"Context: {json.dumps(payload, ensure_ascii=False)}"

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


def _build_fallback_meal_analysis(file_name: str | None = None) -> MealImageAnalysisResult:
    clean_name = "Balanced Meal Plate"
    if file_name:
        stem = re.sub(r"\.[^.]+$", "", file_name).replace("-", " ").replace("_", " ").strip().title()
        if stem and len(stem) > 2:
            clean_name = stem

    return MealImageAnalysisResult(
        data={
            "meal_name_guess": clean_name,
            "summary": f"Nutritional estimate for {clean_name.lower()} based on typical single-serving meal composition.",
            "estimated_calories": 520,
            "estimated_protein": 34,
            "estimated_carbs": 48,
            "estimated_fat": 18,
            "confidence": "medium",
            "notes": [
                "Macros estimated based on standard portion sizing for this dish.",
                "Provides lean protein with balanced complex carbohydrates.",
                "Adjust portion sizes to align with your daily calorie and macro goals.",
            ],
        }
    )


def generate_meal_image_analysis(payload: dict) -> MealImageAnalysisResult:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    image_base64 = _normalize_text(payload.get("image_base64"), "")
    mime_type = _normalize_text(payload.get("mime_type"), "image/jpeg").lower()
    if not image_base64:
        raise RuntimeError("Meal image analysis requires image data")

    # Normalize image to JPEG and cap dimensions with PIL if image_base64 is present
    supported_formats = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if image_base64:
        try:
            raw_bytes = base64.b64decode(image_base64)
            with Image.open(io.BytesIO(raw_bytes)) as img:
                if mime_type not in supported_formats or img.format not in ("JPEG", "PNG", "GIF", "WEBP"):
                    rgb_img = img.convert("RGB")
                    rgb_img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    rgb_img.save(buf, format="JPEG", quality=85)
                    image_base64 = base64.b64encode(buf.getvalue()).decode("ascii")
                    mime_type = "image/jpeg"
        except Exception:
            if mime_type not in supported_formats:
                mime_type = "image/jpeg"

    image_data_url = f"data:{mime_type};base64,{image_base64}"

    request_payload = {
        "model": settings.openai_meal_analysis_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": MEAL_IMAGE_ANALYSIS_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analyze this meal photo and estimate the dish, macros, and practical nutrition notes. "
                            "Be careful and conservative. "
                            "Return only the JSON object requested by the schema."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                    },
                ],
            },
        ],
        "text": {"format": MEAL_IMAGE_ANALYSIS_JSON_SCHEMA},
        "max_output_tokens": 1000,
    }

    data = _openai_responses_json_with_retry(request_payload)
    try:
        result_text = _extract_response_text(data).strip()
        parsed = _parse_json_object(result_text)
    except (KeyError, IndexError, AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError("OpenAI meal image analysis response was missing valid JSON") from exc

    normalized = {
        "meal_name_guess": _normalize_text(parsed.get("meal_name_guess"), "Meal"),
        "summary": _normalize_text(parsed.get("summary"), "A practical meal estimate could not be generated."),
        "estimated_calories": _normalize_int(parsed.get("estimated_calories"), 0, 0, 3000),
        "estimated_protein": _normalize_int(parsed.get("estimated_protein"), 0, 0, 300),
        "estimated_carbs": _normalize_int(parsed.get("estimated_carbs"), 0, 0, 500),
        "estimated_fat": _normalize_int(parsed.get("estimated_fat"), 0, 0, 200),
        "confidence": _normalize_text(parsed.get("confidence"), "medium"),
        "notes": _normalize_string_list(parsed.get("notes")),
    }
    return MealImageAnalysisResult(data=normalized)


def generate_meal_document_analysis(payload: dict) -> MealImageAnalysisResult:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    text_content = _normalize_text(payload.get("text_content"), "")
    file_name = _normalize_text(payload.get("file_name"), "")
    if not text_content:
        raise RuntimeError("Meal document analysis requires extracted text")

    request_payload = {
        "model": settings.openai_meal_analysis_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": MEAL_DOCUMENT_ANALYSIS_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analyze this meal document or meal notes and estimate the dish, macros, and practical nutrition notes. "
                            "Be careful and conservative. "
                            "If the text is partial, derive the most likely meal estimate from what is present. "
                            f"Source file: {file_name or 'unknown'}\n\n"
                            f"Meal document text:\n{text_content}\n\n"
                            "Return only the JSON object requested by the schema."
                        ),
                    },
                ],
            },
        ],
        "text": {"format": MEAL_IMAGE_ANALYSIS_JSON_SCHEMA},
        "max_output_tokens": 1000,
    }

    data = _openai_responses_json_with_retry(request_payload)
    try:
        result_text = _extract_response_text(data).strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI meal document analysis response was missing text") from exc

    parsed = _parse_json_object(result_text)
    normalized = {
        "meal_name_guess": _normalize_text(parsed.get("meal_name_guess"), "Meal"),
        "summary": _normalize_text(parsed.get("summary"), "A practical meal estimate could not be generated."),
        "estimated_calories": _normalize_int(parsed.get("estimated_calories"), 0, 0, 3000),
        "estimated_protein": _normalize_int(parsed.get("estimated_protein"), 0, 0, 300),
        "estimated_carbs": _normalize_int(parsed.get("estimated_carbs"), 0, 0, 500),
        "estimated_fat": _normalize_int(parsed.get("estimated_fat"), 0, 0, 200),
        "confidence": _normalize_text(parsed.get("confidence"), "medium"),
        "notes": _normalize_string_list(parsed.get("notes")),
    }

    return MealImageAnalysisResult(data=normalized)


def _generate_nutrition_plan_json(prompt: str) -> str:
    if settings.anthropic_api_key:
        try:
            candidate = _langchain_anthropic_nutrition_plan_json(prompt)
        except RuntimeError:
            candidate = _anthropic_nutrition_plan_json(prompt)

        normalized = _parse_or_repair_nutrition_plan(candidate)
        if normalized is not None:
            return json.dumps(normalized, ensure_ascii=False)
        raise RuntimeError("Anthropic nutrition response could not be normalized into a valid plan")

    raise RuntimeError("ANTHROPIC_API_KEY is not configured for nutrition plan generation")


def _generate_nutrition_plan_monday_json(prompt: str) -> str:
    if settings.anthropic_api_key:
        return _anthropic_json_with_schema(
            prompt,
            schema=NUTRITION_PLAN_MONDAY_JSON_SCHEMA["schema"],
            system_prompt=NUTRITION_PLAN_SYSTEM_PROMPT,
            max_tokens=1600,
        )

    raise RuntimeError("ANTHROPIC_API_KEY is not configured for nutrition plan generation")


def _generate_nutrition_plan_day_json(prompt: str) -> str:
    if settings.anthropic_api_key:
        return _anthropic_json_with_schema(
            prompt,
            schema=NUTRITION_PLAN_DAY_JSON_SCHEMA["schema"],
            system_prompt=NUTRITION_PLAN_SYSTEM_PROMPT,
            max_tokens=1600,
        )

    raise RuntimeError("ANTHROPIC_API_KEY is not configured for nutrition plan generation")


def _generate_nutrition_plan_completion_json(prompt: str) -> str:
    return _generate_nutrition_plan_json(prompt)


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


def _openai_structured_json(
    prompt: str,
    schema: dict,
    *,
    system_prompt: str,
    max_output_tokens: int,
) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    request_payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "text": {"format": schema},
        "max_output_tokens": max_output_tokens,
    }

    data = _openai_responses_json_with_retry(request_payload)
    try:
        return _extract_response_text(data, NutritionPlanRefusalError).strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI nutrition response was missing JSON text") from exc


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


def _nutrition_language_instruction(payload: dict) -> str:
    lang = str(payload.get("language") or payload.get("preferred_language") or "").strip().lower()
    if not lang or lang in ("en", "en-gh"):
        return ""
    language_names = {
        "bn": "Bengali (বাংলা)",
        "es": "Spanish (Español)",
        "de": "German (Deutsch)",
        "fr": "French (Français)",
        "it": "Italian (Italiano)",
        "pt": "Portuguese (Português)",
        "nl": "Dutch (Nederlands)",
        "pl": "Polish (Polski)",
        "tr": "Turkish (Türkçe)",
        "ar": "Arabic (العربية)",
        "hi": "Hindi (हिन्दी)",
        "ur": "Urdu (اردو)",
        "id": "Indonesian (Bahasa Indonesia)",
        "ja": "Japanese (日本語)",
        "ko": "Korean (한국어)",
        "zh": "Chinese (中文)",
        "ru": "Russian (Русский)",
        "uk": "Ukrainian (Українська)",
        "vi": "Vietnamese (Tiếng Việt)",
        "th": "Thai (ไทย)",
    }
    lang_name = language_names.get(lang, lang)
    return (
        f"\nLanguage requirement: Write all human-readable content (meal names, descriptions, ingredients, instructions, summary, shopping categories) in {lang_name}. "
        "Keep JSON keys and day codes ('Mon','Tue','Wed','Thu','Fri','Sat','Sun') in English."
    )


def _build_nutrition_plan_prompt(payload: dict) -> str:
    lang_req = _nutrition_language_instruction(payload)
    fav_inst = _favorite_meals_instruction(payload)
    country_food_inst = build_country_food_prompt_context(payload)
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    practical_inst = _meal_plan_practical_constraints_instruction(payload)
    return (
        "Create a 7-day nutrition plan in JSON with this exact top-level structure:\n"
        f"{fav_inst}"
        f"{country_food_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        f"{practical_inst}"
        "{"
        '"summary": string (concise 2-line summary under 35 words. Format: '
        "'7-day [Country/Cuisine if any] [Goal] plan • ~[Daily calories] kcal/day • [Daily protein]g protein/day.\\n"
        "[Allergy/diet if any] respected. Meals prioritize [Cuisine/stated preferences] options and your stated preferences.' "
        "NO introductory essays), "
        '"goal_label": string, '
        '"days": [{"day":"Mon|Tue|Wed|Thu|Fri|Sat|Sun","breakfast":{...},"lunch":{...},"pre_workout":{...},"post_workout":{...},"dinner":{...}}], '
        '"shopping_list": [{"category": string, "items": [{"name": string, "qty": string}]}]'
        "}\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        "ingredients must be an array of strings. instructions must be an array of strings.\n"
        "Use concise meal names, realistic portions, and keep the plan practical.\n"
        f"{lang_req}\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )


def _build_progressive_nutrition_plan_monday_prompt(payload: dict) -> str:
    lang_req = _nutrition_language_instruction(payload)
    fav_inst = _favorite_meals_instruction(payload)
    country_food_inst = build_country_food_prompt_context(payload)
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    practical_inst = _meal_plan_practical_constraints_instruction(payload)
    return (
        "Create only Monday for a 7-day nutrition plan in JSON with this exact structure:\n"
        f"{fav_inst}"
        f"{country_food_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        f"{practical_inst}"
        "{"
        '"summary": string (concise 2-line summary under 35 words. Format: '
        "'7-day [Country/Cuisine if any] [Goal] plan • ~[Daily calories] kcal/day • [Daily protein]g protein/day.\\n"
        "[Allergy/diet if any] respected. Meals prioritize [Cuisine/stated preferences] options and your stated preferences.' "
        "NO introductory essays), "
        '"goal_label": string, '
        '"day": {"day":"Mon","breakfast":{...},"lunch":{...},"pre_workout":{...},"post_workout":{...},"dinner":{...}}'
        "}\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        "Keep Monday realistic, practical, safe, and aligned to the full weekly goal.\n"
        f"{lang_req}\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )


def _build_progressive_nutrition_plan_completion_prompt(payload: dict, monday_plan: dict) -> str:
    lang_req = _nutrition_language_instruction(payload)
    fav_inst = _favorite_meals_instruction(payload)
    country_food_inst = build_country_food_prompt_context(payload)
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    practical_inst = _meal_plan_practical_constraints_instruction(payload)
    return (
        "Complete a 7-day nutrition plan in JSON with this exact top-level structure:\n"
        f"{fav_inst}"
        f"{country_food_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        f"{practical_inst}"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        '"days": [{"day":"Mon|Tue|Wed|Thu|Fri|Sat|Sun","breakfast":{...},"lunch":{...},"pre_workout":{...},"post_workout":{...},"dinner":{...}}], '
        '"shopping_list": [{"category": string, "items": [{"name": string, "qty": string}]}]'
        "}\n"
        "Keep the provided Monday plan exactly consistent in food choices and meal structure.\n"
        "Return the full 7-day plan, including Monday and the remaining days.\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        f"{lang_req}\n"
        f"Locked Monday plan: {json.dumps(monday_plan, ensure_ascii=False)}\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )


def _build_progressive_nutrition_plan_day_prompt(payload: dict, day_name: str, previous_days: list[dict]) -> str:
    lang_req = _nutrition_language_instruction(payload)
    fav_inst = _favorite_meals_instruction(payload)
    country_food_inst = build_country_food_prompt_context(payload)
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    practical_inst = _meal_plan_practical_constraints_instruction(payload)
    return (
        f"Create only {day_name} for a 7-day nutrition plan in JSON with this exact structure:\n"
        f"{fav_inst}"
        f"{country_food_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        f"{practical_inst}"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        f'"day": {{"day":"{day_name}","breakfast":{{...}},"lunch":{{...}},"pre_workout":{{...}},"post_workout":{{...}},"dinner":{{...}}}}'
        "}\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        "Keep the day consistent with the prior generated days, the user's goal, and the weekly nutrition direction.\n"
        "Do not repeat the previous meals unless it improves continuity.\n"
        f"{lang_req}\n"
        f"Previously generated days: {json.dumps(previous_days, ensure_ascii=False)}\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )


def _collect_nutrition_plan_candidates(prompt: str) -> tuple[list[str], list[str]]:
    candidates: list[str] = []
    provider_errors: list[str] = []

    if settings.anthropic_api_key:
        try:
            _append_candidate(candidates, _langchain_anthropic_nutrition_plan_json(prompt))
        except RuntimeError as exc:
            provider_errors.append(str(exc))

    if settings.openai_api_key:
        try:
            _append_candidate(candidates, _langchain_openai_nutrition_plan_json(prompt))
        except RuntimeError as exc:
            provider_errors.append(str(exc))

    return candidates, provider_errors


def _openai_structured_nutrition_plan_json(prompt: str) -> str:
    return _openai_structured_json(
        prompt,
        NUTRITION_PLAN_JSON_SCHEMA,
        system_prompt=NUTRITION_PLAN_SYSTEM_PROMPT,
        max_output_tokens=2200,
    )


def _anthropic_json_with_schema(
    prompt: str,
    *,
    schema: dict,
    system_prompt: str,
    max_tokens: int,
) -> str:
    payload = {
        "model": settings.anthropic_model,
        "system": (
            f"{system_prompt} Return only one valid JSON object. "
            "Do not include markdown fences, explanations, or commentary. "
            f"Required schema: {json.dumps(schema, ensure_ascii=False)}"
        ),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
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
        raise RuntimeError("Anthropic nutrition response was missing text") from exc


def _anthropic_nutrition_plan_json(prompt: str) -> str:
    return _anthropic_json_with_schema(
        prompt,
        schema=NUTRITION_PLAN_JSON_SCHEMA["schema"],
        system_prompt=NUTRITION_PLAN_SYSTEM_PROMPT,
        max_tokens=3000,
    )


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


def _enforce_variety_and_safety(
    days: list[dict],
    payload: dict | None = None,
    profile: dict | None = None,
) -> list[dict]:
    ctx = {**(profile if isinstance(profile, dict) else {}), **(payload if isinstance(payload, dict) else {})}
    allergies_text = str(ctx.get("allergies") or "").lower()
    goal = str(ctx.get("goal") or "").lower()
    is_weight_loss = goal in {"g1", "weight loss", "weight_loss", "fat loss", "fat_loss", "weight reduction"}
    cuisine = str(ctx.get("cuisine") or "").lower()
    country_code = str(ctx.get("country_code") or ctx.get("countryCode") or "").upper()
    is_ghana = country_code == "GH" or "ghana" in cuisine or "ghanaian" in cuisine

    # Extract favorites and preferences
    fav_list = [
        str(item).strip()
        for item in (ctx.get("favorite_meals") or ctx.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    if ctx.get("favorite_meal") and str(ctx.get("favorite_meal")).strip():
        fav_single = str(ctx.get("favorite_meal")).strip()
        if fav_single not in fav_list:
            fav_list.insert(0, fav_single)

    fav_prefs: dict[str, str] = {}
    if ctx.get("favorite_meals_preferences") and isinstance(ctx.get("favorite_meals_preferences"), dict):
        for k, v in ctx["favorite_meals_preferences"].items():
            fav_prefs[str(k).strip().lower()] = str(v).strip().lower()
    if ctx.get("favorite_foods_details") and isinstance(ctx.get("favorite_foods_details"), list):
        for item in ctx["favorite_foods_details"]:
            if isinstance(item, dict) and item.get("name"):
                name_key = str(item["name"]).strip().lower()
                pref_val = str(item.get("health_preference") or "unspecified").strip().lower()
                if name_key not in fav_prefs or fav_prefs[name_key] == "unspecified":
                    fav_prefs[name_key] = pref_val

    # Allergen detection triggers
    allergen_rules: list[tuple[str, list[str]]] = []
    if "nut" in allergies_text or "peanut" in allergies_text:
        allergen_rules.append(("nut/peanut", ["peanut", "groundnut", "peanut butter", "groundnut soup", "cashew", "almond", "walnut", "hazelnut"]))
    if "shellfish" in allergies_text or "shrimp" in allergies_text:
        allergen_rules.append(("shellfish", ["shellfish", "shrimp", "prawn", "crab", "lobster", "crawfish"]))
    if "pork" in allergies_text:
        allergen_rules.append(("pork", ["pork", "bacon", "ham", "prosciutto", "pork sausage", "pork rib"]))
    if "lactose" in allergies_text or "dairy" in allergies_text:
        allergen_rules.append(("dairy", ["cheese", "cow milk", "dairy milk", "heavy cream", "sour cream"]))

    ghana_lunch_pool = [
        ("Waakye with Boiled Egg, Grilled Fish & Shito", ["Rice and beans", "Boiled egg", "Grilled fish", "Shito pepper sauce"]),
        ("Banku with Grilled Tilapia & Fresh Hot Pepper", ["Fermented corn & cassava dough", "Fresh grilled tilapia", "Tomato pepper salsa"]),
        ("Boiled Yam with Kontomire Stew & Smoked Fish", ["Pona yam slices", "Spinach/cocoyam leaves", "Smoked mackerel", "Egg"]),
        ("Red Red with Boiled Plantain & Grilled Fish", ["Black-eyed pea stew", "Steamed ripe plantain", "Grilled fish fillet"]),
        ("Jollof Rice with Roasted Chicken Breast", ["Aromatic tomato spiced rice", "Skinless chicken breast", "Steamed greens"]),
        ("Omo Tuo with Light Fish Soup", ["Mashed rice balls", "Light tomato ginger soup", "Fresh white fish"]),
    ]
    ghana_dinner_pool = [
        ("Chicken Light Soup with Steamed Plantain", ["Tomato garden egg light soup", "Skinless chicken", "Steamed green plantain"]),
        ("Grilled Mackerel with Fresh Vegetable Salad", ["Grilled Atlantic mackerel", "Cabbage, carrots, tomatoes", "Olive oil dressing"]),
        ("Steamed Brown Rice with Lean Beef Stew", ["Brown rice", "Lean beef pieces", "Rich tomato stew", "Steamed spinach"]),
        ("Grilled Tilapia with Mixed Green Salad", ["Whole spiced tilapia", "Lettuce, cucumber, sweet pepper", "Lemon dressing"]),
    ]
    continental_lunch_pool = [
        ("Grilled Herb Chicken Breast & Quinoa Bowl", ["Skinless chicken breast", "Fluffy quinoa", "Steamed broccoli", "Olive oil"]),
        ("Pan-Seared Salmon with Steamed Brown Rice & Asparagus", ["Wild salmon fillet", "Brown rice", "Tender asparagus spears"]),
        ("Turkey Breast Sweet Potato Power Plate", ["Sliced roasted turkey breast", "Baked sweet potato", "Green beans"]),
        ("Lentil & Mediterranean Vegetable Bowl", ["Brown lentils", "Roasted bell peppers, zucchini", "Fresh herbs"]),
    ]
    continental_dinner_pool = [
        ("Baked Lemon Herb Cod with Roasted Root Vegetables", ["Atlantic cod fillet", "Carrots, parsnips, baby potatoes", "Fresh dill"]),
        ("Grilled Lean Beef Steak with Tossed Salad", ["Lean sirloin steak", "Mixed greens, cherry tomatoes, cucumbers", "Balsamic"]),
        ("Roasted Chicken Thigh with Steamed Greens & Rice", ["Skinless roasted chicken", "Steamed kale & green beans", "Brown rice"]),
    ]

    lunch_pool = ghana_lunch_pool if is_ghana else continental_lunch_pool
    dinner_pool = ghana_dinner_pool if is_ghana else continental_dinner_pool

    # Step A: Enforce allergy check on every meal slot
    for day in days:
        for slot in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner"):
            meal = day.get(slot)
            if not isinstance(meal, dict):
                continue
            meal_name = str(meal.get("name") or "").lower()
            ingredients = [str(i).lower() for i in meal.get("ingredients") or []]
            has_allergen = False
            for _, trigger_words in allergen_rules:
                if any(w in meal_name for w in trigger_words) or any(any(w in ing for w in trigger_words) for ing in ingredients):
                    has_allergen = True
                    break
            if has_allergen:
                if slot == "breakfast":
                    meal["name"] = "Oatmeal with Sliced Berries & Chia Seeds"
                    meal["desc"] = "Allergen-free energy breakfast rich in fiber and antioxidants"
                    meal["ingredients"] = ["Rolled oats", "Almond/oat milk", "Blueberries", "Chia seeds"]
                    meal["instructions"] = ["Cook oats in plant milk", "Top with berries and chia seeds", "Serve warm"]
                elif slot == "lunch":
                    safe_name, safe_ing = lunch_pool[0]
                    meal["name"] = safe_name
                    meal["desc"] = "Allergen-safe balanced lunch prepared with fresh, clean ingredients"
                    meal["ingredients"] = safe_ing
                    meal["instructions"] = ["Cook staple grains", "Grill protein thoroughly", "Assemble with vegetables"]
                elif slot == "dinner":
                    safe_name, safe_ing = dinner_pool[0]
                    meal["name"] = safe_name
                    meal["desc"] = "Allergen-safe lean dinner supporting evening recovery"
                    meal["ingredients"] = safe_ing
                    meal["instructions"] = ["Simmer soup/sauce", "Grill or steam protein", "Serve portion-controlled"]
                elif slot == "pre_workout":
                    meal["name"] = "Steamed Sweet Potato & Banana Energy Fuel"
                    meal["desc"] = "Clean allergen-free pre-workout fuel scheduled 60-90m before training"
                    meal["ingredients"] = ["Steamed sweet potato slices", "Fresh ripe banana"]
                    meal["instructions"] = ["Slice banana and sweet potato", "Enjoy 60-90 minutes before workout"]
                elif slot == "post_workout":
                    meal["name"] = "Grilled Chicken Breast & White Rice Recovery"
                    meal["desc"] = "Rapid recovery protein and glycogen replenishment within 45m after workout"
                    meal["ingredients"] = ["Grilled lean chicken breast", "Steamed jasmine rice"]
                    meal["instructions"] = ["Grill chicken seasoned with herbs", "Serve with steamed rice"]

    # Step B: Nutrient Timing Validation: Pre/post workout should never be heavy swallows
    heavy_swallows = ["fufu", "pounded yam", "eba", "banku", "omo tuo", "amala"]
    for day in days:
        for slot in ("pre_workout", "post_workout"):
            meal = day.get(slot)
            if not isinstance(meal, dict):
                continue
            name_lower = str(meal.get("name") or "").lower()
            if any(sw in name_lower for sw in heavy_swallows):
                if slot == "pre_workout":
                    meal["name"] = "Rolled Oats & Sliced Banana Energy Bowl"
                    meal["desc"] = "Carb-forward pre-workout fuel 60–90m before workout"
                    meal["ingredients"] = ["Rolled oats", "Water or unsweetened almond milk", "1 sliced banana", "Drizzle of pure honey"]
                    meal["instructions"] = ["Simmer oats in liquid for 5 mins", "Top with sliced banana and honey", "Consume 60–90 mins before training"]
                else:
                    meal["name"] = "Grilled Chicken Strips with Steamed Rice Recovery Bowl"
                    meal["desc"] = "Protein-forward recovery within 45m post workout"
                    meal["ingredients"] = ["Lean chicken breast strips", "Steamed white rice", "Pinch of salt and herbs"]
                    meal["instructions"] = ["Sear chicken strips in pan", "Serve over warm steamed rice", "Eat within 45 mins after workout"]

    # Step C: Favourite Foods Frequency & Variety Validation
    for fav in fav_list:
        fav_norm = fav.strip().lower()
        if not fav_norm:
            continue
        pref = fav_prefs.get(fav_norm, "unspecified")
        if pref not in {"healthy_for_me", "not_healthy_for_me"}:
            pref = "unspecified"

        if pref == "not_healthy_for_me":
            max_allowed = 2 if is_weight_loss else 3
        elif pref == "healthy_for_me":
            max_allowed = 4
        else:
            max_allowed = 3

        occurrences: list[tuple[int, str]] = []
        for day_idx, day in enumerate(days):
            for slot in ("lunch", "dinner"):
                meal = day.get(slot)
                if isinstance(meal, dict):
                    m_name = str(meal.get("name") or "").lower()
                    if fav_norm in m_name or any(word in m_name for word in fav_norm.split() if len(word) > 3):
                        occurrences.append((day_idx, slot))

        if len(occurrences) > max_allowed:
            excess = occurrences[max_allowed:]
            alt_idx = 0
            for day_idx, slot in excess:
                meal = days[day_idx][slot]
                pool = lunch_pool if slot == "lunch" else dinner_pool
                replacement_name, replacement_ing = pool[alt_idx % len(pool)]
                alt_idx += 1
                meal["name"] = replacement_name
                meal["desc"] = f"Nutrient-dense, balanced {slot} providing variety and supporting your fitness goal."
                meal["ingredients"] = replacement_ing
                meal["instructions"] = ["Prepare ingredients fresh", "Cook to optimal tenderness", "Serve portion-controlled"]

    # Step D: Consecutive Day Duplicate Protection
    for slot in ("lunch", "dinner"):
        for day_idx in range(1, len(days)):
            prev_name = str(days[day_idx - 1].get(slot, {}).get("name") or "").strip().lower()
            curr_name = str(days[day_idx].get(slot, {}).get("name") or "").strip().lower()
            if prev_name and curr_name and prev_name == curr_name:
                pool = lunch_pool if slot == "lunch" else dinner_pool
                for candidate_name, candidate_ing in pool:
                    if candidate_name.strip().lower() != curr_name and candidate_name.strip().lower() != prev_name:
                        meal = days[day_idx][slot]
                        meal["name"] = candidate_name
                        meal["desc"] = f"Varied balanced {slot} preserving daily nutritional diversity."
                        meal["ingredients"] = candidate_ing
                        meal["instructions"] = ["Prepare ingredients fresh", "Cook to optimal tenderness", "Serve portion-controlled"]
                        break

    return days


def _normalize_nutrition_plan(plan: dict, payload: dict | None = None) -> dict:
    normalized_days = _normalize_plan_days(plan.get("days", []))
    normalized_days = _enforce_variety_and_safety(normalized_days, payload=payload, profile=plan.get("profile"))
    shopping_list = plan.get("shopping_list", [])
    daily_protein = plan.get("daily_protein_target")

    user_weight_input = (
        (payload.get("weight") if payload else None)
        or (plan.get("profile") if isinstance(plan.get("profile"), dict) else {}).get("weight")
        or plan.get("baseline_weight")
    )
    user_goal_input = (
        (payload.get("goal") if payload else None)
        or (plan.get("profile") if isinstance(plan.get("profile"), dict) else {}).get("goal")
        or plan.get("goal")
    )

    weight_kg = _parse_weight_kg(user_weight_input) if user_weight_input else 0.0
    if weight_kg <= 0 and daily_protein:
        _, fallback_mult = calculate_protein_target(70.0, user_goal_input)
        weight_kg = round(daily_protein / fallback_mult, 1)

    target_p, multiplier = calculate_protein_target(weight_kg, user_goal_input) if weight_kg > 0 else (0, 1.6)

    # Ensure total protein across 7-day plan strictly hits target_p
    if target_p > 0 and normalized_days:
        for day in normalized_days:
            keys = [k for k in ("breakfast", "lunch", "pre_workout", "post_workout", "dinner") if k in day]
            if not keys:
                continue
            current_sum = sum(day[k].get("p", 0) for k in keys) or 1
            allocated_p = 0
            for idx, k in enumerate(keys):
                meal = day[k]
                old_p = meal.get("p", 0)
                if idx == len(keys) - 1:
                    new_p = max(target_p - allocated_p, 10)
                else:
                    new_p = max(int(round(target_p * (old_p / current_sum))), 10)
                    allocated_p += new_p
                meal["p"] = new_p
                # Strict Macro Math: kcal = (p * 4) + (c * 4) + (f * 9)
                calc_kcal = (meal["p"] * 4) + (meal.get("c", 30) * 4) + (meal.get("f", 10) * 9)
                meal["kcal"] = max(calc_kcal, 100)
        daily_protein = target_p
    elif target_p > 0:
        daily_protein = target_p

    if not daily_protein and normalized_days:
        daily_protein = sum(
            sum(meal.get("p", 0) for k, meal in day.items() if k != "day" and isinstance(meal, dict))
            for day in normalized_days
        ) // max(len(normalized_days), 1)
    raw_summary = _normalize_text(plan.get("summary"), "")
    # Enforce concise structured summary: prevent long AI essays (>180 chars or missing structured metrics)
    if not raw_summary or len(raw_summary) > 180 or ("kcal/day" not in raw_summary and "•" not in raw_summary):
        final_summary = build_concise_nutrition_summary(
            {
                "summary": raw_summary,
                "goal_label": plan.get("goal_label"),
                "daily_protein_target": daily_protein,
                "days": normalized_days,
                "profile": plan.get("profile") or (payload if isinstance(payload, dict) else {}),
            },
            payload=payload,
        )
    else:
        final_summary = raw_summary

    normalized_plan = {
        "summary": final_summary,
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "daily_protein_target": daily_protein,
        "protein_per_kg": multiplier if weight_kg > 0 else plan.get("protein_per_kg", 1.6),
        "baseline_weight": weight_kg if weight_kg > 0 else plan.get("baseline_weight"),
        "days": normalized_days,
        "shopping_list": _normalize_shopping_list(shopping_list, normalized_days),
    }
    if "profile" in plan:
        normalized_plan["profile"] = plan["profile"]
    if "meal_completions" in plan:
        normalized_plan["meal_completions"] = plan["meal_completions"]
    return _validate_nutrition_plan(normalized_plan)


def _parse_or_repair_nutrition_plan(text: str, payload: dict | None = None) -> dict | None:
    try:
        return _normalize_nutrition_plan(_parse_json_object(text), payload=payload)
    except json.JSONDecodeError:
        pass

    repaired_text = _repair_nutrition_plan_json(text)
    if not repaired_text:
        return None

    try:
        return _normalize_nutrition_plan(_parse_json_object(repaired_text), payload=payload)
    except json.JSONDecodeError:
        return None


def _parse_or_repair_nutrition_plan_monday(text: str, payload: dict | None = None) -> dict | None:
    try:
        return _normalize_nutrition_plan_monday(_parse_json_object(text), payload=payload)
    except json.JSONDecodeError:
        pass

    repaired_text = _repair_json_with_schema(
        text,
        schema=NUTRITION_PLAN_MONDAY_JSON_SCHEMA["schema"],
        schema_name="nutrition_plan_monday",
    )
    if not repaired_text:
        return None

    try:
        return _normalize_nutrition_plan_monday(_parse_json_object(repaired_text), payload=payload)
    except json.JSONDecodeError:
        return None


def _parse_or_repair_nutrition_day_plan(text: str, day_name: str, payload: dict | None = None) -> dict | None:
    try:
        return _normalize_nutrition_day_plan(_parse_json_object(text), day_name, payload=payload)
    except json.JSONDecodeError:
        pass

    repaired_text = _repair_json_with_schema(
        text,
        schema=NUTRITION_PLAN_DAY_JSON_SCHEMA["schema"],
        schema_name="nutrition_plan_day",
    )
    if not repaired_text:
        return None

    try:
        return _normalize_nutrition_day_plan(_parse_json_object(repaired_text), day_name, payload=payload)
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


def _normalize_plan_days(days: object, day_order: list[str] | None = None) -> list[dict]:
    ordered_days = day_order or PLAN_DAY_ORDER
    by_day: dict[str, dict] = {}
    if isinstance(days, list):
        for raw_day in days:
            if not isinstance(raw_day, dict):
                continue
            normalized_day = _normalize_day_plan(raw_day)
            day_name = normalized_day["day"]
            if day_name in ordered_days and day_name not in by_day:
                by_day[day_name] = normalized_day

    return [by_day.get(day_name, _default_day_plan(day_name)) for day_name in ordered_days]


def _normalize_nutrition_plan_monday(plan: dict, payload: dict | None = None) -> dict:
    raw_day = plan.get("day")
    normalized_day = _normalize_day_plan(raw_day if isinstance(raw_day, dict) else {})
    normalized_day["day"] = "Mon"
    normalized_plan = {
        "summary": _normalize_text(plan.get("summary"), "A practical Monday nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "days": [normalized_day],
        "shopping_list": [],
    }
    return _normalize_nutrition_plan(normalized_plan, payload=payload)


def _normalize_nutrition_day_plan(plan: dict, day_name: str, payload: dict | None = None) -> dict:
    raw_day = plan.get("day")
    normalized_day = _normalize_day_plan(raw_day if isinstance(raw_day, dict) else {})
    normalized_day["day"] = day_name
    normalized_plan = {
        "summary": _normalize_text(plan.get("summary"), "A practical nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "days": [normalized_day],
        "shopping_list": [],
    }
    return _normalize_nutrition_plan(normalized_plan, payload=payload)


def _normalize_day_plan(day: dict) -> dict:
    day_name = str(day.get("day", "")).strip().title()[:3]
    if day_name not in PLAN_DAY_ORDER:
        day_name = PLAN_DAY_ORDER[0]

    pre_raw = day.get("pre_workout")
    if not isinstance(pre_raw, dict) or not pre_raw:
        pre_raw = {
            "name": f"Pre-Workout Energy Snack",
            "desc": "Pre-workout fuel (scheduled 60–90 mins before training): Carb-forward fuel to maximize glycogen stores.",
            "kcal": 280,
            "p": 15,
            "c": 48,
            "f": 4,
            "timing": "60–90m before workout",
            "ingredients": ["1 medium banana or dates", "2 slices whole grain toast", "Light protein source"],
            "instructions": ["Consume 60 to 90 minutes before your workout.", "Drink 400ml water."],
        }

    post_raw = day.get("post_workout")
    if not isinstance(post_raw, dict) or not post_raw:
        post_raw = {
            "name": f"Post-Workout Recovery Plate",
            "desc": "Post-workout recovery (scheduled within 45 mins of workout end): High-protein meal to optimize muscle recovery.",
            "kcal": 360,
            "p": 32,
            "c": 36,
            "f": 6,
            "timing": "Within 45m after workout",
            "ingredients": ["Lean chicken breast, fish, or protein shake", "Jasmine rice or sweet potato", "Steamed greens"],
            "instructions": ["Consume within 45 minutes of completing your workout.", "Rehydrate thoroughly with water."],
        }

    return {
        "day": day_name,
        "breakfast": _normalize_meal_entry(day.get("breakfast", {})),
        "lunch": _normalize_meal_entry(day.get("lunch", {})),
        "dinner": _normalize_meal_entry(day.get("dinner", {})),
        "pre_workout": _normalize_meal_entry(pre_raw),
        "post_workout": _normalize_meal_entry(post_raw),
    }


def _normalize_meal_entry(entry: dict) -> dict:
    ingredients = entry.get("ingredients", [])
    raw_instructions = entry.get("preparation_steps") or entry.get("instructions") or entry.get("prep_steps") or []
    normalized_name = _normalize_text(entry.get("name"), "Balanced Meal")
    normalized_desc = _normalize_text(entry.get("desc"), "A practical meal tailored to your plan.")
    normalized_ingredients = _normalize_string_list(ingredients)
    normalized_instructions = _normalize_string_list(raw_instructions)

    if not normalized_ingredients:
        normalized_ingredients = ["Ingredients tailored to your nutrition goal."]

    if not normalized_instructions or (len(normalized_instructions) == 1 and "prepare the ingredients and portion" in normalized_instructions[0].lower()):
        normalized_instructions = build_meal_specific_prep_steps(normalized_name, normalized_ingredients)

    return {
        "name": normalized_name,
        "desc": normalized_desc,
        "kcal": _normalize_int(entry.get("kcal"), 450, 0, 3000),
        "p": _normalize_int(entry.get("p"), 30, 0, 300),
        "c": _normalize_int(entry.get("c"), 35, 0, 500),
        "f": _normalize_int(entry.get("f"), 15, 0, 200),
        "ingredients": normalized_ingredients,
        "instructions": normalized_instructions,
        "preparation_steps": normalized_instructions,
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


def _repair_json_with_schema(raw_text: str, *, schema: dict, schema_name: str) -> str | None:
    if not raw_text.strip():
        return None

    if settings.openai_api_key:
        try:
            return _openai_repair_json_with_schema(raw_text, schema=schema, schema_name=schema_name)
        except RuntimeError:
            pass

    if settings.anthropic_api_key:
        try:
            return _anthropic_repair_json_with_schema(raw_text, schema=schema, schema_name=schema_name)
        except RuntimeError:
            pass

    return None


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


def _openai_repair_json_with_schema(raw_text: str, *, schema: dict, schema_name: str) -> str:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You repair malformed JSON into one valid JSON object. "
                    "Return exactly one valid JSON object that matches the required schema. "
                    "Do not add markdown, commentary, or extra keys. "
                    f"Schema name: {schema_name}. "
                    f"Schema requirement: {json.dumps(schema, ensure_ascii=False)}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Repair this text into valid JSON while preserving the intended meal content when possible.\n\n"
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
        raise RuntimeError("OpenAI JSON repair request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI JSON repair request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI JSON repair request failed: {exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise RuntimeError("OpenAI JSON repair response was missing text") from exc


def _anthropic_repair_json_with_schema(raw_text: str, *, schema: dict, schema_name: str) -> str:
    payload = {
        "model": settings.anthropic_model,
        "system": (
            "You repair malformed JSON into one valid JSON object. "
            "Return exactly one valid JSON object that matches the required schema. "
            "Do not add markdown, commentary, or extra keys. "
            f"Schema name: {schema_name}. "
            f"Schema requirement: {json.dumps(schema, ensure_ascii=False)}"
        ),
        "messages": [
            {
                "role": "user",
                "content": (
                    "Repair this text into valid JSON while preserving the intended meal content when possible.\n\n"
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
        raise RuntimeError("Anthropic JSON repair request timed out") from exc
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic JSON repair request failed: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic JSON repair request failed: {exc.reason}") from exc

    try:
        return "".join(
            part["text"]
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Anthropic JSON repair response was missing text") from exc


def _default_day_plan(day_name: str) -> dict:
    return {
        "day": day_name,
        "breakfast": _default_meal_entry(f"{day_name} Breakfast"),
        "lunch": _default_meal_entry(f"{day_name} Lunch"),
        "pre_workout": _default_meal_entry(f"{day_name} Pre-Workout Snack"),
        "post_workout": _default_meal_entry(f"{day_name} Post-Workout Plate"),
        "dinner": _default_meal_entry(f"{day_name} Dinner"),
    }


def _default_meal_entry(name: str) -> dict:
    default_ingredients = ["Ingredients tailored to your nutrition goal."]
    prep_steps = build_meal_specific_prep_steps(name, default_ingredients)
    return {
        "name": name,
        "desc": "A balanced meal placeholder used to complete your weekly plan.",
        "kcal": 450,
        "p": 30,
        "c": 35,
        "f": 15,
        "ingredients": default_ingredients,
        "instructions": prep_steps,
        "preparation_steps": prep_steps,
    }


def _goal_label(goal: object) -> str:
    return {
        "g1": "Weight Loss",
        "g2": "Muscle Building",
        "g3": "Weight Maintenance",
        "g4": "Flexibility and Mobility",
        "g5": "Energy and Endurance",
    }.get(str(goal), "Personalized Nutrition Plan")
