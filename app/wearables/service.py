from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from pymongo import UpdateOne

from ..config import settings
from ..database import (
    health_metrics_collection,
    integration_audit_logs_collection,
    longevity_os_profiles_collection,
    provider_tokens_collection,
    sync_errors_collection,
    sync_jobs_collection,
    users_collection,
    wearable_connections_collection,
)
from ..models import LongevityWearableDeviceResponse, LongevityWearablesResponse
from ..longevity_ai import generate_longevity_quick_actions
from .adapters import PROVIDER_NOT_CONFIGURED, get_provider_adapter, is_provider_configured
from .queue import enqueue_integration_job


logger = logging.getLogger("victory_fitness.wearables")

SUPPORTED_PROVIDERS = ("apple-health", "health-connect", "fitbit", "google-fit", "garmin", "this-phone", "qr-import")
OAUTH_PROVIDERS = {"fitbit", "google-fit", "garmin"}
SUPPORTED_METRIC_TYPES = {
    "steps",
    "heart_rate",
    "sleep",
    "calories",
    "workouts",
    "workout",
    "hrv",
    "spo2",
    "stress",
    "body_battery",
    "distance",
}
PROVIDER_DISPLAY = {
    "apple-health": {
        "name": "Apple Watch / Apple Health",
        "image": "https://images.unsplash.com/photo-1434493789847-2f02dc6ca35d?w=600&q=80",
    },
    "health-connect": {
        "name": "Health Connect",
        "image": "https://images.unsplash.com/photo-1510017803434-a899398421b3?w=600&q=80",
    },
    "fitbit": {
        "name": "Fitbit",
        "image": "https://images.unsplash.com/photo-1575311373937-040b8e1fd5b2?w=600&q=80",
    },
    "google-fit": {
        "name": "Google Fit",
        "image": "https://images.unsplash.com/photo-1510017803434-a899398421b3?w=600&q=80",
    },
    "garmin": {
        "name": "Garmin",
        "image": "https://images.unsplash.com/photo-1557438159-8664b4c7301c?w=600&q=80",
    },
    "this-phone": {
        "name": "This Phone",
        "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&q=80",
    },
    "qr-import": {
        "name": "QR Import",
        "image": "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?w=600&q=80",
    },
}
PROVIDER_CONNECTION_TYPE = {
    "apple-health": "native",
    "health-connect": "native",
    "fitbit": "oauth",
    "google-fit": "oauth",
    "garmin": "oauth",
    "this-phone": "native",
    "qr-import": "import",
}
DEMO_PROVIDER_SOURCE_DEVICE = {
    "apple-health": "Apple Watch Series 9",
    "health-connect": "Pixel Watch 3",
    "fitbit": "Fitbit Charge 6",
    "google-fit": "Google Fit",
    "garmin": "Garmin Venu 3",
    "this-phone": "This Phone",
    "qr-import": "QR Scanner Import",
}
DEMO_PROVIDER_METADATA = {
    "apple-health": {
        "source_app": "HealthKit",
        "ecosystem": "Apple",
        "sample_origin": "ios_demo_seed",
    },
    "health-connect": {
        "source_app": "Health Connect",
        "ecosystem": "Android",
        "sample_origin": "android_demo_seed",
    },
    "fitbit": {
        "source_app": "Fitbit Cloud",
        "ecosystem": "Fitbit",
        "sample_origin": "fitbit_demo_seed",
    },
    "google-fit": {
        "source_app": "Google Fit",
        "ecosystem": "Google",
        "sample_origin": "google_fit_sync",
    },
    "garmin": {
        "source_app": "Garmin Connect",
        "ecosystem": "Garmin",
        "sample_origin": "garmin_demo_seed",
    },
    "this-phone": {
        "source_app": "Victory Fitness App",
        "ecosystem": "Mobile",
        "sample_origin": "this_phone_manual_sync",
    },
    "qr-import": {
        "source_app": "QR Import",
        "ecosystem": "Manual",
        "sample_origin": "qr_import_sync",
    },
}


LONGEVITY_HABIT_TEMPLATES = [
    {"id": "hydration", "title": "Hydration", "subtitle": "Daily protocol for longevity", "icon": "water-outline"},
    {"id": "sleep-7h", "title": "7h+ Sleep", "subtitle": "Daily protocol for longevity", "icon": "moon-outline"},
    {"id": "zone-2", "title": "Zone 2 Cardio", "subtitle": "Aerobic base for recovery and heart health", "icon": "heart-outline"},
    {"id": "breathwork", "title": "Breathwork", "subtitle": "Reduce stress and support recovery", "icon": "reorder-two-outline"},
]

