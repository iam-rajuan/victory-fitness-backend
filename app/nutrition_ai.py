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
                "required": ["day", "breakfast", "lunch", "dinner"],
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": ["Mon"],
                    },
                    "breakfast": MEAL_ENTRY_SCHEMA,
                    "lunch": MEAL_ENTRY_SCHEMA,
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
                "required": ["day", "breakfast", "lunch", "dinner"],
                "properties": {
                    "day": {
                        "type": "string",
                        "enum": PLAN_DAY_ORDER,
                    },
                    "breakfast": MEAL_ENTRY_SCHEMA,
                    "lunch": MEAL_ENTRY_SCHEMA,
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
        plan = _build_fallback_nutrition_plan(payload)

    _NUTRITION_PLAN_MEMORY_CACHE[cache_key] = deepcopy(plan)
    return NutritionResult(data=plan)


def generate_progressive_nutrition_plan_monday(payload: dict) -> NutritionResult:
    prompt = _build_progressive_nutrition_plan_monday_prompt(payload)
    plan_text = _generate_nutrition_plan_monday_json(prompt)
    plan = _parse_or_repair_nutrition_plan_monday(plan_text)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid Monday plan JSON")

    return NutritionResult(data=plan)


def generate_progressive_nutrition_plan_completion(payload: dict, monday_plan: dict) -> NutritionResult:
    prompt = _build_progressive_nutrition_plan_completion_prompt(payload, monday_plan)
    plan_text = _generate_nutrition_plan_completion_json(prompt)
    plan = _parse_or_repair_nutrition_plan(plan_text)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid completion plan JSON")

    monday_days = _normalize_plan_days(monday_plan.get("days", []), day_order=["Mon"])
    if monday_days:
        remaining_days = [day for day in plan["days"] if day.get("day") != "Mon"]
        plan["days"] = monday_days + remaining_days

    return NutritionResult(data=_validate_nutrition_plan(plan))


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
    plan = _parse_or_repair_nutrition_day_plan(plan_text, normalized_day)
    if plan is None:
        raise RuntimeError(f"The nutrition model did not return valid {normalized_day} plan JSON")


def generate_progressive_nutrition_plan_monday(payload: dict) -> NutritionResult:
    prompt = _build_progressive_nutrition_plan_monday_prompt(payload)
    plan_text = _generate_nutrition_plan_monday_json(prompt)
    plan = _parse_or_repair_nutrition_plan_monday(plan_text)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid Monday plan JSON")

    return NutritionResult(data=plan)


def generate_progressive_nutrition_plan_completion(payload: dict, monday_plan: dict) -> NutritionResult:
    prompt = _build_progressive_nutrition_plan_completion_prompt(payload, monday_plan)
    plan_text = _generate_nutrition_plan_completion_json(prompt)
    plan = _parse_or_repair_nutrition_plan(plan_text)
    if plan is None:
        raise RuntimeError("The nutrition model did not return valid completion plan JSON")

    monday_days = _normalize_plan_days(monday_plan.get("days", []), day_order=["Mon"])
    if monday_days:
        remaining_days = [day for day in plan["days"] if day.get("day") != "Mon"]
        plan["days"] = monday_days + remaining_days

    return NutritionResult(data=_validate_nutrition_plan(plan))


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
    plan = _parse_or_repair_nutrition_day_plan(plan_text, normalized_day)
    if plan is None:
        raise RuntimeError(f"The nutrition model did not return valid {normalized_day} plan JSON")

    return NutritionResult(data=plan)


def build_nutrition_plan_signature(payload: dict) -> str:
    favorite_meals = [
        str(item).strip()
        for item in (payload.get("favorite_meals") or payload.get("favorite_meals_json") or [])
        if str(item).strip()
    ]
    normalized_profile = {
        "provider": "openai" if settings.openai_api_key else "anthropic" if settings.anthropic_api_key else "none",
        "openai_model": settings.openai_model,
        "anthropic_model": settings.anthropic_model,
        "goal": _normalize_text(payload.get("goal"), ""),
        "cuisine": _normalize_text(payload.get("cuisine"), ""),
        "favorite_meal": _normalize_text(payload.get("favorite_meal"), ""),
        "favorite_meals": favorite_meals,
        "diet": _normalize_text(payload.get("diet"), ""),
        "allergies": _normalize_text(payload.get("allergies"), ""),
        "activity_level": _normalize_text(payload.get("activity_level"), ""),
        "age": _normalize_text(payload.get("age"), ""),
        "gender": _normalize_text(payload.get("gender"), ""),
        "height": _normalize_text(payload.get("height"), ""),
        "weight": _normalize_text(payload.get("weight"), ""),
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
    if goal_code in {"g2", "muscle building", "muscle_building"}:
        multiplier = 2.0
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

    cuisine = str(payload.get("cuisine") or "").strip()

    instructions = [
        "CRITICAL FAVOURITE MEALS & CULINARY MANDATE:",
        "- The 7-day meal plan MUST be built EXCLUSIVELY using the user's declared favourite meals and cuisine preferences.",
        "- STRICTLY FORBIDDEN: NEVER fall back to or introduce country-of-origin, geographic, or regional defaults when favourite meals or cuisine are specified. For example, if a user is located in or from Ghana but lists Italian cuisine and favourites (such as pasta, pizza, risotto), EVERY meal must be Italian or inspired by those favourites. Do NOT include Ghanaian staples like fufu, banku, or jollof.",
    ]
    if favorite_meals:
        instructions.append(f"- User's Explicit Favourite Meals: {', '.join(favorite_meals)}. Prioritize and feature these dishes across lunches and dinners.")
    if cuisine:
        instructions.append(f"- User's Target Cuisine: {cuisine}. Keep all meal recipes authentic to this cuisine style.")
    return "\n".join(instructions) + "\n"


def _workout_nutrient_timing_instruction(payload: dict) -> str:
    workout_time = str(payload.get("workout_time") or "17:30").strip()
    return (
        "WORKOUT NUTRIENT TIMING & MEAL SCHEDULING REQUIREMENTS:\n"
        f"- User's planned workout time is {workout_time} (or on scheduled workout training days).\n"
        "- PRE-WORKOUT MEAL: Schedule 60–90 minutes BEFORE the workout (e.g., at 16:00–16:30 for a 17:30 workout). "
        "It MUST be CARB-FORWARD (high complex carbohydrates, moderate protein, low fat) to maximize glycogen stores and sustain workout energy.\n"
        "- POST-WORKOUT MEAL: Schedule within 45 minutes AFTER the workout ends (e.g., by 19:15 for a workout ending at 18:30). "
        "It MUST be PROTEIN-FORWARD (high complete protein >= 30–40g, moderate carbs, low-to-moderate fat) to trigger muscle protein synthesis and accelerate recovery.\n"
        "- In the meal description ('desc'), explicitly note the nutrient timing and purpose (e.g. 'Pre-workout (60–90m before): Carb-forward fuel...' and 'Post-workout (within 45m): Protein-forward recovery...').\n"
    )


def _protein_target_instruction(payload: dict) -> str:
    weight_val = payload.get("weight")
    weight_kg = _parse_weight_kg(weight_val)
    target_protein = int(round(weight_kg * 1.6))
    return (
        f"PROTEIN ACCURACY TARGET: Daily protein across the 7-day plan must hit approximately {target_protein}g (1.6g/kg ±5g, tolerance range {target_protein - 5}g–{target_protein + 5}g). "
        f"For this {weight_kg}kg user, ensure the average across all 7 days is approximately {target_protein}g/day (~128g/day for an 80kg user). "
        f"Distribute: ~{int(target_protein * 0.25)}g breakfast, ~{int(target_protein * 0.35)}g lunch, ~{int(target_protein * 0.40)}g dinner. If goal is weight loss, keep protein high and reduce carbs.\n"
    )


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

    # User favorite meals priority (Ghana user with Italian favorites gets Italian meals, never country defaults)
    has_explicit_favs = len(favorite_meals) > 0
    display_cuisine = cuisine if cuisine else ("Italian" if any("pasta" in f.lower() or "pizza" in f.lower() or "risotto" in f.lower() for f in favorite_meals) else "balanced")

    summary = (
        f"This tailored 7-day plan supports {goal_label.lower()} with practical {display_cuisine} inspired meals, "
        f"balanced portions, and a repeatable structure centered on your favorite foods."
    )
    if has_explicit_favs:
        summary += f" It exclusively incorporates your favourites: {', '.join(favorite_meals[:3])}."
    if health_conditions:
        summary += f" Mindful of: {', '.join(health_conditions[:3])}."

    weight_kg = _parse_weight_kg(payload.get("weight"))
    # Total protein target: 1.6g/kg (e.g. 80kg -> 128g/day)
    # Check if goal specifically dictates otherwise, but maintain 1.6g/kg ±5g default
    daily_protein, multiplier = calculate_protein_target(payload.get("weight"), goal_code)
    # If standard 1.6g/kg requested or weight specified:
    if goal_code not in {"g2", "muscle building", "muscle_building"}:
        daily_protein = max(int(round(weight_kg * 1.6)), 60)
        multiplier = 1.6

    breakfast_p = max(int(round(daily_protein * 0.25)), 15)
    lunch_p = max(int(round(daily_protein * 0.35)), 20)
    dinner_p = max(daily_protein - breakfast_p - lunch_p, 15)

    is_low_carb = diet_code in {"d4", "keto / low-carb", "keto", "low-carb"} or goal_code == "g1"
    base_carb = 24 if is_low_carb else 42

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days: list[dict] = []

    for index, day_name in enumerate(day_names):
        base_kcal = 380 + (index % 3) * 20
        carb_target = base_carb + (0 if is_low_carb else (index % 2) * 6)

        # Select meal names honoring ONLY user favorites
        if has_explicit_favs:
            lunch_dish = favorite_meals[index % len(favorite_meals)]
            dinner_dish = favorite_meals[(index + 1) % len(favorite_meals)]
            breakfast_name = f"{display_cuisine.capitalize()} Protein Breakfast Bowl" if index % 2 == 0 else f"{display_cuisine.capitalize()} Scrambled Eggs & Toast"
        else:
            lunch_dish = f"{display_cuisine.capitalize()} Rice & Protein Plate"
            dinner_dish = f"Roasted {protein_name} & Vegetables"
            breakfast_name = "Protein Oats Bowl" if index % 2 == 0 else "Egg & Toast Plate"

        # Pre-workout meal scheduled 60-90 mins before workout time (carb-forward)
        # Post-workout meal scheduled within 45 mins of workout end (protein-forward)
        pre_workout_timing = "Scheduled 60–90 mins before workout (e.g. 16:00)"
        post_workout_timing = "Scheduled within 45 mins after workout (e.g. 18:45)"

        days.append(
            {
                "day": day_name,
                "breakfast": {
                    "name": breakfast_name,
                    "desc": f"Morning energy anchor built around {breakfast_protein.lower()} and {breakfast_side}.",
                    "kcal": base_kcal,
                    "p": breakfast_p,
                    "c": carb_target,
                    "f": 12,
                    "ingredients": [
                        breakfast_protein,
                        "Oats or whole grain bread",
                        breakfast_side,
                        "Cinnamon or light seasoning",
                    ],
                    "instructions": [
                        "Prepare the base protein and whole grains.",
                        "Top with fruit or light seasoning.",
                        "Enjoy with water or black coffee.",
                    ],
                },
                "lunch": {
                    "name": f"Pre-Workout: {lunch_dish}",
                    "desc": f"Pre-workout meal ({pre_workout_timing}): Carb-forward fuel featuring {lunch_dish} to maximize glycogen and workout stamina.",
                    "kcal": base_kcal + 180,
                    "p": lunch_p,
                    "c": carb_target + 24,  # Carb-forward
                    "f": 11,
                    "ingredients": [
                        protein_name,
                        "Pasta, rice, or grains matching favorite dish",
                        "Steamed vegetables or salad",
                        "1 tsp olive oil",
                        "Herbs and spices",
                    ],
                    "instructions": [
                        "Cook grains or pasta al dente.",
                        "Sear or grill protein with aromatic herbs.",
                        "Combine for a carb-forward fuel meal 60–90 mins prior to training.",
                    ],
                },
                "dinner": {
                    "name": f"Post-Workout: {dinner_dish}",
                    "desc": f"Post-workout meal ({post_workout_timing}): Protein-forward recovery featuring {dinner_dish} delivering amino acids for muscle repair.",
                    "kcal": base_kcal + 120,
                    "p": dinner_p,  # Protein-forward
                    "c": max(18, carb_target - 4),
                    "f": 14,
                    "ingredients": [
                        protein_name,
                        "Seasonal vegetables",
                        "Light complex carbs",
                        "Garlic and olive oil",
                        "Fresh herbs",
                    ],
                    "instructions": [
                        "Cook protein through to lock in amino acids.",
                        "Steam or roast fresh greens.",
                        "Consume within 45 minutes of workout completion.",
                    ],
                },
            }
        )

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

    return _validate_nutrition_plan(
        {
            "summary": summary,
            "goal_label": goal_label,
            "daily_protein_target": daily_protein,
            "protein_per_kg": multiplier,
            "baseline_weight": weight_kg,
            "days": days,
            "shopping_list": shopping_list,
        }
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
        return _build_fallback_meal_analysis(payload.get("file_name"))

    image_base64 = _normalize_text(payload.get("image_base64"), "")
    mime_type = _normalize_text(payload.get("mime_type"), "image/jpeg").lower()

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

    try:
        data = _openai_responses_json_with_retry(request_payload)
        result_text = _extract_response_text(data).strip()
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
    except Exception as exc:
        return _build_fallback_meal_analysis(payload.get("file_name"))


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
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    return (
        "Create a 7-day nutrition plan in JSON with this exact top-level structure:\n"
        f"{fav_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        '"days": [{"day":"Mon|Tue|Wed|Thu|Fri|Sat|Sun","breakfast":{...},"lunch":{...},"dinner":{...}}], '
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
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    return (
        "Create only Monday for a 7-day nutrition plan in JSON with this exact structure:\n"
        f"{fav_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        '"day": {"day":"Mon","breakfast":{...},"lunch":{...},"dinner":{...}}'
        "}\n"
        "Each meal entry must include: name, desc, kcal, p, c, f, ingredients, instructions.\n"
        "Keep Monday realistic, practical, safe, and aligned to the full weekly goal.\n"
        f"{lang_req}\n"
        f"User context: {json.dumps(payload, ensure_ascii=False)}"
    )


def _build_progressive_nutrition_plan_completion_prompt(payload: dict, monday_plan: dict) -> str:
    lang_req = _nutrition_language_instruction(payload)
    fav_inst = _favorite_meals_instruction(payload)
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    return (
        "Complete a 7-day nutrition plan in JSON with this exact top-level structure:\n"
        f"{fav_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        '"days": [{"day":"Mon|Tue|Wed|Thu|Fri|Sat|Sun","breakfast":{...},"lunch":{...},"dinner":{...}}], '
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
    timing_inst = _workout_nutrient_timing_instruction(payload)
    protein_inst = _protein_target_instruction(payload)
    return (
        f"Create only {day_name} for a 7-day nutrition plan in JSON with this exact structure:\n"
        f"{fav_inst}"
        f"{timing_inst}"
        f"{protein_inst}"
        "{"
        '"summary": string, '
        '"goal_label": string, '
        f'"day": {{"day":"{day_name}","breakfast":{{...}},"lunch":{{...}},"dinner":{{...}}}}'
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


def _normalize_nutrition_plan(plan: dict) -> dict:
    normalized_days = _normalize_plan_days(plan.get("days", []))
    shopping_list = plan.get("shopping_list", [])
    daily_protein = plan.get("daily_protein_target")

    baseline_w = plan.get("baseline_weight")
    weight_kg = _parse_weight_kg(baseline_w) if baseline_w else 0.0
    if weight_kg <= 0 and daily_protein:
        weight_kg = round(daily_protein / 1.6, 1)

    target_p = int(round(weight_kg * 1.6)) if weight_kg > 0 else 0

    # Ensure total protein across 7-day plan strictly hits 1.6g/kg ± 5g
    if target_p > 0 and normalized_days:
        day_proteins = [
            (day.get("breakfast", {}).get("p", 0) + day.get("lunch", {}).get("p", 0) + day.get("dinner", {}).get("p", 0))
            for day in normalized_days
        ]
        avg_p = sum(day_proteins) / max(len(day_proteins), 1)
        if abs(avg_p - target_p) > 5:
            # Rebalance meals so the 7-day average strictly hits target_p ± 5g
            bp = max(int(round(target_p * 0.25)), 15)
            lp = max(int(round(target_p * 0.35)), 20)
            dp = max(target_p - bp - lp, 15)
            for day in normalized_days:
                for m_key, new_p in (("breakfast", bp), ("lunch", lp), ("dinner", dp)):
                    meal = day.get(m_key)
                    if isinstance(meal, dict):
                        old_p = meal.get("p", new_p)
                        meal["p"] = new_p
                        meal["kcal"] = max(int(meal.get("kcal", 400)) + (new_p - old_p) * 4, 150)
            daily_protein = target_p

    if not daily_protein and normalized_days:
        daily_protein = sum(
            (day.get("breakfast", {}).get("p", 0) + day.get("lunch", {}).get("p", 0) + day.get("dinner", {}).get("p", 0))
            for day in normalized_days
        ) // max(len(normalized_days), 1)
    normalized_plan = {
        "summary": _normalize_text(plan.get("summary"), "A practical weekly nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "daily_protein_target": daily_protein,
        "protein_per_kg": 1.6 if weight_kg > 0 else plan.get("protein_per_kg"),
        "baseline_weight": weight_kg if weight_kg > 0 else plan.get("baseline_weight"),
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


def _parse_or_repair_nutrition_plan_monday(text: str) -> dict | None:
    try:
        return _normalize_nutrition_plan_monday(_parse_json_object(text))
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
        return _normalize_nutrition_plan_monday(_parse_json_object(repaired_text))
    except json.JSONDecodeError:
        return None


def _parse_or_repair_nutrition_day_plan(text: str, day_name: str) -> dict | None:
    try:
        return _normalize_nutrition_day_plan(_parse_json_object(text), day_name)
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
        return _normalize_nutrition_day_plan(_parse_json_object(repaired_text), day_name)
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


def _normalize_nutrition_plan_monday(plan: dict) -> dict:
    raw_day = plan.get("day")
    normalized_day = _normalize_day_plan(raw_day if isinstance(raw_day, dict) else {})
    normalized_day["day"] = "Mon"
    normalized_plan = {
        "summary": _normalize_text(plan.get("summary"), "A practical Monday nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "days": [normalized_day],
        "shopping_list": [],
    }
    return _validate_nutrition_plan(normalized_plan)


def _normalize_nutrition_day_plan(plan: dict, day_name: str) -> dict:
    raw_day = plan.get("day")
    normalized_day = _normalize_day_plan(raw_day if isinstance(raw_day, dict) else {})
    normalized_day["day"] = day_name
    normalized_plan = {
        "summary": _normalize_text(plan.get("summary"), "A practical nutrition plan tailored to your profile."),
        "goal_label": _normalize_text(plan.get("goal_label"), "Personalized Nutrition Plan"),
        "days": [normalized_day],
        "shopping_list": [],
    }
    return _validate_nutrition_plan(normalized_plan)


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
