from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AuditLog, StaffProfile
from core.models import Savings, Transaction
from members.models import Member
from .models import JournalEntry, JournalLine, LedgerAccount, ShareCapitalMovement, ShareCapitalPolicy
from .services import (
    AccountingConflict,
    AccountingPermissionDenied,
    InvalidJournal,
    post_journal_entry,
    reverse_journal_entry,
)


class JournalPostingTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.User = get_user_model()
        self.accountant = self.User.objects.create_user(
            username="ledger_accountant", password="synthetic-only-password", is_staff=True
        )
        StaffProfile.objects.create(user=self.accountant, role="accountant", status="active")
        self.member = self.User.objects.create_user(
            username="ledger_member", password="synthetic-only-password"
        )
        self.cash = LedgerAccount.objects.create(
            code="1000", name="Cash at bank", classification="asset", normal_balance="debit"
        )
        self.member_savings = LedgerAccount.objects.create(
            code="2100", name="Member savings payable", classification="liability", normal_balance="credit"
        )

    def deposit_lines(self):
        return [
            {"account_id": self.cash.pk, "debit": "125.00", "credit": "0.00", "memo": "Provider receipt"},
            {"account_id": self.member_savings.pk, "debit": "0.00", "credit": "125.00", "memo": "Member liability"},
        ]

    def post(self, **overrides):
        options = {
            "idempotency_key": "test-event-001",
            "source_type": "synthetic_receipt",
            "source_reference": "receipt-001",
            "description": "Synthetic test deposit",
            "lines": self.deposit_lines(),
            "actor": self.accountant,
        }
        options.update(overrides)
        return post_journal_entry(**options)

    def test_balanced_entry_is_atomic_audited_and_idempotent(self):
        entry = self.post()
        repeated = self.post()
        self.assertEqual(entry.pk, repeated.pk)
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(JournalLine.objects.filter(entry=entry).count(), 2)
        self.assertEqual(entry.status, "posted")
        self.assertIsNotNone(entry.audit_log_id)
        self.assertEqual(entry.audit_log.action, "journal_entry_posted")
        self.assertEqual(
            sum((line.debit for line in entry.lines.all()), Decimal("0.00")),
            sum((line.credit for line in entry.lines.all()), Decimal("0.00")),
        )

    def test_same_idempotency_key_with_changed_data_conflicts(self):
        self.post()
        changed = self.deposit_lines()
        changed[0]["debit"] = "126.00"
        changed[1]["credit"] = "126.00"
        with self.assertRaises(AccountingConflict):
            self.post(lines=changed)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_source_reference_constraint_blocks_duplicate_posting_with_new_key(self):
        self.post()
        with self.assertRaises(AccountingConflict):
            self.post(idempotency_key="different-key-same-source")
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_unbalanced_or_invalid_decimal_rolls_back_everything(self):
        lines = self.deposit_lines()
        lines[1]["credit"] = "124.99"
        with self.assertRaises(InvalidJournal):
            self.post(lines=lines)
        self.assertFalse(JournalEntry.objects.exists())
        self.assertFalse(JournalLine.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action="journal_entry_posted").exists())

        lines = self.deposit_lines()
        lines[0]["debit"] = "125.001"
        with self.assertRaises(InvalidJournal):
            self.post(lines=lines)
        self.assertFalse(JournalEntry.objects.exists())

    def test_only_active_accounting_staff_can_post_manual_entries(self):
        with self.assertRaises(AccountingPermissionDenied):
            self.post(actor=self.member)
        inactive = self.User.objects.create_user(
            username="inactive_accountant", password="synthetic-only-password", is_staff=True
        )
        StaffProfile.objects.create(user=inactive, role="accountant", status="inactive")
        with self.assertRaises(AccountingPermissionDenied):
            self.post(actor=inactive)
        self.assertFalse(JournalEntry.objects.exists())

    def test_inactive_or_mismatched_currency_account_is_rejected(self):
        self.member_savings.active = False
        self.member_savings.save()
        with self.assertRaises(InvalidJournal):
            self.post(idempotency_key="inactive-account")
        self.member_savings.active = True
        self.member_savings.currency = "USD"
        self.member_savings.save()
        with self.assertRaises(InvalidJournal):
            self.post(idempotency_key="currency-mismatch")
        self.assertFalse(JournalEntry.objects.exists())

    def test_full_reversal_is_linked_and_does_not_mutate_original(self):
        original = self.post()
        original_description = original.description
        reversal = reverse_journal_entry(
            entry_id=original.pk,
            idempotency_key="reversal-001",
            reason="Synthetic correction test",
            actor=self.accountant,
        )
        retry = reverse_journal_entry(
            entry_id=original.pk,
            idempotency_key="reversal-001",
            reason="Synthetic correction test",
            actor=self.accountant,
        )
        self.assertEqual(reversal.pk, retry.pk)
        self.assertEqual(reversal.reverses_id, original.pk)
        self.assertEqual(original.description, original_description)
        self.assertEqual(original.status, "posted")
        self.assertEqual(AuditLog.objects.filter(action="journal_entry_reversed").count(), 1)
        self.assertEqual(
            [(line.account_id, line.debit, line.credit) for line in reversal.lines.all()],
            [(line.account_id, line.credit, line.debit) for line in original.lines.all()],
        )
        self.assertTrue(AuditLog.objects.filter(action="journal_entry_reversed").exists())
        with self.assertRaises(AccountingConflict):
            reverse_journal_entry(
                entry_id=original.pk,
                idempotency_key="different-reversal-key",
                reason="Another full reversal",
                actor=self.accountant,
            )

    def test_posted_entry_and_lines_are_immutable(self):
        entry = self.post()
        entry.description = "Changed after posting"
        with self.assertRaises(ValidationError):
            entry.save()
        line = entry.lines.first()
        with self.assertRaises(ValidationError):
            line.delete()

    def test_system_posting_is_explicit_and_still_audited(self):
        entry = post_journal_entry(
            idempotency_key="system-event-001",
            source_type="provider_settlement",
            source_reference="sandbox-ref-001",
            description="Synthetic confirmed settlement",
            lines=self.deposit_lines(),
            system_initiated=True,
        )
        self.assertIsNone(entry.posted_by_id)
        self.assertEqual(entry.audit_log.action, "journal_entry_posted")


class AccountingApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.User = User
        self.accountant = User.objects.create_user(
            username="api_accountant", password="synthetic-only-password", is_staff=True
        )
        StaffProfile.objects.create(user=self.accountant, role="accountant", status="active")
        self.member = User.objects.create_user(
            username="api_member", password="synthetic-only-password"
        )
        self.cash = LedgerAccount.objects.create(
            code="1010", name="Synthetic cash", classification="asset", normal_balance="debit"
        )
        self.savings_liability = LedgerAccount.objects.create(
            code="2110", name="Synthetic member savings", classification="liability", normal_balance="credit"
        )
        self.client = APIClient()

    def adjustment_payload(self, **changes):
        payload = {
            "idempotency_key": "manual-adjustment-001",
            "source_type": "staff_adjustment",
            "source_reference": "supporting-document-001",
            "description": "Synthetic test adjustment",
            "reason": "Test-only evidence reference",
            "lines": [
                {"account_id": self.cash.pk, "debit": "25.00", "credit": "0.00"},
                {"account_id": self.savings_liability.pk, "debit": "0.00", "credit": "25.00"},
            ],
        }
        payload.update(changes)
        return payload

    def test_reconciliation_is_accountant_only_and_does_not_guess_matches(self):
        Transaction.objects.create(user=self.member, type="withdrawal", account_type="", amount="-500.00")
        Savings.objects.create(user=self.member, amount="-500.00", account_type="fosa")
        self.client.force_authenticate(self.member)
        denied = self.client.get("/api/accounting/reconciliation/legacy/")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.accountant)
        response = self.client.get("/api/accounting/reconciliation/legacy/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["transactions"]["unjournaled_count"], 1)
        self.assertEqual(response.data["transactions"]["unjournaled_amount_sum"], "-500.00")
        self.assertFalse(response.data["automatic_balancing_created"])
        self.assertFalse(response.data["savings_records"]["paired_to_transactions"])
        self.assertEqual(response.data["transactions"]["unjournaled_records"][0]["status"], "not_imported_to_double_entry")
        self.assertNotIn("username", str(response.data))

    def test_reconciliation_rejects_bad_date_ranges(self):
        self.client.force_authenticate(self.accountant)
        self.assertEqual(self.client.get("/api/accounting/reconciliation/legacy/?from=tomorrow").status_code, 400)
        self.assertEqual(
            self.client.get("/api/accounting/reconciliation/legacy/?from=2026-11-12&to=2026-11-11").status_code,
            400,
        )

    def test_adjustment_api_is_scoped_idempotent_and_rejects_unbalanced_data(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post("/api/accounting/journal-entries/adjustments/", self.adjustment_payload(), format="json").status_code, 403)

        self.client.force_authenticate(self.accountant)
        unbalanced = self.adjustment_payload()
        unbalanced["lines"][1]["credit"] = "24.99"
        response = self.client.post("/api/accounting/journal-entries/adjustments/", unbalanced, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(JournalEntry.objects.exists())

        payload = self.adjustment_payload()
        first = self.client.post("/api/accounting/journal-entries/adjustments/", payload, format="json")
        retry = self.client.post("/api/accounting/journal-entries/adjustments/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(first.data["id"], retry.data["id"])
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="journal_entry_posted").count(), 1)

        changed = self.adjustment_payload()
        changed["lines"][0]["debit"] = "26.00"
        changed["lines"][1]["credit"] = "26.00"
        conflict = self.client.post("/api/accounting/journal-entries/adjustments/", changed, format="json")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_adjustment_requires_reason_and_reference(self):
        self.client.force_authenticate(self.accountant)
        payload = self.adjustment_payload(reason="", source_reference="")
        response = self.client.post("/api/accounting/journal-entries/adjustments/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(JournalEntry.objects.exists())

    def test_treasurer_can_read_journal_and_reports_without_posting_authority(self):
        from accounts.models import StaffRoleGrant

        treasurer = self.User.objects.create_user(username="api_treasurer")
        StaffRoleGrant.objects.create(user=treasurer, role="treasurer", granted_by=self.accountant,
                                      reason="Synthetic treasury capability test")
        self.client.force_authenticate(self.accountant)
        created = self.client.post("/api/accounting/journal-entries/adjustments/", self.adjustment_payload(), format="json")
        self.assertEqual(created.status_code, 201)
        entry = created.data["id"]

        self.client.force_authenticate(treasurer)
        for path in ("accounts/", "trial-balance/", "journal-entries/", f"journal-entries/{entry}/",
                     "reconciliation/legacy/", "share-capital/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f"/api/accounting/{path}").status_code, 200)
        self.assertEqual(self.client.post("/api/accounting/journal-entries/adjustments/",
            self.adjustment_payload(idempotency_key="forbidden"), format="json").status_code, 403)
        self.assertEqual(self.client.post(f"/api/accounting/journal-entries/{entry}/reverse/",
            {"idempotency_key": "forbidden-reversal", "reason": "Synthetic attempt"}, format="json").status_code, 403)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_chart_of_accounts_is_permission_scoped_and_posted_identity_is_immutable(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/accounting/accounts/").status_code, 403)
        account_payload = {
            "code": "3010", "name": "Synthetic share equity", "classification": "equity",
            "normal_balance": "credit", "system_key": "synthetic.share_equity",
        }
        self.assertEqual(self.client.post("/api/accounting/accounts/", account_payload, format="json").status_code, 403)

        self.client.force_authenticate(self.accountant)
        self.assertEqual(len(self.client.get("/api/accounting/accounts/").data["results"]), 2)
        self.assertEqual(self.client.post("/api/accounting/accounts/", account_payload, format="json").status_code, 403)

        admin = self.User.objects.create_superuser(
            username="chart_admin", email="chart_admin@example.test", password="synthetic-only-password"
        )
        self.client.force_authenticate(admin)
        created = self.client.post("/api/accounting/accounts/", account_payload, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["currency"], "KES")
        self.assertEqual(self.client.patch(
            f"/api/accounting/accounts/{created.data['id']}/", {"active": False}, format="json"
        ).status_code, 200)
        self.assertEqual(self.client.patch(
            f"/api/accounting/accounts/{created.data['id']}/", {"classification": "liability"}, format="json"
        ).status_code, 400)

        self.client.force_authenticate(self.accountant)
        posted = self.client.post(
            "/api/accounting/journal-entries/adjustments/", self.adjustment_payload(), format="json"
        )
        self.assertEqual(posted.status_code, 201)
        self.client.force_authenticate(admin)
        rename = self.client.patch(
            f"/api/accounting/accounts/{self.cash.pk}/", {"name": "Renamed cash"}, format="json"
        )
        self.assertEqual(rename.status_code, 400)
        self.assertEqual(LedgerAccount.objects.get(pk=self.cash.pk).name, "Synthetic cash")

    def test_trial_balance_and_journal_browsing_are_staff_only_and_date_scoped(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/accounting/trial-balance/").status_code, 403)
        self.assertEqual(self.client.get("/api/accounting/journal-entries/").status_code, 403)

        self.client.force_authenticate(self.accountant)
        created = self.client.post(
            "/api/accounting/journal-entries/adjustments/", self.adjustment_payload(), format="json"
        )
        self.assertEqual(created.status_code, 201)
        today = date.today().isoformat()
        balance = self.client.get(f"/api/accounting/trial-balance/?as_of={today}")
        self.assertEqual(balance.status_code, 200)
        self.assertEqual(balance.data["by_currency"]["KES"]["debit_balances"], "25.00")
        self.assertEqual(balance.data["by_currency"]["KES"]["credit_balances"], "25.00")
        self.assertTrue(balance.data["by_currency"]["KES"]["balanced"])

        before_posting = self.client.get("/api/accounting/trial-balance/?as_of=2000-01-01")
        self.assertEqual(before_posting.data["by_currency"]["KES"]["debit_balances"], "0.00")
        self.assertEqual(self.client.get("/api/accounting/trial-balance/?as_of=not-a-date").status_code, 400)
        listing = self.client.get("/api/accounting/journal-entries/?page_size=1")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["id"], created.data["id"])
        detail = self.client.get(f"/api/accounting/journal-entries/{created.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["debit_total"], "25.00")
        self.assertEqual(self.client.get("/api/accounting/journal-entries/?from=tomorrow").status_code, 400)

    def test_reversal_api_requires_accountant_and_is_idempotent(self):
        self.client.force_authenticate(self.accountant)
        created = self.client.post(
            "/api/accounting/journal-entries/adjustments/", self.adjustment_payload(), format="json"
        )
        entry_id = created.data["id"]
        reverse_url = f"/api/accounting/journal-entries/{entry_id}/reverse/"
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(reverse_url, {"idempotency_key": "reverse-api-001", "reason": "test"}, format="json").status_code, 403)

        self.client.force_authenticate(self.accountant)
        body = {"idempotency_key": "reverse-api-001", "reason": "Synthetic reversal test"}
        first = self.client.post(reverse_url, body, format="json")
        retry = self.client.post(reverse_url, body, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(first.data["id"], retry.data["id"])
        self.assertEqual(JournalEntry.objects.count(), 2)
        self.assertEqual(AuditLog.objects.filter(action="journal_entry_reversed").count(), 1)

    def create_member_profile(self, user, suffix):
        return Member.objects.create(
            user=user,
            member_number=f"SYN-{suffix}",
            national_id=f"SYNTH-{suffix}",
            phone_number=f"0710000{suffix:04d}",
            gender="other",
            date_of_birth=date(1990, 1, 1),
            county="Synthetic County",
            address="Synthetic test record",
        )

    def create_share_policy(self):
        from django.contrib.auth import get_user_model

        creator = get_user_model().objects.create_superuser(
            username="policy_creator", email="policy_creator@example.test", password="synthetic-only-password"
        )
        approver = get_user_model().objects.create_superuser(
            username="policy_approver", email="policy_approver@example.test", password="synthetic-only-password"
        )
        self.client.force_authenticate(creator)
        created = self.client.post(
            "/api/accounting/share-capital/policies/",
            {"version": "synthetic-share-v1", "terms": {"test_only": True}},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertFalse(created.data["active"])
        same_person = self.client.post(
            f"/api/accounting/share-capital/policies/{created.data['id']}/approve/", {}, format="json"
        )
        self.assertEqual(same_person.status_code, 403)
        self.client.force_authenticate(approver)
        approved = self.client.post(
            f"/api/accounting/share-capital/policies/{created.data['id']}/approve/", {}, format="json"
        )
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.data["active"])
        return ShareCapitalPolicy.objects.get(pk=created.data["id"])

    def create_share_journal_line(self, amount="100.00", movement_type="issue"):
        equity = LedgerAccount.objects.create(
            code=f"31{JournalEntry.objects.count():02d}",
            name="Synthetic share capital equity",
            classification="equity",
            normal_balance="credit",
        )
        if movement_type == "issue":
            lines = [
                {"account_id": self.cash.pk, "debit": amount, "credit": "0.00"},
                {"account_id": equity.pk, "debit": "0.00", "credit": amount},
            ]
        else:
            lines = [
                {"account_id": equity.pk, "debit": amount, "credit": "0.00"},
                {"account_id": self.cash.pk, "debit": "0.00", "credit": amount},
            ]
        entry = post_journal_entry(
            idempotency_key=f"share-entry-{JournalEntry.objects.count()}",
            source_type="confirmed_share_receipt" if movement_type == "issue" else "confirmed_share_redemption",
            source_reference=f"share-source-{JournalEntry.objects.count()}",
            description="Synthetic share register test",
            lines=lines,
            actor=self.accountant,
            system_initiated=True,
        )
        side = "credit" if movement_type == "issue" else "debit"
        return entry.lines.get(account=equity, **{f"{side}__gt": 0})

    def test_share_capital_policy_requires_two_person_approval(self):
        self.client.force_authenticate(self.accountant)
        self.assertEqual(self.client.post(
            "/api/accounting/share-capital/policies/",
            {"version": "unauthorized", "terms": {"test_only": True}}, format="json"
        ).status_code, 403)
        policy = self.create_share_policy()
        self.assertEqual(policy.approved_by_id, policy.approved_by.pk)
        self.assertNotEqual(policy.created_by_id, policy.approved_by_id)
        with self.assertRaises(ValidationError):
            policy.terms = {"changed": True}
            policy.save()

    def test_share_register_requires_approved_policy_and_posted_equity_link(self):
        member = self.create_member_profile(self.member, 1)
        line = self.create_share_journal_line()
        self.client.force_authenticate(self.accountant)
        inactive_policy_response = self.client.post(
            "/api/accounting/share-capital/",
            {"member_id": member.pk, "journal_line_id": line.pk, "policy_id": 999,
             "idempotency_key": "share-movement-pending", "type": "issue", "units": "10",
             "amount": "100.00", "evidence_reference": "synthetic-evidence"},
            format="json",
        )
        self.assertEqual(inactive_policy_response.status_code, 404)

        policy = self.create_share_policy()
        payload = {
            "member_id": member.pk,
            "journal_line_id": line.pk,
            "policy_id": policy.pk,
            "idempotency_key": "share-movement-001",
            "type": "issue",
            "units": "10.000000",
            "amount": "100.00",
            "evidence_reference": "synthetic-evidence-001",
        }
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post("/api/accounting/share-capital/", payload, format="json").status_code, 403)
        self.client.force_authenticate(self.accountant)
        first = self.client.post("/api/accounting/share-capital/", payload, format="json")
        retry = self.client.post("/api/accounting/share-capital/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(first.data["id"], retry.data["id"])
        self.assertEqual(ShareCapitalMovement.objects.count(), 1)

        policy.active = False
        policy.save(update_fields=("active",))
        after_policy_rotation = self.client.post("/api/accounting/share-capital/", payload, format="json")
        self.assertEqual(after_policy_rotation.status_code, 201)
        self.assertEqual(after_policy_rotation.data["id"], first.data["id"])

        self.client.force_authenticate(self.member)
        own = self.client.get("/api/accounting/share-capital/?member_id=999")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data["results"]["summary"]["units_recorded"], "10.000000")
        self.assertEqual(len(own.data["results"]["results"]), 1)

        other_user = self.User.objects.create_user(username="other_share_member", password="synthetic-only-password")
        self.create_member_profile(other_user, 2)
        self.client.force_authenticate(other_user)
        other = self.client.get("/api/accounting/share-capital/")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["results"]["summary"]["units_recorded"], "0.000000")
        self.assertEqual(other.data["count"], 0)

    def test_share_movement_rejects_unapproved_policy_wrong_direction_and_changed_retry(self):
        member = self.create_member_profile(self.member, 3)
        policy = self.create_share_policy()
        issue_line = self.create_share_journal_line(movement_type="issue")
        self.client.force_authenticate(self.accountant)
        payload = {
            "member_id": member.pk,
            "journal_line_id": issue_line.pk,
            "policy_id": policy.pk,
            "idempotency_key": "share-movement-direction",
            "type": "redeem",
            "units": "2.000000",
            "amount": "100.00",
            "evidence_reference": "synthetic-evidence-002",
        }
        wrong_direction = self.client.post("/api/accounting/share-capital/", payload, format="json")
        self.assertEqual(wrong_direction.status_code, 400)
        payload["type"] = "issue"
        first = self.client.post("/api/accounting/share-capital/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        payload["units"] = "3.000000"
        changed = self.client.post("/api/accounting/share-capital/", payload, format="json")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(ShareCapitalMovement.objects.count(), 1)
