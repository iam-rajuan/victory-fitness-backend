from datetime import datetime, timezone

from ..models import AboutUsResponse, PrivacyPolicyResponse, TermsConditionResponse
from ..utils.datetime import as_utc
from ..utils.html import html_to_plain_text
from ..utils.storage_urls import canonicalize_s3_url, canonicalize_s3_urls_in_html


def serialize_privacy_policy_record(
    record: dict,
    *,
    key: str,
    default_title: str,
) -> PrivacyPolicyResponse:
    versions = [dict(item) for item in (record.get("versions") or []) if isinstance(item, dict)]
    published_id = str(record.get("published_version_id") or "")
    current = next((item for item in versions if str(item.get("id") or "") == published_id), None) or (versions[-1] if versions else {})
    html_content = canonicalize_s3_urls_in_html(current.get("html_content") or record.get("html_content") or "")
    plain_text = html_to_plain_text(html_content)
    updated_at = as_utc(current.get("published_at") or record.get("updated_at") or datetime.now(timezone.utc))
    return PrivacyPolicyResponse(
        key=key,
        title=str(current.get("title") or record.get("title") or default_title),
        html_content=html_content,
        plain_text=plain_text,
        updated_at=updated_at,
        status=str(current.get("status") or record.get("status") or "Published"),
        version=str(current.get("version") or "v1"),
        version_id=str(current.get("id") or published_id),
        filename=str(current.get("filename") or record.get("filename") or ""),
        applies_to=[str(item) for item in (current.get("applies_to") or record.get("applies_to") or ["ALL"])],
        notification_behavior=str(current.get("notification_behavior") or record.get("notification_behavior") or "silent"),
        published_at=as_utc(current.get("published_at")) if current.get("published_at") else updated_at,
        effective_at=as_utc(current.get("effective_at")) if current.get("effective_at") else updated_at,
        pdf_url=canonicalize_s3_url(current.get("pdf_url") or record.get("pdf_url") or ""),
        pdf_filename=str(current.get("pdf_filename") or record.get("pdf_filename") or ""),
        versions=versions,
    )


def serialize_terms_condition_record(
    record: dict,
    *,
    key: str,
    default_title: str,
) -> TermsConditionResponse:
    versions = [dict(item) for item in (record.get("versions") or []) if isinstance(item, dict)]
    published_id = str(record.get("published_version_id") or "")
    current = next((item for item in versions if str(item.get("id") or "") == published_id), None) or (versions[-1] if versions else {})
    html_content = canonicalize_s3_urls_in_html(current.get("html_content") or record.get("html_content") or "")
    plain_text = html_to_plain_text(html_content)
    updated_at = as_utc(current.get("published_at") or record.get("updated_at") or datetime.now(timezone.utc))
    return TermsConditionResponse(
        key=key,
        title=str(current.get("title") or record.get("title") or default_title),
        html_content=html_content,
        plain_text=plain_text,
        updated_at=updated_at,
        status=str(current.get("status") or record.get("status") or "Published"),
        version=str(current.get("version") or "v1"),
        version_id=str(current.get("id") or published_id),
        filename=str(current.get("filename") or record.get("filename") or ""),
        applies_to=[str(item) for item in (current.get("applies_to") or record.get("applies_to") or ["ALL"])],
        notification_behavior=str(current.get("notification_behavior") or record.get("notification_behavior") or "silent"),
        published_at=as_utc(current.get("published_at")) if current.get("published_at") else updated_at,
        effective_at=as_utc(current.get("effective_at")) if current.get("effective_at") else updated_at,
        pdf_url=canonicalize_s3_url(current.get("pdf_url") or record.get("pdf_url") or ""),
        pdf_filename=str(current.get("pdf_filename") or record.get("pdf_filename") or ""),
        versions=versions,
    )


def serialize_about_us_record(
    record: dict,
    *,
    key: str,
    default_title: str,
) -> AboutUsResponse:
    versions = [dict(item) for item in (record.get("versions") or []) if isinstance(item, dict)]
    published_id = str(record.get("published_version_id") or "")
    current = next((item for item in versions if str(item.get("id") or "") == published_id), None) or (versions[-1] if versions else {})
    html_content = canonicalize_s3_urls_in_html(current.get("html_content") or record.get("html_content") or "")
    plain_text = html_to_plain_text(html_content)
    updated_at = as_utc(current.get("published_at") or record.get("updated_at") or datetime.now(timezone.utc))
    return AboutUsResponse(
        key=key,
        title=str(current.get("title") or record.get("title") or default_title),
        html_content=html_content,
        plain_text=plain_text,
        updated_at=updated_at,
        status=str(current.get("status") or record.get("status") or "Current"),
        version=str(current.get("version") or "v1"),
        version_id=str(current.get("id") or published_id),
        filename=str(current.get("filename") or record.get("filename") or ""),
        applies_to=[str(item) for item in (current.get("applies_to") or record.get("applies_to") or ["ALL"])],
        notification_behavior=str(current.get("notification_behavior") or record.get("notification_behavior") or "silent"),
        published_at=as_utc(current.get("published_at")) if current.get("published_at") else updated_at,
        effective_at=as_utc(current.get("effective_at")) if current.get("effective_at") else updated_at,
        pdf_url=canonicalize_s3_url(current.get("pdf_url") or record.get("pdf_url") or ""),
        pdf_filename=str(current.get("pdf_filename") or record.get("pdf_filename") or ""),
        versions=versions,
    )
