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
