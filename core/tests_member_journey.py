from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from members.models import Member
from accounts.models import Notification, StaffProfile
from .models import FosaWithdrawal, Loan, MpesaTransaction, Savings, SavingsDividend, Transaction
from .transport_models import TransportRole

User = get_user_model()


class MemberJourneyApiTests(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="journey_member", password="TestPass123!", first_name="Journey", last_name="Member",
        )
        self.other = User.objects.create_user(username="other_journey_member", password="TestPass123!")
        Member.objects.create(
            user=self.member, member_number="NWJOURNEY1", national_id="99123456",
            phone_number="0712345678", gender="other", date_of_birth=date(1990, 1, 1),
            county="Nairobi", address="Test only",
        )

    def test_dashboard_and_all_time_summary_use_member_scoped_posted_ledger_totals(self):
        Transaction.objects.create(user=self.member, type="deposit", amount=Decimal("10.25"), note="first")
        Transaction.objects.create(user=self.member, type="deposit", amount=Decimal("20.50"), note="second")
        Transaction.objects.create(user=self.other, type="deposit", amount=Decimal("900.00"), note="private")
        Savings.objects.create(user=self.member, amount=Decimal("30.75"), account_type="fosa")

        self.client.force_authenticate(self.member)
        dashboard = self.client.get("/api/dashboard/")
        transactions = self.client.get("/api/transactions/")

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(Decimal(str(dashboard.data["total_deposits"])), Decimal("30.75"))
        self.assertEqual(Decimal(str(dashboard.data["fosa_savings"])), Decimal("30.75"))
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(transactions.data["summary"]["deposits"], "30.75")
        self.assertEqual(transactions.data["summary"]["count"], 2)
        self.assertNotIn("private", [row["note"] for row in transactions.data["results"]])

    def test_dashboard_returns_server_computed_member_and_transport_workspaces(self):
        self.client.force_authenticate(self.member)
        member_response = self.client.get("/api/dashboard/")
        self.assertEqual(member_response.status_code, 200)
        self.assertIn("accounts.read_own", member_response.data["permissions"])
        self.assertEqual([workspace["id"] for workspace in member_response.data["workspaces"]], ["member"])

        TransportRole.objects.create(user=self.member, role="owner")
        TransportRole.objects.create(user=self.member, role="driver")
        crew_response = self.client.get("/api/dashboard/")
        self.assertIn("transport.read_owned", crew_response.data["permissions"])
        self.assertIn("transport.read_assigned", crew_response.data["permissions"])
        self.assertEqual(
            [workspace["id"] for workspace in crew_response.data["workspaces"]],
            ["member", "crew", "owner"],
        )
        self.assertIn("transport.read_owned", crew_response.data["permissions"])

    def test_navigation_permissions_follow_existing_staff_guards_not_role_labels(self):
        from accounts.access import access_snapshot

        secretary = User.objects.create_user(username="nav_secretary", password="TestPass123!", is_staff=True)
        StaffProfile.objects.create(user=secretary, role="secretary", status="active")
        secretary_access = access_snapshot(secretary)
        self.assertIn("staff.console", secretary_access["permissions"])
        self.assertIn("transport.manage", secretary_access["permissions"])
        self.assertIn("payments.reconcile", secretary_access["permissions"])
        self.assertIn("kyc.review", secretary_access["permissions"])
        self.assertIn("staff", [workspace["id"] for workspace in secretary_access["workspaces"]])
        self.assertNotIn("staff.manage", secretary_access["permissions"])

        accountant = User.objects.create_user(username="nav_accountant", password="TestPass123!", is_staff=True)
        StaffProfile.objects.create(user=accountant, role="accountant", status="active")
        accountant_access = access_snapshot(accountant)
        self.assertIn("payments.reconcile", accountant_access["permissions"])
        self.assertNotIn("transport.manage", accountant_access["permissions"])
        self.assertNotIn("staff.manage", accountant_access["permissions"])

        titled_chairman = User.objects.create_user(username="nav_chair", password="TestPass123!")
        StaffProfile.objects.create(user=titled_chairman, role="chairman", status="active")
        chairman_access = access_snapshot(titled_chairman)
        self.assertNotIn("staff.console", chairman_access["permissions"])
        self.assertNotIn("transport.manage", chairman_access["permissions"])
        self.assertNotIn("staff.manage", chairman_access["permissions"])

    def test_transaction_filters_reject_invalid_type_dates_and_reversed_ranges(self):
        self.client.force_authenticate(self.member)
        for query in (
            "?from=not-a-date",
            "?type=not-a-transaction-type",
            "?from=2026-12-02&to=2026-12-01",
        ):
            with self.subTest(query=query):
                response = self.client.get("/api/transactions/" + query)
                self.assertEqual(response.status_code, 400)

    def test_member_read_endpoints_return_scoped_contracts_and_separate_balance_components(self):
        Savings.objects.create(user=self.member, account_type="bosa", amount=Decimal("1200.00"))
        Savings.objects.create(user=self.member, account_type="fosa", amount=Decimal("850.00"))
        Savings.objects.create(user=self.member, account_type="bosa", amount=Decimal("50.00"))
        own_transaction = Transaction.objects.create(
            user=self.member, type="deposit", amount=Decimal("850.00"), note="synthetic deposit",
        )
        Transaction.objects.create(user=self.other, type="deposit", amount=Decimal("900.00"), note="private entry")
        loan = Loan.objects.create(
            user=self.member, amount=Decimal("5000.00"), interest=Decimal("10.00"),
            repayment_months=3, balance=Decimal("5500.00"), status="approved",
        )
        FosaWithdrawal.objects.create(
            user=self.member, amount=Decimal("100.00"), destination_type="mpesa",
            destination_phone="254700000001", client_request_id="5c91aa44-468d-4788-8375-e74e8f6780d3",
            status="pending",
        )
        SavingsDividend.objects.create(
            user=self.member, year=2025, rate=Decimal("8.00"),
            savings_balance=Decimal("1200.00"), amount=Decimal("96.00"),
        )
        own_notice = Notification.objects.create(user=self.member, title="Account update", message="Synthetic only")
        Notification.objects.create(user=self.other, title="Private update", message="Do not expose")
        self.client.force_authenticate(self.member)

        paths = {
            "dashboard": "/api/dashboard/",
            "collateral": "/api/collateral/status/",
            "withdrawals": "/api/withdrawals/",
            "transactions": "/api/transactions/",
            "dividends": "/api/dividends/",
            "profile": "/api/profile/",
            "notifications": "/api/notifications/",
            "identity": "/api/id-verification/status/",
            "savings_statement": "/api/savings/statement/",
            "schedule": f"/api/loan/{loan.id}/schedule/",
        }
        responses = {name: self.client.get(path) for name, path in paths.items()}
        for name, response in responses.items():
            with self.subTest(endpoint=name):
                self.assertEqual(response.status_code, 200, getattr(response, "data", None))

        self.assertEqual(responses["identity"].data["status"], "not_submitted")
        self.assertEqual(responses["collateral"].data["fosa_withdrawals_pending"], 100.0)
        self.assertEqual(len(responses["withdrawals"].data), 1)
        self.assertEqual(responses["transactions"].data["summary"]["count"], 1)
        self.assertEqual([row["id"] for row in responses["transactions"].data["results"]], [own_transaction.id])
        self.assertEqual([row["id"] for row in responses["notifications"].data["notifications"]], [own_notice.id])
        statement = responses["savings_statement"].data
        self.assertEqual(statement["bosa_balance"], 1250.0)
        self.assertEqual(statement["fosa_balance"], 850.0)
        bosa_rows = [row for row in statement["entries"] if row["account_type"] == "bosa"]
        fosa_rows = [row for row in statement["entries"] if row["account_type"] == "fosa"]
        # The endpoint returns newest first, so the first row carries the
        # latest running balance for that account.
        self.assertEqual(bosa_rows[0]["balance"], 1250.0)
        self.assertEqual(fosa_rows[0]["balance"], 850.0)

    def test_invalid_loan_term_returns_actionable_error_instead_of_server_error(self):
        loan = Loan.objects.create(
            user=self.member, amount=Decimal("1000.00"), balance=Decimal("1100.00"),
            repayment_months=0, status="approved",
        )
        self.client.force_authenticate(self.member)
        response = self.client.get(f"/api/loan/{loan.id}/schedule/")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["code"], "invalid_repayment_schedule")

    @patch("core.payments_views.initiate_stk_push")
    def test_repayment_is_posted_only_after_a_valid_provider_callback_and_is_idempotent(self, stk):
        stk.return_value = {
            "CheckoutRequestID": "ws_CO_member_journey_001",
            "MerchantRequestID": "merchant_journey_001",
        }
        loan = Loan.objects.create(
            user=self.member, amount=Decimal("10000.00"), balance=Decimal("10000.00"),
            status="approved", repayment_months=12,
        )
        self.client.force_authenticate(self.member)

        initiated = self.client.post("/api/payments/mpesa/stk/", {
            "payment_type": "repayment", "amount": "2500", "loan_id": loan.id,
        }, format="json")
        self.assertEqual(initiated.status_code, 200)
        self.assertEqual(loan.balance, Decimal("10000.00"))
        self.assertFalse(Transaction.objects.filter(user=self.member, type="repayment").exists())
        payment = MpesaTransaction.objects.get(checkout_request_id="ws_CO_member_journey_001")
        self.assertEqual(payment.status, "pending")

        callback = {
            "Body": {"stkCallback": {
                "MerchantRequestID": "merchant_journey_001",
                "CheckoutRequestID": "ws_CO_member_journey_001",
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {"Item": [
                    {"Name": "Amount", "Value": 2500},
                    {"Name": "MpesaReceiptNumber", "Value": "QXY123ABC"},
                    {"Name": "TransactionDate", "Value": 20261112101010},
                    {"Name": "PhoneNumber", "Value": 254712345678},
                ]},
            }},
        }
        settled = self.client.post("/api/payments/mpesa/repayment/", callback, format="json")
        duplicate = self.client.post("/api/payments/mpesa/repayment/", callback, format="json")

        self.assertEqual(settled.status_code, 200)
        self.assertEqual(duplicate.status_code, 200)
        loan.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(loan.balance, Decimal("7500.00"))
        self.assertEqual(payment.status, "confirmed")
        self.assertEqual(payment.transaction.type, "repayment")
        self.assertEqual(Transaction.objects.filter(user=self.member, type="repayment").count(), 1)


