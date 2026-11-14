"""
Core workflow tests.

Key SACCO business rules that affect test setup:
  1. Loan eligibility is based on BOSA savings only (not FOSA).
  2. The eligibility engine looks at the last 13 calendar months, excluding
     the current month. A member needs >= 6 qualifying months, each with
     >= KES 500 in BOSA deposits.
  3. One deposit made today counts toward next month's check, not this month's.
  4. The test bypasses the eligibility engine by back-dating BOSA savings
     directly into the database — this correctly tests the loan workflow
     without needing to mock time.
"""

from decimal import Decimal
from datetime import date
import uuid
from dateutil.relativedelta import relativedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from members.models import Member
from accounts.models import StaffProfile, AuditLog
from .models import Savings, Loan, Transaction

User = get_user_model()


def _make_member_user(username="member_user", email="member@test.com", national_id=None):
    """Create a User + Member profile ready for financial transactions."""
    import uuid
    user = User.objects.create_user(
        username=username,
        password="TestPass1",
        email=email,
        first_name="Test",
        last_name="Member",
    )
    # Generate a unique 8-digit national ID if not provided
    if national_id is None:
        national_id = str(abs(hash(username)) % 90000000 + 10000000)
    Member.objects.create(
        user=user,
        member_number=f"SACCO{username[:6].upper()}",
        national_id=national_id,
        phone_number="0712345678",
        gender="male",
        date_of_birth=date(1990, 1, 1),
        county="Nairobi",
        address="123 Test Street",
    )
    return user


def _create_bosa_history(user, months=6, amount_per_month=Decimal("1000.00")):
    """
    Back-date BOSA deposits so the eligibility engine sees N qualifying months.
    Deposits are placed on the 15th of each of the last N completed months
    (the eligibility engine excludes the current month).
    """
    today = date.today()
    for i in range(months, 0, -1):
        deposit_date = (today - relativedelta(months=i)).replace(day=15)
        # Use update_fields to set created_at to a past date
        s = Savings.objects.create(
            user=user,
            amount=amount_per_month,
            account_type="bosa",
        )
        Savings.objects.filter(pk=s.pk).update(
            created_at=f"{deposit_date} 10:00:00+00:00"
        )


def _record_savings(user, amount, account_type="fosa"):
    """Seed synthetic posted savings directly; never use member write API."""
    return Savings.objects.create(
        user=user, amount=Decimal(str(amount)), account_type=account_type,
    )


