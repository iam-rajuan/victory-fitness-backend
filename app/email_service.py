from __future__ import annotations

import html
import logging
from typing import Any

try:
    import resend
    from resend.exceptions import ResendError
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    class ResendError(Exception):
        pass

    class _ResendEmailsStub:
        @staticmethod
        def send(params: dict[str, Any]) -> dict[str, str]:
            raise ModuleNotFoundError("resend package is not installed")

    class _ResendStub:
        api_key: str = ""
        Emails = _ResendEmailsStub

    resend = _ResendStub()

from .config import settings

logger = logging.getLogger(__name__)


def _is_resend_configured() -> bool:
    return bool(settings.resend_api_key and settings.resend_from_email)


def _render_html_from_text(text_body: str) -> str:
    escaped = html.escape(text_body.strip())
    return f"<pre style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.6;white-space:pre-wrap;\">{escaped}</pre>"


def _extract_message_id(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("id") or "").strip()
    identifier = getattr(response, "id", "")
    return str(identifier or "").strip()


def _send_email(*, flow: str, to_email: str, subject: str, text_body: str) -> None:
    if not _is_resend_configured():
        raise RuntimeError("Resend is not configured")

    resend.api_key = settings.resend_api_key
    params: resend.Emails.SendParams = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": _render_html_from_text(text_body),
        "tags": [{"name": "flow", "value": flow}],
    }

    try:
        response = resend.Emails.send(params)
    except ResendError as exc:
        logger.exception("email_send_failed flow=%s provider=resend error_type=%s", flow, exc.__class__.__name__)
        raise RuntimeError("Email delivery failed") from exc
    except Exception as exc:
        logger.exception("email_send_failed flow=%s provider=resend error_type=%s", flow, exc.__class__.__name__)
        raise RuntimeError("Email delivery failed") from exc

    message_id = _extract_message_id(response)
    logger.info("email_sent flow=%s provider=resend message_id=%s", flow, message_id or "unknown")


def send_verification_email(to_email: str, code: str) -> None:
    _send_email(
        flow="verification",
        to_email=to_email,
        subject="Your Victory Fitness verification code",
        text_body=(
            "Victory Fitness Email Verification\n\n"
            "Hi,\n\n"
            "Thanks for creating your Victory Fitness account. Use the verification "
            "code below to confirm your email address and finish setting up your account.\n\n"
            f"Verification code: {code}\n\n"
            "This code expires in 10 minutes. For your security, do not share this "
            "code with anyone. Victory Fitness will never ask you for this code outside "
            "the app verification screen.\n\n"
            "If you did not create a Victory Fitness account, you can safely ignore "
            "this email.\n\n"
            "Need help?\n"
            "Contact support at office@victorakko.com.\n\n"
            "Victory Fitness"
        ),
    )


def send_password_reset_email(to_email: str, code: str) -> None:
    _send_email(
        flow="password_reset",
        to_email=to_email,
        subject="Your Victory Fitness password reset code",
        text_body=(
            "Victory Fitness Password Reset\n\n"
            "Hi,\n\n"
            "We received a request to reset your Victory Fitness password. Use the code "
            "below to continue.\n\n"
            f"Password reset code: {code}\n\n"
            "This code expires in 10 minutes. If you did not request a password reset, "
            "you can ignore this email.\n\n"
            "Victory Fitness"
        ),
    )


def send_trial_campaign_email(to_email: str, name: str, day: int, title: str, body: str) -> None:
    if not to_email or not _is_resend_configured():
        return

    _send_email(
        flow="trial_campaign",
        to_email=to_email,
        subject=f"Victory Fitness — {title}",
        text_body=(
            f"Hi {name},\n\n"
            f"{body}\n\n"
            "Open Victory Fitness to continue your Gold trial.\n\n"
            f"Day {day} of your 5-day trial"
        ),
    )


def send_retention_email(
    *,
    to_email: str,
    name: str,
    subject: str,
    body: str,
    flow: str = "retention",
) -> None:
    if not to_email or not _is_resend_configured():
        return

    _send_email(
        flow=flow,
        to_email=to_email,
        subject=subject,
        text_body=(
            f"Hi {name},\n\n"
            f"{body}\n\n"
            "Open Victory Fitness to continue your progress."
        ),
    )
