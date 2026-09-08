from datetime import date, datetime, timezone

from app.utils.analytics import (
    market_filter,
    parse_time_range,
    viral_coefficient,
)


def test_today_previous_window_has_equal_elapsed_duration():
    now = datetime(2026, 8, 8, 12, 30, tzinfo=timezone.utc)

    start, end, previous_start, previous_end = parse_time_range("today", now=now)

    assert start == datetime(2026, 8, 8, tzinfo=timezone.utc)
    assert end - start == previous_end - previous_start
    assert previous_end < start


def test_custom_range_is_inclusive_and_compares_equal_window():
    start, end, previous_start, previous_end = parse_time_range(
        "custom",
        date(2026, 8, 1),
        date(2026, 8, 7),
    )

    assert start == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 7, 23, 59, 59, tzinfo=timezone.utc)
    assert end - start == previous_end - previous_start


def test_market_filter_prefers_iso_country_code():
    clauses = market_filter("ghana")["$or"]
    assert {"country_code": "GH"} in clauses
    assert {"countryCode": {"$in": ["GH", "gh"]}} in clauses
    assert {"onboarding_state.countryCode": {"$in": ["GH", "gh"]}} in clauses
    assert market_filter("all") == {}


def test_market_filter_resolves_non_primary_country_name():
    clauses = market_filter("Bangladesh")["$or"]
    assert {"country_code": "BD"} in clauses
    assert {"country": {"$regex": "^Bangladesh$", "$options": "i"}} in clauses


def test_viral_coefficient_is_per_ten_not_percentage():
    assert viral_coefficient(2, 10) == 2.0
    assert viral_coefficient(0, 0) == 0.0
