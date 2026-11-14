from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase
from members.models import Member
from accounts.models import IDVerification, KYCConsentRecord, KYCSubmission, MemberApproval

User = get_user_model()


class RegistrationTests(APITestCase):

    VALID_PAYLOAD = {
        "username":         "testuser123",
        "password":         "Strongpass1",
        "confirm_password": "Strongpass1",
        "first_name":       "Test",
        "last_name":        "User",
        "email":            "test@example.com",
        "national_id":      "28750187",   # realistic Kenyan NID (7-digit, valid range)
        "phone_number":     "0712345678",
        "gender":           "male",
        "date_of_birth":    "1990-01-01",
        "county":           "Nairobi",
        "address":          "123 Test Street, Nairobi",
    }

    def test_register_creates_user_and_member(self):
        """Successful registration returns 201, creates User and linked Member."""
        response = self.client.post(
            "/api/register/",
            self.VALID_PAYLOAD,
            format="json",
        )

        # Show errors if the request failed (makes debugging easy)
        if response.status_code not in (200, 201):
            self.fail(
                f"Registration returned {response.status_code}. "
                f"Errors: {response.data}"
            )

        self.assertEqual(response.status_code, 201)
        self.assertIn("member_number", response.data)
        self.assertTrue(response.data["member_number"].startswith("SACCO"))

        # User was created
        self.assertTrue(
            User.objects.filter(username=self.VALID_PAYLOAD["username"]).exists()
        )
        user = User.objects.get(username=self.VALID_PAYLOAD["username"])
        self.assertEqual(user.first_name, self.VALID_PAYLOAD["first_name"])
        self.assertEqual(user.last_name,  self.VALID_PAYLOAD["last_name"])
        self.assertEqual(user.email,      self.VALID_PAYLOAD["email"].lower())

        # Member profile was created and linked to user
        self.assertTrue(Member.objects.filter(user=user).exists())
        member = Member.objects.get(user=user)
        self.assertEqual(member.national_id,  self.VALID_PAYLOAD["national_id"])
        self.assertEqual(member.phone_number, "0712345678")
        self.assertEqual(member.county,       "Nairobi")
        self.assertEqual(member.gender,       self.VALID_PAYLOAD["gender"])
        self.assertEqual(member.status,       "inactive")
        self.assertEqual(response.data["membership_status"], "pending_review")
        self.assertEqual(IDVerification.objects.get(user=user).status, "draft")
        self.assertEqual(MemberApproval.objects.filter(applicant=user, decision="pending").count(), 1)
        self.assertEqual(KYCConsentRecord.objects.filter(user=user, purpose="id_verification").count(), 1)

    def test_registration_with_id_document_creates_versioned_submission(self):
        image_data = BytesIO()
        Image.new("RGB", (640, 400), color=(225, 230, 235)).save(image_data, format="PNG")
        image_data.seek(0)
        upload = SimpleUploadedFile(
            "synthetic-id-front.png", image_data.read(), content_type="image/png"
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                "/api/register/",
                {
                    **self.VALID_PAYLOAD,
                    "id_verification_consent": "true",
                    "id_document_front": upload,
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username=self.VALID_PAYLOAD["username"])
        verification = IDVerification.objects.get(user=user)
        submission = KYCSubmission.objects.get(verification=verification, sequence=1)
        self.assertEqual(submission.status, "submitted")
        self.assertTrue(submission.consent_given)
        self.assertTrue(submission.id_document_front.name.startswith("id_documents/submissions/"))
        self.assertEqual(verification.status, "submitted")
        self.assertEqual(User.objects.filter(username=self.VALID_PAYLOAD["username"]).count(), 1)

    def test_duplicate_username_rejected(self):
        """Registering a second account with the same username returns 400."""
        self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")

        payload2 = {**self.VALID_PAYLOAD, "email": "other@example.com", "national_id": "31456789"}
        response = self.client.post("/api/register/", payload2, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_duplicate_national_id_rejected(self):
        """Two members cannot share the same National ID."""
        self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")

        payload2 = {**self.VALID_PAYLOAD, "username": "otheruser", "email": "other2@example.com"}
        response = self.client.post("/api/register/", payload2, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("national_id", response.data)
        self.assertNotIn("already registered", str(response.data.get("national_id", "")).lower())

    def test_registration_retry_does_not_create_duplicate_account_or_review_records(self):
        first = self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")
        second = self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        user = User.objects.get(username=self.VALID_PAYLOAD["username"])
        self.assertEqual(User.objects.filter(username=self.VALID_PAYLOAD["username"]).count(), 1)
        self.assertEqual(Member.objects.filter(user=user).count(), 1)
        self.assertEqual(IDVerification.objects.filter(user=user).count(), 1)
        self.assertEqual(MemberApproval.objects.filter(applicant=user).count(), 1)

    def test_registration_keeps_identity_verification_manual_even_if_provider_credentials_exist(self):
        from accounts.services.id_verification_service import run_id_verification
        from unittest.mock import patch

        with patch("accounts.services.id_verification_service.run_id_verification", wraps=run_id_verification) as provider_path:
            response = self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, 201)
        provider_path.assert_not_called()
        verification = IDVerification.objects.get(user__username=self.VALID_PAYLOAD["username"])
        self.assertEqual(verification.provider, "manual")
        self.assertNotEqual(verification.status, "verified")

    def test_invalid_password_no_number(self):
        """Password without a number is rejected."""
        payload = {**self.VALID_PAYLOAD, "password": "StrongPass", "confirm_password": "StrongPass"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_password_mismatch_rejected(self):
        """Mismatched password and confirm_password is rejected."""
        payload = {**self.VALID_PAYLOAD, "confirm_password": "WrongPass1"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.data)

    def test_invalid_national_id_rejected(self):
        """National ID with letters is rejected."""
        payload = {**self.VALID_PAYLOAD, "national_id": "NID123456", "username": "user2", "email": "u2@test.com"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("national_id", response.data)

    def test_invalid_phone_rejected(self):
        """Non-Kenyan phone number format is rejected."""
        payload = {**self.VALID_PAYLOAD, "phone_number": "1234567890", "username": "user3", "email": "u3@test.com", "national_id": "25678901"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone_number", response.data)

    def test_underage_rejected(self):
        """Members under 18 are rejected."""
        from datetime import date, timedelta
        dob = (date.today() - timedelta(days=365*17)).isoformat()
        payload = {**self.VALID_PAYLOAD, "date_of_birth": dob, "username": "user4", "email": "u4@test.com", "national_id": "31234567"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_of_birth", response.data)

    def test_invalid_county_rejected(self):
        """A county not in Kenya's 47 counties is rejected."""
        payload = {**self.VALID_PAYLOAD, "county": "London", "username": "user5", "email": "u5@test.com", "national_id": "34567890"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("county", response.data)
