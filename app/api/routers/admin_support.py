import re

from fastapi import APIRouter, Query

from ...core.legacy import *
from ...models import SupportMessageSummaryResponse

router = APIRouter()

SUPPORT_MESSAGE_STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED"}


def _normalize_text_filter(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""

@router.get("/admin/support/messages", response_model=SupportMessageListResponse)
async def admin_get_support_messages(
    query: str = Query("", max_length=120),
    status: str = Query("ALL", max_length=40),
    limit: int = Query(500, ge=1, le=1000),
    _: dict = Depends(_require_admin_user),
) -> SupportMessageListResponse:
    normalized_query = _normalize_text_filter(query)
    normalized_status = _normalize_text_filter(status).upper() or "ALL"
    if normalized_status not in {"ALL", *SUPPORT_MESSAGE_STATUSES}:
        raise HTTPException(status_code=400, detail="Invalid support message status filter")

    search_filter: dict = {}
    if normalized_query:
        pattern = re.escape(normalized_query)
        search_filter = {
            "$or": [
                {"subject": {"$regex": pattern, "$options": "i"}},
                {"message": {"$regex": pattern, "$options": "i"}},
                {"user_name": {"$regex": pattern, "$options": "i"}},
                {"user_email": {"$regex": pattern, "$options": "i"}},
                {"admin_notes": {"$regex": pattern, "$options": "i"}},
            ]
        }

    base_records = await support_messages_collection.find(
        search_filter,
        sort=[("created_at", -1), ("_id", -1)],
        limit=limit,
    ).to_list(length=limit)

    visible_records = [
        record for record in base_records
        if normalized_status == "ALL" or str(record.get("status") or "OPEN").strip().upper() == normalized_status
    ]

    now = datetime.now(timezone.utc)
    status_counts = {name: 0 for name in SUPPORT_MESSAGE_STATUSES}
    submitted_last_7_days = 0
    for record in base_records:
        current_status = str(record.get("status") or "OPEN").strip().upper()
        if current_status in status_counts:
            status_counts[current_status] += 1
        created_at = _as_utc(record.get("created_at") or now)
        if created_at >= now - timedelta(days=7):
            submitted_last_7_days += 1

    return SupportMessageListResponse(
        messages=[_serialize_support_message_record(record) for record in visible_records],
        summary=SupportMessageSummaryResponse(
            totalMessages=len(base_records),
            visibleMessages=len(visible_records),
            openMessages=status_counts["OPEN"],
            inProgressMessages=status_counts["IN_PROGRESS"],
            resolvedMessages=status_counts["RESOLVED"],
            submittedLast7Days=submitted_last_7_days,
        ),
        query=normalized_query,
        statusFilter=normalized_status,
    )

@router.patch("/admin/support/messages/{message_id}", response_model=SupportMessageResponse)

async def admin_update_support_message(

    message_id: str,

    payload: AdminSupportMessageUpdateRequest,

    _: dict = Depends(_require_admin_user),

) -> SupportMessageResponse:

    try:

        object_id = ObjectId(message_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid support message id") from exc

    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    if payload.status is not None:
        normalized_status = payload.status.strip().upper()
        if normalized_status not in SUPPORT_MESSAGE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid support message status")
        update_doc["status"] = normalized_status

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()

    await support_messages_collection.update_one({"_id": object_id}, {"$set": update_doc})

    record = await support_messages_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Support message not found")

    return _serialize_support_message_record(record)
