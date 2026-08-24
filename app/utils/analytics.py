"""Analytics helpers for the Admin Intelligence layer.

All helpers are pure functions over Mongo result sets so they are easy to test.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable


# ---------------------------------------------------------------------------
# Time range
# ---------------------------------------------------------------------------

VALID_PRESETS = {"today", "this_week", "this_year", "custom"}


def parse_time_range(
    preset: str = "this_week",
    custom_from: date | None = None,
    custom_to: date | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, datetime, datetime]:
    """Resolve (range_start, range_end, prev_start, prev_end) in UTC.

    The "previous" range is the same length immediately preceding the current
    range, which is exactly what the dashboard needs for trend arrows.
    """
    now = now or datetime.now(timezone.utc)
    preset = (preset or "this_week").strip().lower()
    if preset not in VALID_PRESETS:
        preset = "this_week"

    if preset == "today":
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = now
    elif preset == "this_year":
        start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        end = now
    elif preset == "custom" and custom_from and custom_to:
        start = datetime(custom_from.year, custom_from.month, custom_from.day, tzinfo=timezone.utc)
        end = datetime(custom_to.year, custom_to.month, custom_to.day, 23, 59, 59, tzinfo=timezone.utc)
    else:  # this_week (default)
        # ISO week: Monday as start
        start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        start = start_of_day - timedelta(days=start_of_day.weekday())
        end = now

    # Compare like-for-like elapsed windows and avoid overlapping the boundary.
    length = end - start
    prev_end = start - timedelta(microseconds=1)
    prev_start = prev_end - length

    return start, end, prev_start, prev_end


def trend_arrow(change_pct: float) -> str:
    """Returns 'up' | 'down' | 'flat'.
    Anything within ±0.5% counts as flat so the UI doesn't show noise."""
    if change_pct > 0.5:
        return "up"
    if change_pct < -0.5:
        return "down"
    return "flat"


def pct_change(current: float, previous: float) -> float:
    """Percentage change with a 0-safe denominator. Returns 0.0 when both are 0."""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return ((current - previous) / previous) * 100.0


def color_band(value: float, green_threshold: float, amber_threshold: float, higher_is_good: bool = True) -> str:
    """Return 'green' | 'amber' | 'red' using two thresholds.

    If higher_is_good is True (e.g. trial conversion), high values are green.
    If False (e.g. churn), low values are green.
    """
    if higher_is_good:
        if value >= green_threshold:
            return "green"
        if value >= amber_threshold:
            return "amber"
        return "red"
    if value <= green_threshold:
        return "green"
    if value <= amber_threshold:
        return "amber"
    return "red"


# ---------------------------------------------------------------------------
# Market filter
# ---------------------------------------------------------------------------

VALID_MARKETS = {"all", "ghana", "germany", "india", "other"}

MARKET_TO_CODE = {
    "ghana": "GH",
    "germany": "DE",
    "india": "IN",
}

CODE_TO_DISPLAY = {
    "GH": "Ghana",
    "DE": "Germany",
    "IN": "India",
}


def normalize_market(market: str | None) -> str:
    if not market:
        return "all"
    return market.strip().lower()


def market_filter(market: str | None) -> dict:
    """Build a Mongo filter that limits results to one market.

    `country_code` is preferred (set by the migration). When missing, fall
    back to the free-text `country` field so existing data still works.
    """
    m = normalize_market(market)
    if m == "all":
        return {}
    if m in MARKET_TO_CODE:
        code = MARKET_TO_CODE[m]
        return {
            "$or": [
                {"country_code": code},
                {"country_code": {"$exists": False}, "country": {"$regex": code_to_country_regex(code), "$options": "i"}},
            ]
        }
    if m == "other":
        primary_codes = list(MARKET_TO_CODE.values())
        return {
            "$and": [
                {"country_code": {"$nin": primary_codes + [None, ""]}},
                {"country": {"$not": {"$regex": r"ghana|germany|india", "$options": "i"}}},
            ]
        }

    # Custom country filter
    if len(m) == 2:
        code = m.upper()
        return {
            "$or": [
                {"country_code": code},
                {"country_code": {"$exists": False}, "country": {"$regex": f"^{m}$", "$options": "i"}},
            ]
        }

    # Resolve from COUNTRY_NAME_TO_CODE
    from .country import COUNTRY_NAME_TO_CODE
    cap_name = market.strip().title()
    code = COUNTRY_NAME_TO_CODE.get(cap_name)
    if code:
        return {
            "$or": [
                {"country_code": code},
                {"country_code": {"$exists": False}, "country": {"$regex": f"^{cap_name}$", "$options": "i"}},
            ]
        }

    return {
        "country": {"$regex": f"^{market.strip()}$", "$options": "i"}
    }


def code_to_country_regex(code: str) -> str:
    return {
        "GH": "ghana",
        "DE": "germany|german",
        "IN": "india|indian",
    }.get(code, "")


# ---------------------------------------------------------------------------
# Response shaping
# ---------------------------------------------------------------------------

def build_currency_breakdown(amount_by_country: dict[str, float]) -> dict:
    """Aggregate per-country totals into {eur, ghs, inr}."""
    eur = float(amount_by_country.get("DE", 0.0))
    ghs = float(amount_by_country.get("GH", 0.0))
    inr = float(amount_by_country.get("IN", 0.0))
    return {"eur": round(eur, 2), "ghs": round(ghs, 2), "inr": round(inr, 2)}


def sparkline_series(daily_totals: Iterable[dict], max_points: int = 12) -> list[dict]:
    """Take a [{date, value}] series and trim to the last `max_points` entries,
    padding with zeros if shorter. Sorts by date ascending."""
    series = sorted(daily_totals, key=lambda x: x.get("date") or "")
    series = series[-max_points:]
    out = []
    for point in series:
        out.append({
            "date": point.get("date"),
            "value": float(point.get("value", 0)),
        })
    return out


def safe_ratio(numerator: float, denominator: float) -> float:
    """Returns numerator/denominator as a percentage, or 0.0 when denominator is 0."""
    if denominator == 0:
        return 0.0
    return (numerator / denominator) * 100.0


def viral_coefficient(invited_users: int, new_users: int) -> float:
    """Invited acquisitions per ten new users, not a percentage."""
    if new_users <= 0:
        return 0.0
    return (invited_users / new_users) * 10


def aggregate_by_market(users: Iterable[dict], market_field: str = "country_code") -> dict[str, int]:
    """Bucket rows by their market code so the breakdown panel can show totals."""
    counts: dict[str, int] = {"GH": 0, "DE": 0, "IN": 0, "OTHER": 0}
    for row in users:
        code = (row.get(market_field) or "").upper()
        if code in ("GH", "DE", "IN"):
            counts[code] += 1
        else:
            counts["OTHER"] += 1
    return counts
