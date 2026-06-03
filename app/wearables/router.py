from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dependencies import ensure_subscription_feature_access, require_access_user, require_admin_user
from ..models import (
    IntegrationConnectStartResponse,
    IntegrationConnectionResponse,
    IntegrationImportFileRequest,
    IntegrationImportQrRequest,
    IntegrationListResponse,
    LongevityWearablesResponse,
    NativeIntegrationConnectedRequest,
    NativeIntegrationSamplesRequest,
)
from .adapters import PROVIDER_NOT_CONFIGURED, is_provider_configured
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
    QRHealthSyncRequest,
    ProviderSyncRequest,
    ProviderSyncResponse,
    WearableConnectionResponse,
    WearableConnectionsResponse,
)
from .service import (
    backfill_current_health_metrics_from_history,
    build_longevity_wearables_response,
    build_oauth_connect_url,
    connect_local_provider,
    connect_demo_provider,
    decode_qr_health_payload,
    disconnect_provider,
    enqueue_import_job,
    enqueue_provider_sync_job,
    exchange_fitbit_code,
    exchange_google_fit_code,
    exchange_garmin_code,
    handle_garmin_webhook,
    ingest_mobile_sync,
    refresh_longevity_profile_cache,
    list_integrations,
    list_user_connections,
    mark_native_provider_connected,
    query_health_metrics,
    resolve_target_user_id,
    _serialize_connection,
    summarize_health_metrics,
    sync_connected_wearables_for_user,
    sync_fitbit,
    sync_google_fit as sync_google_fit_provider,
    sync_garmin,
    verify_garmin_webhook_signature,
)


router = APIRouter()


async def require_longevity_access_user(
    user: dict = Depends(require_access_user),
) -> dict:
    ensure_subscription_feature_access(
        user,
        "longevity",
        "Your current plan does not include Longevity OS access",
    )
    return user


@router.post("/admin/wearables/backfill-current-health-metrics")
async def admin_backfill_current_health_metrics(
    force: bool = Query(default=False, description="Rebuild the current snapshot collection from raw history."),
    _: dict = Depends(require_admin_user),
) -> dict[str, object]:
    processed = await backfill_current_health_metrics_from_history(force=force)
    return {
        "status": "success",
        "processed": processed,
        "force": force,
        "message": "Current health metrics backfill completed.",
    }


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


@router.get("/integrations", response_model=IntegrationListResponse)
async def integrations_list(
    user: dict = Depends(require_longevity_access_user),
) -> IntegrationListResponse:
    items = await list_integrations(str(user["_id"]))
    return IntegrationListResponse(
        items=[IntegrationConnectionResponse(**item) for item in items]
    )


