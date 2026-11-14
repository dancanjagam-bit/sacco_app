from decimal import Decimal
import uuid
from unittest import TestCase
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounts.models import AuditLog, StaffProfile
from core.models import FosaWithdrawal, Savings, Transaction, WithdrawalCorrectionProposal
from core.services.fosa_payouts import (
    IdempotencyConflict,
    InsufficientPayoutFunds,
    PayoutRejected,
    PayoutTimedOut,
    process_payout_confirmation,
    reserve_and_submit_withdrawal,
)

User = get_user_model()


class FakePayoutProvider:
    def __init__(self, reference="provider-request-1", error=None):
        self.reference = reference
        self.error = error
        self.calls = 0

    def submit(self, withdrawal):
        self.calls += 1
        if self.error:
            raise self.error
        # Even a mistaken immediate-success response is only request acceptance.
        return {"provider_reference": self.reference, "status": "succeeded"}


class FosaPayoutStateMachineTests(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="withdraw_member", password="Pass12345")
        Savings.objects.create(user=self.member, amount=Decimal("500.00"), account_type="fosa")
        self.client_key = uuid.uuid4()

    def submit(self, provider, amount="100.00", key=None, destination="0712345678"):
        return reserve_and_submit_withdrawal(
            user=self.member,
            amount=Decimal(amount),
            destination_type="mpesa",
            destination=destination,
            client_request_id=key or self.client_key,
            provider=provider,
        )

    def test_acceptance_reserves_funds_until_verified_success_and_duplicate_callback_is_safe(self):
        provider = FakePayoutProvider()
        withdrawal, created = self.submit(provider)
        self.assertTrue(created)
        self.assertEqual(withdrawal.status, "pending")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 0)
        self.assertEqual(Transaction.objects.filter(user=self.member, type="withdrawal").count(), 0)
        self.assertEqual(
            Decimal(str(__import__("core.collateral", fromlist=["get_withdrawable_balance"]).get_withdrawable_balance(self.member)["fosa_withdrawable"])),
            Decimal("400.00"),
        )

        settled = process_payout_confirmation(
            provider_reference="provider-request-1", outcome="succeeded",
            provider_transaction_id="MPESA-RECEIPT-1",
        )
        self.assertEqual(settled.status, "succeeded")
        process_payout_confirmation(
            provider_reference="provider-request-1", outcome="succeeded",
            provider_transaction_id="MPESA-RECEIPT-1",
        )
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.member, type="withdrawal").count(), 1)
        self.assertEqual(
            Savings.objects.filter(user=self.member, account_type="fosa").aggregate(total=Sum("amount"))["total"],
            Decimal("400.00"),
        )

    def test_definitive_failure_releases_hold_without_debit(self):
        withdrawal, _ = self.submit(FakePayoutProvider(error=PayoutRejected("rejected")))
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, "failed")
        self.assertEqual(withdrawal.failure_reason_code, "rejected")
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 0)
        self.assertEqual(FosaWithdrawal.objects.filter(user=self.member, status="uncertain").count(), 0)
        self.assertEqual(
            __import__("core.collateral", fromlist=["get_withdrawable_balance"]).get_withdrawable_balance(self.member)["fosa_withdrawable"],
            500.0,
        )

    def test_timeout_holds_funds_no_retry_and_delayed_success_settles_once(self):
        provider = FakePayoutProvider(error=PayoutTimedOut("timeout-reference"))
        withdrawal, _ = self.submit(provider, amount="125.00")
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, "uncertain")
        self.assertEqual(withdrawal.provider_reference, "timeout-reference")
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 0)
        balance = __import__("core.collateral", fromlist=["get_withdrawable_balance"]).get_withdrawable_balance(self.member)
        self.assertEqual(balance["fosa_withdrawals_pending"], 125.0)
        self.assertEqual(balance["fosa_withdrawable"], 375.0)

        repeated, created = self.submit(provider, amount="125.00")
        self.assertFalse(created)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(repeated.pk, withdrawal.pk)
        process_payout_confirmation(
            provider_reference="timeout-reference", outcome="succeeded",
            provider_transaction_id="MPESA-DELAYED-1",
        )
        self.assertEqual(FosaWithdrawal.objects.get(pk=withdrawal.pk).status, "succeeded")
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.member, type="withdrawal").count(), 1)

    def test_insufficient_funds_and_idempotency_conflicts_do_not_call_provider_twice(self):
        provider = FakePayoutProvider()
        with self.assertRaises(InsufficientPayoutFunds):
            self.submit(provider, amount="501.00")
        self.assertEqual(provider.calls, 0)
        self.submit(provider, amount="100.00")
        with self.assertRaises(IdempotencyConflict):
            self.submit(provider, amount="150.00")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(FosaWithdrawal.objects.filter(user=self.member).count(), 1)

    def test_invalid_or_unsupported_destinations_are_rejected(self):
        provider = FakePayoutProvider()
        with self.assertRaises(ValueError):
            self.submit(provider, destination="not-a-phone")
        with self.assertRaises(ValueError):
            reserve_and_submit_withdrawal(
                user=self.member, amount=Decimal("1"), destination_type="cash",
                destination="0712345678", client_request_id=uuid.uuid4(), provider=provider,
            )
        self.assertEqual(provider.calls, 0)


