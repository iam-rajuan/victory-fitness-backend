from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

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

    )

    if not record:

        raise HTTPException(status_code=500, detail="Privacy policy could not be saved")

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

    )

    if not record:

        raise HTTPException(status_code=500, detail="Terms & Conditions could not be saved")

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

    )

    if not record:

        raise HTTPException(status_code=500, detail="About Us could not be saved")

    return _serialize_about_us_record(record)
