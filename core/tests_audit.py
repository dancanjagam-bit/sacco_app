"""
Tests for the financial audit engine.
Verifies that the audit rules correctly detect:
  - Transaction integrity violations
  - Loan balance mismatches
  - Duplicate transactions
  - Collateral integrity issues
  - Dividend amount mismatches
  - Loans approved without audit logs
  - The audit finding lifecycle (open → reviewing → resolved)
"""

from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import AuditLog
from core.models import Savings, Loan, Transaction, LoanGuarantor, SavingsDividend, AuditFinding
from core.audit_engine import run_full_audit
from members.models import Member

User = get_user_model()


def _make_user(username, email, national_id=None):
    if national_id is None:
        national_id = str(abs(hash(username + "audit")) % 90000000 + 10000000)
    user = User.objects.create_user(
        username=username, password="TestPass1", email=email,
        first_name="Audit", last_name="Test",
    )
    # Use a unique member number derived from the primary key to avoid collisions
    # We create the user first so we have a pk, then create the Member
    Member.objects.create(
        user=user,
        member_number=f"AUD{user.pk:06d}",
        national_id=national_id,
        phone_number="0712345678",
        gender="male",
        date_of_birth=date(1990, 1, 1),
        county="Nairobi",
        address="Test",
    )
    return user


def _make_admin():
    return User.objects.create_superuser(
        username="audit_admin", password="AdminPass1", email="auditadmin@test.com"
    )


class AuditEngineTests(APITestCase):
    """Direct tests of the audit engine rules."""

    def setUp(self):
        self.member = _make_user("audit_member", "amember@test.com")
        self.admin  = _make_admin()

    def test_clean_system_produces_no_findings(self):
        """A system with properly recorded transactions produces zero findings."""
        # Create a proper deposit
        Savings.objects.create(user=self.member, amount=Decimal("1000"), account_type="bosa")
        Transaction.objects.create(
            user=self.member, type="deposit", amount=Decimal("1000"),
            note="BOSA deposit", created_at=date.today(),
        )
        findings = run_full_audit()
        # Filter out suspicious pattern findings (they're informational)
        real_findings = [f for f in findings if f["rule"] != "SUSPICIOUS_PATTERN" and f["rule"] != "ORPHANED_RECORD"]
        self.assertEqual(len(real_findings), 0, f"Expected 0 findings but got: {[(f['rule'], f['title']) for f in findings]}")

    def test_savings_without_transaction_detected(self):
        """Savings row without a matching Transaction is flagged."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        # No Transaction row created
        findings = run_full_audit()
        txn_findings = [f for f in findings if f["rule"] == "TXN_INTEGRITY" and "without matching Transaction" in f["title"]]
        self.assertEqual(len(txn_findings), 1)

    def test_transaction_without_savings_detected(self):
        """Transaction deposit without a matching Savings row is flagged (high severity)."""
        Transaction.objects.create(
            user=self.member, type="deposit", amount=Decimal("2000"),
            note="Ghost deposit", created_at=date.today(),
        )
        findings = run_full_audit()
        ghost = [f for f in findings if f["rule"] == "TXN_INTEGRITY" and "without matching Savings" in f["title"]]
        self.assertEqual(len(ghost), 1)
        self.assertEqual(ghost[0]["severity"], "high")

    def test_loan_balance_mismatch_detected(self):
        """Loan with stored balance that doesn't match transaction history is flagged."""
        loan = Loan.objects.create(
            user=self.member, amount=Decimal("5000"),
            interest=Decimal("10"), repayment_months=12,
            balance=Decimal("3000"),  # Should be 5500 - 0 repayments = 5500
            status="approved", total_savings_at_application=Decimal("10000"),
        )
        findings = run_full_audit()
        balance_findings = [f for f in findings if f["rule"] == "LOAN_BALANCE"]
        self.assertGreater(len(balance_findings), 0)
        self.assertIn("balance mismatch", balance_findings[0]["title"].lower())

    def test_repaid_loan_with_nonzero_balance_detected(self):
        """A loan marked 'repaid' but with non-zero balance is flagged."""
        Loan.objects.create(
            user=self.member, amount=Decimal("1000"),
            interest=Decimal("10"), repayment_months=6,
            balance=Decimal("100"),  # Should be 0 if repaid
            status="repaid",
        )
        findings = run_full_audit()
        repaid = [f for f in findings if f["rule"] == "LOAN_BALANCE" and "non-zero" in f["title"].lower()]
        self.assertEqual(len(repaid), 1)
        self.assertEqual(repaid[0]["severity"], "high")

    def test_duplicate_savings_detected(self):
        """Two identical savings entries within 60 seconds are flagged."""
        from django.utils import timezone
        now = timezone.now()
        s1 = Savings.objects.create(user=self.member, amount=Decimal("1000"), account_type="bosa")
        Savings.objects.filter(pk=s1.pk).update(created_at=now)
        s2 = Savings.objects.create(user=self.member, amount=Decimal("1000"), account_type="bosa")
        Savings.objects.filter(pk=s2.pk).update(created_at=now + timedelta(seconds=5))

        findings = run_full_audit()
        dup = [f for f in findings if f["rule"] == "DUPLICATE_SAVINGS"]
        self.assertGreater(len(dup), 0)

    def test_dividend_mismatch_detected(self):
        """Dividend where stored amount != balance × rate is flagged."""
        SavingsDividend.objects.create(
            user=self.member, year=2025,
            rate=Decimal("8.00"),
            savings_balance=Decimal("10000"),
            amount=Decimal("900"),  # Should be 800 (10000 × 8%)
        )
        findings = run_full_audit()
        div = [f for f in findings if f["rule"] == "DIVIDEND_INTEGRITY"]
        self.assertEqual(len(div), 1)
        self.assertIn("mismatch", div[0]["title"].lower())

    def test_loan_approved_without_audit_log_detected(self):
        """Loan approved but no AuditLog entry is flagged."""
        Loan.objects.create(
            user=self.member, amount=Decimal("2000"),
            interest=Decimal("10"), repayment_months=12,
            balance=Decimal("2200"), status="approved",
        )
        findings = run_full_audit()
        missing = [f for f in findings if f["rule"] == "MISSING_AUDIT_LOG"]
        self.assertGreater(len(missing), 0)

    def test_collateral_lock_not_released_detected(self):
        """Guarantor with locked_amount > 0 on a repaid loan is flagged."""
        borrower = _make_user("audit_borrower", "ab@test.com", "40000001")
        guarantor = _make_user("audit_guarantor", "ag@test.com", "40000002")
        loan = Loan.objects.create(
            user=borrower, amount=Decimal("3000"),
            interest=Decimal("10"), repayment_months=12,
            balance=Decimal("0"), status="repaid",
        )
        LoanGuarantor.objects.create(
            loan=loan, guarantor=guarantor,
            status="accepted", pledged_amount=Decimal("2000"),
            locked_amount=Decimal("1500"),  # Should be 0 for repaid loan
        )
        findings = run_full_audit()
        collateral = [f for f in findings if f["rule"] == "COLLATERAL_INTEGRITY" and "not released" in f["title"].lower()]
        self.assertEqual(len(collateral), 1)
        self.assertEqual(collateral[0]["severity"], "high")

    def test_findings_sorted_by_severity(self):
        """Critical findings appear before high, which appear before medium."""
        # Create a critical issue (balance mismatch)
        Loan.objects.create(
            user=self.member, amount=Decimal("1000"),
            interest=Decimal("10"), repayment_months=6,
            balance=Decimal("999"), status="approved",
        )
        findings = run_full_audit()
        if len(findings) > 1:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            for i in range(len(findings) - 1):
                self.assertLessEqual(
                    severity_order.get(findings[i]["severity"], 99),
                    severity_order.get(findings[i + 1]["severity"], 99),
                    f"Findings not sorted: {findings[i]['severity']} before {findings[i+1]['severity']}"
                )