LONGEVITY_HEAL_CATEGORY_TEMPLATES = [
    {"id": "recovery", "label": "POST WORKOUT RECOVERY", "image": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80", "color": "#EC4899"},
    {"id": "heart", "label": "HEART HEALTH", "image": "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=600&q=80", "color": "#00C9A7"},
    {"id": "mental", "label": "MENTAL HEALTH AND ANXIETY", "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600&q=80", "color": "#F97316"},
    {"id": "immunity", "label": "IMMUNITY AND INFECTION", "image": "https://images.unsplash.com/photo-1584362917165-526a968579e8?w=600&q=80", "color": "#FF6B6B"},
]
LONGEVITY_QUICK_ACTION_TEMPLATES = {
    "recovery": {
        "id": "recovery-reset",
        "label": "Recovery Reset",
        "image": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80",
        "color": "#EC4899",
    },
    "sleep": {
        "id": "sleep-protocol",
        "label": "Sleep Protocol",
        "image": "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=600&q=80",
        "color": "#4F8EF7",
    },
    "stress": {
        "id": "stress-reset",
        "label": "Stress Reset",
        "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600&q=80",
        "color": "#F97316",
    },
    "movement": {
        "id": "movement-boost",
        "label": "Movement Boost",
        "image": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=600&q=80",
        "color": "#10B981",
    },
    "breath": {
        "id": "breath-lab",
        "label": "Breath Lab",
        "image": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=600&q=80",
        "color": "#14B8A6",
    },
}

LONGEVITY_MASTERCLASS_TEMPLATES = {
    "heart": {
        "id": "mc-heart-zone2",
        "title": "Zone 2 For Heart Health",
        "description": "Build aerobic capacity, improve recovery, and support long-term cardiovascular resilience.",
        "thumbnail": "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=600&q=80",
    },
    "recovery": {
        "id": "mc-recovery-blueprint",
        "title": "Post Workout Recovery Blueprint",
        "description": "Use sleep, hydration, and recovery windows to turn training stress into adaptation.",
        "thumbnail": "https://images.unsplash.com/photo-1541781774459-bb2a1b920155?w=600&q=80",
    },
    "mental": {
        "id": "mc-stress-anxiety",
        "title": "Mental Health And Anxiety Reset",
        "description": "Lower baseline stress with breathing, routine, and recovery practices built from your data.",
        "thumbnail": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600&q=80",
    },
    "immunity": {
        "id": "mc-immunity-foundation",
        "title": "Immunity And Infection Foundation",
        "description": "Strengthen resilience with sleep quality, movement consistency, and nutrition timing.",
        "thumbnail": "https://images.unsplash.com/photo-1584362917165-526a968579e8?w=600&q=80",
    },
}
FITBIT_AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
FITBIT_API_BASE = "https://api.fitbit.com"
GOOGLE_FIT_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_scheduler_task: asyncio.Task | None = None
_scheduler_stop = asyncio.Event()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_provider(provider: str) -> str:
    normalized = _ensure_supported_provider(provider)
    if normalized == "this-phone":
        return "health-connect"
    return normalized


async def _append_audit_log(user_id: str, provider: str, action: str, *, status_value: str = "success", detail: str = "", metadata: dict[str, Any] | None = None) -> None:
    await integration_audit_logs_collection.insert_one(
        {
            "user_id": user_id,
            "provider": provider,
            "action": action,
            "status": status_value,
            "detail": detail,
            "metadata": dict(metadata or {}),
            "created_at": _utc_now(),
        }
    )


async def _start_sync_job(user_id: str, provider: str, *, trigger: str) -> str:
    now = _utc_now()
    document = {
        "_id": ObjectId(),
        "user_id": user_id,
        "provider": provider,
        "trigger": trigger,
        "status": "running",
        "started_at": now,
        "finished_at": None,
        "records_processed": 0,
        "error_message": "",
        "created_at": now,
        "updated_at": now,
    }
    await sync_jobs_collection.insert_one(document)
    return str(document["_id"])


async def _finish_sync_job(job_id: str | None, *, status_value: str, synced_records: int = 0, skipped_duplicates: int = 0, detail: str = "") -> None:
    if not job_id:
        return
    await sync_jobs_collection.update_one(
        {"_id": ObjectId(job_id)},
        {
            "$set": {
                "status": status_value,
                "synced_records": synced_records,
                "skipped_duplicates": skipped_duplicates,
                "records_processed": synced_records,
                "error_message": detail if status_value == "failed" else "",
                "detail": detail,
                "finished_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        },
    )


async def _record_sync_error(user_id: str, provider: str, *, job_id: str | None = None, stage: str = "", detail: str = "", metadata: dict[str, Any] | None = None) -> None:
    await sync_errors_collection.insert_one(
        {
            "user_id": user_id,
            "provider": provider,
            "job_id": job_id,
            "stage": stage,
            "error_code": stage or "sync_error",
            "error_message": detail,
            "raw_error": detail,
            "detail": detail,
            "metadata": dict(metadata or {}),
            "created_at": _utc_now(),
        }
    )


async def _upsert_provider_token(user_id: str, provider: str, *, access_token: str | None = None, refresh_token: str | None = None, expires_at: datetime | None = None, metadata: dict[str, Any] | None = None) -> None:
    await provider_tokens_collection.update_one(
        {"user_id": user_id, "provider": provider},
        {
            "$set": {
                "access_token_encrypted": encrypt_token(access_token) if access_token else "",
                "refresh_token_encrypted": encrypt_token(refresh_token) if refresh_token else "",
                "expires_at": _as_utc(expires_at) if expires_at else None,
                "metadata": dict(metadata or {}),
                "updated_at": _utc_now(),
            },
            "$setOnInsert": {
                "user_id": user_id,
                "provider": provider,
                "created_at": _utc_now(),
            },
        },
        upsert=True,
    )


async def _load_provider_token(user_id: str, provider: str) -> dict[str, Any] | None:
    return await provider_tokens_collection.find_one({"user_id": user_id, "provider": provider})


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _summarize_metric_window(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics_by_type: dict[str, list[float]] = {}
    active_dates: set[str] = set()
    workouts_total = 0.0

    for record in records:
        record_time = _parse_datetime_value(record.get("end_time") or record.get("start_time") or record.get("synced_at"))
        if record_time:
            active_dates.add(record_time.date().isoformat())

        metric_type = str(record.get("metric_type") or "").strip().lower()
        value = _coerce_float(record.get("value"))
        if value is None:
            continue
        metrics_by_type.setdefault(metric_type, []).append(value)
        if metric_type == "workouts":
            workouts_total += value

    def average(metric_type: str) -> float:
        values = metrics_by_type.get(metric_type) or []
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    return {
        "record_count": len(records),
        "active_days": len(active_dates),
        "sleep_hours": round(average("sleep"), 1),
        "hrv_ms": int(round(average("hrv"))),
        "heart_rate_bpm": int(round(average("heart_rate"))),
        "stress_score": int(round(average("stress"))),
        "body_battery": int(round(average("body_battery"))),
        "steps": int(round(average("steps"))),
        "spo2_percent": int(round(average("spo2"))),
        "workouts": int(round(workouts_total)),
        "distance_meters": round(average("distance"), 2),
    }


def _date_to_bounds(value: date | None, is_end: bool = False) -> datetime | None:
    if value is None:
        return None
    clock = time.max if is_end else time.min
    return datetime.combine(value, clock, tzinfo=timezone.utc)


def _ensure_supported_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported wearable provider")
    return normalized


async def _deactivate_other_connections(user_id: str, active_provider: str) -> None:
    now = _utc_now()
    await wearable_connections_collection.update_many(
        {
            "user_id": user_id,
            "provider": {"$ne": active_provider},
            "status": "connected",
        },
        {
            "$set": {
                "status": "disconnected",
                "permission_granted": False,
                "disconnected_at": now,
                "updated_at": now,
                "last_sync_status": "idle",
                "last_sync_message": f"Disconnected because {active_provider} was connected.",
            }
        },
    )


def _serialize_connection(record: dict) -> dict[str, Any]:
    metadata = dict(record.get("metadata") or {})
    device_name = str(
        record.get("device_name")
        or record.get("source_device")
        or metadata.get("device_name")
        or metadata.get("source_device")
        or ""
    )
    return {
        "id": str(record.get("_id") or ""),
        "user_id": str(record.get("user_id") or ""),
        "provider": str(record.get("provider") or ""),
        "status": str(record.get("status") or "disconnected"),
        "device_name": device_name,
        "scopes": [str(item) for item in record.get("scopes") or []],
        "provider_user_id": str(record.get("provider_user_id") or "") or None,
        "connected_at": record.get("connected_at"),
        "disconnected_at": record.get("disconnected_at"),
        "last_synced_at": record.get("last_synced_at"),
        "last_sync_status": str(record.get("last_sync_status") or "idle"),
        "last_sync_message": str(record.get("last_sync_message") or ""),
        "permission_granted": bool(record.get("permission_granted") or metadata.get("permission_granted") or False),
        "source_device": device_name,
        "platform": str(record.get("platform") or metadata.get("platform") or ""),
        "metadata": metadata,
        "created_at": record.get("created_at") or _utc_now(),
        "updated_at": record.get("updated_at") or _utc_now(),
    }


def _serialize_integration(record: dict | None, provider: str) -> dict[str, Any]:
    display = PROVIDER_DISPLAY[provider]
    connection_type = PROVIDER_CONNECTION_TYPE.get(provider, "native")
    status_value = "not_connected"
    connected = False
    needs_permission = provider in {"apple-health", "health-connect", "this-phone"} and not bool(record)
    last_error = ""
    last_sync_message = ""
    connected_at = None
    disconnected_at = None
    last_synced_at = None
    source_device = ""
    device_name = ""
    platform = ""
    permission_granted = False
    provider_configured = is_provider_configured(provider)

    if not provider_configured:
        status_value = PROVIDER_NOT_CONFIGURED

    if record:
        connected = str(record.get("status") or "").lower() == "connected"
        connected_at = record.get("connected_at")
        disconnected_at = record.get("disconnected_at")
        last_synced_at = record.get("last_synced_at")
        metadata = dict(record.get("metadata") or {})
        device_name = str(
            record.get("device_name")
            or record.get("source_device")
            or metadata.get("device_name")
            or metadata.get("source_device")
            or ""
        )
        source_device = device_name
        platform = str(record.get("platform") or metadata.get("platform") or "")
        permission_granted = bool(record.get("permission_granted") or metadata.get("permission_granted") or False)
        last_sync_status = str(record.get("last_sync_status") or "idle").lower()
        last_sync_message = str(record.get("last_sync_message") or "")
        last_error = last_sync_message if last_sync_status == "failed" else ""
        if not provider_configured:
            status_value = PROVIDER_NOT_CONFIGURED
        elif last_sync_status == "failed":
            status_value = "error"
        elif last_sync_status == "running":
            status_value = "syncing"
        elif connection_type == "native" and bool(metadata.get("native_permission_required")) and not bool(metadata.get("permission_granted")):
            status_value = "needs_permission"
        elif connected:
            status_value = "connected"
        else:
            status_value = "not_connected"

    return {
        "provider": provider,
        "display_name": display["name"],
        "connection_type": connection_type,
        "status": status_value,
        "connected": connected,
        "needs_permission": needs_permission and not connected,
        "connected_at": connected_at,
        "disconnected_at": disconnected_at,
        "last_synced_at": last_synced_at,
        "last_error": last_error,
        "last_sync_message": last_sync_message,
        "permission_granted": permission_granted,
        "device_name": device_name,
        "source_device": source_device,
        "platform": platform,
        "metadata": dict(record.get("metadata") or {}) if record else {},
    }


def _serialize_metric(record: dict) -> dict[str, Any]:
    return {
        "id": str(record.get("_id") or ""),
        "user_id": str(record.get("user_id") or ""),
        "provider": str(record.get("provider") or ""),
        "metric_type": str(record.get("metric_type") or ""),
        "value": record.get("value"),
        "unit": str(record.get("unit") or ""),
        "start_time": record.get("start_time"),
        "end_time": record.get("end_time"),
        "source_device": str(record.get("source_device") or ""),
        "metadata": dict(record.get("metadata") or {}),
        "synced_at": record.get("synced_at") or _utc_now(),
    }


def _get_fernet() -> Fernet:
    raw = (getattr(settings, "wearable_token_encryption_key", "") or "").strip()
    if not raw:
        raise HTTPException(
            status_code=503,
            detail="Wearable token encryption is not configured",
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(value: str | None) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_token(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to decrypt wearable token") from exc


def _build_dedupe_key(document: dict[str, Any]) -> str:
    external_id = str(document.get("external_id") or (document.get("metadata") or {}).get("external_id") or "").strip()
    payload = {
        "user_id": str(document.get("user_id") or ""),
        "provider": str(document.get("provider") or ""),
        "metric_type": str(document.get("metric_type") or document.get("type") or ""),
        "value": document.get("value"),
        "unit": str(document.get("unit") or ""),
        "start_time": _as_utc(document["start_time"] if document.get("start_time") is not None else document["started_at"]).isoformat(),
        "end_time": _as_utc(document["end_time"] if document.get("end_time") is not None else document["ended_at"]).isoformat(),
        "source_device": str(document.get("source_device") or ""),
        "external_id": external_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def decode_qr_health_payload(qr_payload: str) -> dict[str, Any]:
    raw_payload = str(qr_payload or "").strip()
    if not raw_payload:
        raise HTTPException(status_code=400, detail="QR payload is empty")

    candidates = [raw_payload]
    try:
        padding = (-len(raw_payload)) % 4
        decoded = base64.urlsafe_b64decode((raw_payload + ("=" * padding)).encode("utf-8")).decode("utf-8")
        candidates.append(decoded)
    except Exception:
        pass

    parsed: dict[str, Any] | None = None
    for candidate in candidates:
        try:
            candidate_value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate_value, dict):
            parsed = candidate_value
            break

    if parsed is None:
        raise HTTPException(status_code=400, detail="QR payload must contain valid JSON health sync data")

    metrics = parsed.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise HTTPException(status_code=400, detail="QR payload does not contain any metrics")

    source_device = str(parsed.get("source_device") or "")
    batch_id = str(parsed.get("batch_id") or "").strip() or None
    return {
        "metrics": metrics,
        "source_device": source_device,
        "batch_id": batch_id,
    }


async def upsert_wearable_connection(
    user_id: str,
    provider: str,
    *,
    status_value: str,
    device_name: str = "",
    source_device: str = "",
    platform: str = "",
    permission_granted: bool | None = None,
    metadata: dict[str, Any] | None = None,
    scopes: list[str] | None = None,
    provider_user_id: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
    oauth_state: str | None = None,
    connected_at: datetime | None = None,
    last_synced_at: datetime | None = None,
    last_sync_status: str | None = None,
    last_sync_message: str | None = None,
) -> dict:
    provider = _ensure_supported_provider(provider)
    now = _utc_now()
    normalized_device_name = str(device_name or source_device or (metadata or {}).get("device_name") or (metadata or {}).get("source_device") or "")
    update_fields: dict[str, Any] = {
        "status": status_value,
        "updated_at": now,
    }
    if normalized_device_name:
        update_fields["device_name"] = normalized_device_name
        update_fields["source_device"] = normalized_device_name
    if platform:
        update_fields["platform"] = platform
    if permission_granted is not None:
        update_fields["permission_granted"] = bool(permission_granted)
    if metadata is not None:
        update_fields["metadata"] = metadata
    if scopes is not None:
        update_fields["scopes"] = scopes
    if provider_user_id is not None:
        update_fields["provider_user_id"] = provider_user_id
    if access_token is not None:
        update_fields["access_token_encrypted"] = encrypt_token(access_token) if access_token else ""
    if refresh_token is not None:
        update_fields["refresh_token_encrypted"] = encrypt_token(refresh_token) if refresh_token else ""
    if token_expires_at is not None:
        update_fields["token_expires_at"] = _as_utc(token_expires_at)
    if oauth_state is not None:
        update_fields["oauth_state"] = oauth_state
    if connected_at is not None:
        update_fields["connected_at"] = _as_utc(connected_at)
    if last_synced_at is not None:
        update_fields["last_synced_at"] = _as_utc(last_synced_at)
    if last_sync_status is not None:
        update_fields["last_sync_status"] = last_sync_status
    if last_sync_message is not None:
        update_fields["last_sync_message"] = last_sync_message
    if status_value == "connected":
        update_fields["disconnected_at"] = None
        update_fields.setdefault("connected_at", connected_at or now)
    elif status_value == "disconnected":
        update_fields["disconnected_at"] = now

    await wearable_connections_collection.update_one(
        {"user_id": user_id, "provider": provider},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "user_id": user_id,
                "provider": provider,
                "created_at": now,
            },
        },
        upsert=True,
    )
    if status_value == "connected":
        await _deactivate_other_connections(user_id, provider)
    if access_token is not None or refresh_token is not None or token_expires_at is not None:
        await _upsert_provider_token(
            user_id,
            provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=token_expires_at,
            metadata={"oauth_state": oauth_state or ""},
        )
    connection = await wearable_connections_collection.find_one({"user_id": user_id, "provider": provider})
    if not connection:
        raise HTTPException(status_code=500, detail="Failed to persist wearable connection")
    return connection


async def list_user_connections(user_id: str) -> list[dict]:
    records = await wearable_connections_collection.find(
        {"user_id": user_id},
        sort=[("provider", 1)],
    ).to_list(length=None)
    return [_serialize_connection(record) for record in records]


async def list_integrations(user_id: str) -> list[dict[str, Any]]:
    records = await wearable_connections_collection.find({"user_id": user_id}).to_list(length=None)
    records_by_provider = {str(item.get("provider") or ""): item for item in records}
    return [_serialize_integration(records_by_provider.get(provider), provider) for provider in SUPPORTED_PROVIDERS]


async def enqueue_provider_sync_job(user_id: str, provider: str, *, trigger: str = "manual_sync") -> str:
    provider = _ensure_supported_provider(provider)
    require_configured = provider in OAUTH_PROVIDERS
    if require_configured and not is_provider_configured(provider):
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
    job_id = await _start_sync_job(user_id, provider, trigger=trigger)
    await upsert_wearable_connection(
        user_id,
        provider,
        status_value="connected",
        last_sync_status="running",
        last_sync_message=f"{provider} sync queued.",
    )
    await enqueue_integration_job(
        {
            "job_id": job_id,
            "job_type": "sync-provider-data",
            "user_id": user_id,
            "provider": provider,
        }
    )
    await _append_audit_log(user_id, provider, "sync_queued", detail=f"{provider} sync queued.", metadata={"job_id": job_id})
    return job_id


async def enqueue_import_job(
    user_id: str,
    provider: str,
    *,
    metrics: list[dict[str, Any]],
    source_device: str = "",
    batch_id: str | None = None,
) -> str:
    provider = _ensure_supported_provider(provider)
    job_id = await _start_sync_job(user_id, provider, trigger="process-imported-health-data")
    await enqueue_integration_job(
        {
            "job_id": job_id,
            "job_type": "process-imported-health-data",
            "user_id": user_id,
            "provider": provider,
            "metrics": metrics,
            "source_device": source_device,
            "batch_id": batch_id,
        }
    )
    await _append_audit_log(user_id, provider, "import_queued", detail="Imported health payload queued.", metadata={"job_id": job_id})
    return job_id


async def mark_native_provider_connected(
    user_id: str,
    provider: str,
    *,
    source_device: str = "",
    platform: str = "",
    permission_granted: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict:
    provider = _normalize_provider(provider)
    if provider not in {"apple-health", "health-connect"}:
        raise HTTPException(status_code=400, detail="Native connected endpoint only supports Apple Watch / Apple Health or Health Connect")
    merged_metadata = {
        "source": "native",
        "native_sync_enabled": True,
        "native_permission_required": not permission_granted,
        "permission_granted": permission_granted,
        "platform": platform,
        "device_name": source_device,
        "source_device": source_device,
        **dict(metadata or {}),
    }
    connection = await upsert_wearable_connection(
        user_id,
        provider,
        status_value="connected" if permission_granted else "pending",
        device_name=source_device,
        source_device=source_device,
        platform=platform,
        permission_granted=permission_granted,
        metadata=merged_metadata,
        connected_at=_utc_now() if permission_granted else None,
        last_sync_status="idle",
        last_sync_message=f"{PROVIDER_DISPLAY[provider]['name']} connected successfully." if permission_granted else f"{PROVIDER_DISPLAY[provider]['name']} permission is required.",
    )
    await _append_audit_log(user_id, provider, "connect", detail=str(connection.get("last_sync_message") or ""), metadata={"platform": platform, "source_device": source_device})
    return connection


async def connect_local_provider(user_id: str, provider: str) -> dict:
    provider = _ensure_supported_provider(provider)
    now = _utc_now()
    source = "local"
    source_device = ""
    last_sync_message = "Provider connected. Press sync to import health data."
    metadata: dict[str, Any] = {
        "source": source,
    }
    if provider in {"fitbit", "google-fit", "garmin"}:
        metadata["oauth_required"] = True
        last_sync_message = f"{PROVIDER_DISPLAY[provider]['name']} requires OAuth login through the connect endpoint."
    if provider == "apple-health":
        source = "native"
        source_device = "Apple Health"
        metadata = {
            "source": source,
            "native_sync_enabled": True,
            "native_permission_required": True,
            "ecosystem": "Apple",
            "device_name": source_device,
        }
        last_sync_message = "Apple Watch / Apple Health connected successfully. Press sync to import health data."
    if provider == "health-connect":
        source = "native"
        source_device = "Health Connect"
        metadata = {
            "source": source,
            "native_sync_enabled": True,
            "native_permission_required": True,
            "ecosystem": "Android",
            "device_name": source_device,
        }
        last_sync_message = "Health Connect connected successfully. Press sync to import health data."
    if provider == "this-phone":
        source = "mobile"
        source_device = "This Phone"
        metadata = {
            "source": source,
            "manual_sync_enabled": True,
            "device_name": source_device,
        }
        last_sync_message = "This phone is ready. Import health data from the phone to save it in Longevity OS."
    if provider == "qr-import":
        source = "qr"
        source_device = "QR Import"
        metadata = {
            "source": source,
            "manual_qr_enabled": True,
            "device_name": source_device,
        }
        last_sync_message = "QR import is ready. Scan or paste a wearable QR payload to save the synced data."
    connection = await upsert_wearable_connection(
        user_id,
        provider,
        status_value="connected",
        device_name=source_device,
        source_device=source_device,
        metadata=metadata,
        connected_at=now,
        permission_granted=True,
        last_sync_status="idle",
        last_sync_message=last_sync_message,
    )
    await _append_audit_log(user_id, provider, "connect", detail=last_sync_message, metadata={"connection_type": PROVIDER_CONNECTION_TYPE.get(provider, "native")})
    return connection


async def connect_demo_provider(user_id: str, provider: str) -> dict:
    raise HTTPException(status_code=410, detail="demo_connect_removed")


async def disconnect_provider(user_id: str, provider: str) -> dict[str, Any]:
    provider = _ensure_supported_provider(provider)
    existing = await wearable_connections_collection.find_one({"user_id": user_id, "provider": provider}) or {}
    source_device = str(existing.get("source_device") or (existing.get("metadata") or {}).get("source_device") or "")
    platform = str(existing.get("platform") or (existing.get("metadata") or {}).get("platform") or "")
    now = _utc_now()
    await wearable_connections_collection.update_one(
        {"user_id": user_id, "provider": provider},
        {
            "$set": {
                "status": "disconnected",
                "updated_at": now,
                "access_token_encrypted": "",
                "refresh_token_encrypted": "",
                "oauth_state": "",
                "token_expires_at": None,
                "last_sync_status": "idle",
                "last_sync_message": "Provider disconnected by user.",
                "permission_granted": False,
                "disconnected_at": now,
            }
        },
    )
    await provider_tokens_collection.delete_one({"user_id": user_id, "provider": provider})
    await _append_audit_log(user_id, provider, "disconnect", detail="Provider disconnected by user.")
    return {
        "provider": provider,
        "disconnected": True,
        "status": "disconnected",
        "device_name": source_device,
        "source_device": source_device,
        "platform": platform,
        "disconnected_at": now,
        "permission_granted": False,
        "message": "Provider disconnected by user.",
    }


def _normalize_metric_document(
    user_id: str,
    provider: str,
    metric: dict[str, Any],
    fallback_source_device: str = "",
) -> dict[str, Any]:
    metric_type = str(metric.get("metric_type") or "").strip().lower()
    if metric_type == "workout":
        metric_type = "workouts"
    if metric_type not in SUPPORTED_METRIC_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported metric_type: {metric_type}")
    start_time = metric.get("start_time")
    end_time = metric.get("end_time")
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise HTTPException(status_code=400, detail="Each metric requires start_time and end_time")

    metadata = dict(metric.get("metadata") or {})
    external_id = str(metric.get("external_id") or metadata.get("external_id") or "").strip()
    canonical_type = "workout" if metric_type == "workouts" else metric_type
    created_at = _utc_now()
    document = {
        "_id": ObjectId(),
        "user_id": user_id,
        "provider": provider,
        "external_id": external_id,
        "type": canonical_type,
        "metric_type": metric_type,
        "value": metric.get("value"),
        "unit": str(metric.get("unit") or ""),
        "started_at": _as_utc(start_time),
        "ended_at": _as_utc(end_time),
        "start_time": _as_utc(start_time),
        "end_time": _as_utc(end_time),
        "source_device": str(metric.get("source_device") or fallback_source_device or ""),
        "metadata": metadata,
        "created_at": created_at,
        "synced_at": created_at,
    }
    document["dedupe_key"] = _build_dedupe_key(document)
    return document


async def store_normalized_metrics(
    user_id: str,
    provider: str,
    metrics: list[dict[str, Any]],
    *,
    source_device: str = "",
) -> tuple[int, int]:
    provider = _ensure_supported_provider(provider)
    documents = [_normalize_metric_document(user_id, provider, metric, source_device) for metric in metrics]
    if not documents:
        return 0, 0

    operations = [
        UpdateOne(
            {"dedupe_key": document["dedupe_key"]},
            {"$setOnInsert": document},
            upsert=True,
        )
        for document in documents
    ]
    result = await health_metrics_collection.bulk_write(operations, ordered=False)
    inserted = int((result.upserted_count or 0))
    skipped = max(len(documents) - inserted, 0)
    return inserted, skipped


async def ingest_mobile_sync(
    user_id: str,
    provider: str,
    metrics: list[dict[str, Any]],
    *,
    source_device: str = "",
    batch_id: str | None = None,
    trigger: str = "native_upload",
) -> dict[str, Any]:
    job_id = await _start_sync_job(user_id, provider, trigger=trigger)
    try:
        inserted, skipped = await store_normalized_metrics(
            user_id,
            provider,
            metrics,
            source_device=source_device,
        )
        now = _utc_now()
        metadata = {"last_batch_id": batch_id or ""}
        connection = await upsert_wearable_connection(
            user_id,
            provider,
            status_value="connected",
            source_device=source_device,
            metadata=metadata,
            connected_at=now,
            last_synced_at=now,
            last_sync_status="success",
            last_sync_message=f"Stored {inserted} health records from {provider}.",
        )
        await _finish_sync_job(job_id, status_value="success", synced_records=inserted, skipped_duplicates=skipped, detail="Health samples stored.")
        await _append_audit_log(user_id, provider, "sync", detail=f"Stored {inserted} health records.", metadata={"job_id": job_id, "skipped_duplicates": skipped})
        return {
            "inserted": inserted,
            "skipped": skipped,
            "connection": connection,
            "last_synced_at": now,
            "job_id": job_id,
        }
    except Exception as exc:
        await _finish_sync_job(job_id, status_value="failed", detail=str(exc))
        await _record_sync_error(user_id, provider, job_id=job_id, stage="native_upload", detail=str(exc))
        await _append_audit_log(user_id, provider, "sync", status_value="failed", detail=str(exc), metadata={"job_id": job_id})
        raise


async def query_health_metrics(
    user_id: str,
    *,
    provider: str | None = None,
    metric_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    filter_doc: dict[str, Any] = {"user_id": user_id}
    if provider:
        filter_doc["provider"] = _ensure_supported_provider(provider)
    if metric_type:
        normalized_metric = metric_type.strip().lower()
        if normalized_metric not in SUPPORTED_METRIC_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported metric_type filter")
        filter_doc["metric_type"] = normalized_metric

    start_dt = _date_to_bounds(start_date)
    end_dt = _date_to_bounds(end_date, is_end=True)
    if start_dt is not None:
        filter_doc["end_time"] = {"$gte": start_dt}
    if end_dt is not None:
        filter_doc["start_time"] = {"$lte": end_dt}

    return await health_metrics_collection.find(
        filter_doc,
        sort=[("synced_at", -1), ("end_time", -1), ("_id", -1)],
    ).to_list(length=5000)


async def summarize_health_metrics(
    user_id: str,
    *,
    provider: str | None = None,
    metric_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    records = await query_health_metrics(
        user_id,
        provider=provider,
        metric_type=metric_type,
        start_date=start_date,
        end_date=end_date,
    )
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        metric_type = str(record.get("metric_type") or "").strip().lower()
        if metric_type == "workout":
            metric_type = "workouts"
        if metric_type not in SUPPORTED_METRIC_TYPES:
            continue
        key = (metric_type, str(record.get("provider") or ""))
        bucket = groups.setdefault(
            key,
            {
                "metric_type": key[0],
                "provider": key[1],
                "records": 0,
                "numeric_values": [],
                "unit_counts": {},
                "latest_end_time": None,
                "latest_value": None,
            },
        )
        bucket["records"] += 1
        unit = str(record.get("unit") or "").strip()
        if unit:
            unit_counts = bucket.setdefault("unit_counts", {})
            unit_counts[unit] = int(unit_counts.get(unit) or 0) + 1
        value = record.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            bucket["numeric_values"].append(float(value))
        end_time = record.get("end_time")
        if isinstance(end_time, datetime):
            current_latest = bucket.get("latest_end_time")
            if current_latest is None or end_time > current_latest:
                bucket["latest_end_time"] = end_time
                bucket["latest_value"] = float(value)

    items: list[dict[str, Any]] = []
    for bucket in groups.values():
        numeric_values = bucket.pop("numeric_values")
        unit_counts = bucket.pop("unit_counts")
        unit = ""
        if unit_counts:
            unit = max(unit_counts.items(), key=lambda item: item[1])[0]
        total_value = float(sum(numeric_values)) if numeric_values else 0.0
        average_value = float(total_value / len(numeric_values)) if numeric_values else 0.0
        items.append(
            {
                **bucket,
                "unit": unit,
                "total_value": total_value,
                "average_value": average_value,
                "min_value": min(numeric_values) if numeric_values else None,
                "max_value": max(numeric_values) if numeric_values else None,
                "latest_value": bucket.get("latest_value"),
            }
        )
    items.sort(key=lambda item: (item["metric_type"], item["provider"]))
    return items


def _build_demo_metrics(provider: str) -> list[dict[str, Any]]:
    provider = _ensure_supported_provider(provider)
    now = _utc_now()
    source_device = DEMO_PROVIDER_SOURCE_DEVICE.get(provider, "Demo Wearable")
    demo_profiles: dict[str, list[dict[str, Any]]] = {
        "apple-health": [
            {"date": now - timedelta(days=4), "steps": 8124, "sleep": 6.9, "heart_rate": 64, "hrv": 39, "spo2": 98, "stress": 41, "body_battery": 66, "calories": 2214, "distance": 5.9, "workouts": 1},
            {"date": now - timedelta(days=3), "steps": 9688, "sleep": 7.2, "heart_rate": 62, "hrv": 43, "spo2": 98, "stress": 37, "body_battery": 71, "calories": 2338, "distance": 6.8, "workouts": 1},
            {"date": now - timedelta(days=2), "steps": 11236, "sleep": 7.7, "heart_rate": 60, "hrv": 48, "spo2": 99, "stress": 30, "body_battery": 79, "calories": 2475, "distance": 8.1, "workouts": 1},
            {"date": now - timedelta(days=1), "steps": 10452, "sleep": 7.4, "heart_rate": 61, "hrv": 46, "spo2": 99, "stress": 33, "body_battery": 76, "calories": 2390, "distance": 7.4, "workouts": 1},
            {"date": now, "steps": 8875, "sleep": 7.0, "heart_rate": 63, "hrv": 42, "spo2": 98, "stress": 36, "body_battery": 72, "calories": 2281, "distance": 6.3, "workouts": 1},
        ],
        "health-connect": [
            {"date": now - timedelta(days=4), "steps": 6892, "sleep": 6.5, "heart_rate": 67, "hrv": 35, "spo2": 97, "stress": 46, "body_battery": 59, "calories": 2142, "distance": 5.1, "workouts": 0},
            {"date": now - timedelta(days=3), "steps": 8450, "sleep": 6.8, "heart_rate": 65, "hrv": 38, "spo2": 97, "stress": 43, "body_battery": 63, "calories": 2236, "distance": 6.0, "workouts": 1},
            {"date": now - timedelta(days=2), "steps": 9234, "sleep": 7.0, "heart_rate": 64, "hrv": 41, "spo2": 98, "stress": 39, "body_battery": 68, "calories": 2319, "distance": 6.6, "workouts": 1},
            {"date": now - timedelta(days=1), "steps": 10126, "sleep": 7.3, "heart_rate": 62, "hrv": 44, "spo2": 98, "stress": 35, "body_battery": 73, "calories": 2405, "distance": 7.2, "workouts": 1},
            {"date": now, "steps": 7810, "sleep": 6.9, "heart_rate": 63, "hrv": 40, "spo2": 98, "stress": 38, "body_battery": 69, "calories": 2261, "distance": 5.8, "workouts": 1},
        ],
        "fitbit": [
            {"date": now - timedelta(days=4), "steps": 7420, "sleep": 6.6, "heart_rate": 66, "hrv": 36, "spo2": 97, "stress": 45, "body_battery": 60, "calories": 2176, "distance": 5.5, "workouts": 1},
            {"date": now - timedelta(days=3), "steps": 9312, "sleep": 7.0, "heart_rate": 64, "hrv": 40, "spo2": 98, "stress": 40, "body_battery": 66, "calories": 2298, "distance": 6.7, "workouts": 1},
            {"date": now - timedelta(days=2), "steps": 10884, "sleep": 7.4, "heart_rate": 62, "hrv": 45, "spo2": 98, "stress": 34, "body_battery": 75, "calories": 2436, "distance": 7.8, "workouts": 1},
            {"date": now - timedelta(days=1), "steps": 9861, "sleep": 7.1, "heart_rate": 63, "hrv": 43, "spo2": 99, "stress": 36, "body_battery": 72, "calories": 2362, "distance": 7.0, "workouts": 1},
            {"date": now, "steps": 8526, "sleep": 6.8, "heart_rate": 64, "hrv": 41, "spo2": 98, "stress": 37, "body_battery": 70, "calories": 2248, "distance": 6.1, "workouts": 1},
        ],
        "garmin": [
            {"date": now - timedelta(days=4), "steps": 8805, "sleep": 7.1, "heart_rate": 61, "hrv": 44, "spo2": 98, "stress": 38, "body_battery": 72, "calories": 2288, "distance": 6.4, "workouts": 1},
            {"date": now - timedelta(days=3), "steps": 10472, "sleep": 7.3, "heart_rate": 60, "hrv": 47, "spo2": 99, "stress": 33, "body_battery": 78, "calories": 2401, "distance": 7.6, "workouts": 1},
            {"date": now - timedelta(days=2), "steps": 11894, "sleep": 7.8, "heart_rate": 58, "hrv": 51, "spo2": 99, "stress": 29, "body_battery": 84, "calories": 2529, "distance": 8.7, "workouts": 1},
            {"date": now - timedelta(days=1), "steps": 11106, "sleep": 7.5, "heart_rate": 59, "hrv": 49, "spo2": 99, "stress": 31, "body_battery": 81, "calories": 2452, "distance": 8.0, "workouts": 1},
            {"date": now, "steps": 9368, "sleep": 7.2, "heart_rate": 60, "hrv": 46, "spo2": 99, "stress": 34, "body_battery": 77, "calories": 2337, "distance": 6.9, "workouts": 1},
        ],
    }
    days = demo_profiles[provider]
    provider_metadata = DEMO_PROVIDER_METADATA.get(provider, {})
    metrics: list[dict[str, Any]] = []
    for index, item in enumerate(days):
        start = datetime.combine(item["date"].date(), time.min, tzinfo=timezone.utc)
        end = datetime.combine(item["date"].date(), time.max, tzinfo=timezone.utc)
        for metric_type, unit in (
            ("steps", "count"),
            ("sleep", "hours"),
            ("heart_rate", "bpm"),
            ("hrv", "ms"),
            ("spo2", "%"),
            ("stress", "score"),
            ("body_battery", "score"),
            ("calories", "kcal"),
            ("distance", "km"),
            ("workouts", "count"),
        ):
            metrics.append(
                {
                    "metric_type": metric_type,
                    "value": item[metric_type],
                    "unit": unit,
                    "start_time": start,
                    "end_time": end,
                    "source_device": source_device,
                    "metadata": {
                        **provider_metadata,
                        "source": "demo",
                        "external_id": f"demo-{provider}-{metric_type}-{index}",
                        "recorded_on": item["date"].date().isoformat(),
                    },
                }
            )
    return metrics


async def _sync_demo_provider(connection: dict) -> tuple[int, int]:
    provider = str(connection.get("provider") or "")
    user_id = str(connection.get("user_id") or "")
    inserted, skipped = await store_normalized_metrics(
        user_id,
        provider,
        _build_demo_metrics(provider),
        source_device=DEMO_PROVIDER_SOURCE_DEVICE.get(provider, "Demo Wearable"),
    )
    await upsert_wearable_connection(
        user_id,
        provider,
        status_value="connected",
        source_device=DEMO_PROVIDER_SOURCE_DEVICE.get(provider, "Demo Wearable"),
        metadata={
            **dict(connection.get("metadata") or {}),
            "demo_sync_enabled": True,
            "demo_profile_key": provider,
            "source": "demo",
        },
        connected_at=connection.get("connected_at") or _utc_now(),
        last_synced_at=_utc_now(),
        last_sync_status="success",
        last_sync_message=f"{PROVIDER_DISPLAY[provider]['name']} demo sync completed with {inserted} records.",
    )
    return inserted, skipped


async def build_longevity_metric_insights(user_id: str) -> dict[str, Any]:
    records = await health_metrics_collection.find(
        {"user_id": user_id},
        sort=[("start_time", -1), ("_id", -1)],
    ).to_list(length=500)
    if not records:
        return {"has_metrics": False}

    existing_profile = await longevity_os_profiles_collection.find_one(
        {"user_id": user_id},
        {"habits": 1, "weekly_plan": 1, "updated_at": 1},
    ) or {}

    metrics_by_type: dict[str, list[float]] = {}
    for record in records:
        metric_type = str(record.get("metric_type") or "")
        value = _coerce_float(record.get("value"))
        if value is None:
            continue
        metrics_by_type.setdefault(metric_type, []).append(value)

    def avg(metric_type: str) -> float | None:
        values = metrics_by_type.get(metric_type) or []
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"body_metrics.age": 1})
    age_raw = str(((user or {}).get("body_metrics") or {}).get("age") or "").strip()
    chronological_age = age_raw if age_raw else "N/A"
    sleep_avg = avg("sleep") or 0
    hrv_avg = avg("hrv") or 0
    heart_rate_avg = avg("heart_rate") or 0
    stress_avg = avg("stress") or 0
    body_battery_avg = avg("body_battery") or 0
    steps_avg = avg("steps") or 0
    spo2_avg = avg("spo2") or 0
    workouts_total = int(round(sum(metrics_by_type.get("workouts") or []))) if metrics_by_type.get("workouts") else 0

    sleep_score = max(0, min(int(round((sleep_avg / 8.0) * 100)), 100))
    recovery_score = max(
        0,
        min(
            int(
                round(
                    (sleep_score * 0.35)
                    + (min(hrv_avg, 70) / 70 * 100 * 0.25)
                    + (body_battery_avg * 0.2)
                    + ((100 - min(stress_avg, 100)) * 0.2)
                )
            ),
            100,
        ),
    )
    trending_years_younger = round(
        max(0, min(5, ((sleep_avg - 6.0) * 0.6) + ((hrv_avg - 35) * 0.04) + ((body_battery_avg - 50) * 0.03))),
        1,
    )

    biological_age = chronological_age
    if age_raw:
        try:
            biological_age = str(max(int(float(age_raw) - trending_years_younger), 18))
        except ValueError:
            biological_age = chronological_age

    focus_areas: list[str] = []
    if sleep_avg < 7:
        focus_areas.append("improve sleep consistency")
    if hrv_avg < 40:
        focus_areas.append("reduce nervous-system stress")
    if steps_avg < 9000:
        focus_areas.append("increase daily movement")
    if spo2_avg and spo2_avg < 97:
        focus_areas.append("support recovery and breathing quality")
    if not focus_areas:
        focus_areas.append("maintain your current recovery momentum")

    latest_time = max(
        (
            _parse_datetime_value(record.get("end_time") or record.get("start_time") or record.get("synced_at"))
            for record in records
        ),
        default=None,
    )
    if latest_time is None:
        latest_time = _utc_now()

    recent_window_start = latest_time - timedelta(days=7)
    previous_window_start = latest_time - timedelta(days=14)
    recent_records = [
        record
        for record in records
        if (record_time := _parse_datetime_value(record.get("end_time") or record.get("start_time") or record.get("synced_at")))
        and record_time >= recent_window_start
    ]
    previous_records = [
        record
        for record in records
        if (record_time := _parse_datetime_value(record.get("end_time") or record.get("start_time") or record.get("synced_at")))
        and previous_window_start <= record_time < recent_window_start
    ]
    recent_summary = _summarize_metric_window(recent_records)
    previous_summary = _summarize_metric_window(previous_records)

    habits = [dict(item) for item in existing_profile.get("habits") or []]
    completed_habits = [
        str(item.get("title") or "").strip()
        for item in habits
        if str(item.get("title") or "").strip() and bool(item.get("done"))
    ]
    pending_habits = [
        str(item.get("title") or "").strip()
        for item in habits
        if str(item.get("title") or "").strip() and not bool(item.get("done"))
    ]
    habit_completion_rate = round((len(completed_habits) / max(len(habits), 1)) * 100, 1) if habits else 0.0

    weekly_plan = existing_profile.get("weekly_plan") or {}
    prior_plan = None
    if isinstance(weekly_plan, dict) and weekly_plan:
        section_titles = [
            str(item.get("title") or "").strip()
            for item in weekly_plan.get("plan_sections") or []
            if str(item.get("title") or "").strip()
        ]
        prior_plan = {
            "generated_at": weekly_plan.get("generated_at"),
            "message": weekly_plan.get("message"),
            "section_titles": section_titles,
        }

    return {
        "has_metrics": True,
        "overview": {
            "biological_age": biological_age,
            "chronological_age": chronological_age,
            "trending_years_younger": trending_years_younger,
            "recovery_score": recovery_score,
            "hrv_ms": int(round(hrv_avg)),
            "sleep_score": sleep_score,
        },
        "summary": {
            "sleep_hours": round(sleep_avg, 1),
            "hrv_ms": int(round(hrv_avg)),
            "resting_heart_rate": int(round(heart_rate_avg)) if heart_rate_avg else 0,
            "stress_score": int(round(stress_avg)) if stress_avg else 0,
            "body_battery": int(round(body_battery_avg)) if body_battery_avg else 0,
            "steps": int(round(steps_avg)) if steps_avg else 0,
            "spo2": int(round(spo2_avg)) if spo2_avg else 0,
            "workouts": workouts_total,
        },
        "focus_areas": focus_areas[:3],
        "history": {
            "record_count": len(records),
            "recent_7d": recent_summary,
            "previous_7d": previous_summary,
            "habit_completion_rate": habit_completion_rate,
            "completed_habits": completed_habits[:8],
            "pending_habits": pending_habits[:8],
            "prior_weekly_plan": prior_plan,
        },
    }


async def refresh_longevity_profile_cache(user_id: str) -> dict[str, Any]:
    insights = await build_longevity_metric_insights(user_id)
    if not insights.get("has_metrics"):
        return insights

    summary = dict(insights.get("summary") or {})
    sleep_hours = float(summary.get("sleep_hours") or 0)
    steps = int(summary.get("steps") or 0)
    stress_score = int(summary.get("stress_score") or 0)
    workouts = int(summary.get("workouts") or 0)
    recovery_score = int((insights.get("overview") or {}).get("recovery_score") or 0)

    existing_profile = await longevity_os_profiles_collection.find_one({"user_id": user_id}) or {}
    existing_habits = [dict(item) for item in existing_profile.get("habits") or []]
    existing_habit_by_id = {
        str(item.get("id") or "").strip(): dict(item)
        for item in existing_habits
        if str(item.get("id") or "").strip()
    }

    computed_done_by_id = {
        "hydration": True,
        "sleep-7h": sleep_hours >= 7,
        "zone-2": workouts >= 1 or steps >= 9000,
        "breathwork": stress_score <= 35,
    }

    habits: list[dict[str, Any]] = []
    template_ids: set[str] = set()
    for template in LONGEVITY_HABIT_TEMPLATES:
        template_id = str(template.get("id") or "").strip()
        template_ids.add(template_id)
        existing = existing_habit_by_id.get(template_id, {})
        habits.append(
            {
                "id": template_id,
                "title": str(existing.get("title") or template.get("title") or "").strip(),
                "subtitle": str(existing.get("subtitle") or template.get("subtitle") or "").strip(),
                "icon": str(existing.get("icon") or template.get("icon") or "").strip(),
                "done": bool(computed_done_by_id.get(template_id, existing.get("done", False))),
            }
        )

    for existing in existing_habits:
        existing_id = str(existing.get("id") or "").strip()
        if not existing_id or existing_id in template_ids:
            continue
        habits.append(
            {
                "id": existing_id,
                "title": str(existing.get("title") or "Custom Habit").strip(),
                "subtitle": str(existing.get("subtitle") or "").strip(),
                "icon": str(existing.get("icon") or "sparkles-outline").strip(),
                "done": bool(existing.get("done", False)),
            }
        )

    heal_categories = [dict(item) for item in LONGEVITY_HEAL_CATEGORY_TEMPLATES]
    if stress_score > 40:
        heal_categories.sort(key=lambda item: 0 if item["id"] == "mental" else 1)
    elif sleep_hours < 7:
        heal_categories.sort(key=lambda item: 0 if item["id"] == "recovery" else 1)
    else:
        heal_categories.sort(key=lambda item: 0 if item["id"] == "heart" else 1)

    quick_actions = generate_longevity_quick_actions(insights)

    prioritized_category_ids = [str(item.get("id") or "") for item in heal_categories[:4]]
    masterclass_key_map = {
        "heart": "heart",
        "recovery": "recovery",
        "mental": "mental",
        "immunity": "immunity",
    }
    masterclasses: list[dict[str, Any]] = []
    for category_id in prioritized_category_ids:
        template_key = masterclass_key_map.get(category_id)
        if template_key:
            masterclasses.append(dict(LONGEVITY_MASTERCLASS_TEMPLATES[template_key]))

    now = _utc_now()
    await longevity_os_profiles_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "overview": dict(insights.get("overview") or {}),
                "quick_actions": quick_actions,
                "habits": habits,
                "heal_categories": heal_categories,
                "masterclasses": masterclasses,
                "wearables.has_data": True,
                "wearables.last_synced_at": now,
                "wearables.sync_message": "Data synced successfully. All Longevity OS calculations are using the synced data.",
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return insights


async def _http_json_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
    retries: int = 3,
) -> dict[str, Any]:
    request_headers = headers or {}
    body: bytes | None = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers = {**request_headers, "Content-Type": "application/json"}
    elif data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request_headers = {**request_headers, "Content-Type": "application/x-www-form-urlencoded"}

    request = urllib.request.Request(url, data=body, method=method.upper(), headers=request_headers)

    def _do_request() -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8") or "{}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = exc
                if exc.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                    retry_after = exc.headers.get("Retry-After")
                    delay_seconds = float(retry_after) if retry_after and retry_after.isdigit() else float(2 ** attempt)
                    import time as _time
                    _time.sleep(delay_seconds)
                    continue
                raise HTTPException(status_code=502, detail=f"Wearable provider request failed: {detail or exc.reason}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < retries - 1:
                    import time as _time
                    _time.sleep(float(2 ** attempt))
                    continue
                raise HTTPException(status_code=502, detail="Wearable provider is unavailable") from exc
        if last_error:
            raise HTTPException(status_code=502, detail="Wearable provider request failed") from last_error

    return await asyncio.to_thread(_do_request)


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return f"Basic {base64.b64encode(raw).decode('utf-8')}"


def _get_fitbit_settings() -> dict[str, Any]:
    client_id = (getattr(settings, "fitbit_client_id", "") or "").strip()
    client_secret = (getattr(settings, "fitbit_client_secret", "") or "").strip()
    redirect_uri = (getattr(settings, "fitbit_redirect_uri", "") or "").strip() or f"{settings.api_public_base_url}/integrations/fitbit/callback"
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
    scopes = list(getattr(settings, "fitbit_scopes", []) or ["activity", "heartrate", "sleep", "profile"])
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "authorize_url": (getattr(settings, "fitbit_auth_url", "") or FITBIT_AUTHORIZE_URL).strip(),
        "token_url": (getattr(settings, "fitbit_token_url", "") or FITBIT_TOKEN_URL).strip(),
        "api_base": (getattr(settings, "fitbit_api_base_url", "") or FITBIT_API_BASE).strip().rstrip("/"),
    }


def _get_garmin_settings() -> dict[str, Any]:
    client_id = (getattr(settings, "garmin_client_id", "") or "").strip()
    client_secret = (getattr(settings, "garmin_client_secret", "") or "").strip()
    redirect_uri = (getattr(settings, "garmin_redirect_uri", "") or "").strip() or f"{settings.api_public_base_url}/integrations/garmin/callback"
    authorize_url = (getattr(settings, "garmin_authorize_url", "") or "").strip()
    token_url = (getattr(settings, "garmin_token_url", "") or "").strip()
    api_base = (getattr(settings, "garmin_api_base_url", "") or "").strip()
    enabled = bool(getattr(settings, "garmin_enabled", False))
    if not enabled or not client_id or not client_secret or not redirect_uri or not authorize_url or not token_url or not api_base:
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
    scopes = list(getattr(settings, "garmin_scopes", []) or [])
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "authorize_url": authorize_url,
        "token_url": token_url,
        "api_base": api_base.rstrip("/"),
        "scopes": scopes,
    }


def _get_google_fit_settings() -> dict[str, Any]:
    client_id = (getattr(settings, "google_client_id", "") or "").strip()
    client_secret = (getattr(settings, "google_client_secret", "") or "").strip()
    redirect_uri = (getattr(settings, "google_fit_redirect_uri", "") or "").strip() or f"{settings.api_public_base_url}/integrations/google-fit/callback"
    authorize_url = (getattr(settings, "google_auth_uri", "") or GOOGLE_FIT_AUTHORIZE_URL).strip() or GOOGLE_FIT_AUTHORIZE_URL
    token_url = (getattr(settings, "google_token_uri", "") or "").strip()
    api_base = (getattr(settings, "google_fit_api_base_url", "") or "").strip()
    scopes = list(getattr(settings, "google_fit_scopes", []) or [])
    if not client_id or not client_secret or not redirect_uri or not authorize_url or not token_url or not api_base:
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "authorize_url": authorize_url,
        "token_url": token_url,
        "api_base": api_base.rstrip("/"),
        "scopes": scopes,
    }


async def build_oauth_connect_url(user_id: str, provider: str) -> dict[str, Any]:
    provider = _ensure_supported_provider(provider)
    if provider == "fitbit":
        config = _get_fitbit_settings()
        scopes = config["scopes"]
        base_url = str(config["authorize_url"] or FITBIT_AUTHORIZE_URL)
    elif provider == "google-fit":
        config = _get_google_fit_settings()
        scopes = config["scopes"]
        base_url = str(config["authorize_url"] or GOOGLE_FIT_AUTHORIZE_URL)
    elif provider == "garmin":
        config = _get_garmin_settings()
        scopes = config["scopes"]
        base_url = config["authorize_url"]
    else:
        raise HTTPException(status_code=400, detail="OAuth connect is not supported for this provider")

    state = uuid4().hex
    expires_at = _utc_now() + timedelta(minutes=15)
    await upsert_wearable_connection(
        user_id,
        provider,
        status_value="pending",
        scopes=scopes,
        oauth_state=state,
        metadata={"oauth_expires_at": expires_at.isoformat()},
        last_sync_status="idle",
        last_sync_message="Waiting for provider authorization callback.",
    )
    query = {
        "client_id": config["client_id"],
        "response_type": "code",
        "redirect_uri": config["redirect_uri"],
        "scope": " ".join(scopes),
        "state": state,
    }
    if provider == "google-fit":
        query["access_type"] = "offline"
        query["include_granted_scopes"] = "true"
        query["prompt"] = "consent"
    authorization_url = f"{base_url}?{urllib.parse.urlencode(query)}"
    return {
        "provider": provider,
        "authorization_url": authorization_url,
        "state": state,
        "expires_at": expires_at,
    }


async def _get_connection_by_state(provider: str, state: str) -> dict:
    connection = await wearable_connections_collection.find_one({"provider": provider, "oauth_state": state})
    if not connection:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    metadata = dict(connection.get("metadata") or {})
    expires_at_raw = str(metadata.get("oauth_expires_at") or "").strip()
    if expires_at_raw:
        try:
            if datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00")) < _utc_now():
                raise HTTPException(status_code=400, detail="Expired OAuth state")
        except HTTPException:
            raise
        except Exception:
            pass
    return connection


async def exchange_fitbit_code(state: str, code: str) -> dict[str, Any]:
    connection = await _get_connection_by_state("fitbit", state)
    config = _get_fitbit_settings()
    response = await _http_json_request(
        "POST",
        _get_fitbit_settings()["token_url"],
        headers={"Authorization": _basic_auth_header(config["client_id"], config["client_secret"])},
        data={
            "client_id": config["client_id"],
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
            "code": code,
        },
    )
    expires_at = _utc_now() + timedelta(seconds=int(response.get("expires_in") or 0))
    updated = await upsert_wearable_connection(
        str(connection["user_id"]),
        "fitbit",
        status_value="connected",
        device_name="Fitbit",
        source_device="Fitbit",
        scopes=str(response.get("scope") or "").split(),
        provider_user_id=str(response.get("user_id") or ""),
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or ""),
        token_expires_at=expires_at,
        oauth_state="",
        connected_at=_utc_now(),
        permission_granted=True,
        last_sync_status="idle",
        last_sync_message="Fitbit connected successfully.",
    )
    return _serialize_connection(updated)


async def exchange_garmin_code(state: str, code: str) -> dict[str, Any]:
    connection = await _get_connection_by_state("garmin", state)
    config = _get_garmin_settings()
    response = await _http_json_request(
        "POST",
        config["token_url"],
        headers={"Authorization": _basic_auth_header(config["client_id"], config["client_secret"])},
        data={
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
            "code": code,
        },
    )
    expires_at = _utc_now() + timedelta(seconds=int(response.get("expires_in") or 0))
    metadata = dict(connection.get("metadata") or {})
    if response.get("scope"):
        metadata["oauth_scope"] = str(response.get("scope"))
    updated = await upsert_wearable_connection(
        str(connection["user_id"]),
        "garmin",
        status_value="connected",
        device_name="Garmin",
        source_device="Garmin",
        scopes=str(response.get("scope") or "").split(),
        provider_user_id=str(response.get("user_id") or response.get("sub") or ""),
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or ""),
        token_expires_at=expires_at,
        oauth_state="",
        connected_at=_utc_now(),
        metadata=metadata,
        permission_granted=True,
        last_sync_status="idle",
        last_sync_message="Garmin connected successfully.",
    )
    return _serialize_connection(updated)


