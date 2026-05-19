from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dependencies import require_access_user
from ..models import LongevityWearablesResponse
from .schemas import (
    GarminWebhookRequest,
    GarminWebhookResponse,
    HealthMetricListResponse,
    HealthMetricResponse,
    HealthMetricSummaryResponse,
    LongevityWearableSyncRequest,
    MobileHealthSyncRequest,
    OAuthConnectResponse,
    ProviderDisconnectResponse,
    ProviderSyncRequest,
    ProviderSyncResponse,
    WearableConnectionResponse,
    WearableConnectionsResponse,
)
from .service import (
    build_longevity_wearables_response,
    build_oauth_connect_url,
    connect_demo_provider,
    disconnect_provider,
    exchange_fitbit_code,
    exchange_garmin_code,
    handle_garmin_webhook,
    ingest_mobile_sync,
    list_user_connections,
    query_health_metrics,
    resolve_target_user_id,
    summarize_health_metrics,
    sync_connected_wearables_for_user,
    sync_fitbit,
    sync_garmin,
    verify_garmin_webhook_signature,
)


router = APIRouter()


def _metric_response(item: dict) -> HealthMetricResponse:
    return HealthMetricResponse(
        id=str(item.get("_id") or ""),
        user_id=str(item.get("user_id") or ""),
        provider=str(item.get("provider") or ""),
        metric_type=str(item.get("metric_type") or ""),
        value=item.get("value"),
        unit=str(item.get("unit") or ""),
        start_time=item.get("start_time"),
        end_time=item.get("end_time"),
        source_device=str(item.get("source_device") or ""),
        metadata=dict(item.get("metadata") or {}),
        synced_at=item.get("synced_at"),
    )


@router.get("/wearables/connections", response_model=WearableConnectionsResponse)
async def wearable_connections(
    user: dict = Depends(require_access_user),
) -> WearableConnectionsResponse:
    records = await list_user_connections(str(user["_id"]))
    return WearableConnectionsResponse(
        connections=[WearableConnectionResponse(**record) for record in records]
    )


@router.delete("/wearables/{provider}/connection", response_model=ProviderDisconnectResponse)
async def wearable_disconnect(
    provider: str,
    user: dict = Depends(require_access_user),
) -> ProviderDisconnectResponse:
    await disconnect_provider(str(user["_id"]), provider)
    return ProviderDisconnectResponse(provider=provider)


@router.post("/wearables/{provider}/demo-connect", response_model=WearableConnectionResponse)
async def wearable_demo_connect(
    provider: str,
    user: dict = Depends(require_access_user),
) -> WearableConnectionResponse:
    connection = await connect_demo_provider(str(user["_id"]), provider)
    return WearableConnectionResponse(**connection)


@router.post("/wearables/apple-health/sync", response_model=ProviderSyncResponse)
async def apple_health_sync(
    payload: MobileHealthSyncRequest,
    user: dict = Depends(require_access_user),
) -> ProviderSyncResponse:
    result = await ingest_mobile_sync(
        str(user["_id"]),
        "apple-health",
        [item.model_dump() for item in payload.metrics],
        source_device=payload.source_device,
        batch_id=payload.batch_id,
    )
    return ProviderSyncResponse(
        provider="apple-health",
        user_id=str(user["_id"]),
        synced_records=int(result["inserted"]),
        skipped_duplicates=int(result["skipped"]),
        connection_status=str((result["connection"] or {}).get("status") or "connected"),
        last_synced_at=result["last_synced_at"],
        message="Apple Health data synced successfully.",
    )


@router.post("/wearables/health-connect/sync", response_model=ProviderSyncResponse)
async def health_connect_sync(
    payload: MobileHealthSyncRequest,
    user: dict = Depends(require_access_user),
) -> ProviderSyncResponse:
    result = await ingest_mobile_sync(
        str(user["_id"]),
        "health-connect",
        [item.model_dump() for item in payload.metrics],
        source_device=payload.source_device,
        batch_id=payload.batch_id,
    )
    return ProviderSyncResponse(
        provider="health-connect",
        user_id=str(user["_id"]),
        synced_records=int(result["inserted"]),
        skipped_duplicates=int(result["skipped"]),
        connection_status=str((result["connection"] or {}).get("status") or "connected"),
        last_synced_at=result["last_synced_at"],
        message="Health Connect data synced successfully.",
    )


@router.get("/wearables/fitbit/connect", response_model=OAuthConnectResponse)
async def fitbit_connect(
    user: dict = Depends(require_access_user),
) -> OAuthConnectResponse:
    payload = await build_oauth_connect_url(str(user["_id"]), "fitbit")
    return OAuthConnectResponse(**payload)


@router.get("/wearables/fitbit/callback", response_model=WearableConnectionResponse)
async def fitbit_callback(
    code: str,
    state: str,
) -> WearableConnectionResponse:
    connection = await exchange_fitbit_code(state, code)
    return WearableConnectionResponse(**connection)