class AuditAPITests(APITestCase):
    """Test the audit API endpoints."""

    def setUp(self):
        self.member = _make_user("api_member", "apim@test.com")
        self.admin  = _make_admin()

    def test_run_audit_requires_admin(self):
        """Regular member cannot run audit."""
        self.client.force_authenticate(user=self.member)
        res = self.client.post("/api/admin/audit/run/")
        self.assertEqual(res.status_code, 403)

    def test_admin_can_run_audit(self):
        """Admin can run the full audit and get results."""
        # Create a finding-worthy scenario
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/audit/run/")
        if res.status_code != 200:
            self.fail(f"Audit run failed {res.status_code}: {res.data}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("run_id", res.data)
        self.assertIn("summary", res.data)
        self.assertGreater(res.data["findings"], 0)

    def test_findings_are_persisted(self):
        """Running audit creates AuditFinding records."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/audit/run/")
        self.assertTrue(AuditFinding.objects.exists())

    def test_admin_can_list_findings(self):
        """Admin can list findings with filters."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/audit/run/")

        res = self.client.get("/api/admin/audit/findings/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("results", res.data)
        self.assertGreater(res.data["total"], 0)

    def test_filter_findings_by_severity(self):
        """Filter findings by severity works."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/audit/run/")

        res = self.client.get("/api/admin/audit/findings/?severity=medium")
        self.assertEqual(res.status_code, 200)
        for f in res.data["results"]:
            self.assertEqual(f["severity"], "medium")

    def test_review_finding(self):
        """Admin can review and resolve a finding."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/audit/run/")
        finding = AuditFinding.objects.first()

        res = self.client.post(
            f"/api/admin/audit/findings/{finding.id}/review/",
            {"status": "resolved", "notes": "Investigated and corrected", "resolution": "Fixed in database"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Review failed {res.status_code}: {res.data}")
        finding.refresh_from_db()
        self.assertEqual(finding.status, "resolved")
        self.assertEqual(finding.reviewed_by, self.admin)
        self.assertIsNotNone(finding.reviewed_at)
        self.assertEqual(finding.resolution, "Fixed in database")

    def test_dismiss_finding(self):
        """Admin can dismiss a finding as not actionable."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/audit/run/")
        finding = AuditFinding.objects.first()

        res = self.client.post(
            f"/api/admin/audit/findings/{finding.id}/review/",
            {"status": "dismissed", "notes": "False positive"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        finding.refresh_from_db()
        self.assertEqual(finding.status, "dismissed")

    def test_audit_report_endpoint(self):
        """Admin can get a grouped audit report."""
        Savings.objects.create(user=self.member, amount=Decimal("500"), account_type="bosa")
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/audit/run/")

        res = self.client.get("/api/admin/audit/report/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("summary", res.data)
        self.assertIn("by_rule", res.data)
        self.assertGreater(len(res.data["by_rule"]), 0)
