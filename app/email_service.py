import smtplib
from email.message import EmailMessage

from .config import settings


def send_verification_email(to_email: str, code: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "Your Victory Fitness verification code"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to_email
    message.set_content(
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
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
