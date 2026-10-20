import re
from typing import Any


COUNTRY_CURRENCY_CODES = {
    "DE": "EUR",
    "GH": "GHS",
    "IN": "INR",
    "GB": "GBP",
    "US": "USD",
}

COUNTRY_NAME_CURRENCY_CODES = {
    "germany": "EUR",
    "deutschland": "EUR",
    "ghana": "GHS",
    "india": "INR",
    "united kingdom": "GBP",
    "uk": "GBP",
    "great britain": "GBP",
    "united states": "USD",
    "united states of america": "USD",
    "usa": "USD",
}

def currency_for_country(country_code: Any = None, country: Any = None, fallback: str = "EUR") -> str:
    code = str(country_code or "").strip().upper()
    if code in COUNTRY_CURRENCY_CODES:
        return COUNTRY_CURRENCY_CODES[code]
    name = re.sub(r"\s+", " ", str(country or "").strip().lower())
    return COUNTRY_NAME_CURRENCY_CODES.get(name, fallback)


def _currency_from_legacy_budget(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if "GH₵" in text or "GHS" in text:
        return "GHS"
    if "€" in text or "EUR" in text:
        return "EUR"
    if "£" in text or "GBP" in text:
        return "GBP"
    if "$" in text or "USD" in text:
        return "USD"
    if "₹" in text or "INR" in text:
        return "INR"
    code_match = re.search(r"(?:^|\s)([A-Z]{3})(?:\s|$)", text)
    if code_match:
        return code_match.group(1)
    return None


def _amount_from_budget(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if float(value) >= 0 else None
    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        amount = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    return amount if amount >= 0 else None


def normalize_weekly_food_budget(payload: dict, *, country_code: Any = None, country: Any = None) -> dict:
    """Return a copy with an unambiguous budget amount and ISO currency.

    Historical records stored a free-form EUR string. A legacy numeric-only value
    therefore remains EUR instead of being silently reinterpreted after a country
    change. New structured amounts derive currency from the reliable user country
    only when no explicit currency was supplied.
    """
    normalized = dict(payload)
    legacy_value = normalized.get("weekly_food_budget")
    explicit_amount = normalized.get("weekly_food_budget_amount")
    amount = _amount_from_budget(explicit_amount if explicit_amount is not None else legacy_value)
    if amount is None:
        return normalized

    raw_currency = str(normalized.get("weekly_food_budget_currency") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", raw_currency):
        raw_currency = ""
    legacy_currency = _currency_from_legacy_budget(legacy_value)
    if raw_currency:
        currency = raw_currency
    elif legacy_currency:
        currency = legacy_currency
    elif legacy_value not in (None, ""):
        currency = "EUR"
    else:
        currency = currency_for_country(country_code, country)

    normalized["weekly_food_budget_amount"] = int(amount) if amount.is_integer() else amount
    normalized["weekly_food_budget_currency"] = currency
    normalized["weekly_food_budget"] = f"{normalized['weekly_food_budget_amount']} {currency}"
    return normalized