@router.get("/integrations/{provider}/connect", response_model=IntegrationConnectStartResponse)
async def integration_connect(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> IntegrationConnectStartResponse:
    normalized_provider = provider.strip().lower()
    if normalized_provider in {"fitbit", "google-fit", "garmin"}:
        if not is_provider_configured(normalized_provider):
            raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
        payload = await build_oauth_connect_url(str(user["_id"]), normalized_provider)
        return IntegrationConnectStartResponse(
            provider=normalized_provider,
            connection_type="oauth",
            authorization_url=str(payload.get("authorization_url") or ""),
            state=str(payload.get("state") or ""),
            expires_at=payload.get("expires_at"),
            message="Continue in browser to complete provider login.",
        )
    if normalized_provider in {"apple-health", "health-connect", "this-phone"}:
        return IntegrationConnectStartResponse(
            provider=normalized_provider,
            connection_type="native",
            message="Continue in the mobile app to approve native health permissions.",
        )
    if normalized_provider == "qr-import":
        return IntegrationConnectStartResponse(
            provider=normalized_provider,
            connection_type="import",
            message="Continue in the app to import a supported QR or file payload.",
        )
    raise HTTPException(status_code=400, detail="Unsupported integration provider")


@router.post("/integrations/{provider}/connect-local", response_model=WearableConnectionResponse)
async def integration_connect_local(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> WearableConnectionResponse:
    connection = await connect_local_provider(str(user["_id"]), provider)
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.get("/integrations/{provider}/callback", response_model=WearableConnectionResponse)
async def integration_callback(
    provider: str,
    code: str,
    state: str,
) -> WearableConnectionResponse:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "fitbit":
        connection = await exchange_fitbit_code(state, code)
    elif normalized_provider == "google-fit":
        connection = await exchange_google_fit_code(state, code)
    elif normalized_provider == "garmin":
        connection = await exchange_garmin_code(state, code)
    else:
        raise HTTPException(status_code=400, detail="Callback is only supported for OAuth providers")
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/integrations/native/connected", response_model=WearableConnectionResponse)
async def integrations_native_connected(
    payload: NativeIntegrationConnectedRequest,
    user: dict = Depends(require_longevity_access_user),
) -> WearableConnectionResponse:
    connection = await mark_native_provider_connected(
        str(user["_id"]),
        payload.provider,
        source_device=payload.source_device,
        platform=payload.platform,
        permission_granted=payload.permission_granted,
        metadata=payload.metadata,
    )
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/integrations/native/samples", response_model=ProviderSyncResponse)
async def integrations_native_samples(
    payload: NativeIntegrationSamplesRequest,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    mobile_payload = MobileHealthSyncRequest(
        metrics=payload.metrics,
        source_device=payload.source_device,
        batch_id=payload.batch_id,
    )
    provider = payload.provider.strip().lower()
    if provider == "this-phone":
        provider = "apple-health" if payload.platform.strip().lower() == "ios" else "health-connect"
    result = await ingest_mobile_sync(
        str(user["_id"]),
        provider,
        [item.model_dump() for item in mobile_payload.metrics],
        source_device=mobile_payload.source_device,
        batch_id=mobile_payload.batch_id,
        trigger="native_samples",
    )
    await refresh_longevity_profile_cache(str(user["_id"]))
    return ProviderSyncResponse(
        provider=provider,
        user_id=str(user["_id"]),
        synced_records=int(result["inserted"]),
        skipped_duplicates=int(result["skipped"]),
        connection_status=str((result["connection"] or {}).get("status") or "connected"),
        last_synced_at=result["last_synced_at"],
        message=f"{provider} samples synced successfully.",
    )


@router.post("/integrations/{provider}/sync", response_model=ProviderSyncResponse)
async def integration_sync(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "fitbit":
        job_id = await enqueue_provider_sync_job(str(user["_id"]), "fitbit")
        return ProviderSyncResponse(provider="fitbit", user_id=str(user["_id"]), connection_status="syncing", message=f"Fitbit sync queued with job {job_id}.")
    if normalized_provider == "google-fit":
        if not is_provider_configured("google-fit"):
            raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
        job_id = await enqueue_provider_sync_job(str(user["_id"]), "google-fit")
        return ProviderSyncResponse(provider="google-fit", user_id=str(user["_id"]), connection_status="syncing", message=f"Google Fit sync queued with job {job_id}.")
    if normalized_provider == "garmin":
        if not is_provider_configured("garmin"):
            raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
        job_id = await enqueue_provider_sync_job(str(user["_id"]), "garmin")
        return ProviderSyncResponse(provider="garmin", user_id=str(user["_id"]), connection_status="syncing", message=f"Garmin sync queued with job {job_id}.")
    if normalized_provider in {"apple-health", "health-connect", "this-phone", "qr-import"}:
        connection = await connect_local_provider(str(user["_id"]), normalized_provider)
        return ProviderSyncResponse(
            provider=normalized_provider,
            user_id=str(user["_id"]),
            synced_records=0,
            skipped_duplicates=0,
            connection_status=str(connection.get("status") or "connected"),
            last_synced_at=connection.get("last_synced_at"),
            message="Sync is initiated from the mobile app for this provider.",
        )
    raise HTTPException(status_code=400, detail="Unsupported integration provider")


@router.delete("/integrations/{provider}", response_model=ProviderDisconnectResponse)
async def integration_disconnect(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderDisconnectResponse:
    result = await disconnect_provider(str(user["_id"]), provider)
    return ProviderDisconnectResponse(**result)


@router.post("/integrations/import/qr", response_model=ProviderSyncResponse)
async def integration_import_qr(
    payload: IntegrationImportQrRequest,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    decoded = decode_qr_health_payload(payload.qr_payload)
    job_id = await enqueue_import_job(
        str(user["_id"]),
        "qr-import",
        metrics=list(decoded["metrics"]),
        source_device=payload.source_device or str(decoded.get("source_device") or "QR Import"),
        batch_id=decoded.get("batch_id"),
    )
    return ProviderSyncResponse(
        provider="qr-import",
        user_id=str(user["_id"]),
        connection_status="syncing",
        message=f"QR import queued with job {job_id}.",
    )


@router.post("/integrations/import/file", response_model=ProviderSyncResponse)
async def integration_import_file(
    payload: IntegrationImportFileRequest,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    try:
        decoded_bytes = base64.b64decode(payload.content_base64.encode("utf-8"))
        parsed = json.loads(decoded_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Imported file must be base64-encoded JSON health data") from exc
    metrics = parsed.get("metrics") if isinstance(parsed, dict) else parsed
    if not isinstance(metrics, list) or not metrics:
        raise HTTPException(status_code=400, detail="Imported file does not contain any health metrics")
    job_id = await enqueue_import_job(
        str(user["_id"]),
        "qr-import",
        metrics=[dict(item) for item in metrics],
        source_device=payload.source_device or payload.file_name or "Imported File",
        batch_id=str(parsed.get("batch_id") or "") if isinstance(parsed, dict) else None,
    )
    return ProviderSyncResponse(
        provider="qr-import",
        user_id=str(user["_id"]),
        connection_status="syncing",
        message=f"File import queued with job {job_id}.",
    )


@router.post("/webhooks/fitbit")
async def fitbit_webhook(
    request: Request,
) -> dict[str, object]:
    if not is_provider_configured("fitbit"):
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
    payload = await request.json()
    return {
        "accepted": True,
        "provider": "fitbit",
        "queued": False,
        "message": "Fitbit webhook received.",
        "events": len(payload) if isinstance(payload, list) else 1,
    }



@router.post("/webhooks/google-fit")
async def google_fit_webhook(
    request: Request,
) -> dict[str, object]:
    if not is_provider_configured("google-fit"):
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
    payload = await request.json()
    return {
        "accepted": True,
        "provider": "google-fit",
        "queued": False,
        "message": "Google Fit webhook received.",
        "events": len(payload) if isinstance(payload, list) else 1,
    }


@router.get("/wearables/connections", response_model=WearableConnectionsResponse)
async def wearable_connections(
    user: dict = Depends(require_longevity_access_user),
) -> WearableConnectionsResponse:
    records = await list_user_connections(str(user["_id"]))
    return WearableConnectionsResponse(
        connections=[WearableConnectionResponse(**_serialize_connection(record)) for record in records]
    )


@router.delete("/wearables/{provider}/connection", response_model=ProviderDisconnectResponse)
async def wearable_disconnect(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderDisconnectResponse:
    result = await disconnect_provider(str(user["_id"]), provider)
    return ProviderDisconnectResponse(**result)


@router.post("/wearables/{provider}/demo-connect", response_model=WearableConnectionResponse)
async def wearable_demo_connect(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> WearableConnectionResponse:
    connection = await connect_demo_provider(str(user["_id"]), provider)
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/wearables/{provider}/connect-local", response_model=WearableConnectionResponse)
async def wearable_local_connect(
    provider: str,
    user: dict = Depends(require_longevity_access_user),
) -> WearableConnectionResponse:
    connection = await connect_local_provider(str(user["_id"]), provider)
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/wearables/apple-health/sync", response_model=ProviderSyncResponse)
async def apple_health_sync(
    payload: MobileHealthSyncRequest,
    user: dict = Depends(require_longevity_access_user),
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
    user: dict = Depends(require_longevity_access_user),
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


@router.post("/wearables/this-phone/sync", response_model=ProviderSyncResponse)
async def this_phone_sync(
    payload: MobileHealthSyncRequest,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    result = await ingest_mobile_sync(
        str(user["_id"]),
        "this-phone",
        [item.model_dump() for item in payload.metrics],
        source_device=payload.source_device or "This Phone",
        batch_id=payload.batch_id,
    )
    return ProviderSyncResponse(
        provider="this-phone",
        user_id=str(user["_id"]),
        synced_records=int(result["inserted"]),
        skipped_duplicates=int(result["skipped"]),
        connection_status=str((result["connection"] or {}).get("status") or "connected"),
        last_synced_at=result["last_synced_at"],
        message="This phone data synced successfully.",
    )


@router.post("/wearables/qr-import/sync", response_model=ProviderSyncResponse)
async def qr_import_sync(
    payload: QRHealthSyncRequest,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    decoded = decode_qr_health_payload(payload.qr_payload)
    result = await ingest_mobile_sync(
        str(user["_id"]),
        "qr-import",
        list(decoded["metrics"]),
        source_device=payload.source_device or str(decoded.get("source_device") or "QR Import"),
        batch_id=decoded.get("batch_id"),
    )
    return ProviderSyncResponse(
        provider="qr-import",
        user_id=str(user["_id"]),
        synced_records=int(result["inserted"]),
        skipped_duplicates=int(result["skipped"]),
        connection_status=str((result["connection"] or {}).get("status") or "connected"),
        last_synced_at=result["last_synced_at"],
        message="QR wearable data synced successfully.",
    )


@router.get("/wearables/fitbit/connect", response_model=OAuthConnectResponse)
async def fitbit_connect(
    user: dict = Depends(require_longevity_access_user),
) -> OAuthConnectResponse:
    payload = await build_oauth_connect_url(str(user["_id"]), "fitbit")
    return OAuthConnectResponse(**payload)


@router.get("/wearables/fitbit/callback", response_model=WearableConnectionResponse)
async def fitbit_callback(
    code: str,
    state: str,
) -> WearableConnectionResponse:
    connection = await exchange_fitbit_code(state, code)
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/wearables/fitbit/sync", response_model=ProviderSyncResponse)
async def fitbit_sync(
    payload: ProviderSyncRequest,
    user: dict = Depends(require_longevity_access_user),
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
    user: dict = Depends(require_longevity_access_user),
) -> OAuthConnectResponse:
    payload = await build_oauth_connect_url(str(user["_id"]), "garmin")
    return OAuthConnectResponse(**payload)


@router.get("/wearables/google-fit/connect", response_model=OAuthConnectResponse)
async def google_fit_connect(
    user: dict = Depends(require_longevity_access_user),
) -> OAuthConnectResponse:
    payload = await build_oauth_connect_url(str(user["_id"]), "google-fit")
    return OAuthConnectResponse(**payload)


@router.get("/wearables/google-fit/callback", response_model=WearableConnectionResponse)
async def google_fit_callback(
    code: str,
    state: str,
) -> WearableConnectionResponse:
    connection = await exchange_google_fit_code(state, code)
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/wearables/google-fit/sync", response_model=ProviderSyncResponse)
async def google_fit_sync_endpoint(
    payload: ProviderSyncRequest,
    user: dict = Depends(require_longevity_access_user),
) -> ProviderSyncResponse:
    inserted, skipped = await sync_google_fit_provider(
        str(user["_id"]),
        start_date=payload.start_date,
        end_date=payload.end_date,
        metrics=[item.model_dump() for item in payload.metrics],
        source_device=payload.source_device,
        pull_remote=payload.pull_remote,
    )
    return ProviderSyncResponse(
        provider="google-fit",
        user_id=str(user["_id"]),
        synced_records=inserted,
        skipped_duplicates=skipped,
        last_synced_at=None,
        message="Google Fit sync completed.",
    )


@router.get("/wearables/garmin/callback", response_model=WearableConnectionResponse)
async def garmin_callback(
    code: str,
    state: str,
) -> WearableConnectionResponse:
    connection = await exchange_garmin_code(state, code)
    return WearableConnectionResponse(**_serialize_connection(connection))


@router.post("/wearables/garmin/sync", response_model=ProviderSyncResponse)
async def garmin_sync(
    payload: ProviderSyncRequest,
    user: dict = Depends(require_longevity_access_user),
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
    if not is_provider_configured("garmin"):
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
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
    user: dict = Depends(require_longevity_access_user),
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
    user: dict = Depends(require_longevity_access_user),
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
    user: dict = Depends(require_longevity_access_user),
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
    user: dict = Depends(require_longevity_access_user),
):
    return await build_longevity_wearables_response(str(user["_id"]))


@router.post("/longevity-os/wearables/sync", response_model=LongevityWearablesResponse)
async def longevity_os_sync_wearables(
    payload: LongevityWearableSyncRequest | None = None,
    user: dict = Depends(require_longevity_access_user),
):
    selected_providers: list[str] = []
    if payload:
        if payload.provider:
            selected_providers.append(payload.provider)
        selected_providers.extend([provider for provider in payload.providers if provider not in selected_providers])
    return await sync_connected_wearables_for_user(
        str(user["_id"]),
        providers=selected_providers or None,
    )
