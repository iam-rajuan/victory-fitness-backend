from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException

from ..config import settings


PROVIDER_NOT_CONFIGURED = "provider_not_configured"


class HealthProviderAdapter(Protocol):
    provider: str

    async def connect(self, user_id: str) -> dict[str, Any]:
        ...

    async def sync(self, user_id: str) -> dict[str, Any]:
        ...

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        ...

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        ...

    async def callback(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def refresh_token(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError


def is_provider_configured(provider: str) -> bool:
    normalized = (provider or "").strip().lower()
    if normalized == "fitbit":
        return bool(settings.fitbit_client_id and settings.fitbit_client_secret)
    if normalized == "garmin":
        return bool(
            settings.garmin_enabled
            and settings.garmin_client_id
            and settings.garmin_client_secret
            and settings.garmin_authorize_url
            and settings.garmin_token_url
            and settings.garmin_api_base_url
        )
    if normalized in {"apple-health", "health-connect", "this-phone", "qr-import"}:
        return True
    return False


def require_provider_configured(provider: str) -> None:
    if not is_provider_configured(provider):
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED)


@dataclass(slots=True)
class FitbitAdapter:
    provider: str = "fitbit"

    async def connect(self, user_id: str) -> dict[str, Any]:
        require_provider_configured(self.provider)
        from .service import build_oauth_connect_url

        return await build_oauth_connect_url(user_id, self.provider)

    async def callback(self, params: dict[str, Any]) -> dict[str, Any]:
        from .service import exchange_fitbit_code

        return await exchange_fitbit_code(str(params.get("state") or ""), str(params.get("code") or ""))

    async def sync(self, user_id: str) -> dict[str, Any]:
        from .service import sync_fitbit

        inserted, skipped = await sync_fitbit(user_id)
        return {"provider": self.provider, "inserted": inserted, "skipped": skipped}

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        from .service import disconnect_provider

        await disconnect_provider(user_id, self.provider)
        return {"provider": self.provider, "disconnected": True}

    async def refresh_token(self, user_id: str) -> dict[str, Any]:
        from ..database import wearable_connections_collection
        from .service import _refresh_oauth_connection  # type: ignore[attr-defined]

        connection = await wearable_connections_collection.find_one({"user_id": user_id, "provider": self.provider})
        if not connection:
            raise HTTPException(status_code=404, detail="Fitbit is not connected for this user")
        updated = await _refresh_oauth_connection(connection)
        return {"provider": self.provider, "status": str(updated.get("status") or "connected")}

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in list(raw_data or [])]


@dataclass(slots=True)
class GarminAdapter:
    provider: str = "garmin"

    async def connect(self, user_id: str) -> dict[str, Any]:
        require_provider_configured(self.provider)
        from .service import build_oauth_connect_url

        return await build_oauth_connect_url(user_id, self.provider)

    async def callback(self, params: dict[str, Any]) -> dict[str, Any]:
        from .service import exchange_garmin_code

        return await exchange_garmin_code(str(params.get("state") or ""), str(params.get("code") or ""))

    async def sync(self, user_id: str) -> dict[str, Any]:
        from .service import sync_garmin

        inserted, skipped = await sync_garmin(user_id)
        return {"provider": self.provider, "inserted": inserted, "skipped": skipped}

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        from .service import disconnect_provider

        await disconnect_provider(user_id, self.provider)
        return {"provider": self.provider, "disconnected": True}

    async def refresh_token(self, user_id: str) -> dict[str, Any]:
        from ..database import wearable_connections_collection
        from .service import _refresh_oauth_connection  # type: ignore[attr-defined]

        connection = await wearable_connections_collection.find_one({"user_id": user_id, "provider": self.provider})
        if not connection:
            raise HTTPException(status_code=404, detail="Garmin is not connected for this user")
        updated = await _refresh_oauth_connection(connection)
        return {"provider": self.provider, "status": str(updated.get("status") or "connected")}

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in list(raw_data or [])]


@dataclass(slots=True)
class AppleHealthAdapter:
    provider: str = "apple-health"

    async def connect(self, user_id: str) -> dict[str, Any]:
        from .service import connect_local_provider

        return await connect_local_provider(user_id, self.provider)

    async def sync(self, user_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=400, detail="Apple Health sync must be initiated from the iOS app")

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        from .service import disconnect_provider

        await disconnect_provider(user_id, self.provider)
        return {"provider": self.provider, "disconnected": True}

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in list(raw_data or [])]


@dataclass(slots=True)
class HealthConnectAdapter:
    provider: str = "health-connect"

    async def connect(self, user_id: str) -> dict[str, Any]:
        from .service import connect_local_provider

        return await connect_local_provider(user_id, self.provider)

    async def sync(self, user_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=400, detail="Health Connect sync must be initiated from the Android app")

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        from .service import disconnect_provider

        await disconnect_provider(user_id, self.provider)
        return {"provider": self.provider, "disconnected": True}

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in list(raw_data or [])]


@dataclass(slots=True)
class ThisPhoneAdapter:
    provider: str = "this-phone"

    async def connect(self, user_id: str) -> dict[str, Any]:
        from .service import connect_local_provider

        return await connect_local_provider(user_id, self.provider)

    async def sync(self, user_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=400, detail="This Phone sync must be initiated from the mobile app")

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        from .service import disconnect_provider

        await disconnect_provider(user_id, self.provider)
        return {"provider": self.provider, "disconnected": True}

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        return [dict(item) for item in list(raw_data or [])]


@dataclass(slots=True)
class QRImportAdapter:
    provider: str = "qr-import"

    async def connect(self, user_id: str) -> dict[str, Any]:
        from .service import connect_local_provider

        return await connect_local_provider(user_id, self.provider)

    async def sync(self, user_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=400, detail="QR import sync requires an uploaded import payload")

    async def disconnect(self, user_id: str) -> dict[str, Any]:
        from .service import disconnect_provider

        await disconnect_provider(user_id, self.provider)
        return {"provider": self.provider, "disconnected": True}

    async def normalize(self, raw_data: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_data, list):
            raise HTTPException(status_code=400, detail="Imported health data must be a list of normalized samples")
        return [dict(item) for item in raw_data]


def get_provider_adapter(provider: str) -> HealthProviderAdapter:
    normalized = (provider or "").strip().lower()
    if normalized == "fitbit":
        return FitbitAdapter()
    if normalized == "garmin":
        return GarminAdapter()
    if normalized == "apple-health":
        return AppleHealthAdapter()
    if normalized == "health-connect":
        return HealthConnectAdapter()
    if normalized == "this-phone":
        return ThisPhoneAdapter()
    if normalized == "qr-import":
        return QRImportAdapter()
    raise HTTPException(status_code=400, detail="Unsupported integration provider")
