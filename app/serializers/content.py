from datetime import datetime, timezone

from ..models import AboutUsResponse, PrivacyPolicyResponse, TermsConditionResponse
from ..utils.datetime import as_utc
from ..utils.html import html_to_plain_text


def serialize_privacy_policy_record(
    record: dict,
    *,
    key: str,
    default_title: str,
) -> PrivacyPolicyResponse:
    html_content = str(record.get("html_content") or "")
    plain_text = html_to_plain_text(html_content)
    updated_at = as_utc(record.get("updated_at") or datetime.now(timezone.utc))
    return PrivacyPolicyResponse(
        key=key,
        title=str(record.get("title") or default_title),
        html_content=html_content,
        plain_text=plain_text,
        updated_at=updated_at,
    )


def serialize_terms_condition_record(
    record: dict,
    *,
    key: str,
    default_title: str,
) -> TermsConditionResponse:
    html_content = str(record.get("html_content") or "")
    plain_text = html_to_plain_text(html_content)
    updated_at = as_utc(record.get("updated_at") or datetime.now(timezone.utc))
    return TermsConditionResponse(
        key=key,
        title=str(record.get("title") or default_title),
        html_content=html_content,
        plain_text=plain_text,
        updated_at=updated_at,
    )


def serialize_about_us_record(
    record: dict,
    *,
    key: str,
    default_title: str,
) -> AboutUsResponse:
    html_content = str(record.get("html_content") or "")
    plain_text = html_to_plain_text(html_content)
    updated_at = as_utc(record.get("updated_at") or datetime.now(timezone.utc))
    return AboutUsResponse(
        key=key,
        title=str(record.get("title") or default_title),
        html_content=html_content,
        plain_text=plain_text,
        updated_at=updated_at,
    )
