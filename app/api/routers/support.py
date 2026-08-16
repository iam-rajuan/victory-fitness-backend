from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/support/messages", response_model=SupportMessageResponse, status_code=status.HTTP_201_CREATED)

async def create_support_message(

    payload: SupportMessageCreateRequest,

    user: dict = Depends(_require_access_user),

) -> SupportMessageResponse:

    now = datetime.now(timezone.utc)

    document = {

        "_id": ObjectId(),

        "user_id": str(user["_id"]),

        "user_name": str(user.get("name") or "Member").strip() or "Member",

        "user_email": str(user.get("email") or "").strip().lower(),

        "subject": payload.subject.strip(),

        "message": payload.message.strip(),

        "status": "OPEN",

        "admin_notes": "",

        "created_at": now,

        "updated_at": now,

    }

    await support_messages_collection.insert_one(document)

    return _serialize_support_message_record(document)
