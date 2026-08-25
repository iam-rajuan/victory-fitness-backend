from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from urllib import error, request
from uuid import uuid4

from .config import settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import sentry_sdk
except ModuleNotFoundError:  # pragma: no cover - test/local fallback
    sentry_sdk = None

try:  # pragma: no cover - optional dependency
    from opentelemetry import trace
except ModuleNotFoundError:  # pragma: no cover - test/local fallback
    trace = None


def observability_status() -> dict[str, Any]:
    return {
        "featureFlagsProvider": str(settings.feature_flags_provider or "growthbook"),
        "requestAnalyticsEnabled": bool(settings.request_analytics_enabled),
        "posthogConfigured": bool(settings.posthog_api_key),
        "plausibleConfigured": bool(settings.plausible_domain),
        "sentryConfigured": bool(settings.sentry_dsn),
        "otelConfigured": bool(settings.otel_exporter_otlp_endpoint),
        "cloudflareConfigured": bool(settings.cloudflare_zone or settings.cloudflare_zero_trust_aud),
    }


def init_observability() -> None:
    if settings.sentry_dsn and sentry_sdk is not None:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.0)
    if settings.otel_exporter_otlp_endpoint and trace is not None:
        logger.info(
            "otel_configured endpoint=%s service_name=%s",
            settings.otel_exporter_otlp_endpoint,
            settings.otel_service_name,
        )


def capture_exception(exc: Exception, *, context: dict[str, Any] | None = None) -> None:
    if sentry_sdk is not None and settings.sentry_dsn:
        with sentry_sdk.push_scope() as scope:  # pragma: no cover - optional dependency
            for key, value in (context or {}).items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exc)
    logger.error("captured_exception error=%s context=%s", exc.__class__.__name__, context or {})


def _send_posthog_event(event: str, properties: dict[str, Any]) -> None:
    if not settings.posthog_api_key:
        return
    payload = {
        "api_key": settings.posthog_api_key,
        "event": event,
        "distinct_id": str(properties.get("distinct_id") or properties.get("user_id") or properties.get("trace_id") or "server"),
        "properties": properties,
    }
    endpoint = f"{settings.posthog_api_host.rstrip('/')}/capture/"
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        response.read()


def _send_plausible_event(name: str, props: dict[str, Any]) -> None:
    if not settings.plausible_domain:
        return
    payload = {
        "name": name,
        "domain": settings.plausible_domain,
        "url": str(props.get("url") or "https://api.victoryfitness.de/internal"),
        "props": props,
    }
    req = request.Request(
        f"{settings.plausible_api_host.rstrip('/')}/api/event",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **({"Authorization": f"Bearer {settings.plausible_api_key}"} if settings.plausible_api_key else {}),
        },
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        response.read()


async def record_observability_event(event: str, properties: dict[str, Any]) -> None:
    tasks = []
    if settings.posthog_api_key:
        tasks.append(asyncio.to_thread(_send_posthog_event, event, properties))
    if settings.plausible_domain:
        tasks.append(asyncio.to_thread(_send_plausible_event, event, properties))
    if not tasks:
        return
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.warning("observability_event_failed event=%s error=%s", event, result.__class__.__name__)


def _request_ip(request) -> str:
    trusted_header = str(settings.trusted_proxy_header or "CF-Connecting-IP").strip()
    candidate = request.headers.get(trusted_header) or request.headers.get("x-forwarded-for") or ""
    if candidate:
        return candidate.split(",")[0].strip()
    return request.client.host if request.client else ""


async def observability_middleware(request, call_next):
    request_id = str(uuid4())
    trace_id = str(uuid4()).replace("-", "")
    request.state.request_id = request_id
    request.state.trace_id = trace_id
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        capture_exception(
            exc,
            context={
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id,
                "trace_id": trace_id,
                "ip": _request_ip(request),
                "duration_ms": duration_ms,
            },
        )
        raise
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = trace_id
    if settings.request_analytics_enabled:
        asyncio.create_task(
            record_observability_event(
                "api_request_completed",
                {
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "ip": _request_ip(request),
                    "url": str(request.url),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
    return response
