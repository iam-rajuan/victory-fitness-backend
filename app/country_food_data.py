from __future__ import annotations

from typing import Any


GHANA_FOOD_DATASET_VERSION = "ghanaian-approved-foods-2026-10-01"

GHANA_FOOD_DATASET: dict[str, Any] = {
    "country": "Ghana",
    "country_codes": ["GH"],
    "cuisine_aliases": ["ghanaian", "ghana"],
    "version": GHANA_FOOD_DATASET_VERSION,
    "meals": {
        "breakfast": [
            {"dish": "Hausa koko", "with": ["koose", "bofrot"]},
            {"dish": "Koko / Akasa", "with": ["koose or tea bread", "sugar", "milk"]},
            {"dish": "Koose (Kose)", "with": ["Hausa koko or koko"]},
            {"dish": "Bofrot (Togbei)", "with": ["koko or tea"]},
            {"dish": "Tom Brown", "with": ["milk", "sugar", "bread"]},
            {"dish": "Oblayo", "with": ["sugar", "milk", "bread"]},
            {"dish": "Rice water", "with": ["milk", "sugar", "bread"]},
            {"dish": "Tea bread / Butter bread", "with": ["omelette", "Milo or tea"]},
            {"dish": "Gari soakings", "with": ["sugar", "milk", "roasted groundnuts"]},
            {"dish": "Boiled yam (Bayere)", "with": ["egg stew or Ntorewa abom"]},
            {"dish": "Ampesi", "with": ["kontomire stew", "boiled egg"]},
            {"dish": "Waakye", "with": ["gari", "shito", "talia", "boiled egg", "fish"]},
        ],
        "lunch": [
            {"dish": "Waakye", "with": ["gari", "shito", "stew", "talia", "egg", "wele", "fried fish"]},
            {"dish": "Jollof", "with": ["fried chicken", "shito", "salad"]},
            {"dish": "Fried rice", "with": ["chicken", "shito", "salad"]},
            {"dish": "Plain rice and stew", "with": ["chicken, beef or fish"]},
            {"dish": "Gob3 / Red red", "with": ["fried ripe plantain", "gari"]},
            {"dish": "Kenkey", "with": ["fried fish", "shito", "kpakpo shito"]},
            {"dish": "Banku", "with": ["grilled tilapia", "pepper sauce"]},
            {"dish": "Banku and okro", "with": ["fish or crab"]},
            {"dish": "Ampesi with palava sauce", "with": ["fish", "egg"]},
            {"dish": "Eto / Oto", "with": ["boiled eggs", "avocado"]},
            {"dish": "Omo tuo", "with": ["groundnut/palm nut soup", "chicken"]},
            {"dish": "Mpotompoto", "with": ["fish or smoked herring"]},
            {"dish": "Abolo", "with": ["fried fish", "pepper"]},
            {"dish": "Yakeyake", "with": ["fried fish", "pepper sauce"]},
        ],
        "dinner": [
            {"dish": "Fufu + Nkrakra", "with": ["light soup", "goat meat"]},
            {"dish": "Fufu + Nkate nkwan", "with": ["groundnut soup", "chicken/goat"]},
            {"dish": "Fufu + Abenkwan", "with": ["palm nut soup", "fish/crab/snails"]},
            {"dish": "Fufu + Abunuabunu", "with": ["green kontomire soup", "smoked fish/mushrooms"]},
            {"dish": "Banku + Okro soup", "with": ["fish/crab/wele"]},
            {"dish": "Akple", "with": ["fetri detsi", "crab/fish"]},
            {"dish": "Tuo Zaafi / TZ", "with": ["ayoyo soup", "wagashi/beef"]},
            {"dish": "Kokonte", "with": ["groundnut/light soup", "goat"]},
            {"dish": "Konkonte + palm nut soup", "with": ["fish"]},
            {"dish": "Apapransa", "with": ["crab", "fish"]},
            {"dish": "Kenkey", "with": ["fried fish", "shito", "pepper"]},
            {"dish": "Kelewele", "with": ["roasted groundnuts"]},
        ],
    },
    "glossary": {
        "Nkrakra": "Ghanaian light soup, commonly served with fufu and goat meat.",
        "Nkate nkwan": "Groundnut soup, commonly served with fufu and chicken or goat.",
        "Abenkwan": "Palm nut soup, commonly served with fish, crab, snails, or fufu.",
        "Abunuabunu": "Green kontomire soup, commonly served with smoked fish or mushrooms.",
        "Fetri detsi": "Okro soup or stew, often served with akple and seafood.",
        "Ayoyo": "Jute leaves soup, commonly served with Tuo Zaafi.",
        "Kontomire stew/Palava sauce": "Cocoyam leaf stew, commonly paired with ampesi, fish, and egg.",
        "Ntorewa abom": "Garden egg sauce or mash, often served with boiled yam.",
        "Shito": "Ghanaian black pepper sauce.",
        "Kpakpo shito": "Small hot green pepper used for fresh pepper sauce.",
        "Gari": "Granulated cassava, used as a side or topping.",
        "Talia": "Spaghetti or pasta, often served with waakye.",
        "Kelewele/Fried plantain": "Spiced fried ripe plantain or fried ripe plantain side.",
        "Wele": "Cowhide, used as a protein side in stews and waakye.",
        "Wagashi": "West African cheese, often used as a protein in northern Ghanaian meals.",
        "Akrantie": "Grasscutter meat.",
        "Nwa": "Snails.",
        "Mpataa/Tilapia": "Fish, especially tilapia.",
        "Koobi": "Salted dried fish.",
        "Kako": "Salted dried fish.",
        "Momoni": "Fermented salted fish condiment.",
    },
}

