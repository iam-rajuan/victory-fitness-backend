import unittest
from unittest.mock import patch

from app import email_service
from app.config import settings


class EmailServiceTests(unittest.TestCase):
    def test_send_verification_email_uses_resend(self) -> None:
        with patch.object(settings, "resend_api_key", "re_test_key"), patch.object(
            settings,
            "resend_from_email",
            "Victory Fitness <noreply@victoryfitness.de>",
        ), patch.object(email_service.resend.Emails, "send", return_value={"id": "email_123"}) as mocked_send:
            email_service.send_verification_email("user@example.com", "123456")

        mocked_send.assert_called_once()
        params = mocked_send.call_args.args[0]
        self.assertEqual(params["from"], "Victory Fitness <noreply@victoryfitness.de>")
        self.assertEqual(params["to"], ["user@example.com"])
        self.assertEqual(params["subject"], "Your Victory Fitness verification code")
        self.assertIn("Verification code: 123456", params["text"])
        self.assertIn("Verification code: 123456", params["html"])
        self.assertEqual(params["tags"], [{"name": "flow", "value": "verification"}])

    def test_send_password_reset_email_raises_when_resend_not_configured(self) -> None:
        with patch.object(settings, "resend_api_key", ""), patch.object(settings, "resend_from_email", ""):
            with self.assertRaises(RuntimeError) as context:
                email_service.send_password_reset_email("user@example.com", "654321")

        self.assertEqual(str(context.exception), "Resend is not configured")

    def test_send_trial_campaign_email_skips_without_recipient(self) -> None:
        with patch.object(settings, "resend_api_key", "re_test_key"), patch.object(
            settings,
            "resend_from_email",
            "Victory Fitness <noreply@victoryfitness.de>",
        ), patch.object(email_service.resend.Emails, "send") as mocked_send:
            email_service.send_trial_campaign_email("", "Ava", 3, "Keep going", "Use one more feature today.")

        mocked_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
