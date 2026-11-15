from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import OTPRequest
from members.models import Member
from sacco.notifications import send_otp


ACCEPTED = {"status": "accepted", "reason_code": ""}


@override_settings(RESEND_API_KEY="", AT_USERNAME="live-app")
class PasswordRecoveryDeliveryTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="member_recovery", email="registered@example.invalid", password="Synthetic-only123!"
        )
        Member.objects.create(
            user=self.user, member_number="TEST0001", national_id="28345678",
            phone_number="0712345678", gender="female", date_of_birth=date(1990, 1, 1),
            county="Nairobi", address="Test address",
        )

    def request_code(self, method, identifier=None):
        return self.client.post(
            reverse("forgot-password"),
            {"identifier": identifier or self.user.email.upper(), "method": method},
            format="json",
        )

    @patch("sacco.notifications._send_email", return_value=ACCEPTED)
    def test_registered_email_receives_code_and_can_reset_password(self, send_email):
        response = self.request_code("email")
        self.assertEqual(response.status_code, 200)
        otp = OTPRequest.objects.get(user=self.user)
        self.assertEqual(otp.delivery_status, "accepted")
        address, _, message = send_email.call_args.args
        self.assertEqual(address, self.user.email)
        self.assertRegex(otp.code, r"^[0-9]{6}$")
        self.assertIn(otp.code, message)
        self.assertNotIn(otp.code, str(response.data))
        result = self.client.post(reverse("reset-password"), {
            "identifier": self.user.email,
            "code": otp.code,
            "new_password": "Synthetic-Changed789!",
            "confirm_password": "Synthetic-Changed789!",
        }, format="json")
        self.assertEqual(result.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Synthetic-Changed789!"))

    @patch("sacco.notifications._send_sms", return_value=ACCEPTED)
    def test_registered_phone_receives_code_when_selected(self, send_sms):
        self.assertEqual(self.request_code("phone").status_code, 200)
        otp = OTPRequest.objects.get(user=self.user)
        self.assertEqual(otp.delivery_status, "accepted")
        phone, message = send_sms.call_args.args
        self.assertEqual(phone, self.user.member_profile.phone_number)
        self.assertIn(otp.code, message)

    @patch("sacco.notifications._send_sms", return_value=ACCEPTED)
    def test_unverified_recovery_phone_falls_back_to_registered_phone(self, send_sms):
        self.user.recovery_phone = "0799999999"
        self.user.save(update_fields=["recovery_phone"])
        self.assertEqual(self.request_code("recovery_phone").status_code, 200)
        self.assertEqual(send_sms.call_args.args[0], self.user.member_profile.phone_number)

    @patch("sacco.notifications._send_email", return_value=ACCEPTED)
    def test_unverified_recovery_email_falls_back_to_registered_email(self, send_email):
        self.user.recovery_email = "unverified@example.invalid"
        self.user.save(update_fields=["recovery_email"])
        self.assertEqual(self.request_code("recovery_email").status_code, 200)
        self.assertEqual(send_email.call_args.args[0], self.user.email)

    @patch("sacco.notifications._send_email", return_value=ACCEPTED)
    def test_verified_backup_is_used_when_selected(self, send_email):
        self.user.recovery_email = "backup@example.invalid"
        self.user.recovery_email_verified = True
        self.user.save(update_fields=["recovery_email", "recovery_email_verified"])
        self.assertEqual(self.request_code("recovery_email").status_code, 200)
        self.assertEqual(send_email.call_args.args[0], self.user.recovery_email)

    @patch("sacco.notifications._send_email", return_value={"status": "failed", "reason_code": "provider_error"})
    def test_failure_does_not_reveal_account_or_enable_reset(self, send_email):
        failed = self.request_code("email")
        unknown = self.request_code("email", "unknown@example.invalid")
        self.assertEqual(failed.data, unknown.data)
        send_email.assert_called_once()
        otp = OTPRequest.objects.get(user=self.user)
        self.assertEqual(otp.delivery_status, "failed")
        response = self.client.post(reverse("verify-otp"), {
            "identifier": self.user.email, "code": otp.code,
        }, format="json")
        self.assertEqual(response.status_code, 400)


@override_settings(RESEND_API_KEY="test-key", RESEND_FROM_EMAIL="otp@example.invalid")
class HTTPSOTPEmailTests(SimpleTestCase):
    @patch("sacco.notifications.requests.post")
    def test_https_provider_accepts_email_with_code(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"id": "test-message-id"}
        user = Mock(email="registered@example.invalid")

        self.assertEqual(send_otp(user, "123456", "email"), ACCEPTED)
        (url,), options = post.call_args
        self.assertEqual(url, "https://api.resend.com/emails")
        self.assertEqual(options["json"]["to"], [user.email])
        self.assertIn("123456", options["json"]["text"])
        self.assertFalse(options["allow_redirects"])
