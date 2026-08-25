import re

from fastapi import APIRouter, Query

from ...core.legacy import *
from ...models import CoachingApplicationSummaryResponse

router = APIRouter()

APPLICATION_STATUSES = {"NEW", "REVIEWING", "APPROVED", "REJECTED"}

@router.get("/admin/applications", response_model=CoachingApplicationListResponse)
async def admin_get_coaching_applications(
    query: str = Query("", max_length=120),
    status: str = Query("ALL", max_length=40),
    limit: int = Query(500, ge=1, le=1000),
    _: dict = Depends(_require_admin_user),
) -> CoachingApplicationListResponse:
    normalized_query = query.strip()
    normalized_status = status.strip().upper() or "ALL"
    if normalized_status not in {"ALL", *APPLICATION_STATUSES}:
        raise HTTPException(status_code=400, detail="Invalid application status filter")

    search_filter: dict = {}
    if normalized_query:
        pattern = re.escape(normalized_query)
        search_filter = {
            "$or": [
                {"first_name": {"$regex": pattern, "$options": "i"}},
                {"last_name": {"$regex": pattern, "$options": "i"}},
                {"email": {"$regex": pattern, "$options": "i"}},
                {"phone_number": {"$regex": pattern, "$options": "i"}},
                {"goal": {"$regex": pattern, "$options": "i"}},
                {"obstacle": {"$regex": pattern, "$options": "i"}},
                {"investment": {"$regex": pattern, "$options": "i"}},
                {"commitment": {"$regex": pattern, "$options": "i"}},
            ]
        }

    base_records = await coaching_applications_collection.find(
        search_filter,
        sort=[("created_at", -1), ("_id", -1)],
        limit=limit,
    ).to_list(length=limit)

    visible_records = [
        record for record in base_records
        if normalized_status == "ALL" or str(record.get("status") or "NEW").strip().upper() == normalized_status
    ]

    now = datetime.now(timezone.utc)
    submitted_last_7_days = 0
    for record in base_records:
        created_at = _as_utc(record.get("created_at") or now)
        if created_at >= now - timedelta(days=7):
            submitted_last_7_days += 1

    status_counts = {name: 0 for name in APPLICATION_STATUSES}
    for record in base_records:
        current_status = str(record.get("status") or "NEW").strip().upper()
        if current_status in status_counts:
            status_counts[current_status] += 1

    return CoachingApplicationListResponse(
        applications=[_serialize_coaching_application_record(record) for record in visible_records],
        summary=CoachingApplicationSummaryResponse(
            totalApplications=len(base_records),
            visibleApplications=len(visible_records),
            newApplications=status_counts["NEW"],
            reviewingApplications=status_counts["REVIEWING"],
            approvedApplications=status_counts["APPROVED"],
            rejectedApplications=status_counts["REJECTED"],
            withPhoneNumber=sum(1 for record in base_records if str(record.get("phone_number") or "").strip()),
            submittedLast7Days=submitted_last_7_days,
        ),
        query=normalized_query,
        statusFilter=normalized_status,
    )

@router.patch("/admin/applications/{application_id}", response_model=CoachingApplicationResponse)

async def admin_update_coaching_application(

    application_id: str,

    payload: AdminCoachingApplicationUpdateRequest,

    _: dict = Depends(_require_admin_user),

) -> CoachingApplicationResponse:

    try:

        object_id = ObjectId(application_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid application id") from exc

    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    if payload.status is not None:
        normalized_status = payload.status.strip().upper()
        if normalized_status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid application status")
        update_doc["status"] = normalized_status

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()

    await coaching_applications_collection.update_one({"_id": object_id}, {"$set": update_doc})

    record = await coaching_applications_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Application not found")

    return _serialize_coaching_application_record(record)