class FosaPayoutAPITests(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="payout_api_member", password="Pass12345")
        Savings.objects.create(user=self.member, amount=Decimal("800.00"), account_type="fosa")

    def test_live_withdrawal_is_disabled_without_provider_and_does_not_debit(self):
        self.client.force_authenticate(self.member)
        response = self.client.post("/api/withdraw/", {
            "amount": "100.00", "account_type": "fosa", "destination_type": "mpesa",
            "destination": "0712345678", "client_request_id": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "unavailable")
        self.assertIn("No funds were debited", response.data["error"])
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 0)
        self.assertEqual(Transaction.objects.filter(user=self.member, type="withdrawal").count(), 0)
        self.assertEqual(FosaWithdrawal.objects.filter(user=self.member).count(), 0)

    def test_unauthorized_request_and_private_withdrawal_list(self):
        unauthorized = self.client.post("/api/withdraw/", {
            "amount": "100.00", "account_type": "fosa", "destination_type": "mpesa",
            "destination": "0712345678", "client_request_id": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(unauthorized.status_code, 401)
        stranger = User.objects.create_user(username="payout_stranger", password="Pass12345")
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/withdrawals/").data, [])
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get("/api/withdrawals/").data, [])

    def test_reconciliation_report_is_staff_only_and_masks_member_identity(self):
        original = Transaction.objects.create(user=self.member, type="withdrawal", amount="50.00", note="FOSA withdrawal")
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/admin/withdrawal-reconciliation/").status_code, 403)
        admin = User.objects.create_superuser("withdrawal_auditor", "auditor@example.invalid", "Pass12345")
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/admin/withdrawal-reconciliation/").status_code, 403)
        from accounts.models import StaffRoleGrant
        StaffRoleGrant.objects.create(user=admin, role="treasurer", granted_by=admin, reason="Synthetic reconciliation duty")
        response = self.client.get("/api/admin/withdrawal-reconciliation/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["withdrawals"][0]["transaction_id"], original.id)
        self.assertEqual(response.data["withdrawals"][0]["status"], "needs_investigation")
        self.assertNotIn(self.member.username, str(response.data))
        if self.member.email:
            self.assertNotIn(self.member.email, str(response.data))

    def test_reversal_requires_accounting_role_and_approval_posts_audited_linked_adjustment(self):
        savings_debit = Savings.objects.create(user=self.member, amount=Decimal("-25.00"), account_type="fosa")
        original = Transaction.objects.create(user=self.member, type="withdrawal", amount=Decimal("25.00"), note="FOSA withdrawal")
        accountant = User.objects.create_user(username="payout_accountant", password="Pass12345", is_staff=True)
        StaffProfile.objects.create(user=accountant, role="accountant", status="active")
        self.client.force_authenticate(accountant)
        proposal = self.client.post("/api/admin/withdrawal-corrections/", {
            "transaction_id": original.id,
            "savings_id": savings_debit.id,
            "reason": "Provider confirmed payout failed.",
            "evidence_reference": "provider-case-123",
        }, format="json")
        self.assertEqual(proposal.status_code, 201)
        self.assertEqual(Savings.objects.filter(user=self.member, amount=Decimal("25.00")).count(), 0)
        item = WithdrawalCorrectionProposal.objects.get(pk=proposal.data["id"])
        self.assertEqual(item.status, "proposed")

        self.assertEqual(self.client.post(f"/api/admin/withdrawal-corrections/{item.id}/decision/", {
            "action": "approve", "reason": "Evidence reviewed and payout was not delivered.",
        }, format="json").status_code, 403)
        second_accountant = User.objects.create_user(username="payout_reviewer", password="Pass12345", is_staff=True)
        StaffProfile.objects.create(user=second_accountant, role="accountant", status="active")
        self.client.force_authenticate(second_accountant)
        decision = self.client.post(f"/api/admin/withdrawal-corrections/{item.id}/decision/", {
            "action": "approve", "reason": "Evidence reviewed and payout was not delivered.",
        }, format="json")
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.data["status"], "approved")
        credit = Savings.objects.get(user=self.member, amount=Decimal("25.00"))
        adjustment = Transaction.objects.get(reverses=original)
        self.assertEqual(adjustment.type, "adjustment")
        self.assertEqual(adjustment.amount, credit.amount)
        self.assertTrue(AuditLog.objects.filter(action="withdrawal_correction_proposed").exists())
        self.assertTrue(AuditLog.objects.filter(action="withdrawal_correction_approve").exists())
