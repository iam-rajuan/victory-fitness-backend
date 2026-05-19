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
from fastapi import HTTPException, Request, status
from pymongo import UpdateOne

from ..config import settings
from ..database import health_metrics_collection, users_collection, wearable_connections_collection
from ..models import LongevityWearableDeviceResponse, LongevityWearablesResponse


logger = logging.getLogger("victory_fitness.wearables")

SUPPORTED_PROVIDERS = ("apple-health", "health-connect", "fitbit", "garmin")
OAUTH_PROVIDERS = {"fitbit", "garmin"}
SUPPORTED_METRIC_TYPES = {
    "steps",
    "heart_rate",
    "sleep",
    "calories",
    "workouts",
    "hrv",
    "spo2",
    "stress",
    "body_battery",
    "distance",
}
PROVIDER_DISPLAY = {
    "apple-health": {
        "name": "Apple Health",
        "image": "https://images.unsplash.com/photo-1434493789847-2f02dc6ca35d?w=600&q=80",
    },
    "health-connect": {
        "name": "Google Fit",
        "image": "https://images.unsplash.com/photo-1510017803434-a899398421b3?w=600&q=80",
    },
    "fitbit": {
        "name": "Fitbit",
        "image": "https://images.unsplash.com/photo-1575311373937-040b8e1fd5b2?w=600&q=80",
    },
    "garmin": {
        "name": "Garmin",
        "image": "https://images.unsplash.com/photo-1557438159-8664b4c7301c?w=600&q=80",
    },
}
FITBIT_AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
FITBIT_API_BASE = "https://api.fitbit.com"
_scheduler_task: asyncio.Task | None = None
_scheduler_stop = asyncio.Event()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def _serialize_connection(record: dict) -> dict[str, Any]:
    return {
        "id": str(record.get("_id") or ""),
        "user_id": str(record.get("user_id") or ""),
        "provider": str(record.get("provider") or ""),
        "status": str(record.get("status") or "disconnected"),
        "scopes": [str(item) for item in record.get("scopes") or []],
        "provider_user_id": str(record.get("provider_user_id") or "") or None,
        "connected_at": record.get("connected_at"),
        "last_synced_at": record.get("last_synced_at"),
        "last_sync_status": str(record.get("last_sync_status") or "idle"),
        "last_sync_message": str(record.get("last_sync_message") or ""),
        "metadata": dict(record.get("metadata") or {}),
        "created_at": record.get("created_at") or _utc_now(),
        "updated_at": record.get("updated_at") or _utc_now(),
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
    external_id = str((document.get("metadata") or {}).get("external_id") or "").strip()
    payload = {
        "user_id": str(document.get("user_id") or ""),
        "provider": str(document.get("provider") or ""),
        "metric_type": str(document.get("metric_type") or ""),
        "value": document.get("value"),
        "unit": str(document.get("unit") or ""),
        "start_time": _as_utc(document["start_time"]).isoformat(),
        "end_time": _as_utc(document["end_time"]).isoformat(),
        "source_device": str(document.get("source_device") or ""),
        "external_id": external_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


async def upsert_wearable_connection(
    user_id: str,
    provider: str,
    *,
    status_value: str,
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
    update_fields: dict[str, Any] = {
        "status": status_value,
        "updated_at": now,
    }
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


async def disconnect_provider(user_id: str, provider: str) -> None:
    provider = _ensure_supported_provider(provider)
    await wearable_connections_collection.update_one(
        {"user_id": user_id, "provider": provider},
        {
            "$set": {
                "status": "disconnected",
                "updated_at": _utc_now(),
                "access_token_encrypted": "",
                "refresh_token_encrypted": "",
                "oauth_state": "",
                "token_expires_at": None,
                "last_sync_status": "idle",
                "last_sync_message": "Provider disconnected by user.",
            }
        },
    )


def _normalize_metric_document(
    user_id: str,
    provider: str,
    metric: dict[str, Any],
    fallback_source_device: str = "",
) -> dict[str, Any]:
    metric_type = str(metric.get("metric_type") or "").strip().lower()
    if metric_type not in SUPPORTED_METRIC_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported metric_type: {metric_type}")
    start_time = metric.get("start_time")
    end_time = metric.get("end_time")
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise HTTPException(status_code=400, detail="Each metric requires start_time and end_time")

    metadata = dict(metric.get("metadata") or {})
    document = {
        "_id": ObjectId(),
        "user_id": user_id,
        "provider": provider,
        "metric_type": metric_type,
        "value": metric.get("value"),
        "unit": str(metric.get("unit") or ""),
        "start_time": _as_utc(start_time),
        "end_time": _as_utc(end_time),
        "source_device": str(metric.get("source_device") or fallback_source_device or ""),
        "metadata": metadata,
        "synced_at": _utc_now(),
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
) -> dict[str, Any]:
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
        metadata=metadata,
        connected_at=now,
        last_synced_at=now,
        last_sync_status="success",
        last_sync_message=f"Stored {inserted} health records from {provider}.",
    )
    return {
        "inserted": inserted,
        "skipped": skipped,
        "connection": connection,
        "last_synced_at": now,
    }


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

    time_filter: dict[str, Any] = {}
    start_dt = _date_to_bounds(start_date)
    end_dt = _date_to_bounds(end_date, is_end=True)
    if start_dt is not None:
        time_filter["$gte"] = start_dt
    if end_dt is not None:
        time_filter["$lte"] = end_dt
    if time_filter:
        filter_doc["start_time"] = time_filter

    return await health_metrics_collection.find(
        filter_doc,
        sort=[("start_time", -1), ("_id", -1)],
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
        key = (str(record.get("metric_type") or ""), str(record.get("provider") or ""))
        bucket = groups.setdefault(
            key,
            {
                "metric_type": key[0],
                "provider": key[1],
                "records": 0,
                "numeric_values": [],
                "latest_end_time": None,
            },
        )
        bucket["records"] += 1
        value = record.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            bucket["numeric_values"].append(float(value))
        end_time = record.get("end_time")
        if isinstance(end_time, datetime):
            current_latest = bucket.get("latest_end_time")
            bucket["latest_end_time"] = end_time if current_latest is None or end_time > current_latest else current_latest

    items: list[dict[str, Any]] = []
    for bucket in groups.values():
        numeric_values = bucket.pop("numeric_values")
        total_value = float(sum(numeric_values)) if numeric_values else 0.0
        average_value = float(total_value / len(numeric_values)) if numeric_values else 0.0
        items.append(
            {
                **bucket,
                "total_value": total_value,
                "average_value": average_value,
                "min_value": min(numeric_values) if numeric_values else None,
                "max_value": max(numeric_values) if numeric_values else None,
            }
        )
    items.sort(key=lambda item: (item["metric_type"], item["provider"]))
    return items


async def _http_json_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 20,
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
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise HTTPException(status_code=502, detail=f"Wearable provider request failed: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise HTTPException(status_code=502, detail="Wearable provider is unavailable") from exc

    return await asyncio.to_thread(_do_request)


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return f"Basic {base64.b64encode(raw).decode('utf-8')}"


def _get_fitbit_settings() -> dict[str, Any]:
    client_id = (getattr(settings, "fitbit_client_id", "") or "").strip()
    client_secret = (getattr(settings, "fitbit_client_secret", "") or "").strip()
    redirect_uri = (getattr(settings, "fitbit_redirect_uri", "") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=503, detail="Fitbit OAuth is not configured")
    scopes = list(getattr(settings, "fitbit_scopes", []) or ["activity", "heartrate", "sleep", "profile"])
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
    }


def _get_garmin_settings() -> dict[str, Any]:
    client_id = (getattr(settings, "garmin_client_id", "") or "").strip()
    client_secret = (getattr(settings, "garmin_client_secret", "") or "").strip()
    redirect_uri = (getattr(settings, "garmin_redirect_uri", "") or "").strip()
    authorize_url = (getattr(settings, "garmin_authorize_url", "") or "").strip()
    token_url = (getattr(settings, "garmin_token_url", "") or "").strip()
    api_base = (getattr(settings, "garmin_api_base_url", "") or "").strip()
    if not client_id or not client_secret or not redirect_uri or not authorize_url or not token_url or not api_base:
        raise HTTPException(status_code=503, detail="Garmin OAuth is not configured")
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


async def build_oauth_connect_url(user_id: str, provider: str) -> dict[str, Any]:
    provider = _ensure_supported_provider(provider)
    if provider == "fitbit":
        config = _get_fitbit_settings()
        scopes = config["scopes"]
        base_url = FITBIT_AUTHORIZE_URL
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
        FITBIT_TOKEN_URL,
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
        scopes=str(response.get("scope") or "").split(),
        provider_user_id=str(response.get("user_id") or ""),
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or ""),
        token_expires_at=expires_at,
        oauth_state="",
        connected_at=_utc_now(),
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
        scopes=str(response.get("scope") or "").split(),
        provider_user_id=str(response.get("user_id") or response.get("sub") or ""),
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or ""),
        token_expires_at=expires_at,
        oauth_state="",
        connected_at=_utc_now(),
        metadata=metadata,
        last_sync_status="idle",
        last_sync_message="Garmin connected successfully.",
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
            FITBIT_TOKEN_URL,
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
    else:
        return connection

    expires_at = _utc_now() + timedelta(seconds=int(response.get("expires_in") or 0))
    updated = await upsert_wearable_connection(
        str(connection["user_id"]),
        provider,
        status_value="connected",
        access_token=str(response.get("access_token") or ""),
        refresh_token=str(response.get("refresh_token") or refresh_token),
        token_expires_at=expires_at,
        last_sync_status=str(connection.get("last_sync_status") or "idle"),
        last_sync_message=str(connection.get("last_sync_message") or ""),
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
    return await _http_json_request(
        "GET",
        f"{FITBIT_API_BASE}{path}",
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


async def _fetch_garmin_json(access_token: str, path: str) -> dict[str, Any]:
    config = _get_garmin_settings()
    return await _http_json_request(
        "GET",
        f"{config['api_base']}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
    )


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
    connections_by_provider = {str(item.get("provider") or ""): item for item in connections}
    devices: list[LongevityWearableDeviceResponse] = []
    latest_sync: datetime | None = None
    for provider in SUPPORTED_PROVIDERS:
        connection = connections_by_provider.get(provider)
        display = PROVIDER_DISPLAY[provider]
        is_active = bool(connection and str(connection.get("status") or "").lower() == "connected")
        status_value = "CONNECTED" if is_active else "CONNECT"
        if connection and str(connection.get("last_sync_status") or "").lower() == "failed":
            status_value = "ERROR"
        last_synced_at = connection.get("last_synced_at") if connection else None
        if isinstance(last_synced_at, datetime) and (latest_sync is None or last_synced_at > latest_sync):
            latest_sync = last_synced_at
        devices.append(
            LongevityWearableDeviceResponse(
                id=provider,
                name=display["name"],
                status=status_value,
                active=is_active,
                image=display["image"],
            )
        )

    total_records = await health_metrics_collection.count_documents({"user_id": user_id})
    sync_message = (
        f"{total_records} normalized wearable records available."
        if total_records
        else "No data synced yet. Connect a device and press sync to begin your longevity analysis."
    )
    return LongevityWearablesResponse(
        devices=devices,
        last_synced_at=latest_sync,
        has_data=total_records > 0,
        sync_message=sync_message,
    )


async def sync_connected_wearables_for_user(user_id: str) -> LongevityWearablesResponse:
    connections = await wearable_connections_collection.find(
        {"user_id": user_id, "provider": {"$in": ["fitbit", "garmin"]}, "status": "connected"}
    ).to_list(length=None)
    today = _utc_now().date()
    for connection in connections:
        provider = str(connection.get("provider") or "")
        try:
            if provider == "fitbit":
                await _sync_fitbit_remote(connection, today, today)
            elif provider == "garmin":
                await _sync_garmin_remote(connection, today, today)
        except Exception as exc:
            await upsert_wearable_connection(
                str(connection.get("user_id") or ""),
                provider,
                status_value="connected",
                last_sync_status="failed",
                last_sync_message=str(exc),
            )
            logger.exception("wearable_sync_failed provider=%s user_id=%s", provider, user_id)
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
        {"provider": {"$in": ["fitbit", "garmin"]}, "status": "connected"}
    ).to_list(length=None)
    for connection in connections:
        provider = str(connection.get("provider") or "")
        user_id = str(connection.get("user_id") or "")
        try:
            if provider == "fitbit":
                await _sync_fitbit_remote(connection, start, end)
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
