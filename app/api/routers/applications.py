from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/applications", response_model=CoachingApplicationResponse, status_code=status.HTTP_201_CREATED)

async def create_coaching_application(

    payload: CoachingApplicationCreateRequest,

    user: dict = Depends(_require_access_user),

) -> CoachingApplicationResponse:

    if not payload.agreement_accepted:

        raise HTTPException(status_code=400, detail="You must accept the agreement before submitting")

    now = datetime.now(timezone.utc)
    account_name = str(user.get("name") or "").strip()
    account_email = str(user.get("email") or "").lower().strip()
    account_country = str(user.get("country") or "").strip()
    account_country_code = str(user.get("country_code") or "").strip().upper()
    account_phone = str(user.get("contact_number") or "").strip()
    subscription_tier = str(user.get("subscription_tier") or user.get("subscription_role") or "").strip().upper()
    submitted_first_name = payload.first_name.strip()
    submitted_last_name = payload.last_name.strip()
    submitted_email = payload.email.lower().strip()
    submitted_phone = str(payload.phone_number or "").strip()

    if not submitted_email or submitted_email.endswith("@victory.local"):
        submitted_email = account_email
    if not submitted_phone and account_phone:
        submitted_phone = account_phone
    if submitted_first_name.lower() == "inner" and submitted_last_name.lower() == "circle" and account_name:
        parts = account_name.split()
        submitted_first_name = parts[0]
        submitted_last_name = " ".join(parts[1:]) or submitted_last_name

    if not submitted_email:
        raise HTTPException(status_code=400, detail="Applicant email is required")

    document = {

        "_id": ObjectId(),

        "user_id": str(user["_id"]),
        "applicant_user_name": account_name,
        "applicant_user_email": account_email,
        "applicant_user_country": account_country,
        "applicant_user_country_code": account_country_code,
        "applicant_subscription_tier": subscription_tier,
        "applicant_is_admin": bool(user.get("is_admin", False)),

        "first_name": submitted_first_name,

        "last_name": submitted_last_name,

        "email": submitted_email,

        "phone_number": submitted_phone,
        "country": account_country,
        "country_code": account_country_code,
        "market": account_country or account_country_code,

        "goal": payload.goal.strip(),

        "obstacle": payload.obstacle.strip(),

        "investment": payload.investment.strip(),

        "commitment": payload.commitment.strip(),

        "injury": payload.injury.strip(),

        "additional_notes": str(payload.additional_notes or "").strip(),
        "question_answers": [
            {
                "id": str(item.id or "").strip(),
                "order": item.order,
                "question": item.question.strip(),
                "hint": item.hint.strip(),
                "answer": item.answer.strip(),
            }
            for item in payload.question_answers
            if item.question.strip() and item.answer.strip()
        ],

        "agreement_accepted": True,

        "status": "NEW",

        "admin_notes": "",

        "created_at": now,

        "updated_at": now,

    }

    await coaching_applications_collection.insert_one(document)

    return _serialize_coaching_application_record(document)
