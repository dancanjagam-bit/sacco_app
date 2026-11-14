"""Acceptance tests for welfare module enhancements and workspace access scope."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.access import access_snapshot
from accounts.models import StaffRoleGrant
from accounts.welfare_models import WelfarePolicy, WelfareRequest, WelfareDocument
from members.models import Member

User = get_user_model()


class WelfareAcceptanceTests(APITestCase):
    """Verify welfare module access scope, permissions, and new features."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="wa-manager", is_superuser=True)
        cls.officer = User.objects.create_user(username="wa-officer")
        cls.member_user = User.objects.create_user(username="wa-member", is_member=True)
        cls.other_member = User.objects.create_user(username="wa-other", is_member=True)
        cls.non_member = User.objects.create_user(username="wa-nonmember", is_member=False)

        StaffRoleGrant.objects.create(
            user=cls.officer, role="welfare_officer",
            granted_by=cls.manager, reason="Acceptance test",
        )

        for number, user in enumerate((cls.member_user, cls.other_member), 1):
            Member.objects.create(
                user=user, member_number=f"WAM{number:04d}", national_id=f"WAM{number}",
                phone_number=f"254700000{number:04d}", gender="other",
                date_of_birth="1990-01-01", county="Test", address="Test", status="active",
            )

        WelfarePolicy.objects.create(
            version="wa-test-v1", approval_reference="Synthetic AGM minute",
            approved_by=cls.manager, active=True,
            benefits={
                "medical": {"maximum_benefit": "50000.00", "minimum_contributions": "2000.00"},
            },
        )

    def create_request(self, user=None, amount="5000.00"):
        """Create a welfare request as the member user."""
        self.client.force_authenticate(user or self.member_user)
        response = self.client.post(reverse("welfare-requests"), {
            "category": "medical", "description": "Acceptance test request",
            "requested_amount": amount,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    # ── Access scope tests ──────────────────────────────────────────────────

    def test_member_can_only_see_own_requests(self):
        """A member sees only their own welfare requests, never another member's."""
        self.create_request(self.member_user)
        self.create_request(self.other_member)
        self.client.force_authenticate(self.member_user)
        response = self.client.get(reverse("welfare-requests"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["category"], "medical")

    def test_officer_can_see_all_requests_with_committee_scope(self):
        """Welfare officer sees all requests when scope=committee."""
        self.create_request(self.member_user)
        self.create_request(self.other_member)
        self.client.force_authenticate(self.officer)
        response = self.client.get(reverse("welfare-requests") + "?scope=committee")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_non_member_cannot_submit_welfare_request(self):
        """A user without an active membership cannot submit welfare requests."""
        self.client.force_authenticate(self.non_member)
        response = self.client.post(reverse("welfare-requests"), {
            "category": "medical", "description": "Should fail",
            "requested_amount": "100.00",
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_access_committee_scope(self):
        """A regular member cannot access the officer/committee view."""
        self.client.force_authenticate(self.member_user)
        response = self.client.get(reverse("welfare-requests") + "?scope=committee")
        self.assertEqual(response.status_code, 403)

    # ── Welfare officer workspace summary ──────────────────────────────────

    def test_welfare_officer_workspace_summary(self):
        """The staff workspace summary endpoint returns metrics for welfare_officer."""
        self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        response = self.client.get(reverse("staff-workspace-summary", args=["welfare_officer"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["workspace"], "welfare_officer")
        self.assertTrue(any(m["id"] == "pending_cases" for m in response.data["metrics"]))
        self.assertTrue(any(m["id"] == "pooled_fund" for m in response.data["metrics"]))

    def test_member_cannot_access_welfare_officer_summary(self):
        """A member without welfare.review cannot access the welfare officer summary."""
        self.client.force_authenticate(self.member_user)
        response = self.client.get(reverse("staff-workspace-summary", args=["welfare_officer"]))
        self.assertEqual(response.status_code, 403)

    # ── Request additional information ─────────────────────────────────────

    def test_officer_can_request_additional_information(self):
        """Officer can request additional info, changing status to needs_information."""
        request_id = self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        response = self.client.post(
            reverse("welfare-request-info", args=[request_id]),
            {"notes": "Please provide a hospital bill receipt."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "needs_information")
        self.assertEqual(response.data["review_notes"], "Please provide a hospital bill receipt.")

    def test_member_can_resubmit_after_info_request(self):
        """Member can resubmit after officer requests information."""
        request_id = self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        self.client.post(
            reverse("welfare-request-info", args=[request_id]),
            {"notes": "Need more details."},
            format="json",
        )
        self.client.force_authenticate(self.member_user)
        response = self.client.post(reverse("welfare-resubmit", args=[request_id]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "submitted")

    def test_officer_cannot_decide_own_request(self):
        """A welfare officer cannot decide their own welfare request."""
        # Make the officer a member too
        Member.objects.create(
            user=self.officer, member_number="WAOFF001", national_id="WAOFF",
            phone_number="2547000009001", gender="other",
            date_of_birth="1990-01-01", county="Test", address="Test", status="active",
        )
        request_id = self.create_request(self.officer)
        self.client.force_authenticate(self.officer)
        response = self.client.post(
            reverse("welfare-decide", args=[request_id]),
            {"action": "reject", "reason": "Should fail"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    # ── Member dashboard ───────────────────────────────────────────────────

    def test_member_dashboard_returns_contributions_and_case_counts(self):
        """Member dashboard returns total contributions, case counts, and categories."""
        self.create_request(self.member_user)
        self.client.force_authenticate(self.member_user)
        response = self.client.get(reverse("welfare-member-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_contributions"], "0")
        self.assertEqual(response.data["case_counts"]["submitted"], 1)
        self.assertTrue(len(response.data["categories"]) > 0)

    def test_non_member_cannot_access_member_dashboard(self):
        self.client.force_authenticate(self.non_member)
        response = self.client.get(reverse("welfare-member-dashboard"))
        self.assertEqual(response.status_code, 403)

    # ── Officer dashboard ──────────────────────────────────────────────────

    def test_officer_dashboard_returns_case_counts_and_fund_balance(self):
        self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        response = self.client.get(reverse("welfare-officer-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue("case_counts" in response.data)
        self.assertTrue("pooled_fund_balance" in response.data)
        self.assertEqual(response.data["case_counts"]["submitted"], 1)

    def test_member_cannot_access_officer_dashboard(self):
        self.client.force_authenticate(self.member_user)
        response = self.client.get(reverse("welfare-officer-dashboard"))
        self.assertEqual(response.status_code, 403)

    # ── Approval permission boundary ───────────────────────────────────────

    def test_approve_without_policy_returns_conflict(self):
        """Approval requires a configured welfare policy for the category."""
        # Delete the policy and create a request in an unconfigured category.
        WelfarePolicy.objects.filter(active=True).update(active=False)
        request_id = self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        response = self.client.post(
            reverse("welfare-decide", args=[request_id]),
            {"action": "approve", "reason": "No policy test"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_reject_works_without_policy(self):
        """Rejection does not require a policy to be configured."""
        WelfarePolicy.objects.filter(active=True).update(active=False)
        request_id = self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        response = self.client.post(
            reverse("welfare-decide", args=[request_id]),
            {"action": "reject", "reason": "Rejected without policy"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "rejected")

    def test_duplicate_decision_returns_conflict(self):
        """Deciding an already-decided request returns 409."""
        request_id = self.create_request(self.member_user)
        self.client.force_authenticate(self.officer)
        self.client.post(
            reverse("welfare-decide", args=[request_id]),
            {"action": "reject", "reason": "First decision"},
            format="json",
        )
        response = self.client.post(
            reverse("welfare-decide", args=[request_id]),
            {"action": "approve", "reason": "Second attempt"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    # ── Access snapshot includes welfare_officer workspace ──────────────────

    def test_welfare_officer_has_welfare_workspace(self):
        """The access snapshot includes the welfare_officer workspace for an officer."""
        snapshot = access_snapshot(self.officer)
        workspace_ids = [ws["id"] for ws in snapshot["workspaces"]]
        self.assertIn("welfare_officer", workspace_ids)
        self.assertIn("welfare.review", snapshot["permissions"])

    def test_member_has_welfare_read_own_permission(self):
        """Members get welfare.read_own permission."""
        snapshot = access_snapshot(self.member_user)
        self.assertIn("welfare.read_own", snapshot["permissions"])
