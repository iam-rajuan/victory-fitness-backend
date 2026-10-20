from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


def _as_aware_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def strength_plan_is_complete_or_expired(record: dict[str, Any], now: datetime | None = None) -> bool:
    reference_time = now or datetime.now(timezone.utc)
    plan = dict(record.get("plan") or {})
    days = [day for day in plan.get("days") or [] if isinstance(day, dict)]
    progress = [item for item in record.get("progress") or [] if isinstance(item, dict)]
    completed_day_keys = {str(item.get("day") or "") for item in progress if item.get("completed")}
    if days and all(str(day.get("day") or "") in completed_day_keys for day in days):
        return True

    created_at = _as_aware_utc(record.get("created_at"))
    return bool(created_at and reference_time.astimezone(timezone.utc) >= created_at + timedelta(days=7))


def newest_active_strength_plan(
    records: Iterable[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any] | None:
    reference_time = now or datetime.now(timezone.utc)
    return next(
        (
            record
            for record in records
            if isinstance(record.get("plan"), dict)
            and not strength_plan_is_complete_or_expired(record, reference_time)
        ),
        None,
    )
