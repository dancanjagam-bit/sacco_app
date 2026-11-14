from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounting.models import JournalEntry, LedgerAccount
from accounts.models import StaffRoleGrant
from accounts.welfare_models import WelfarePayout, WelfareRequest
from members.models import Member


class WelfarePayoutTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.manager = users.create_user(username="test-payout-welfare-manager", is_superuser=True)
        cls.treasurer = users.create_user(username="test-payout-welfare-treasurer")
        cls.member = users.create_user(username="test-payout-welfare-member", is_member=True)
        StaffRoleGrant.objects.create(user=cls.treasurer, role="treasurer", granted_by=cls.manager, reason="Test")
        member = Member.objects.create(
            user=cls.member, member_number="WELTEST", national_id="WELTEST", phone_number="+254711000001",
            gender="other", date_of_birth="1990-01-01", county="Test", address="Test", status="active",
        )
        cls.case = WelfareRequest.objects.create(
            member=member, category="test", description="Synthetic welfare request",
            requested_amount="100.25", approved_amount="100.25", status="approved",
        )
        cls.payout = WelfarePayout.objects.create(request=cls.case)
        LedgerAccount.objects.create(
            code="WB-TEST", name="Test benefits", classification="expense", normal_balance="debit",
            system_key="welfare_benefits",
        )
        LedgerAccount.objects.create(
            code="WC-TEST", name="Test disbursement cash", classification="asset", normal_balance="debit",
            system_key="welfare_payout_cash",
        )

    def setUp(self):
        self.start = reverse("welfare-start-payout", args=[self.case.pk])
        self.refresh = reverse("welfare-refresh-payout", args=[self.case.pk])
        self.client.force_authenticate(self.treasurer)

    def result(self, **overrides):
        return {
            "outcome": "confirmed", "client_reference": f"welfare-payout:{self.payout.pk}",
            "provider_reference": "TEST-REFERENCE", "transaction_id": "TEST-RECEIPT",
            "amount": "100.25", "destination": "+254711000001", **overrides,
        }

    def test_provider_disabled_and_member_denied_without_posting(self):
        with patch("accounts.welfare_views.get_welfare_provider", return_value=None):
            self.assertEqual(self.client.post(self.start).status_code, 503)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(self.start).status_code, 403)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, "awaiting_provider")
        self.assertFalse(JournalEntry.objects.exists())

    def test_pending_then_confirmed_is_idempotent_and_balanced(self):
        provider = Mock()
        def submit(**payload):
            self.payout.refresh_from_db()
            self.assertEqual(self.payout.status, "pending")
            self.assertEqual(payload["amount"], Decimal("100.25"))
            return {"provider_reference": "TEST-REFERENCE"}
        provider.submit.side_effect = submit
        provider.status.return_value = self.result()
        with patch("accounts.welfare_views.get_welfare_provider", return_value=provider):
            self.assertEqual(self.client.post(self.start).data["status"], "pending")
            self.assertEqual(self.client.post(self.start).data["status"], "pending")
            self.assertFalse(JournalEntry.objects.exists())
            self.assertEqual(self.client.post(self.refresh).data["status"], "confirmed")
            self.assertEqual(self.client.post(self.refresh).data["status"], "confirmed")
        provider.submit.assert_called_once()
        provider.status.assert_called_once()
        entry = JournalEntry.objects.get(source_type="welfare_payout")
        self.assertEqual(sum(row.debit for row in entry.lines.all()), Decimal("100.25"))
        self.assertEqual(sum(row.credit for row in entry.lines.all()), Decimal("100.25"))

    def test_timeout_recovers_by_client_reference_and_rejects_amount_mismatch(self):
        provider = Mock()
        provider.submit.side_effect = TimeoutError()
        provider.status.side_effect = [self.result(amount="100.00"), self.result()]
        with patch("accounts.welfare_views.get_welfare_provider", return_value=provider):
            self.assertEqual(self.client.post(self.start).data["status"], "uncertain")
            self.assertEqual(self.client.post(self.refresh).status_code, 409)
            self.assertFalse(JournalEntry.objects.exists())
            self.assertEqual(self.client.post(self.refresh).data["status"], "confirmed")
        provider.submit.assert_called_once()

    def test_queue_sums_multiple_amounts_and_list_uses_role_permission(self):
        case = WelfareRequest.objects.create(
            member=self.case.member, category="test", description="Another synthetic claim",
            requested_amount="2.75", approved_amount="2.75", status="approved",
        )
        WelfarePayout.objects.create(request=case)
        response = self.client.get(reverse("welfare-treasurer-queue"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["total_pending_amount"]), Decimal("103.00"))
