from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/applications", response_model=CoachingApplicationResponse, status_code=status.HTTP_201_CREATED)

async def create_coaching_application(

    payload: CoachingApplicationCreateRequest,

    user: dict = Depends(_require_application_access_user),

) -> CoachingApplicationResponse:

    if not payload.agreement_accepted:

        raise HTTPException(status_code=400, detail="You must accept the agreement before submitting")

    now = datetime.now(timezone.utc)

    document = {

        "_id": ObjectId(),

        "user_id": str(user["_id"]),

        "first_name": payload.first_name.strip(),

        "last_name": payload.last_name.strip(),

        "email": payload.email.lower().strip(),

        "phone_number": str(payload.phone_number or "").strip(),

        "goal": payload.goal.strip(),

        "obstacle": payload.obstacle.strip(),

        "investment": payload.investment.strip(),

        "commitment": payload.commitment.strip(),

        "injury": payload.injury.strip(),

        "additional_notes": str(payload.additional_notes or "").strip(),

        "agreement_accepted": True,

        "status": "NEW",

        "admin_notes": "",

        "created_at": now,

        "updated_at": now,

    }

    await coaching_applications_collection.insert_one(document)

    return _serialize_coaching_application_record(document)
