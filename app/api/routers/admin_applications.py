from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/applications", response_model=CoachingApplicationListResponse)

async def admin_get_coaching_applications(_: dict = Depends(_require_admin_user)) -> CoachingApplicationListResponse:

    records = await coaching_applications_collection.find(

        {},

        sort=[("created_at", -1), ("_id", -1)],

        limit=300,

    ).to_list(length=300)

    return CoachingApplicationListResponse(

        applications=[_serialize_coaching_application_record(record) for record in records]

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

        update_doc["status"] = payload.status.strip().upper()

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()

    await coaching_applications_collection.update_one({"_id": object_id}, {"$set": update_doc})

    record = await coaching_applications_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Application not found")

    return _serialize_coaching_application_record(record)
