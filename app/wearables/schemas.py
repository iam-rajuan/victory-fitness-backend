from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


WearableProvider = Literal["apple-health", "health-connect", "fitbit", "garmin", "this-phone", "qr-import"]
HealthMetricType = Literal[
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
]


class NormalizedHealthMetricIn(BaseModel):
    metric_type: HealthMetricType
    value: float | int | str = Field(description="Primary normalized metric value.")
    unit: str = Field(default="", max_length=40)
    start_time: datetime
    end_time: datetime
    source_device: str = Field(default="", max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MobileHealthSyncRequest(BaseModel):
    metrics: list[NormalizedHealthMetricIn] = Field(default_factory=list, min_length=1)
    source_device: str = Field(default="", max_length=160)
    batch_id: str | None = Field(default=None, max_length=120)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "metrics": [
                        {
                            "metric_type": "steps",
                            "value": 8421,
                            "unit": "count",
                            "start_time": "2026-05-18T00:00:00Z",
                            "end_time": "2026-05-18T23:59:59Z",
                            "source_device": "Apple Watch Series 9",
                            "metadata": {
                                "source_app": "HealthKit",
                                "external_id": "steps-2026-05-18",
                            },
                        },
                        {
                            "metric_type": "sleep",
                            "value": 7.4,
                            "unit": "hours",
                            "start_time": "2026-05-17T22:31:00Z",
                            "end_time": "2026-05-18T05:55:00Z",
                            "source_device": "Apple Watch Series 9",
                            "metadata": {
                                "deep_sleep_minutes": 92,
                                "rem_sleep_minutes": 110,
                            },
                        },
                    ],
                    "source_device": "iPhone 15 Pro",
                    "batch_id": "apple-sync-2026-05-18-001",
                }
            ]
        }
    }


class QRHealthSyncRequest(BaseModel):
    qr_payload: str = Field(min_length=8, max_length=500000)
    source_device: str = Field(default="", max_length=160)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "qr_payload": "{\"metrics\":[{\"metric_type\":\"steps\",\"value\":8421,\"unit\":\"count\",\"start_time\":\"2026-05-18T00:00:00Z\",\"end_time\":\"2026-05-18T23:59:59Z\",\"source_device\":\"Apple Watch Series 9\",\"metadata\":{\"external_id\":\"steps-2026-05-18\"}}],\"source_device\":\"iPhone 15 Pro\",\"batch_id\":\"qr-sync-2026-05-18-001\"}",
                    "source_device": "iPhone 15 Pro",
                }
            ]
        }
    }


class OAuthConnectResponse(BaseModel):
    provider: WearableProvider
    authorization_url: str
    state: str
    expires_at: datetime


class WearableConnectionResponse(BaseModel):
    id: str
    user_id: str
    provider: WearableProvider
    status: str
    scopes: list[str] = Field(default_factory=list)
    provider_user_id: str | None = None
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_sync_status: str = "idle"
    last_sync_message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class WearableConnectionsResponse(BaseModel):
    connections: list[WearableConnectionResponse] = Field(default_factory=list)


class ProviderSyncRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    pull_remote: bool = True
    source_device: str = Field(default="", max_length=160)
    metrics: list[NormalizedHealthMetricIn] = Field(default_factory=list)


class LongevityWearableSyncRequest(BaseModel):
    provider: WearableProvider | None = None
    providers: list[WearableProvider] = Field(default_factory=list)


class ProviderDisconnectResponse(BaseModel):
    provider: WearableProvider
    disconnected: bool = True


class ProviderSyncResponse(BaseModel):
    provider: WearableProvider
    user_id: str
    synced_records: int = 0
    skipped_duplicates: int = 0
    connection_status: str = "connected"
    last_synced_at: datetime | None = None
    message: str = ""


class HealthMetricResponse(BaseModel):
    id: str
    user_id: str
    provider: WearableProvider
    metric_type: HealthMetricType
    value: float | int | str
    unit: str = ""
    start_time: datetime
    end_time: datetime
    source_device: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    synced_at: datetime


class HealthMetricListResponse(BaseModel):
    items: list[HealthMetricResponse] = Field(default_factory=list)
    total: int = 0


class HealthMetricSummaryItem(BaseModel):
    metric_type: str
    provider: str
    records: int = 0
    total_value: float = 0
    average_value: float = 0
    min_value: float | None = None
    max_value: float | None = None
    latest_end_time: datetime | None = None


class HealthMetricSummaryResponse(BaseModel):
    user_id: str
    from_date: date | None = None
    to_date: date | None = None
    items: list[HealthMetricSummaryItem] = Field(default_factory=list)


class GarminWebhookRequest(BaseModel):
    provider_user_id: str | None = Field(default=None, max_length=120)
    external_user_id: str | None = Field(default=None, max_length=120)
    event_type: str = Field(default="daily_summary", max_length=120)
    metrics: list[NormalizedHealthMetricIn] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class GarminWebhookResponse(BaseModel):
    accepted: bool = True
    queued: bool = False
    synced_records: int = 0
    message: str = ""
