from datetime import datetime, timezone

from fastapi import APIRouter

from ...core.legacy import *
from ...feature_flags import evaluate_many_feature_flags, feature_flag_provider_name, list_feature_flags, upsert_feature_flag
from ...models import (
    AdminFeatureFlagItem,
    AdminFeatureFlagListResponse,
    AdminFeatureFlagRequest,
    RuntimeFeatureFlagItem,
    RuntimeFeatureFlagListResponse,
)

router = APIRouter()


@router.get("/admin/feature-flags", response_model=AdminFeatureFlagListResponse)
async def admin_list_feature_flags(_: dict = Depends(_require_admin_user)) -> AdminFeatureFlagListResponse:
    rows = await list_feature_flags()
    return AdminFeatureFlagListResponse(
        items=[
            AdminFeatureFlagItem(
                key=str(row.get("key") or ""),
                description=str(row.get("description") or ""),
                enabled=bool(row.get("enabled")),
                rolloutPct=int(row.get("rollout_pct") or 0),
                allowedCountries=[str(item or "").upper() for item in row.get("allowed_countries") or [] if str(item or "").strip()],
                updatedAt=row.get("updated_at") or datetime.now(timezone.utc),
            )
            for row in rows
        ]
    )


@router.post("/admin/feature-flags", response_model=AdminFeatureFlagItem)
async def admin_upsert_feature_flag(
    payload: AdminFeatureFlagRequest,
    admin: dict = Depends(_require_admin_user),
) -> AdminFeatureFlagItem:
    row = await upsert_feature_flag(
        key=payload.key,
        description=payload.description,
        enabled=payload.enabled,
        rollout_pct=payload.rolloutPct,
        allowed_countries=payload.allowedCountries,
    )
    await _record_analytics_event(
        "feature_flag_updated",
        user_id=str(admin.get("_id") or ""),
        details={"key": payload.key, "rollout_pct": payload.rolloutPct, "enabled": payload.enabled},
    )
    return AdminFeatureFlagItem(
        key=str(row.get("key") or ""),
        description=str(row.get("description") or ""),
        enabled=bool(row.get("enabled")),
        rolloutPct=int(row.get("rollout_pct") or 0),
        allowedCountries=[str(item or "").upper() for item in row.get("allowed_countries") or [] if str(item or "").strip()],
        updatedAt=row.get("updated_at") or datetime.now(timezone.utc),
    )


@router.get("/me/feature-flags", response_model=RuntimeFeatureFlagListResponse)
async def get_me_feature_flags(user: dict = Depends(_require_access_user)) -> RuntimeFeatureFlagListResponse:
    rows = await list_feature_flags()
    keys = [str(row.get("key") or "").strip().lower() for row in rows if str(row.get("key") or "").strip()]
    evaluated = await evaluate_many_feature_flags(keys, user=user)
    return RuntimeFeatureFlagListResponse(
        provider=feature_flag_provider_name(),
        items=[RuntimeFeatureFlagItem(**item) for item in evaluated],
    )