async def exchange_google_fit_code(state: str, code: str) -> dict[str, Any]:
    connection = await _get_connection_by_state("google-fit", state)
    config = _get_google_fit_settings()
    response = await _http_json_request(
        "POST",
        config["token_url"],
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
            "code": code,
        },
    )
    expires_at = _utc_now() + timedelta(seconds=int(response.get("expires_in") or 0))
    updated = await upsert_wearable_connection(
        str(connection["user_id"]),
        "google-fit",
        status_value="connected",
        device_name="Google Fit",
        source_device="Google Fit",
        scopes=str(response.get("scope") or "").split(),
        provider_user_id=str(response.get("id_token") or response.get("sub") or ""),
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or ""),
        token_expires_at=expires_at,
        oauth_state="",
        connected_at=_utc_now(),
        metadata={"oauth_scope": str(response.get("scope") or "")},
        permission_granted=True,
        last_sync_status="idle",
        last_sync_message="Google Fit connected successfully.",
    )
    return _serialize_connection(updated)


async def _refresh_oauth_connection(connection: dict) -> dict:
    provider = str(connection.get("provider") or "")
    refresh_token = decrypt_token(str(connection.get("refresh_token_encrypted") or ""))
    if not refresh_token:
        raise HTTPException(status_code=401, detail=f"{provider} refresh token is missing")

    if provider == "fitbit":
        config = _get_fitbit_settings()
        response = await _http_json_request(
            "POST",
            _get_fitbit_settings()["token_url"],
            headers={"Authorization": _basic_auth_header(config["client_id"], config["client_secret"])},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
    elif provider == "garmin":
        config = _get_garmin_settings()
        response = await _http_json_request(
            "POST",
            config["token_url"],
            headers={"Authorization": _basic_auth_header(config["client_id"], config["client_secret"])},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
    elif provider == "google-fit":
        config = _get_google_fit_settings()
        response = await _http_json_request(
            "POST",
            config["token_url"],
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    else:
        return connection

    expires_at = _utc_now() + timedelta(seconds=int(response.get("expires_in") or 0))
    updated = await upsert_wearable_connection(
        str(connection["user_id"]),
        provider,
        status_value="connected",
        device_name=str(connection.get("device_name") or connection.get("source_device") or provider.title()),
        source_device=str(connection.get("source_device") or provider.title()),
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or refresh_token),
        token_expires_at=expires_at,
        last_sync_status=str(connection.get("last_sync_status") or "idle"),
        last_sync_message=str(connection.get("last_sync_message") or ""),
        permission_granted=True,
    )
    return updated


async def _ensure_active_access_token(connection: dict) -> tuple[dict, str]:
    provider = str(connection.get("provider") or "")
    access_token = decrypt_token(str(connection.get("access_token_encrypted") or ""))
    expires_at = connection.get("token_expires_at")
    if not access_token or not isinstance(expires_at, datetime) or _as_utc(expires_at) <= _utc_now() + timedelta(minutes=2):
        connection = await _refresh_oauth_connection(connection)
        access_token = decrypt_token(str(connection.get("access_token_encrypted") or ""))
    if not access_token:
        raise HTTPException(status_code=401, detail=f"{provider} access token is missing")
    return connection, access_token


def _coerce_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return None
    return None


def _fitbit_daily_record_to_metric(
    provider: str,
    metric_type: str,
    date_label: str,
    value: Any,
    unit: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    numeric_value = _coerce_number(value)
    if numeric_value is None:
        return None
    start_time = datetime.fromisoformat(f"{date_label}T00:00:00+00:00")
    end_time = datetime.fromisoformat(f"{date_label}T23:59:59+00:00")
    return {
        "metric_type": metric_type,
        "value": numeric_value,
        "unit": unit,
        "start_time": start_time,
        "end_time": end_time,
        "source_device": "Fitbit",
        "metadata": metadata or {},
    }


async def _fetch_fitbit_json(access_token: str, path: str) -> dict[str, Any]:
    fitbit_api_base = str(_get_fitbit_settings()["api_base"] or FITBIT_API_BASE)
    return await _http_json_request(
        "GET",
        f"{fitbit_api_base}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
    )


async def _sync_fitbit_remote(connection: dict, start_date: date, end_date: date) -> tuple[int, int]:
    connection, access_token = await _ensure_active_access_token(connection)
    user_id = str(connection.get("user_id") or "")
    collected: list[dict[str, Any]] = []
    metric_paths = {
        "steps": ("/1/user/-/activities/steps/date/{start}/{end}.json", "count", "activities-steps"),
        "calories": ("/1/user/-/activities/calories/date/{start}/{end}.json", "kcal", "activities-calories"),
        "distance": ("/1/user/-/activities/distance/date/{start}/{end}.json", "km", "activities-distance"),
    }
    for metric_type, (template, unit, response_key) in metric_paths.items():
        payload = await _fetch_fitbit_json(access_token, template.format(start=start_date.isoformat(), end=end_date.isoformat()))
        for item in payload.get(response_key) or []:
            metric = _fitbit_daily_record_to_metric(
                "fitbit",
                metric_type,
                str(item.get("dateTime") or ""),
                item.get("value"),
                unit,
            )
            if metric:
                collected.append(metric)

    current_date = start_date
    while current_date <= end_date:
        date_label = current_date.isoformat()
        heart_payload = await _fetch_fitbit_json(access_token, f"/1/user/-/activities/heart/date/{date_label}/1d.json")
        for item in heart_payload.get("activities-heart") or []:
            value = ((item.get("value") or {}).get("restingHeartRate"))
            metric = _fitbit_daily_record_to_metric(
                "fitbit",
                "heart_rate",
                str(item.get("dateTime") or date_label),
                value,
                "bpm",
                metadata={"source": "restingHeartRate"},
            )
            if metric:
                collected.append(metric)

        sleep_payload = await _fetch_fitbit_json(access_token, f"/1.2/user/-/sleep/date/{date_label}.json")
        for entry in sleep_payload.get("sleep") or []:
            start_time_raw = str(entry.get("startTime") or "")
            end_time_raw = str(entry.get("endTime") or "")
            try:
                start_time = datetime.fromisoformat(start_time_raw.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(end_time_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            minutes_asleep = _coerce_number(entry.get("minutesAsleep"))
            collected.append(
                {
                    "metric_type": "sleep",
                    "value": round((float(minutes_asleep or 0) / 60), 2),
                    "unit": "hours",
                    "start_time": start_time,
                    "end_time": end_time,
                    "source_device": "Fitbit",
                    "metadata": {
                        "minutes_asleep": minutes_asleep or 0,
                        "minutes_awake": _coerce_number(entry.get("minutesAwake")) or 0,
                        "efficiency": _coerce_number(entry.get("efficiency")) or 0,
                        "log_id": entry.get("logId"),
                        "external_id": f"fitbit-sleep-{entry.get('logId')}",
                    },
                }
            )
        current_date += timedelta(days=1)

    inserted, skipped = await store_normalized_metrics(user_id, "fitbit", collected, source_device="Fitbit")
    await upsert_wearable_connection(
        user_id,
        "fitbit",
        status_value="connected",
        source_device=str(connection.get("source_device") or "Fitbit"),
        last_synced_at=_utc_now(),
        last_sync_status="success",
        last_sync_message=f"Fitbit sync completed with {inserted} records.",
    )
    return inserted, skipped


async def sync_fitbit(
    user_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    metrics: list[dict[str, Any]] | None = None,
    source_device: str = "",
    pull_remote: bool = True,
) -> tuple[int, int]:
    if metrics:
        result = await ingest_mobile_sync(user_id, "fitbit", metrics, source_device=source_device)
        return int(result["inserted"]), int(result["skipped"])

    connection = await wearable_connections_collection.find_one({"user_id": user_id, "provider": "fitbit"})
    if not connection or str(connection.get("status") or "").lower() != "connected":
        raise HTTPException(status_code=404, detail="Fitbit is not connected for this user")

    if not pull_remote:
        return 0, 0

    end = end_date or _utc_now().date()
    start = start_date or end
    return await _sync_fitbit_remote(connection, start, end)


async def sync_google_fit(
    user_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    metrics: list[dict[str, Any]] | None = None,
    source_device: str = "",
    pull_remote: bool = True,
) -> tuple[int, int]:
    if metrics:
        result = await ingest_mobile_sync(user_id, "google-fit", metrics, source_device=source_device)
        return int(result["inserted"]), int(result["skipped"])

    connection = await wearable_connections_collection.find_one({"user_id": user_id, "provider": "google-fit"})
    if not connection or str(connection.get("status") or "").lower() != "connected":
        raise HTTPException(status_code=404, detail="Google Fit is not connected for this user")

    if not pull_remote:
        return 0, 0

    end = end_date or _utc_now().date()
    start = start_date or end
    return await _sync_google_fit_remote(connection, start, end)


async def _fetch_garmin_json(access_token: str, path: str) -> dict[str, Any]:
    config = _get_garmin_settings()
    return await _http_json_request(
        "GET",
        f"{config['api_base']}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
    )


async def _fetch_google_fit_json(access_token: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _get_google_fit_settings()
    method = "POST" if json_body is not None else "GET"
    return await _http_json_request(
        method,
        f"{config['api_base']}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        json_body=json_body,
    )


def _google_bucket_metric_to_value(point: dict[str, Any]) -> float | int | None:
    for item in point.get("value") or []:
        if "intVal" in item:
            return _coerce_number(item.get("intVal"))
        if "fpVal" in item:
            return _coerce_number(item.get("fpVal"))
    return None


async def _sync_google_fit_remote(connection: dict, start_date: date, end_date: date) -> tuple[int, int]:
    connection, access_token = await _ensure_active_access_token(connection)
    user_id = str(connection.get("user_id") or "")
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    aggregate_specs = [
        ("com.google.step_count.delta", "steps", "count"),
        ("com.google.distance.delta", "distance", "m"),
        ("com.google.calories.expended", "calories", "kcal"),
        ("com.google.heart_rate.bpm", "heart_rate", "bpm"),
    ]
    payload = {
        "startTimeMillis": int(start_dt.timestamp() * 1000),
        "endTimeMillis": int(end_dt.timestamp() * 1000),
        "aggregateBy": [{"dataTypeName": data_type_name} for data_type_name, _, _ in aggregate_specs],
        "bucketByTime": {"durationMillis": 86400000},
    }
    response = await _fetch_google_fit_json(access_token, "/users/me/dataset:aggregate", json_body=payload)
    metrics: list[dict[str, Any]] = []
    for bucket in response.get("bucket") or []:
        bucket_start_ms = int(bucket.get("startTimeMillis") or payload["startTimeMillis"])
        bucket_end_ms = int(bucket.get("endTimeMillis") or payload["endTimeMillis"])
        bucket_start = datetime.fromtimestamp(bucket_start_ms / 1000, tz=timezone.utc)
        bucket_end = datetime.fromtimestamp(bucket_end_ms / 1000, tz=timezone.utc)
        datasets = list(bucket.get("dataset") or [])
        for index, dataset in enumerate(datasets):
            if index >= len(aggregate_specs):
                continue
            _, metric_type, unit = aggregate_specs[index]
            points = list(dataset.get("point") or [])
            if not points:
                continue
            total_value = 0.0
            for point in points:
                value = _google_bucket_metric_to_value(point)
                if value is None:
                    continue
                total_value += float(value)
            if total_value <= 0:
                continue
            metrics.append(
                {
                    "metric_type": metric_type,
                    "value": int(total_value) if metric_type == "steps" else round(total_value, 2),
                    "unit": unit,
                    "start_time": bucket_start,
                    "end_time": bucket_end,
                    "source_device": "Google Fit",
                    "metadata": {"external_id": f"google-fit-{metric_type}-{bucket_start.date().isoformat()}"},
                }
            )
    inserted, skipped = await store_normalized_metrics(user_id, "google-fit", metrics, source_device="Google Fit")
    await upsert_wearable_connection(
        user_id,
        "google-fit",
        status_value="connected",
        source_device=str(connection.get("source_device") or "Google Fit"),
        last_synced_at=_utc_now(),
        last_sync_status="success",
        last_sync_message=f"Google Fit sync completed with {inserted} records.",
    )
    return inserted, skipped


async def _sync_garmin_remote(connection: dict, start_date: date, end_date: date) -> tuple[int, int]:
    connection, access_token = await _ensure_active_access_token(connection)
    user_id = str(connection.get("user_id") or "")
    config = _get_garmin_settings()
    daily_path_template = str(getattr(settings, "garmin_daily_summary_path", "/wellness-api/rest/dailies"))
    query = urllib.parse.urlencode({"uploadStartTimeInSeconds": int(datetime.combine(start_date, time.min, tzinfo=timezone.utc).timestamp()), "uploadEndTimeInSeconds": int(datetime.combine(end_date, time.max, tzinfo=timezone.utc).timestamp())})
    payload = await _fetch_garmin_json(access_token, f"{daily_path_template}?{query}")
    summaries = payload.get("dailies") or payload.get("dailySummaries") or payload.get("items") or []
    metrics: list[dict[str, Any]] = []
    for summary in summaries:
        calendar_date = str(summary.get("calendarDate") or summary.get("date") or "")
        if not calendar_date:
            continue
        metrics_map = [
            ("steps", summary.get("steps"), "count"),
            ("calories", summary.get("activeKilocalories") or summary.get("calories"), "kcal"),
            ("distance", summary.get("distanceInMeters"), "m"),
            ("stress", summary.get("averageStressLevel"), "score"),
            ("body_battery", summary.get("bodyBatteryChargedValue") or summary.get("bodyBattery"), "score"),
            ("spo2", summary.get("avgSpo2Value"), "%"),
        ]
        for metric_type, value, unit in metrics_map:
            metric = _fitbit_daily_record_to_metric(
                "garmin",
                metric_type,
                calendar_date,
                value,
                unit,
                metadata={"external_id": f"garmin-{metric_type}-{calendar_date}"},
            )
            if metric:
                metrics.append(metric)

    inserted, skipped = await store_normalized_metrics(user_id, "garmin", metrics, source_device="Garmin")
    await upsert_wearable_connection(
        user_id,
        "garmin",
        status_value="connected",
        source_device=str(connection.get("source_device") or "Garmin"),
        metadata={"api_base": config["api_base"]},
        last_synced_at=_utc_now(),
        last_sync_status="success",
        last_sync_message=f"Garmin sync completed with {inserted} records.",
    )
    return inserted, skipped


async def sync_garmin(
    user_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    metrics: list[dict[str, Any]] | None = None,
    source_device: str = "",
    pull_remote: bool = True,
) -> tuple[int, int]:
    if metrics:
        result = await ingest_mobile_sync(user_id, "garmin", metrics, source_device=source_device)
        return int(result["inserted"]), int(result["skipped"])

    connection = await wearable_connections_collection.find_one({"user_id": user_id, "provider": "garmin"})
    if not connection or str(connection.get("status") or "").lower() != "connected":
        raise HTTPException(status_code=404, detail="Garmin is not connected for this user")

    if not pull_remote:
        return 0, 0

    end = end_date or _utc_now().date()
    start = start_date or end
    return await _sync_garmin_remote(connection, start, end)


async def build_longevity_wearables_response(user_id: str) -> LongevityWearablesResponse:
    connections = await wearable_connections_collection.find({"user_id": user_id}).to_list(length=None)
    connections.sort(
        key=lambda item: (
            item.get("updated_at") or item.get("connected_at") or item.get("last_synced_at") or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    connections_by_provider = {str(item.get("provider") or ""): item for item in connections}
    active_provider = ""
    active_timestamp: datetime | None = None
    for connection in connections:
        if str(connection.get("status") or "").lower() != "connected":
            continue
        candidate_timestamp = connection.get("updated_at") or connection.get("connected_at") or connection.get("last_synced_at")
        candidate_timestamp = candidate_timestamp if isinstance(candidate_timestamp, datetime) else None
        if active_timestamp is None or (candidate_timestamp is not None and candidate_timestamp > active_timestamp):
            active_timestamp = candidate_timestamp
            active_provider = str(connection.get("provider") or "")
    devices: list[LongevityWearableDeviceResponse] = []
    latest_sync: datetime | None = None
    for provider in SUPPORTED_PROVIDERS:
        connection = connections_by_provider.get(provider)
        display = PROVIDER_DISPLAY[provider]
        connection_metadata = dict((connection or {}).get("metadata") or {})
        is_active = bool(connection and str(connection.get("status") or "").lower() == "connected" and provider == active_provider)
        status_value = "CONNECTED" if is_active else "CONNECT"
        if connection and str(connection.get("last_sync_status") or "").lower() == "failed":
            status_value = "ERROR"
        last_synced_at = connection.get("last_synced_at") if connection else None
        if isinstance(last_synced_at, datetime) and (latest_sync is None or last_synced_at > latest_sync):
            latest_sync = last_synced_at
        device_name = str(
            (connection or {}).get("device_name")
            or (connection or {}).get("source_device")
            or connection_metadata.get("device_name")
            or connection_metadata.get("source_device")
            or ""
        )
        display_name = device_name if is_active and device_name else display["name"]
        devices.append(
            LongevityWearableDeviceResponse(
                id=provider,
                name=display_name,
                status=status_value,
                active=is_active,
                image=display["image"],
                device_name=device_name,
                source_device=device_name,
                platform=str((connection or {}).get("platform") or connection_metadata.get("platform") or ""),
            )
        )

    total_records = await health_metrics_collection.count_documents({"user_id": user_id})
    profile = await longevity_os_profiles_collection.find_one({"user_id": user_id}, {"wearables.sync_message": 1})
    cached_sync_message = str((((profile or {}).get("wearables") or {}).get("sync_message") or "")).strip()
    sync_message = (
        cached_sync_message
        if cached_sync_message
        else (
            f"{total_records} normalized wearable records available."
            if total_records
            else "No data synced yet. Add a wearable and press sync to import health data into Longevity OS."
        )
    )
    return LongevityWearablesResponse(
        devices=devices,
        last_synced_at=latest_sync,
        has_data=total_records > 0,
        sync_message=sync_message,
    )


async def sync_connected_wearables_for_user(
    user_id: str,
    providers: list[str] | None = None,
) -> LongevityWearablesResponse:
    selected_providers = [_ensure_supported_provider(provider) for provider in (providers or []) if str(provider or "").strip()]
    if selected_providers:
        connection_filter: dict[str, Any] = {
            "user_id": user_id,
            "provider": {"$in": selected_providers},
            "status": "connected",
        }
    else:
        connection_filter = {
            "user_id": user_id,
            "provider": {"$in": list(SUPPORTED_PROVIDERS)},
            "status": "connected",
        }

    connections = await wearable_connections_collection.find(connection_filter).to_list(length=None)
    if selected_providers and not connections:
        for provider in selected_providers:
            await connect_local_provider(user_id, provider)
        connections = await wearable_connections_collection.find(connection_filter).to_list(length=None)
    if not connections:
        raise HTTPException(status_code=400, detail="Select a wearable first, then sync your health data")
    today = _utc_now().date()
    for connection in connections:
        provider = str(connection.get("provider") or "")
        try:
            if provider == "fitbit":
                await _sync_fitbit_remote(connection, today, today)
            elif provider == "google-fit":
                await _sync_google_fit_remote(connection, today, today)
            elif provider == "garmin":
                await _sync_garmin_remote(connection, today, today)
        except Exception as exc:
            await upsert_wearable_connection(
                str(connection.get("user_id") or ""),
                provider,
                status_value="connected",
                source_device=str(connection.get("source_device") or (connection.get("metadata") or {}).get("source_device") or ""),
                last_sync_status="failed",
                last_sync_message=str(exc),
            )
            logger.exception("wearable_sync_failed provider=%s user_id=%s", provider, user_id)
    await refresh_longevity_profile_cache(user_id)
    return await build_longevity_wearables_response(user_id)


def resolve_target_user_id(actor: dict, requested_user_id: str | None = None) -> str:
    actor_user_id = str(actor.get("_id") or "")
    target = (requested_user_id or "").strip()
    if target and target != actor_user_id:
        if not actor.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin access required for cross-user wearable access")
        return target
    return actor_user_id


async def verify_garmin_webhook_signature(request: Request) -> None:
    secret = (getattr(settings, "garmin_webhook_secret", "") or "").strip()
    if not secret:
        return
    signature = (request.headers.get("X-Garmin-Signature") or request.headers.get("X-Hub-Signature-256") or "").strip()
    if not signature:
        raise HTTPException(status_code=401, detail="Missing Garmin webhook signature")
    payload = await request.body()
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature.split("=")[-1]
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid Garmin webhook signature")


def _decode_svix_signing_secret(secret: str) -> bytes:
    normalized = (secret or "").strip()
    if normalized.startswith("whsec_"):
        normalized = normalized[len("whsec_") :]
    try:
        return base64.b64decode(normalized, validate=True)
    except Exception:
        return normalized.encode("utf-8")


async def handle_garmin_webhook(payload: dict[str, Any]) -> tuple[bool, int]:
    provider_user_id = str(payload.get("provider_user_id") or "").strip()
    external_user_id = str(payload.get("external_user_id") or "").strip()
    metrics = [dict(item) for item in payload.get("metrics") or []]

    connection: dict | None = None
    if provider_user_id:
        connection = await wearable_connections_collection.find_one({"provider": "garmin", "provider_user_id": provider_user_id})
    if connection is None and external_user_id:
        user = await users_collection.find_one({"email": external_user_id.lower()})
        if user:
            connection = await wearable_connections_collection.find_one({"provider": "garmin", "user_id": str(user["_id"])})
    if connection is None:
        return False, 0

    synced_records = 0
    if metrics:
        inserted, _ = await store_normalized_metrics(
            str(connection.get("user_id") or ""),
            "garmin",
            metrics,
            source_device="Garmin Webhook",
        )
        synced_records = inserted
    else:
        start = _utc_now().date()
        inserted, _ = await _sync_garmin_remote(connection, start, start)
        synced_records = inserted
    return True, synced_records


async def _run_scheduled_sync_cycle() -> None:
    if not getattr(settings, "wearable_scheduler_enabled", True):
        return
    lookback_days = max(int(getattr(settings, "wearable_scheduler_lookback_days", 1) or 1), 1)
    end = _utc_now().date()
    start = end - timedelta(days=lookback_days - 1)
    connections = await wearable_connections_collection.find(
        {"provider": {"$in": ["fitbit", "google-fit", "garmin"]}, "status": "connected"}
    ).to_list(length=None)
    for connection in connections:
        provider = str(connection.get("provider") or "")
        user_id = str(connection.get("user_id") or "")
        try:
            if provider == "fitbit":
                await _sync_fitbit_remote(connection, start, end)
            elif provider == "google-fit":
                await _sync_google_fit_remote(connection, start, end)
            elif provider == "garmin":
                await _sync_garmin_remote(connection, start, end)
        except Exception as exc:
            logger.exception("scheduled_wearable_sync_failed provider=%s user_id=%s", provider, user_id)
            await upsert_wearable_connection(
                user_id,
                provider,
                status_value="connected",
                last_sync_status="failed",
                last_sync_message=str(exc),
            )


async def _scheduler_loop() -> None:
    interval_seconds = max(int(getattr(settings, "wearable_scheduler_interval_minutes", 30) or 30), 1) * 60
    while not _scheduler_stop.is_set():
        await _run_scheduled_sync_cycle()
        try:
            await asyncio.wait_for(_scheduler_stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


async def start_wearables_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None or not getattr(settings, "wearable_scheduler_enabled", True):
        return
    _scheduler_stop.clear()
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("wearable_scheduler_started")


async def stop_wearables_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None:
        return
    _scheduler_stop.set()
    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass
    _scheduler_task = None
    logger.info("wearable_scheduler_stopped")
