from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/support/messages", response_model=SupportMessageListResponse)

async def admin_get_support_messages(_: dict = Depends(_require_admin_user)) -> SupportMessageListResponse:

    records = await support_messages_collection.find(

        {},

        sort=[("created_at", -1), ("_id", -1)],

        limit=300,

    ).to_list(length=300)

    return SupportMessageListResponse(

        messages=[_serialize_support_message_record(record) for record in records]

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

        update_doc["status"] = payload.status.strip().upper()

    if payload.admin_notes is not None:

        update_doc["admin_notes"] = payload.admin_notes.strip()

    await support_messages_collection.update_one({"_id": object_id}, {"$set": update_doc})

    record = await support_messages_collection.find_one({"_id": object_id})

    if not record:

        raise HTTPException(status_code=404, detail="Support message not found")

    return _serialize_support_message_record(record)
