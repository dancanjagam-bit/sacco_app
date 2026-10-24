"""
Extended core tests — Issue B coverage.

Covers workflows that had no dedicated tests:
  - Exit request (BOSA withdrawal workflow)
  - Guarantor nomination and response
  - Dividend payout
  - Collateral status endpoint
  - Savings statement endpoint
  - Repayment schedule endpoint
"""

from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from members.models import Member
from core.models import Savings, Loan, LoanGuarantor, ExitRequest

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers (same as core/tests.py — kept local to avoid import coupling)
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(username, email, national_id=None):
    if national_id is None:
        national_id = str(abs(hash(username + "ext")) % 90000000 + 10000000)
    user = User.objects.create_user(
        username=username, password="TestPass1", email=email,
        first_name="Test", last_name="User",
    )
    Member.objects.create(
        user=user,
        member_number=f"EXT{username[:5].upper()}",
        national_id=national_id,
        phone_number="0712345678",
        gender="male",
        date_of_birth=date(1990, 1, 1),
        county="Nairobi",
        address="Test Address",
    )
    return user


def _make_admin():
    return User.objects.create_superuser(
        username="ext_admin", password="AdminPass1", email="extadmin@test.com"
    )


def _bosa_history(user, months=6, amount=Decimal("1000.00")):
    today = date.today()
    for i in range(months, 0, -1):
        d = (today - relativedelta(months=i)).replace(day=15)
        s = Savings.objects.create(user=user, amount=amount, account_type="bosa")
        Savings.objects.filter(pk=s.pk).update(
            created_at=str(d) + " 10:00:00+00:00"
        )


def _approved_loan(member_user, admin_user, amount=Decimal("3000.00")):
    """Create a loan and approve it, returning the refreshed Loan object."""
    _bosa_history(member_user)
    loan = Loan.objects.create(
        user=member_user, amount=amount,
        interest=Decimal("10.00"), repayment_months=12,
        balance=amount, savings_months=6,
        total_savings_at_application=Decimal("6000.00"),
    )
    loan.status = "approved"
    loan.approved_by = admin_user
    from django.utils import timezone
    loan.approved_at = timezone.now()
    interest_amount = amount * Decimal("10") / Decimal("100")
    loan.balance = amount + interest_amount
    loan.save()
    return loan


# ─────────────────────────────────────────────────────────────────────────────
# Exit Request Tests
# ─────────────────────────────────────────────────────────────────────────────