@router.post("/wearables/fitbit/sync", response_model=ProviderSyncResponse)
async def fitbit_sync(
    payload: ProviderSyncRequest,
    user: dict = Depends(require_access_user),
) -> ProviderSyncResponse:
    inserted, skipped = await sync_fitbit(
        str(user["_id"]),
        start_date=payload.start_date,
        end_date=payload.end_date,
        metrics=[item.model_dump() for item in payload.metrics],
        source_device=payload.source_device,
        pull_remote=payload.pull_remote,
    )
    return ProviderSyncResponse(
        provider="fitbit",
        user_id=str(user["_id"]),
        synced_records=inserted,
        skipped_duplicates=skipped,
        last_synced_at=None,
        message="Fitbit sync completed.",
    )


@router.get("/wearables/garmin/connect", response_model=OAuthConnectResponse)
async def garmin_connect(
    user: dict = Depends(require_access_user),
) -> OAuthConnectResponse:
    payload = await build_oauth_connect_url(str(user["_id"]), "garmin")
    return OAuthConnectResponse(**payload)


@router.get("/wearables/garmin/callback", response_model=WearableConnectionResponse)
async def garmin_callback(
    code: str,
    state: str,
) -> WearableConnectionResponse:
    connection = await exchange_garmin_code(state, code)
    return WearableConnectionResponse(**connection)


@router.post("/wearables/garmin/sync", response_model=ProviderSyncResponse)
async def garmin_sync(
    payload: ProviderSyncRequest,
    user: dict = Depends(require_access_user),
) -> ProviderSyncResponse:
    inserted, skipped = await sync_garmin(
        str(user["_id"]),
        start_date=payload.start_date,
        end_date=payload.end_date,
        metrics=[item.model_dump() for item in payload.metrics],
        source_device=payload.source_device,
        pull_remote=payload.pull_remote,
    )
    return ProviderSyncResponse(
        provider="garmin",
        user_id=str(user["_id"]),
        synced_records=inserted,
        skipped_duplicates=skipped,
        last_synced_at=None,
        message="Garmin sync completed.",
    )


@router.post("/wearables/garmin/webhook", response_model=GarminWebhookResponse)
async def garmin_webhook(
    request: Request,
    payload: GarminWebhookRequest,
) -> GarminWebhookResponse:
    await verify_garmin_webhook_signature(request)
    accepted, synced_records = await handle_garmin_webhook(payload.model_dump())
    if not accepted:
        raise HTTPException(status_code=404, detail="Garmin user mapping not found")
    return GarminWebhookResponse(
        accepted=True,
        queued=not bool(payload.metrics),
        synced_records=synced_records,
        message="Garmin webhook processed.",
    )


@router.get("/health-data/me", response_model=HealthMetricListResponse)
async def health_data_me(
    provider: str | None = None,
    metric_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: str | None = Query(default=None, description="Admin-only cross-user query override."),
    user: dict = Depends(require_access_user),
) -> HealthMetricListResponse:
    target_user_id = resolve_target_user_id(user, user_id)
    records = await query_health_metrics(
        target_user_id,
        provider=provider,
        metric_type=metric_type,
        start_date=start_date,
        end_date=end_date,
    )
    return HealthMetricListResponse(
        items=[_metric_response(item) for item in records],
        total=len(records),
    )


@router.get("/health-data/me/summary", response_model=HealthMetricSummaryResponse)
async def health_data_me_summary(
    provider: str | None = None,
    metric_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: str | None = Query(default=None, description="Admin-only cross-user query override."),
    user: dict = Depends(require_access_user),
) -> HealthMetricSummaryResponse:
    target_user_id = resolve_target_user_id(user, user_id)
    summary_items = await summarize_health_metrics(
        target_user_id,
        provider=provider,
        metric_type=metric_type,
        start_date=start_date,
        end_date=end_date,
    )
    return HealthMetricSummaryResponse(
        user_id=target_user_id,
        from_date=start_date,
        to_date=end_date,
        items=summary_items,
    )


@router.get("/health-data/me/{metric_type}", response_model=HealthMetricListResponse)
async def health_data_by_metric_type(
    metric_type: str,
    provider: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: str | None = Query(default=None, description="Admin-only cross-user query override."),
    user: dict = Depends(require_access_user),
) -> HealthMetricListResponse:
    target_user_id = resolve_target_user_id(user, user_id)
    records = await query_health_metrics(
        target_user_id,
        provider=provider,
        metric_type=metric_type,
        start_date=start_date,
        end_date=end_date,
    )
    return HealthMetricListResponse(
        items=[_metric_response(item) for item in records],
        total=len(records),
    )


@router.get("/longevity-os/wearables", response_model=LongevityWearablesResponse)
async def longevity_os_wearables(
    user: dict = Depends(require_access_user),
):
    return await build_longevity_wearables_response(str(user["_id"]))


@router.post("/longevity-os/wearables/sync", response_model=LongevityWearablesResponse)
async def longevity_os_sync_wearables(
    payload: LongevityWearableSyncRequest | None = None,
    user: dict = Depends(require_access_user),
):
    selected_provider = payload.provider if payload else None
    return await sync_connected_wearables_for_user(str(user["_id"]), providers=[selected_provider] if selected_provider else None)
