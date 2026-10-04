from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

EU_COUNTRY_CODES = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}


def _market_query(applies_to: list[str], notification_behavior: str) -> dict:
    markets = {str(item or "").strip().upper() for item in applies_to or []}
    if notification_behavior == "eu":
        markets = {"EU"}
    if not markets or "ALL" in markets:
        return {"is_admin": {"$ne": True}}
    country_codes: set[str] = set()
    if "EU" in markets:
        country_codes.update(EU_COUNTRY_CODES)
    country_codes.update(item for item in markets if item not in {"ALL", "EU"})
    return {"is_admin": {"$ne": True}, "country_code": {"$in": sorted(country_codes)}}


async def _notify_legal_document_publish(document_title: str, payload) -> None:
    if payload.notification_behavior == "silent":
        return
    now = datetime.now(timezone.utc)
    query = _market_query(payload.applies_to, payload.notification_behavior)
    notification = {
        "id": uuid4().hex,
        "type": "legal_document_update",
        "title": f"{document_title} updated",
        "message": f"A new version of {document_title} has been published.",
        "data": {
            "type": "legal_document_update",
            "document": document_title,
            "effectiveAt": (payload.effective_at or now).isoformat(),
        },
        "copy_variant": "legal",
        "created_at": now,
        "read": False,
        "delivery": {"status": "inbox_only", "providers": []},
    }
    await users_collection.update_many(
        query,
        {"$push": {"app_notifications": {"$each": [notification], "$slice": -50}}},
    )

@router.get("/admin/content/privacy-policy", response_model=PrivacyPolicyResponse)
async def admin_get_privacy_policy(_: dict = Depends(_require_admin_user)) -> PrivacyPolicyResponse:
    record = await _ensure_privacy_policy_record()
    return _serialize_privacy_policy_record(record)

@router.put("/admin/content/privacy-policy", response_model=PrivacyPolicyResponse)
async def admin_update_privacy_policy(
    payload: UpdatePrivacyPolicyRequest,
    _: dict = Depends(_require_admin_user),
) -> PrivacyPolicyResponse:
    record = await upsert_content_record(
        key=PRIVACY_POLICY_KEY,
        title=payload.title,
        html_content=payload.html_content,
        filename=payload.filename,
        version=payload.version,
        applies_to=payload.applies_to,
        notification_behavior=payload.notification_behavior,
        effective_at=payload.effective_at,
    )
    if not record:
        raise HTTPException(status_code=500, detail="Privacy policy could not be saved")
    await _notify_legal_document_publish("Privacy Policy", payload)
    return _serialize_privacy_policy_record(record)

@router.get("/admin/content/terms-condition", response_model=TermsConditionResponse)
async def admin_get_terms_condition(_: dict = Depends(_require_admin_user)) -> TermsConditionResponse:
    record = await _ensure_terms_condition_record()
    return _serialize_terms_condition_record(record)

@router.put("/admin/content/terms-condition", response_model=TermsConditionResponse)
async def admin_update_terms_condition(
    payload: UpdateTermsConditionRequest,
    _: dict = Depends(_require_admin_user),
) -> TermsConditionResponse:
    record = await upsert_content_record(
        key=TERMS_CONDITION_KEY,
        title=payload.title,
        html_content=payload.html_content,
        filename=payload.filename,
        version=payload.version,
        applies_to=payload.applies_to,
        notification_behavior=payload.notification_behavior,
        effective_at=payload.effective_at,
    )
    if not record:
        raise HTTPException(status_code=500, detail="Terms & Conditions could not be saved")
    await _notify_legal_document_publish("Terms & Conditions", payload)
    return _serialize_terms_condition_record(record)

@router.get("/admin/content/about-us", response_model=AboutUsResponse)
async def admin_get_about_us(_: dict = Depends(_require_admin_user)) -> AboutUsResponse:
    record = await _ensure_about_us_record()
    return _serialize_about_us_record(record)

@router.put("/admin/content/about-us", response_model=AboutUsResponse)
async def admin_update_about_us(
    payload: UpdateAboutUsRequest,
    _: dict = Depends(_require_admin_user),
) -> AboutUsResponse:
    record = await upsert_content_record(
        key=ABOUT_US_KEY,
        title=payload.title,
        html_content=payload.html_content,
        filename=payload.filename,
        version=payload.version,
        applies_to=payload.applies_to,
        notification_behavior=payload.notification_behavior,
        effective_at=payload.effective_at,
    )
    if not record:
        raise HTTPException(status_code=500, detail="About Us could not be saved")
    return _serialize_about_us_record(record)


@router.get("/admin/content/inner-circle/application-questions", response_model=InnerCircleApplicationQuestionsResponse)
async def admin_get_inner_circle_application_questions(
    _: dict = Depends(_require_admin_user),
) -> InnerCircleApplicationQuestionsResponse:
    record = await _get_inner_circle_application_questions_record()
    return _serialize_inner_circle_application_questions(record)


@router.put("/admin/content/inner-circle/application-questions", response_model=InnerCircleApplicationQuestionsResponse)
async def admin_update_inner_circle_application_questions(
    payload: UpdateInnerCircleApplicationQuestionsRequest,
    _: dict = Depends(_require_admin_user),
) -> InnerCircleApplicationQuestionsResponse:
    now = datetime.now(timezone.utc)
    questions = [
        item.model_dump()
        for item in sorted(payload.questions, key=lambda question: question.order)
        if item.active and item.question.strip()
    ]
    if not questions:
        raise HTTPException(status_code=400, detail="At least one active question is required")

    await app_content_collection.update_one(
        {"key": INNER_CIRCLE_APPLICATION_QUESTIONS_KEY},
        {
            "$set": {
                "title": payload.title.strip() or DEFAULT_INNER_CIRCLE_APPLICATION_TITLE,
                "subtitle": payload.subtitle.strip() or DEFAULT_INNER_CIRCLE_APPLICATION_SUBTITLE,
                "questions": questions,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now, "key": INNER_CIRCLE_APPLICATION_QUESTIONS_KEY},
        },
        upsert=True,
    )
    record = await app_content_collection.find_one({"key": INNER_CIRCLE_APPLICATION_QUESTIONS_KEY})
    return _serialize_inner_circle_application_questions(record or {})