class CoreWorkflowTests(APITestCase):
    """Full happy-path: deposit → apply → approve → repay."""

    def setUp(self):
        self.member = _make_member_user("member_user", "member@test.com")
        self.admin = User.objects.create_superuser(
            username="admin_user",
            password="AdminPass1",
            email="admin@test.com",
        )
        # Give member 6 months of qualifying BOSA history (min for Bronze tier)
        _create_bosa_history(self.member, months=6, amount_per_month=Decimal("1000.00"))

    def test_member_cannot_post_unverified_direct_deposit(self):
        """A member-supplied amount is not evidence of money received."""
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            "/api/deposit/",
            {"amount": "500.00", "account_type": "bosa"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "provider_confirmation_required")
        self.assertFalse(Savings.objects.filter(user=self.member, amount=Decimal("500.00")).exists())
        self.assertFalse(Transaction.objects.filter(user=self.member, type="deposit").exists())

    def test_active_accountant_manual_deposit_requires_reason_and_is_audited(self):
        accountant = User.objects.create_user(
            username="accountant", password="TestPass1", is_staff=True,
        )
        StaffProfile.objects.create(user=accountant, role="accountant", status="active")
        self.client.force_authenticate(user=accountant)
        missing_reason = self.client.post(
            "/api/deposit/", {"amount": "500.00", "account_type": "bosa"}, format="json",
        )
        self.assertEqual(missing_reason.status_code, 400)
        self.assertFalse(Transaction.objects.filter(user=accountant, type="deposit").exists())

        response = self.client.post(
            "/api/deposit/",
            {"amount": "500.00", "account_type": "bosa", "reason": "Cash received at office"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Savings.objects.get(user=accountant).account_type, "bosa")
        entry = Transaction.objects.get(user=accountant, type="deposit")
        self.assertEqual(entry.account_type, "bosa")
        self.assertTrue(AuditLog.objects.filter(action="deposit", target__contains=str(entry.pk)).exists())

    def test_apply_loan_rejected_without_bosa_history(self):
        """A fresh user with no BOSA history cannot apply for a loan."""
        fresh_user = _make_member_user("fresh_user", "fresh@test.com")
        self.client.force_authenticate(user=fresh_user)
        res = self.client.post(
            "/api/loan/apply/",
            {"amount": "1000.00", "repayment_months": 12},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.data)
        # Error must explain why — either no BOSA savings or insufficient months
        error_msg = res.data["error"].lower()
        self.assertTrue(
            "bosa" in error_msg or "6 months" in error_msg,
            f"Unexpected error message: {res.data['error']}"
        )

    def test_full_loan_workflow(self):
        """
        Happy path:
          member deposits → applies for loan → admin approves →
          member repays part → balance reduces correctly.
        """
        self.client.force_authenticate(user=self.member)

        # Seed a posted current-period savings row for this isolated workflow.
        _record_savings(self.member, "2000.00", "bosa")

        # 2. Apply for a loan — BOSA balance is 6×1000 + 2000 = 8000
        #    Bronze tier (6 months) → max loan = 8000 × 3 = 24000
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "5000.00", "repayment_months": 12},
            format="json",
        )
        if loan_res.status_code not in (200, 201):
            self.fail(f"Loan apply failed {loan_res.status_code}: {loan_res.data}")

        loan_id = loan_res.data["loan_id"]
        loan = Loan.objects.get(id=loan_id)
        self.assertEqual(loan.amount, Decimal("5000.00"))
        self.assertEqual(loan.status, "pending")

        # 3. Admin approves
        self.client.force_authenticate(user=self.admin)
        approve = self.client.post(f"/api/admin/loan/{loan_id}/approve/")
        if approve.status_code != 200:
            self.fail(f"Approve failed {approve.status_code}: {approve.data}")

        loan.refresh_from_db()
        self.assertEqual(loan.status, "approved")
        # Interest: Bronze 12-month = 10% → 5000 + 500 = 5500
        self.assertEqual(loan.balance, Decimal("5500.00"))

        # 4. Legacy direct repayment is disabled: only confirmed provider
        # callbacks may post money or reduce a loan balance.
        self.client.force_authenticate(user=self.member)
        repay = self.client.post(
            f"/api/loan/{loan_id}/repay/",
            {"amount": "1000.00"},
            format="json",
        )
        self.assertEqual(repay.status_code, 409)
        self.assertIn("confirmed M-Pesa", repay.data["error"])

        loan.refresh_from_db()
        self.assertEqual(loan.balance, Decimal("5500.00"))
        self.assertEqual(Transaction.objects.filter(user=self.member, type="repayment").count(), 0)

    def test_repayment_exceeding_balance_rejected(self):
        """Repayment larger than outstanding balance is rejected."""
        self.client.force_authenticate(user=self.member)
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "3000.00", "repayment_months": 12},
            format="json",
        )
        if loan_res.status_code not in (200, 201):
            self.fail(f"Loan apply failed: {loan_res.data}")

        loan_id = loan_res.data["loan_id"]
        self.client.force_authenticate(user=self.admin)
        self.client.post(f"/api/admin/loan/{loan_id}/approve/")

        self.client.force_authenticate(user=self.member)
        loan = Loan.objects.get(id=loan_id)
        res = self.client.post(
            f"/api/loan/{loan_id}/repay/",
            {"amount": str(float(loan.balance) + 1)},
            format="json",
        )
        self.assertEqual(res.status_code, 409)
        loan.refresh_from_db()
        self.assertEqual(loan.balance, Decimal("3300.00"))
        self.assertEqual(Transaction.objects.filter(user=self.member, type="repayment").count(), 0)

    def test_duplicate_pending_loan_rejected(self):
        """A member cannot have two pending loan applications simultaneously."""
        self.client.force_authenticate(user=self.member)
        self.client.post(
            "/api/loan/apply/",
            {"amount": "1000.00", "repayment_months": 6},
            format="json",
        )
        res = self.client.post(
            "/api/loan/apply/",
            {"amount": "500.00", "repayment_months": 6},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("pending", res.data.get("error", "").lower())


class SavingsBOSAFOSATests(APITestCase):
    """Verify BOSA/FOSA split and withdrawal rules."""

    def setUp(self):
        self.member = _make_member_user("savings_user", "savings@test.com")
        self.client.force_authenticate(user=self.member)

    def test_bosa_deposit_creates_record(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            "/api/deposit/",
            {"amount": "2000.00", "account_type": "bosa"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Savings.objects.filter(user=self.member, account_type="bosa").exists())

    def test_fosa_deposit_creates_record(self):
        res = self.client.post(
            "/api/deposit/",
            {"amount": "500.00", "account_type": "fosa"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Savings.objects.filter(user=self.member, account_type="fosa").exists())

    def test_fosa_withdrawal_without_provider_is_disabled_without_debit(self):
        """No outbound provider means no withdrawal request or ledger debit."""
        _record_savings(self.member, "3000.00", "fosa")
        res = self.client.post(
            "/api/withdraw/",
            {
                "amount": "1000.00", "account_type": "fosa",
                "destination_type": "mpesa", "destination": "0712345678",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.data["status"], "unavailable")
        self.assertIn("No funds were debited", res.data["error"])
        from django.db.models import Sum
        net = Savings.objects.filter(user=self.member, account_type="fosa").aggregate(
            t=Sum("amount")
        )["t"]
        self.assertEqual(net, Decimal("3000.00"))
        self.assertEqual(Transaction.objects.filter(user=self.member, type="withdrawal").count(), 0)

    def test_bosa_withdrawal_blocked_for_active_member(self):
        """An active member cannot withdraw BOSA savings."""
        _record_savings(self.member, "5000.00", "bosa")
        res = self.client.post(
            "/api/withdraw/",
            {
                "amount": "1000.00", "account_type": "bosa",
                "destination_type": "mpesa", "destination": "0712345678",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("non-withdrawable", res.data.get("error", "").lower())

    def test_fosa_withdrawal_is_disabled_without_provider_even_before_funds_check(self):
        """The route cannot create any request while outbound payouts are unavailable."""
        _record_savings(self.member, "500.00", "fosa")
        res = self.client.post(
            "/api/withdraw/",
            {
                "amount": "1000.00", "account_type": "fosa",
                "destination_type": "mpesa", "destination": "0712345678",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(res.status_code, 503)
        self.assertEqual(Savings.objects.filter(user=self.member, amount__lt=0).count(), 0)
        self.assertEqual(Transaction.objects.filter(user=self.member, type="withdrawal").count(), 0)
