import unittest

from pydantic import ValidationError

from app.models import CoachingApplicationCreateRequest, RegisterRequest


class PhoneValidationTests(unittest.TestCase):
    def test_register_request_accepts_e164_number(self) -> None:
        payload = RegisterRequest(
            name="Jane",
            surname="Doe",
            email="jane@example.com",
            mobile="+233241234567",
            password="strongpass123",
        )

        self.assertEqual(payload.mobile, "+233241234567")

    def test_register_request_rejects_non_e164_number(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(
                name="Jane",
                surname="Doe",
                email="jane@example.com",
                mobile="0241234567",
                password="strongpass123",
            )

    def test_application_request_normalizes_optional_phone_number(self) -> None:
        payload = CoachingApplicationCreateRequest(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone_number="+233 24 123 4567",
            goal="Build muscle",
            obstacle="Consistency",
            investment="Yes",
            commitment="Very committed",
            injury="No",
            agreement_accepted=True,
        )

        self.assertEqual(payload.phone_number, "+233241234567")

    def test_application_request_rejects_invalid_optional_phone_number(self) -> None:
        with self.assertRaises(ValidationError):
            CoachingApplicationCreateRequest(
                first_name="Jane",
                last_name="Doe",
                email="jane@example.com",
                phone_number="0241234567",
                goal="Build muscle",
                obstacle="Consistency",
                investment="Yes",
                commitment="Very committed",
                injury="No",
                agreement_accepted=True,
            )


if __name__ == "__main__":
    unittest.main()