class ExitRequestTests(APITestCase):

    def setUp(self):
        self.member = _make_user("exit_member", "exit@test.com")
        self.admin  = _make_admin()
        # Give member some BOSA savings
        Savings.objects.create(
            user=self.member, amount=Decimal("5000.00"), account_type="bosa"
        )

    def test_member_can_submit_exit_request(self):
        """Member with no loans or pledges can submit an exit request."""
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            "/api/exit-request/",
            {"reason": "Relocating abroad"},
            format="json",
        )
        if res.status_code != 201:
            self.fail(f"Exit request failed {res.status_code}: {res.data}")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(ExitRequest.objects.filter(user=self.member).exists())

    def test_member_can_view_own_exit_request(self):
        """Member can retrieve their exit request status."""
        ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=False, has_guarantor_pledges=False,
        )
        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/exit-request/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.data["exit_request"])
        self.assertEqual(res.data["exit_request"]["status"], "pending")

    def test_duplicate_exit_request_blocked(self):
        """Member cannot submit a second exit request while one is pending."""
        ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=False, has_guarantor_pledges=False,
        )
        self.client.force_authenticate(user=self.member)
        res = self.client.post("/api/exit-request/", {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("active exit request", res.data.get("error", "").lower())

    def test_admin_can_list_exit_requests(self):
        """Admin can list all exit requests."""
        ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=False, has_guarantor_pledges=False,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/admin/exit-requests/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["bosa_balance"], 5000.0)

    def test_admin_can_approve_exit_request(self):
        """Admin can approve an exit request — sets release_date 60 days out."""
        req = ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=False, has_guarantor_pledges=False,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/admin/exit-requests/{req.id}/review/",
            {"action": "approve", "notes": "Approved after verification"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Approval failed {res.status_code}: {res.data}")
        req.refresh_from_db()
        self.assertEqual(req.status, "approved")
        self.assertIsNotNone(req.release_date)
        # Release date must be at least 60 days from today
        from datetime import date, timedelta
        self.assertGreaterEqual(req.release_date, date.today() + timedelta(days=59))

    def test_admin_can_reject_exit_request(self):
        """Admin can reject an exit request — must supply a reason."""
        req = ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=False, has_guarantor_pledges=False,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/admin/exit-requests/{req.id}/review/",
            {
                "action": "reject",
                "rejection_reason": "Member has pending obligations.",
            },
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Rejection failed {res.status_code}: {res.data}")
        req.refresh_from_db()
        self.assertEqual(req.status, "rejected")
        self.assertEqual(req.rejection_reason, "Member has pending obligations.")

    def test_exit_blocked_when_active_loan_exists(self):
        """Admin cannot approve an exit if member has an active unpaid loan."""
        req = ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=True, has_guarantor_pledges=False,
        )
        # Create the actual loan so the server-side re-check finds it
        Loan.objects.create(
            user=self.member, amount=Decimal("2000.00"),
            interest=Decimal("10.00"), repayment_months=12,
            balance=Decimal("2000.00"), status="approved",
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/admin/exit-requests/{req.id}/review/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("loan", res.data.get("error", "").lower())

    def test_member_can_cancel_pending_exit(self):
        """Member can cancel their own pending exit request."""
        req = ExitRequest.objects.create(
            user=self.member, bosa_balance=Decimal("5000.00"),
            has_active_loan=False, has_guarantor_pledges=False,
        )
        self.client.force_authenticate(user=self.member)
        res = self.client.post(f"/api/exit-request/{req.id}/cancel/")
        if res.status_code != 200:
            self.fail(f"Cancel failed {res.status_code}: {res.data}")
        req.refresh_from_db()
        self.assertEqual(req.status, "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# Guarantor Tests
# ─────────────────────────────────────────────────────────────────────────────

class GuarantorTests(APITestCase):

    def setUp(self):
        self.borrower  = _make_user("borrower",  "borrower@test.com",  "10000001")
        self.guarantor = _make_user("guarantor", "guarantor@test.com", "10000002")
        self.admin     = _make_admin()
        _bosa_history(self.borrower)
        # Give guarantor some savings too
        Savings.objects.create(
            user=self.guarantor, amount=Decimal("10000.00"), account_type="bosa"
        )

    def test_member_can_add_guarantor_to_loan(self):
        """Borrower can nominate a guarantor for a pending loan."""
        self.client.force_authenticate(user=self.borrower)
        # Apply for a loan first
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "5000.00", "repayment_months": 12},
            format="json",
        )
        if loan_res.status_code not in (200, 201):
            self.fail(f"Loan apply failed: {loan_res.data}")
        loan_id = loan_res.data["loan_id"]

        # Add guarantor by member number
        guarantor_member = self.guarantor.member_profile
        res = self.client.post(
            f"/api/loan/{loan_id}/guarantors/",
            {"identifier": guarantor_member.member_number},
            format="json",
        )
        if res.status_code not in (200, 201):
            self.fail(f"Add guarantor failed {res.status_code}: {res.data}")
        self.assertTrue(
            LoanGuarantor.objects.filter(
                loan_id=loan_id, guarantor=self.guarantor
            ).exists()
        )

    def test_self_guarantee_blocked(self):
        """Member cannot guarantee their own loan."""
        self.client.force_authenticate(user=self.borrower)
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "3000.00", "repayment_months": 12},
            format="json",
        )
        loan_id = loan_res.data["loan_id"]

        borrower_member = self.borrower.member_profile
        res = self.client.post(
            f"/api/loan/{loan_id}/guarantors/",
            {"identifier": borrower_member.member_number},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("own loan", res.data.get("error", "").lower())

    def test_guarantor_can_view_pending_requests(self):
        """Guarantor sees pending requests addressed to them."""
        self.client.force_authenticate(user=self.borrower)
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "3000.00", "repayment_months": 12},
            format="json",
        )
        if loan_res.status_code not in (200, 201):
            self.fail(f"Loan apply failed {loan_res.status_code}: {loan_res.data}")
        loan_id = loan_res.data["loan_id"]
        guarantor_member = self.guarantor.member_profile
        add_res = self.client.post(
            f"/api/loan/{loan_id}/guarantors/",
            {"identifier": guarantor_member.member_number},
            format="json",
        )
        if add_res.status_code not in (200, 201):
            self.fail(f"Add guarantor failed {add_res.status_code}: {add_res.data}")

        self.client.force_authenticate(user=self.guarantor)
        res = self.client.get("/api/guarantor/pending/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["loan_id"], loan_id)

    def test_guarantor_can_accept_request(self):
        """Guarantor can accept a pending guarantor request."""
        self.client.force_authenticate(user=self.borrower)
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "3000.00", "repayment_months": 12},
            format="json",
        )
        loan_id = loan_res.data["loan_id"]
        guarantor_member = self.guarantor.member_profile
        add_res = self.client.post(
            f"/api/loan/{loan_id}/guarantors/",
            {"identifier": guarantor_member.member_number},
            format="json",
        )
        g_id = add_res.data["guarantor_id"]

        self.client.force_authenticate(user=self.guarantor)
        res = self.client.post(
            f"/api/guarantor/{g_id}/respond/",
            {"action": "accept", "message": "Happy to help"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Accept failed {res.status_code}: {res.data}")
        g = LoanGuarantor.objects.get(id=g_id)
        self.assertEqual(g.status, "accepted")

    def test_guarantor_can_decline_request(self):
        """Guarantor can decline a pending guarantor request."""
        self.client.force_authenticate(user=self.borrower)
        loan_res = self.client.post(
            "/api/loan/apply/",
            {"amount": "3000.00", "repayment_months": 12},
            format="json",
        )
        loan_id = loan_res.data["loan_id"]
        add_res = self.client.post(
            f"/api/loan/{loan_id}/guarantors/",
            {"identifier": self.guarantor.member_profile.member_number},
            format="json",
        )
        g_id = add_res.data["guarantor_id"]

        self.client.force_authenticate(user=self.guarantor)
        res = self.client.post(
            f"/api/guarantor/{g_id}/respond/",
            {"action": "decline", "message": "Unable at this time"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Decline failed {res.status_code}: {res.data}")
        g = LoanGuarantor.objects.get(id=g_id)
        self.assertEqual(g.status, "declined")


# ─────────────────────────────────────────────────────────────────────────────
# Dividend Tests
# ─────────────────────────────────────────────────────────────────────────────

class DividendTests(APITestCase):

    def setUp(self):
        self.member = _make_user("div_member", "div@test.com")
        self.admin  = _make_admin()
        Savings.objects.create(
            user=self.member, amount=Decimal("10000.00"), account_type="bosa"
        )

    def test_admin_can_pay_dividends(self):
        """Admin can calculate and pay annual dividends to all members."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/dividends/pay/",
            {"year": 2025, "rate": "8.00"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Dividend payout failed {res.status_code}: {res.data}")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.data["members_paid"], 0)
        # 8% of KES 10,000 = KES 800
        self.assertEqual(res.data["total_paid"], 800.0)

    def test_dividend_idempotent_same_year(self):
        """Paying dividends twice for the same year does not double-pay."""
        self.client.force_authenticate(user=self.admin)
        self.client.post(
            "/api/admin/dividends/pay/",
            {"year": 2024, "rate": "8.00"},
            format="json",
        )
        res2 = self.client.post(
            "/api/admin/dividends/pay/",
            {"year": 2024, "rate": "8.00"},
            format="json",
        )
        self.assertEqual(res2.status_code, 200)
        # Second run should pay 0 members (already paid for 2024)
        self.assertEqual(res2.data["members_paid"], 0)

    def test_member_can_view_dividend_history(self):
        """Member can view their own dividend history."""
        self.client.force_authenticate(user=self.admin)
        self.client.post(
            "/api/admin/dividends/pay/",
            {"year": 2023, "rate": "7.50"},
            format="json",
        )
        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/dividends/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["year"], 2023)
        self.assertEqual(res.data[0]["rate"], 7.5)

    def test_invalid_rate_rejected(self):
        """Dividend rate outside 0–100% is rejected."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/dividends/pay/",
            {"year": 2022, "rate": "150"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.data)


# ─────────────────────────────────────────────────────────────────────────────
# Collateral Status & Savings Statement Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────

class CollateralAndStatementTests(APITestCase):

    def setUp(self):
        self.member = _make_user("col_member", "col@test.com")
        self.client.force_authenticate(user=self.member)
        Savings.objects.create(
            user=self.member, amount=Decimal("5000.00"), account_type="bosa"
        )
        Savings.objects.create(
            user=self.member, amount=Decimal("2000.00"), account_type="fosa"
        )

    def test_collateral_status_returns_bosa_fosa_split(self):
        """Collateral status shows BOSA, FOSA, locked, and withdrawable amounts."""
        res = self.client.get("/api/collateral/status/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("bosa_balance",     res.data)
        self.assertIn("fosa_balance",     res.data)
        self.assertIn("withdrawable",     res.data)
        self.assertIn("total_locked",     res.data)
        self.assertEqual(res.data["bosa_balance"],  5000.0)
        self.assertEqual(res.data["fosa_balance"],  2000.0)
        # No active loans — nothing should be locked
        self.assertEqual(res.data["total_locked"],  0.0)
        self.assertEqual(res.data["withdrawable"],  2000.0)  # Only FOSA withdrawable

    def test_savings_statement_lists_entries(self):
        """Savings statement returns a running balance for each entry."""
        res = self.client.get("/api/savings/statement/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("entries",       res.data)
        self.assertIn("total_balance", res.data)
        self.assertEqual(len(res.data["entries"]), 2)
        self.assertEqual(res.data["total_balance"], 7000.0)

    def test_repayment_schedule_available_for_approved_loan(self):
        """Repayment schedule endpoint returns installment breakdown."""
        admin = _make_admin()
        loan  = _approved_loan(self.member, admin, Decimal("3000.00"))

        res = self.client.get(f"/api/loan/{loan.id}/schedule/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("schedule",        res.data)
        self.assertIn("total_payable",   res.data)
        self.assertIn("monthly_payment", res.data)
        self.assertEqual(len(res.data["schedule"]), 12)
        # Total payable = 3000 + 10% = 3300
        self.assertEqual(res.data["total_payable"], 3300.0)
