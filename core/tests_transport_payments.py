import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounting.models import JournalEntry, LedgerAccount
from accounts.models import AuditLog, StaffDutyAssignment, StaffRoleGrant
from core.services.daraja_service import DarajaError
from core.services.transport_accounting import CLEARING_KEY, RECEIPT_ACCOUNT_KEYS, RECEIPT_SOURCE
from core.services.transport_payments import stk_callback_tag
from core.transport_models import (
    CrewAssignment, TransportPayment, TransportPaymentReviewEvent, TransportRemittance, TransportRole,
    TransportRoute, Vehicle,
)


@override_settings(
    MPESA_CONSUMER_KEY="synthetic", MPESA_CONSUMER_SECRET="synthetic", MPESA_PASSKEY="synthetic",
    MPESA_CALLBACK_BASE_URL="https://example.invalid", MPESA_ENV="sandbox", TRANSPORT_C2B_CALLBACK_TOKEN="",
)
class TransportPaymentTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model()
        cls.driver = user.objects.create_user(username="synthetic-payment-driver")
        cls.clerk = user.objects.create_user(username="synthetic-payment-clerk")
        cls.treasurer = user.objects.create_user(username="synthetic-payment-treasurer")
        cls.manager = user.objects.create_user(username="synthetic-payment-manager", is_superuser=True)
        TransportRole.objects.create(user=cls.driver, role="driver")
        vehicle = Vehicle.objects.create(registration="TEST-PAYMENT", owner=cls.driver)
        route = TransportRoute.objects.create(name="Synthetic payment route")
        cls.assignment = CrewAssignment.objects.create(vehicle=vehicle, route=route, driver=cls.driver,
            starts_at=timezone.now(), status="active")
        cls.remittance = TransportRemittance.objects.create(
            requested_by=cls.driver, assignment=cls.assignment, shift=cls.assignment.shift,
            vehicle=vehicle, route=route, amount="100.00", idempotency_key=uuid.uuid4(),
        )
        for clerk in (cls.clerk, cls.driver):
            StaffRoleGrant.objects.create(user=clerk, role="clerk", granted_by=cls.manager, reason="Synthetic test scope")
            StaffDutyAssignment.objects.create(staff=clerk, duty="cash_handover", vehicle=vehicle,
                assigned_by=cls.manager, reason="Synthetic test scope")
        StaffRoleGrant.objects.create(user=cls.treasurer, role="treasurer", granted_by=cls.manager,
            reason="Synthetic test role")
        for method in ("cash", "stk"):
            LedgerAccount.objects.create(code=method, name=f"Synthetic {method} receipts", classification="asset",
                normal_balance="debit", system_key=RECEIPT_ACCOUNT_KEYS[method])
        LedgerAccount.objects.create(code="clear", name="Synthetic receipts clearing", classification="liability",
            normal_balance="credit", system_key=CLEARING_KEY)

    def setUp(self):
        self.client.force_authenticate(self.driver)
        self.provider = APIClient()
        self.remittance_url = f"/api/transport/remittances/{self.remittance.public_id}/"
        self.queue_url = "/api/transport/payment-queue/"

    def stk_payload(self, *, checkout="ws-test-checkout", merchant="test-merchant", receipt="TEST-STK", code=0):
        return {"Body": {"stkCallback": {
            "CheckoutRequestID": checkout, "MerchantRequestID": merchant, "ResultCode": code,
            "CallbackMetadata": {"Item": [
                {"Name": "Amount", "Value": 100}, {"Name": "PhoneNumber", "Value": 254712345678},
                {"Name": "MpesaReceiptNumber", "Value": receipt},
            ]},
        }}}

    def start_stk(self, **overrides):
        body = {"amount": "100.00", "phone": "0712345678", "client_key": str(uuid.uuid4())} | overrides
        return self.client.post(self.remittance_url + "stk/", body, format="json")

    def test_signed_callback_can_arrive_before_provider_response_and_posts_once(self):
        callback_url = ""

        def provider_request(**kwargs):
            nonlocal callback_url
            attempt = TransportPayment.objects.get()
            self.assertEqual(attempt.remittance_id, self.remittance.pk)
            self.assertEqual(attempt.status, "pending")
            self.assertIsNone(attempt.mpesa_transaction_id)
            callback_url = "/api/payments/mpesa/" + kwargs["callback_tag"] + "/"
            payload = self.stk_payload()
            self.assertEqual(self.provider.post(callback_url, payload, format="json").status_code, 200)
            return {"CheckoutRequestID": "ws-test-checkout", "MerchantRequestID": "test-merchant"}

        key = str(uuid.uuid4())
        with patch("core.services.daraja_service.initiate_stk_push", side_effect=provider_request) as initiate:
            self.assertEqual(self.start_stk(client_key=key).data["status"], "confirmed")
            replay = self.start_stk(client_key=key)
            self.assertTrue(replay.data["duplicate"])
            self.assertEqual(self.start_stk(client_key=key, phone="0722222222").status_code, 409)
            self.assertEqual(initiate.call_count, 1)
        self.assertEqual(self.provider.post(callback_url, self.stk_payload(), format="json").status_code, 200)
        self.assertEqual(TransportPayment.objects.get().received_amount, Decimal("100.00"))
        self.assertEqual(JournalEntry.objects.filter(source_type=RECEIPT_SOURCE).count(), 1)

    def test_uncertain_attempt_blocks_retry_and_accepts_late_signed_result(self):
        with patch("core.services.daraja_service.initiate_stk_push", side_effect=DarajaError("timeout")) as initiate:
            attempt = self.start_stk()
            self.assertEqual(attempt.status_code, 202)
            self.assertEqual(attempt.data["status"], "needs_review")
            self.assertEqual(self.start_stk().status_code, 409)
            self.assertEqual(initiate.call_count, 1)
        payment = TransportPayment.objects.get(pk=attempt.data["payment_id"])
        callback_url = "/api/payments/mpesa/" + stk_callback_tag(payment) + "/"
        wrong_url = callback_url[:-2] + ("A" if callback_url[-2] != "A" else "B") + "/"
        self.provider.post(wrong_url, self.stk_payload(), format="json")
        payment.refresh_from_db()
        self.assertIsNone(payment.received_amount)
        self.provider.post(callback_url, self.stk_payload(code=1032), format="json")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "failed")
        self.provider.post(callback_url, self.stk_payload(), format="json")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "confirmed")
        self.assertEqual(TransportPaymentReviewEvent.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.filter(source_type=RECEIPT_SOURCE).count(), 1)

    def test_cash_requires_a_different_assigned_clerk_and_posts_counted_amount(self):
        key = str(uuid.uuid4())
        payload = {"amount": "90.00", "client_key": key}
        cash = self.client.post(self.remittance_url + "cash/", payload, format="json")
        self.assertEqual(cash.status_code, 201)
        self.assertIsNone(cash.data["received_amount"])
        self.assertFalse(JournalEntry.objects.exists())
        self.assertEqual(self.start_stk(client_key=key, amount="90.00").status_code, 409)
        confirmation = {"payment_id": cash.data["id"], "confirm": True, "received_amount": "85.25",
            "reason": "Synthetic cash counted at clerk desk"}
        self.assertEqual(self.client.post(self.queue_url, confirmation, format="json").status_code, 403)
        self.client.force_authenticate(self.clerk)
        self.assertTrue(self.client.get(self.queue_url).data[0]["can_confirm_cash"])
        self.assertEqual(self.client.post(self.queue_url, confirmation | {"received_amount": "85.251"}, format="json").status_code, 400)
        confirmed = self.client.post(self.queue_url, confirmation, format="json")
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.data["status"], "needs_review")
        self.assertEqual(confirmed.data["received_amount"], "85.25")
        self.assertEqual(self.client.post(self.queue_url, confirmation, format="json").status_code, 409)
        self.client.force_authenticate(self.treasurer)
        resolved = self.client.post(self.queue_url, {"payment_id": cash.data["id"], "resolve": True,
            "reason": "Counted amount reconciled to signed handover evidence"}, format="json")
        self.assertEqual(resolved.data["status"], "confirmed")
        self.assertTrue(AuditLog.objects.filter(target=f"Transport payment #{cash.data['id']}").exists())
        self.assertEqual(JournalEntry.objects.filter(source_type=RECEIPT_SOURCE).count(), 1)

    @override_settings(TRANSPORT_C2B_CALLBACK_TOKEN="synthetic-secret")
    def test_unmatched_paybill_receipt_matches_by_reference_and_excess_stays_in_review(self):
        path = "/api/payments/mpesa/c2b/confirmation/"
        payload = {"TransID": "TEST-C2B", "TransAmount": "125.05", "BillRefNumber": "TR-MISTYPED"}
        self.assertEqual(self.provider.post(path, payload, format="json").status_code, 403)
        self.assertEqual(self.provider.post(path + "synthetic-secret/", payload, format="json").status_code, 200)
        self.assertEqual(self.provider.post(path + "synthetic-secret/", payload, format="json").status_code, 200)
        payment = TransportPayment.objects.get()
        self.assertEqual(payment.status, "unmatched")
        self.client.force_authenticate(self.treasurer)
        matched = self.client.post(self.queue_url, {"payment_id": payment.pk, "remittance_id": self.remittance.payment_reference,
            "reason": "Synthetic provider statement verified against the shift"}, format="json")
        self.assertEqual(matched.status_code, 200)
        self.assertEqual(matched.data["remittance"], str(self.remittance.public_id))
        self.assertIn("excess", self.client.get(self.queue_url).data[0]["queue_reasons"])
        self.assertEqual(JournalEntry.objects.filter(source_type=RECEIPT_SOURCE).count(), 1)
