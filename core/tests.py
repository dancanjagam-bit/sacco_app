from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Savings, Loan, Transaction

User = get_user_model()


class CoreWorkflowTests(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="member_user",
            password="memberpass",
            email="member@example.com",
        )
        self.admin = User.objects.create_superuser(
            username="admin_user",
            password="adminpass",
            email="admin@example.com",
        )

    def test_deposit_apply_approve_and_repay_loan(self):
        self.client.force_authenticate(user=self.member)

        deposit_response = self.client.post(
            "/api/deposit/",
            {"amount": "1000.00"},
            format="json",
        )
        self.assertEqual(deposit_response.status_code, 200)
        self.assertEqual(Savings.objects.filter(user=self.member).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.member, type="deposit").count(), 1)

        loan_response = self.client.post(
            "/api/loan/apply/",
            {"amount": "500.00", "repayment_months": 12},
            format="json",
        )
        self.assertEqual(loan_response.status_code, 200)
        loan_id = loan_response.data["loan_id"]

        loan = Loan.objects.get(id=loan_id)
        self.assertEqual(loan.amount, Decimal("500.00"))
        self.assertEqual(loan.status, "pending")

        self.client.force_authenticate(user=self.admin)
        approve_response = self.client.post(f"/api/admin/loan/{loan_id}/approve/")
        self.assertEqual(approve_response.status_code, 200)

        loan.refresh_from_db()
        self.assertEqual(loan.status, "approved")
        self.assertEqual(loan.balance, Decimal("550.00"))
        self.assertEqual(Transaction.objects.filter(user=self.member, type="loan").count(), 1)

        self.client.force_authenticate(user=self.member)
        repay_response = self.client.post(
            f"/api/loan/{loan_id}/repay/",
            {"amount": "200.00"},
            format="json",
        )
        self.assertEqual(repay_response.status_code, 200)

        loan.refresh_from_db()
        self.assertEqual(loan.balance, Decimal("350.00"))
        self.assertEqual(Transaction.objects.filter(user=self.member, type="repayment").count(), 1)
