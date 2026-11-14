from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.access import access_snapshot
from accounts.models import StaffDutyAssignment, StaffRoleGrant
from core.models import CRBCheck, Loan, LoanGuarantor, Transaction
from core.transport_models import (
    CrewAssignment, TransportRole, TransportRoute, Vehicle, VehicleOwnership,
)
from members.models import Member

User = get_user_model()


class WorkspaceAccessTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_superuser("workspace_manager", "manager@example.invalid", "synthetic-password")
        self.member = User.objects.create_user("workspace_member", password="synthetic-password", is_member=True)
        self.other_member = User.objects.create_user("workspace_other", password="synthetic-password", is_member=True)
        self.owner = User.objects.create_user("workspace_owner", password="synthetic-password", is_member=True)
        self.driver = User.objects.create_user("workspace_driver", password="synthetic-password", is_member=True)
        self.other_driver = User.objects.create_user("workspace_other_driver", password="synthetic-password", is_member=True)
        self.clerk = User.objects.create_user("workspace_clerk", password="synthetic-password", is_member=False)
        self.credit = User.objects.create_user("workspace_credit", password="synthetic-password", is_member=False)
        self.chairman = User.objects.create_user("workspace_chairman", password="synthetic-password", is_member=False)
        self.treasurer = User.objects.create_user("workspace_treasurer", password="synthetic-password", is_member=False)
        self.secretary = User.objects.create_user("workspace_secretary", password="synthetic-password", is_member=False)

        for user, number in ((self.member, "TEST000001"), (self.other_member, "TEST000002")):
            Member.objects.create(
                user=user, member_number=number, national_id=f"SYNTH-{number}", phone_number="254700000001",
                gender="other", date_of_birth="1990-01-01", county="Synthetic", address="Test only",
            )
        self.route = TransportRoute.objects.create(name="Workspace test route")
        self.vehicle = Vehicle.objects.create(registration="WS-TEST-01", owner=self.owner)
        self.other_vehicle = Vehicle.objects.create(registration="WS-TEST-02", owner=self.other_member)
        now = timezone.now()
        self.assignment = CrewAssignment.objects.create(
            vehicle=self.vehicle, route=self.route, driver=self.driver,
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=5), status="active",
            created_by=self.manager,
        )
        self.other_assignment = CrewAssignment.objects.create(
            vehicle=self.other_vehicle, route=self.route, driver=self.other_driver,
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=5), status="active",
            created_by=self.manager,
        )

    def grant_role(self, user, role):
        return StaffRoleGrant.objects.create(user=user, role=role, granted_by=self.manager, reason="Synthetic test grant")

    def duty(self, user, duty, **scope):
        return StaffDutyAssignment.objects.create(
            staff=user, duty=duty, assigned_by=self.manager, starts_at=timezone.now() - timedelta(minutes=1),
            reason="Synthetic scoped assignment", **scope,
        )

    def test_multiple_roles_produce_only_server_authorized_workspaces(self):
        self.grant_role(self.treasurer, "treasurer")
        TransportRole.objects.create(user=self.treasurer, role="owner")
        snapshot = access_snapshot(self.treasurer)
        self.assertEqual({"treasurer", "owner"}, {item["id"] for item in snapshot["workspaces"]})
        self.assertIn("payments.reconcile", snapshot["permissions"])
        self.assertIn("transport.read_owned", snapshot["permissions"])

    def test_superuser_gets_system_workspace_without_operational_roles(self):
        snapshot = access_snapshot(self.manager)
        self.assertEqual({"member", "staff"}, {item["id"] for item in snapshot["workspaces"]})
        self.assertIn("staff.manage", snapshot["permissions"])
        self.assertNotIn("payments.reconcile", snapshot["permissions"])
        self.assertNotIn("loans.approve_assigned", snapshot["permissions"])
        self.assertNotIn("clerk", snapshot["staff_roles"])

    def test_staff_role_grant_is_manager_only_and_revocation_removes_workspace(self):
        self.client.force_authenticate(self.member)
        denied = self.client.post("/api/admin/access/roles/", {"user_id": self.credit.pk, "role": "credit_officer", "reason": "test"}, format="json")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.manager)
        self_grant = self.client.post("/api/admin/access/roles/", {"user_id": self.manager.pk, "role": "treasurer", "reason": "self"}, format="json")
        self.assertEqual(self_grant.status_code, 403)
        granted = self.client.post("/api/admin/access/roles/", {"user_id": self.credit.pk, "role": "credit_officer", "reason": "assigned synthetic duties"}, format="json")
        self.assertEqual(granted.status_code, 201)
        self.client.force_authenticate(self.credit)
        self.assertIn("credit_officer", {item["id"] for item in access_snapshot(self.credit)["workspaces"]})
        self.client.force_authenticate(self.manager)
        revoked = self.client.post(f"/api/admin/access/roles/{granted.data['id']}/revoke/", {"reason": "test revocation"}, format="json")
        self.assertEqual(revoked.status_code, 200)
        self.client.force_authenticate(self.credit)
        self.assertNotIn("credit_officer", {item["id"] for item in access_snapshot(self.credit)["workspaces"]})
        self.assertEqual(self.client.get("/api/staff/workspaces/credit_officer/summary/").status_code, 403)

    def test_owner_and_crew_endpoints_do_not_expose_unrelated_vehicle_or_shift(self):
        TransportRole.objects.create(user=self.owner, role="owner")
        TransportRole.objects.create(user=self.driver, role="driver")
        self.client.force_authenticate(self.owner)
        vehicle_rows = self.client.get("/api/transport/vehicles/").data
        self.assertEqual([row["id"] for row in vehicle_rows], [self.vehicle.pk])
        self.assertEqual(self.client.get(f"/api/transport/owner/vehicles/{self.other_vehicle.pk}/").status_code, 404)

        TransportRole.objects.create(user=self.other_driver, role="driver")
        self.client.force_authenticate(self.other_driver)
        today = self.client.get("/api/transport/crew/today/")
        self.assertEqual(today.data["assignment"]["id"], self.other_assignment.pk)
        self.assertNotEqual(today.data["assignment"]["id"], self.assignment.pk)
        rejected = self.client.post("/api/transport/crew/today/", {
            "assignment": self.assignment.pk, "amount": "100.00", "client_key": "be5a2c10-2a8d-42ba-9a60-0d4c7a1f3901",
        }, format="json")
        self.assertEqual(rejected.status_code, 403)

    def test_owner_history_is_limited_to_their_effective_ownership_period(self):
        now = timezone.now()
        ownership = VehicleOwnership.objects.filter(vehicle=self.vehicle, owner=self.owner).first()
        ownership.starts_at = now - timedelta(days=7)
        ownership.save(update_fields=["starts_at"])
        self.vehicle.owner = self.other_member
        self.vehicle.save(update_fields=["owner"])
        ownership.refresh_from_db()
        ownership.ends_at = now - timedelta(days=2)
        ownership.save(update_fields=["ends_at"])
        inside_period = CrewAssignment.objects.create(
            vehicle=self.vehicle, route=self.route, driver=self.driver,
            starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=4),
            status="ended", created_by=self.manager,
        )
        outside_period = CrewAssignment.objects.create(
            vehicle=self.vehicle, route=self.route, driver=self.other_driver,
            starts_at=now - timedelta(days=1), ends_at=now - timedelta(hours=12),
            status="ended", created_by=self.manager,
        )
        TransportRole.objects.create(user=self.owner, role="owner")
        self.client.force_authenticate(self.owner)
        response = self.client.get(f"/api/transport/owner/vehicles/{self.vehicle.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["assignments"]], [inside_period.pk])
        self.assertNotIn(outside_period.pk, [row["id"] for row in response.data["assignments"]])

    def test_member_transaction_history_is_scoped_to_the_signed_in_account(self):
        own = Transaction.objects.create(user=self.member, type="deposit", account_type="fosa", amount="100.00")
        other = Transaction.objects.create(user=self.other_member, type="deposit", account_type="fosa", amount="900.00")
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/transactions/")
        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data.get("results", response.data)}
        self.assertIn(own.pk, returned_ids)
        self.assertNotIn(other.pk, returned_ids)

    def test_crew_history_contains_only_past_assignments_of_signed_in_crew(self):
        now = timezone.now()
        past = CrewAssignment.objects.create(
            vehicle=self.vehicle, route=self.route, driver=self.driver,
            starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1),
            status="ended", created_by=self.manager,
        )
        TransportRole.objects.create(user=self.driver, role="driver")
        self.client.force_authenticate(self.driver)
        response = self.client.get("/api/transport/crew/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [past.pk])
        self.client.force_authenticate(self.other_driver)
        denied = self.client.get("/api/transport/crew/history/")
        self.assertEqual(denied.status_code, 403)

    def test_clerk_queryset_and_assignment_create_are_vehicle_scoped(self):
        self.grant_role(self.clerk, "clerk")
        self.duty(self.clerk, "transport_assignment", vehicle=self.vehicle)
        TransportRole.objects.create(user=self.other_member, role="driver")
        TransportRole.objects.create(user=self.other_driver, role="driver")
        self.client.force_authenticate(self.clerk)
        rows = self.client.get("/api/transport/assignments/").data
        self.assertEqual({row["id"] for row in rows}, {self.assignment.pk})
        vehicle_rows = self.client.get("/api/transport/vehicles/").data
        self.assertEqual({row["id"] for row in vehicle_rows}, {self.vehicle.pk})

        response = self.client.post("/api/transport/assignments/", {
            "vehicle": self.other_vehicle.pk, "route": self.route.pk, "driver": self.other_member.pk,
            "starts_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "ends_at": (timezone.now() + timedelta(days=1, hours=8)).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CrewAssignment.objects.filter(vehicle=self.other_vehicle, driver=self.other_member).count(), 0)

    def test_appraisal_and_loan_decision_are_separate_scoped_permissions(self):
        appraisal_loan = Loan.objects.create(user=self.member, amount="5000.00", status="pending", repayment_months=6)
        unrelated_loan = Loan.objects.create(user=self.other_member, amount="6000.00", status="pending", repayment_months=6)
        self.grant_role(self.credit, "credit_officer")
        self.grant_role(self.chairman, "chairman")
        self.duty(self.credit, "loan_appraisal", loan=appraisal_loan)
        self.duty(self.chairman, "loan_approval", loan=unrelated_loan)
        guarantor = LoanGuarantor.objects.create(loan=appraisal_loan, guarantor=self.owner, status="accepted", message="Synthetic consent")
        crb = CRBCheck.objects.create(loan=appraisal_loan, member=self.member, provider="stub", status="needs_review", raw_response={"private": "must-not-be-returned"})

        self.client.force_authenticate(self.credit)
        visible = self.client.get("/api/admin/loans/")
        self.assertEqual(visible.status_code, 200)
        self.assertEqual({row["id"] for row in visible.data}, {appraisal_loan.pk})
        self.assertTrue(visible.data[0]["can_appraise"])
        self.assertFalse(visible.data[0]["can_decide"])
        self.assertEqual(self.client.get(f"/api/admin/loan/{appraisal_loan.pk}/guarantors/").data[0]["id"], guarantor.pk)
        crb_detail = self.client.get(f"/api/admin/crb-checks/{crb.pk}/")
        self.assertEqual(crb_detail.status_code, 200)
        self.assertNotIn("raw_response", crb_detail.data)
        self.assertEqual(self.client.post(f"/api/admin/loan/{appraisal_loan.pk}/approve/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.post(f"/api/admin/loan/{unrelated_loan.pk}/approve/", {}, format="json").status_code, 403)
        self.assertEqual(Loan.objects.get(pk=appraisal_loan.pk).status, "pending")

        self.client.force_authenticate(self.chairman)
        decisions = self.client.get("/api/admin/loans/")
        self.assertEqual({row["id"] for row in decisions.data}, {unrelated_loan.pk})
        self.assertTrue(decisions.data[0]["can_decide"])
        self.assertEqual(self.client.get(f"/api/admin/loan/{appraisal_loan.pk}/guarantors/").status_code, 403)

        self.grant_role(self.clerk, "credit_officer")
        self.client.force_authenticate(self.clerk)
        empty_queue = self.client.get("/api/admin/loans/")
        self.assertEqual(empty_queue.status_code, 200)
        self.assertEqual(empty_queue.data, [])

    def test_staff_workspace_summary_and_cash_issue_queues_use_scopes(self):
        from core.transport_models import TransportAssignmentIssue
        self.grant_role(self.clerk, "clerk")
        issue = TransportAssignmentIssue.objects.create(reported_by=self.driver, assignment=self.assignment, message="Synthetic issue")
        self.duty(self.clerk, "transport_issue", transport_issue=issue)
        self.client.force_authenticate(self.clerk)
        response = self.client.get("/api/transport/issues/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [issue.pk])
        self.assertEqual(self.client.get("/api/staff/workspaces/clerk/summary/").status_code, 200)
        resolve = self.client.post(f"/api/transport/issues/{issue.pk}/resolve/", {"reason": "Verified assignment and corrected the route record."}, format="json")
        self.assertEqual(resolve.status_code, 200)
        self.assertEqual(TransportAssignmentIssue.objects.get(pk=issue.pk).status, "resolved")
