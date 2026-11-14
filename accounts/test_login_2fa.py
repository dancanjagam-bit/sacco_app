"""Regression coverage for member login and the staff 2FA contract."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import OTPRequest


User = get_user_model()


class LoginTwoFactorFlowTests(APITestCase):
    password = "Synthetic-Login-Only123!"

    def setUp(self):
        self.member = User.objects.create_user(
            username="login_member",
            email="member@example.invalid",
            password=self.password,
        )
        self.staff = User.objects.create_user(
            username="login_staff",
            email="staff@example.invalid",
            password=self.password,
            is_staff=True,
        )

    def test_member_login_returns_tokens(self):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"username": self.member.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("requires_2fa", response.data)

    @patch(
        "accounts.services.otp_delivery.send_otp",
        return_value={"status": "unavailable", "reason_code": "email_not_configured"},
    )
    def test_staff_with_unavailable_delivery_gets_retryable_challenge_without_tokens(self, _send):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"username": self.staff.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["requires_2fa"])
        self.assertEqual(response.data["delivery_status"], "unavailable")
        self.assertIn("not configured", response.data["message"])
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertNotIn("code", response.data)

        verify = self.client.post(
            reverse("login-2fa"),
            {"identifier": self.staff.username, "code": "123456"},
            format="json",
        )
        self.assertEqual(verify.status_code, 400)
        self.assertNotIn("access", verify.data)

    @patch(
        "accounts.services.otp_delivery.send_otp",
        return_value={"status": "accepted", "reason_code": ""},
    )
    def test_accepted_staff_challenge_verifies_once(self, _send):
        challenge = self.client.post(
            reverse("token_obtain_pair"),
            {"username": self.staff.username, "password": self.password},
            format="json",
        )
        self.assertEqual(challenge.status_code, 200)
        self.assertTrue(challenge.data["requires_2fa"])
        self.assertEqual(challenge.data["delivery_status"], "accepted")
        self.assertNotIn("access", challenge.data)

        otp = OTPRequest.objects.get(
            user=self.staff,
            purpose="login_2fa",
            used=False,
            delivery_status="accepted",
        )
        verify = self.client.post(
            reverse("login-2fa"),
            {"identifier": self.staff.username, "code": otp.code},
            format="json",
        )

        self.assertEqual(verify.status_code, 200)
        self.assertIn("access", verify.data)
        self.assertIn("refresh", verify.data)
        self.assertTrue(OTPRequest.objects.get(pk=otp.pk).used)

        replay = self.client.post(
            reverse("login-2fa"),
            {"identifier": self.staff.username, "code": otp.code},
            format="json",
        )
        self.assertEqual(replay.status_code, 400)
        self.assertNotIn("access", replay.data)
