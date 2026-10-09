from fastapi import APIRouter

from ...core.legacy import *
from ...models import LegalContentUploadRequest, LegalContentUploadResponse
from ...repositories.content import update_content_pdf_metadata

router = APIRouter()

EU_COUNTRY_CODES = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}

LEGAL_DOCUMENT_KEYS = {
    "privacy-policy": PRIVACY_POLICY_KEY,
    "terms-condition": TERMS_CONDITION_KEY,
    "about-us": ABOUT_US_KEY,
}


def _legal_content_key(document_key: str) -> str:
    key = LEGAL_DOCUMENT_KEYS.get(str(document_key or "").strip().lower())
    if not key:
        raise HTTPException(status_code=404, detail="Legal content document not found")
    return key


def _safe_legal_filename(value: str | None, fallback: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._ -]", "", str(value or "").strip()).strip()
    return name[:180] or fallback


async def _upload_legal_asset(
    *,
    payload: LegalContentUploadRequest,
    admin_user: dict,
    folder_name: str,
    allowed_types: dict[str, str],
    invalid_type_message: str,
    max_size_bytes: int,
    upload_log_label: str,
) -> str:
    try:
        return await asyncio.to_thread(
            _upload_binary_to_s3,
            folder_name,
            str(admin_user["_id"]),
            payload.file_base64,
            payload.mime_type,
            payload.file_name,
            allowed_types=allowed_types,
            invalid_type_message=invalid_type_message,
            invalid_payload_message=f"{upload_log_label.capitalize()} payload is not valid base64",
            max_size_bytes=max_size_bytes,
            upload_log_label=upload_log_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Legal {upload_log_label} upload failed") from exc


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


@router.post("/admin/content/legal-image", response_model=LegalContentUploadResponse)
async def admin_upload_legal_image(
    payload: LegalContentUploadRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> LegalContentUploadResponse:
    url = await _upload_legal_asset(
        payload=payload,
        admin_user=admin_user,
        folder_name="legal-images",
        allowed_types={
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        },
        invalid_type_message="Only JPEG, PNG, WEBP, and GIF images are supported",
        max_size_bytes=8 * 1024 * 1024,
        upload_log_label="image",
    )
    return LegalContentUploadResponse(
        url=url,
        filename=_safe_legal_filename(payload.file_name, "legal-image"),
    )


@router.post("/admin/content/{document_key}/pdf", response_model=LegalContentUploadResponse)
async def admin_upload_legal_pdf(
    document_key: str,
    payload: LegalContentUploadRequest,
    admin_user: dict = Depends(_require_admin_user),
) -> LegalContentUploadResponse:
    content_key = _legal_content_key(document_key)
    normalized_mime = str(payload.mime_type or "").strip().lower()
    if normalized_mime != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    url = await _upload_legal_asset(
        payload=payload,
        admin_user=admin_user,
        folder_name="legal-pdfs",
        allowed_types={"application/pdf": ".pdf"},
        invalid_type_message="Only PDF files are supported",
        max_size_bytes=20 * 1024 * 1024,
        upload_log_label="pdf",
    )
    filename = _safe_legal_filename(payload.file_name, "legal-document.pdf")
    await update_content_pdf_metadata(key=content_key, pdf_url=url, pdf_filename=filename)
    return LegalContentUploadResponse(url=url, filename=filename)


@router.delete("/admin/content/{document_key}/pdf")
async def admin_remove_legal_pdf(
    document_key: str,
    _: dict = Depends(_require_admin_user),
) -> dict[str, bool]:
    await update_content_pdf_metadata(key=_legal_content_key(document_key), pdf_url="", pdf_filename="")
    return {"removed": True}

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
        pdf_url=payload.pdf_url,
        pdf_filename=payload.pdf_filename,
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
        pdf_url=payload.pdf_url,
        pdf_filename=payload.pdf_filename,
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
        pdf_url=payload.pdf_url,
        pdf_filename=payload.pdf_filename,
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
