from fastapi import APIRouter

from ...core.legacy import *
from ...feature_flags import feature_flag_provider_name
from ...models import InfrastructureStatusResponse
from ...observability import observability_status

router = APIRouter()

@router.get("/favicon.ico")

async def get_favicon_ico() -> Response:

    content = _build_favicon_ico_bytes()

    if not content:

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(content=content, media_type="image/x-icon")

@router.get("/favicon.png")

async def get_favicon_png() -> Response:

    content = _build_favicon_png_bytes()

    if not content:

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(content=content, media_type="image/png")

@router.get("/")

async def root() -> dict[str, str]:

    return {

        "status": "success",

        "message": "Victory Fitness API is running",

    }

@router.get("/health")

async def health() -> dict[str, str]:

    return {"status": "ok"}


@router.get("/system/infrastructure", response_model=InfrastructureStatusResponse)
async def infrastructure_status() -> InfrastructureStatusResponse:
    status = observability_status()
    return InfrastructureStatusResponse(
        status="ok",
        featureFlagsProvider=feature_flag_provider_name(),
        requestAnalyticsEnabled=bool(status["requestAnalyticsEnabled"]),
        posthogConfigured=bool(status["posthogConfigured"]),
        plausibleConfigured=bool(status["plausibleConfigured"]),
        sentryConfigured=bool(status["sentryConfigured"]),
        otelConfigured=bool(status["otelConfigured"]),
        aiGenerationJobConcurrency=max(int(getattr(settings, "ai_generation_job_concurrency", 10) or 10), 1),
        aiGenerationTimeoutSeconds=max(int(getattr(settings, "ai_generation_timeout_seconds", 30) or 30), 1),
        pushNotificationConcurrency=max(int(getattr(settings, "push_notification_concurrency", 50) or 50), 1),
        weeklyDigestCronUtc=str(getattr(settings, "weekly_digest_cron_utc", "0 22 * * 0") or "0 22 * * 0"),
        gcpPrimaryRegion=str(getattr(settings, "gcp_primary_region", "") or ""),
        gcpSecondaryRegions=list(getattr(settings, "gcp_secondary_regions", []) or []),
        cloudflareConfigured=bool(status["cloudflareConfigured"]),
    )
