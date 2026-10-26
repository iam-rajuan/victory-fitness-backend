from fastapi import APIRouter, Depends, Request

from ...consent_service import append_consent_event, latest_consent_statuses
from ...core.legacy import _require_access_user
from ...models import ConsentChangeRequest

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else None)


@router.get("/me/consents")
async def get_my_consents(user: dict = Depends(_require_access_user)) -> dict:
    return {"consents": await latest_consent_statuses(str(user["_id"]))}


@router.post("/me/consents")
async def change_my_consent(
    payload: ConsentChangeRequest,
    request: Request,
    user: dict = Depends(_require_access_user),
) -> dict:
    if payload.source == "journal_dialog" and payload.consent_id != "journal":
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="journal_dialog is only valid for journal consent")
    event = await append_consent_event(
        user_id=str(user["_id"]),
        consent_id=payload.consent_id,
        granted=payload.granted,
        language=payload.language,
        source=payload.source,
        ip_address=_client_ip(request),
    )
    return {
        "consent_id": event["consent_id"],
        "version": event["version"],
        "granted": event["granted"],
        "language": event["language"],
        "timestamp_utc": event["timestamp_utc"],
    }
