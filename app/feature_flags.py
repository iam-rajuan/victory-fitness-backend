from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .database import feature_flags_collection


def _rollout_bucket(*parts: str) -> int:
    seed = ":".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


async def list_feature_flags() -> list[dict[str, Any]]:
    rows = await feature_flags_collection.find({}).sort("key", 1).to_list(length=None)
    return [dict(row) for row in rows if isinstance(row, dict)]


async def upsert_feature_flag(
    *,
    key: str,
    description: str,
    enabled: bool,
    rollout_pct: int,
    allowed_countries: list[str],
) -> dict[str, Any]:
    normalized_key = str(key).strip().lower()
    now = datetime.now(timezone.utc)
    update = {
        "key": normalized_key,
        "description": str(description or "").strip(),
        "enabled": bool(enabled),
        "rollout_pct": max(min(int(rollout_pct), 100), 0),
        "allowed_countries": sorted({str(item or "").strip().upper() for item in allowed_countries if str(item or "").strip()}),
        "updated_at": now,
    }
    await feature_flags_collection.update_one(
        {"key": normalized_key},
        {"$set": update, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return await feature_flags_collection.find_one({"key": normalized_key}) or update


async def evaluate_feature_flag(key: str, *, user: dict | None = None) -> tuple[bool, str]:
    normalized_key = str(key).strip().lower()
    record = await feature_flags_collection.find_one({"key": normalized_key})
    if not record:
        return False, "missing"
    if not bool(record.get("enabled")):
        return False, "disabled"
    allowed_countries = [str(item or "").strip().upper() for item in record.get("allowed_countries") or [] if str(item or "").strip()]
    user_country = str((user or {}).get("country_code") or "").strip().upper()
    if allowed_countries and user_country not in allowed_countries:
        return False, "country_excluded"
    rollout_pct = max(min(int(record.get("rollout_pct") or 0), 100), 0)
    if rollout_pct >= 100:
        return True, "full_rollout"
    if rollout_pct <= 0:
        return False, "rollout_zero"
    subject_key = str((user or {}).get("_id") or (user or {}).get("id") or "anonymous")
    bucket = _rollout_bucket(normalized_key, subject_key, user_country)
    return bucket < rollout_pct, f"rollout_{rollout_pct}"


async def evaluate_many_feature_flags(keys: list[str], *, user: dict | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key in keys:
        enabled, reason = await evaluate_feature_flag(key, user=user)
        results.append({"key": str(key).strip().lower(), "enabled": enabled, "reason": reason})
    return results


def feature_flag_provider_name() -> str:
    return str(getattr(settings, "feature_flags_provider", "growthbook") or "growthbook").lower()