COUNTRY_FOOD_DATASETS = {
    "ghana": GHANA_FOOD_DATASET,
    "gh": GHANA_FOOD_DATASET,
}


def _normalize(value: object) -> str:
    return str(value or "").strip().lower()


def get_country_food_dataset(payload: dict) -> dict[str, Any] | None:
    country = _normalize(payload.get("country") or payload.get("user_country"))
    country_code = _normalize(payload.get("country_code") or payload.get("countryCode") or payload.get("user_country_code"))
    cuisine = _normalize(payload.get("cuisine"))
    favorite_meals = [
        _normalize(item)
        for item in (payload.get("favorite_meals") or payload.get("favorite_meals_json") or [])
        if _normalize(item)
    ]
    if _normalize(payload.get("favorite_meal")):
        favorite_meals.insert(0, _normalize(payload.get("favorite_meal")))

    approved_dish_terms = {
        _normalize(item.get("dish"))
        for items in GHANA_FOOD_DATASET["meals"].values()
        for item in items
        if _normalize(item.get("dish"))
    }
    has_ghana_cuisine = any(alias in cuisine for alias in GHANA_FOOD_DATASET["cuisine_aliases"])
    has_approved_favorite = any(
        any(term and term in meal for term in approved_dish_terms)
        for meal in favorite_meals
    )
    has_explicit_non_ghanaian_preference = (
        (country == "ghana" or country_code == "gh")
        and bool(cuisine)
        and cuisine not in {"balanced", "any", "mixed", "local"}
        and not has_ghana_cuisine
        and not has_approved_favorite
    )

    if has_explicit_non_ghanaian_preference:
        return None

    if country == "ghana" or country_code == "gh":
        return GHANA_FOOD_DATASET

    if has_ghana_cuisine:
        return GHANA_FOOD_DATASET

    return None


def country_food_dataset_version(payload: dict) -> str:
    dataset = get_country_food_dataset(payload)
    return str(dataset.get("version") or "") if dataset else ""


def build_country_food_prompt_context(payload: dict) -> str:
    dataset = get_country_food_dataset(payload)
    if not dataset:
        return ""

    lines = [
        "COUNTRY-SPECIFIC APPROVED FOOD DATASET:",
        f"- Active country dataset: {dataset['country']} ({dataset['version']}).",
        "- PRIORITY RULE: For Ghana/Ghanaian users, load and prioritize these approved Ghanaian dishes and combinations before general AI food knowledge.",
        "- Preserve the listed combinations. Do not invent incorrect pairings such as 'Fufu with stew' when approved soup combinations are provided.",
        "- Meal times are flexible. Waakye, Kenkey, Banku, and other listed foods may appear outside their common period when it fits the user's plan.",
        "- Respect allergies, dietary restrictions, preferences, calorie targets, protein targets, budget, and favorite meals. If one approved Ghanaian meal is unsuitable, choose another approved Ghanaian option.",
        "- General food knowledge may be used only as fallback or minor variety after the approved Ghana dataset has been prioritized.",
    ]
    for meal_period, dishes in dataset["meals"].items():
        lines.append(f"{meal_period.upper()}:")
        for item in dishes:
            lines.append(f"- {item['dish']} -> with {', '.join(item['with'])}")
    lines.append("GLOSSARY:")
    for term, meaning in dataset["glossary"].items():
        lines.append(f"- {term}: {meaning}")
    return "\n".join(lines) + "\n"
