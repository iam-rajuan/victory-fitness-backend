import asyncio
import re

from fastapi import APIRouter, Query

from ...core.legacy import *
from ...email_service import send_inner_circle_application_email
from ...models import CoachingApplicationSummaryResponse

router = APIRouter()

APPLICATION_STATUSES = {"NEW", "REVIEWING", "APPROVED", "REJECTED"}

def _application_user_snapshot(user: dict | None) -> dict:
    if not user:
        return {}
    country = str(user.get("country") or "").strip()
    country_code = str(user.get("country_code") or "").strip().upper()
    return {
        "applicant_user_name": str(user.get("name") or "").strip(),
        "applicant_user_email": str(user.get("email") or "").strip().lower(),
        "applicant_user_country": country,
        "applicant_user_country_code": country_code,
        "applicant_subscription_tier": str(user.get("subscription_tier") or user.get("subscription_role") or "").strip().upper(),
        "applicant_is_admin": bool(user.get("is_admin", False)),
        "country": country,
        "country_code": country_code,
        "market": country or country_code,
    }

async def _enrich_application_records(records: list[dict]) -> list[dict]:
    user_ids: list[ObjectId] = []
    for record in records:
        user_id = str(record.get("user_id") or "").strip()
        if not user_id:
            continue
        try:
            user_ids.append(ObjectId(user_id))
        except Exception:
            continue
    if not user_ids:
        return records

    users = await users_collection.find({"_id": {"$in": list(set(user_ids))}}).to_list(length=len(user_ids))
    users_by_id = {str(item.get("_id")): item for item in users}
    for record in records:
        if record.get("applicant_user_email") and record.get("market"):
            continue
        snapshot = _application_user_snapshot(users_by_id.get(str(record.get("user_id") or "")))
        if not snapshot:
            continue
        missing_snapshot = {key: value for key, value in snapshot.items() if value and not record.get(key)}
        if not missing_snapshot:
            continue
        record.update(missing_snapshot)
        await coaching_applications_collection.update_one(
            {"_id": record["_id"]},
            {"$set": missing_snapshot},
        )
    return records

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
                {"applicant_user_name": {"$regex": pattern, "$options": "i"}},
                {"applicant_user_email": {"$regex": pattern, "$options": "i"}},
                {"market": {"$regex": pattern, "$options": "i"}},
                {"country": {"$regex": pattern, "$options": "i"}},
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
    base_records = await _enrich_application_records(base_records)

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

    existing_record = await coaching_applications_collection.find_one({"_id": object_id})
    if not existing_record:
        raise HTTPException(status_code=404, detail="Application not found")

    update_doc: dict = {"updated_at": datetime.now(timezone.utc)}

    if payload.status is not None:
        normalized_status = payload.status.strip().upper()
        if normalized_status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid application status")
        update_doc["status"] = normalized_status

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()

    if payload.admin_reply is not None:
        update_doc["admin_reply"] = payload.admin_reply.strip()

    if payload.admin_verdict is not None:
        update_doc["admin_verdict"] = payload.admin_verdict.strip()

    if payload.call_slot is not None:
        update_doc["call_slot"] = payload.call_slot.strip()

    await coaching_applications_collection.update_one({"_id": object_id}, {"$set": update_doc})

    if payload.notify_applicant:
        reply_text = (payload.admin_reply or str(existing_record.get("admin_reply") or "")).strip()
        recipient_email = str(existing_record.get("email") or "").strip()
        applicant_name = f"{str(existing_record.get('first_name') or '').strip()} {str(existing_record.get('last_name') or '').strip()}".strip()
        verdict = (payload.admin_verdict or str(existing_record.get("admin_verdict") or "")).strip()
        if not reply_text:
            await coaching_applications_collection.update_one(
                {"_id": object_id},
                {"$set": {"applicant_email_status": "failed", "applicant_email_error": "Applicant message is required before sending email"}},
            )
            raise HTTPException(status_code=400, detail="Applicant message is required before sending email")
        if not recipient_email:
            await coaching_applications_collection.update_one(
                {"_id": object_id},
                {"$set": {"applicant_email_status": "failed", "applicant_email_error": "Applicant email is missing"}},
            )
            raise HTTPException(status_code=400, detail="Applicant email is missing")
        try:
            await asyncio.to_thread(
                send_inner_circle_application_email,
                to_email=recipient_email,
                name=applicant_name or "there",
                verdict=verdict,
                message=reply_text,
            )
            await coaching_applications_collection.update_one(
                {"_id": object_id},
                {
                    "$set": {
                        "applicant_notified_at": update_doc["updated_at"],
                        "applicant_email_status": "sent",
                        "applicant_email_error": "",
                    }
                },
            )
        except RuntimeError as exc:
            await coaching_applications_collection.update_one(
                {"_id": object_id},
                {"$set": {"applicant_email_status": "failed", "applicant_email_error": str(exc)}},
            )
            raise HTTPException(status_code=502, detail=f"Application saved, but email delivery failed: {exc}") from exc

    record = await coaching_applications_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Application not found")

    return _serialize_coaching_application_record(record)
