"""Country / market helpers — derive ISO codes from free-text country, bucket
markets, and back-fill `country_code` for existing users on first boot."""
from __future__ import annotations

from typing import Iterable


# ---------------------------------------------------------------------------
# Country text -> ISO-2 mapping
# ---------------------------------------------------------------------------

COUNTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "GH": ("ghana", "accra", "kumasi"),
    "DE": ("germany", "german", "berlin", "munich", "frankfurt", "hamburg", "cologne", "köln"),
    "IN": ("india", "indian", "mumbai", "delhi", "bangalore", "bengaluru", "chennai", "hyderabad", "kolkata"),
    "US": ("united states", "usa", "u.s.a", "america", "new york", "los angeles", "chicago", "texas", "california"),
    "GB": ("united kingdom", "uk", "england", "london", "manchester", "birmingham"),
    "NG": ("nigeria", "nigerian", "lagos", "abuja"),
    "KE": ("kenya", "kenyan", "nairobi"),
    "ZA": ("south africa", "johannesburg", "cape town"),
    "CA": ("canada", "toronto", "vancouver", "montreal"),
    "AU": ("australia", "sydney", "melbourne"),
}


def derive_country_code(country: str | None) -> str | None:
    """Best-effort ISO-2 code from a free-text `country` value."""
    if not country:
        return None
    text = country.strip().lower()
    if not text:
        return None
    for code, keywords in COUNTRY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return code
    return None


# ---------------------------------------------------------------------------
# Market bucketing
# ---------------------------------------------------------------------------

PRIMARY_MARKETS = {"GH", "DE", "IN"}


def market_bucket(country_code: str | None) -> str:
    """One of 'Ghana' | 'Germany' | 'India' | 'Other'."""
    if not country_code:
        return "Other"
    code = country_code.upper()
    if code == "GH":
        return "Ghana"
    if code == "DE":
        return "Germany"
    if code == "IN":
        return "India"
    return "Other"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

async def backfill_country_codes(users_collection, *, logger=None) -> int:
    """Idempotent migration: sets `country_code` for users where it is missing.

    Returns the number of users updated. Safe to call on every server start —
    it only writes when `country_code` is None or empty.
    """
    if users_collection is None:
        return 0
    try:
        cursor = users_collection.find(
            {"$or": [{"country_code": None}, {"country_code": {"$exists": False}}, {"country_code": ""}]},
            projection={"country": 1, "country_code": 1},
        )
        updated = 0
        async for user in cursor:
            code = derive_country_code(user.get("country"))
            if not code:
                continue
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"country_code": code}},
            )
            updated += 1
        if logger and updated:
            logger.info("Analytics migration: back-filled country_code for %s users", updated)
        return updated
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.warning("backfill_country_codes failed: %s", exc)
        return 0


COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "Afghanistan": "AF", "Albania": "AL", "Algeria": "DZ", "Andorra": "AD", "Angola": "AO", "Argentina": "AR",
    "Armenia": "AM", "Australia": "AU", "Austria": "AT", "Azerbaijan": "AZ", "Bahamas": "BS", "Bahrain": "BH",
    "Bangladesh": "BD", "Barbados": "BB", "Belgium": "BE", "Belize": "BZ", "Benin": "BJ", "Bhutan": "BT",
    "Bolivia": "BO", "Bosnia and Herzegovina": "BA", "Botswana": "BW", "Brazil": "BR", "Brunei": "BN",
    "Bulgaria": "BG", "Burkina Faso": "BF", "Burundi": "BI", "Cambodia": "KH", "Cameroon": "CM", "Canada": "CA",
    "Cape Verde": "CV", "Chile": "CL", "China": "CN", "Colombia": "CO", "Costa Rica": "CR", "Croatia": "HR",
    "Cuba": "CU", "Cyprus": "CY", "Czech Republic": "CZ", "Denmark": "DK", "Djibouti": "DJ", "Dominica": "DM",
    "Dominican Republic": "DO", "Ecuador": "EC", "Egypt": "EG", "El Salvador": "SV", "Estonia": "EE",
    "Ethiopia": "ET", "Fiji": "FJ", "Finland": "FI", "France": "FR", "Georgia": "GE", "Germany": "DE",
    "Ghana": "GH", "Greece": "GR", "Guatemala": "GT", "Honduras": "HN", "Hungary": "HU", "Iceland": "IS",
    "India": "IN", "Indonesia": "ID", "Iran": "IR", "Iraq": "IQ", "Ireland": "IE", "Israel": "IL",
    "Italy": "IT", "Jamaica": "JM", "Japan": "JP", "Jordan": "JO", "Kazakhstan": "KZ", "Kenya": "KE",
    "Kuwait": "KW", "Latvia": "LV", "Lebanon": "LB", "Libya": "LY", "Liechtenstein": "LI", "Lithuania": "LT",
    "Luxembourg": "LU", "Macedonia": "MK", "Madagascar": "MG", "Malaysia": "MY", "Maldives": "MV",
    "Malta": "MT", "Mexico": "MX", "Moldova": "MD", "Monaco": "MC", "Mongolia": "MN", "Montenegro": "ME",
    "Morocco": "MA", "Nepal": "NP", "Netherlands": "NL", "New Zealand": "NZ", "Nicaragua": "NI",
    "Nigeria": "NG", "Norway": "NO", "Oman": "OM", "Pakistan": "PK", "Panama": "PA", "Paraguay": "PY",
    "Peru": "PE", "Philippines": "PH", "Poland": "PL", "Portugal": "PT", "Qatar": "QA", "Romania": "RO",
    "Russia": "RU", "Rwanda": "RW", "Saudi Arabia": "SA", "Senegal": "SN", "Serbia": "RS", "Singapore": "SG",
    "Slovakia": "SK", "Slovenia": "SI", "Somalia": "SO", "South Africa": "ZA", "South Korea": "KR",
    "Spain": "ES", "Sri Lanka": "LK", "Sudan": "SD", "Sweden": "SE", "Switzerland": "CH", "Syria": "SY",
    "Taiwan": "TW", "Tajikistan": "TJ", "Tanzania": "TZ", "Thailand": "TH", "Tunisia": "TN", "Turkey": "TR",
    "Uganda": "UG", "Ukraine": "UA", "United Arab Emirates": "AE", "United Kingdom": "GB", "United States": "US",
    "Uruguay": "UY", "Uzbekistan": "UZ", "Venezuela": "VE", "Vietnam": "VN", "Yemen": "YE", "Zambia": "ZM",
    "Zimbabwe": "ZW"
}

CODE_TO_COUNTRY_NAME: dict[str, str] = {v: k for k, v in COUNTRY_NAME_TO_CODE.items()}
