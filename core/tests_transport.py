from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import AuditLog, StaffDutyAssignment, StaffProfile, StaffRoleGrant
from .models import Transaction
from .transport_models import (TransportRole, TransportRoute, Vehicle, CrewAssignment,
    TransportCollection, TransportExpense, TransportDeductionRule,
    TransportShiftClosure, TransportRemittance, TransportPayment,
    TransportPaymentReviewEvent, TransportPaymentAllocation, VehicleOwnership)

User = get_user_model()


class TransportPhaseOneTests(APITestCase):
    def setUp(self):
        self.staff=User.objects.create_user(username="ops",password="pass",is_staff=True,is_superuser=True)
        self.owner=User.objects.create_user(username="owner",password="pass")
        self.driver=User.objects.create_user(username="driver",password="pass",first_name="Test Driver")
        self.other=User.objects.create_user(username="other",password="pass")
        for u,r in ((self.owner,"owner"),(self.driver,"driver")):
            TransportRole.objects.create(user=u,role=r)
        self.route=TransportRoute.objects.create(name="Town - Market")
        self.vehicle=Vehicle.objects.create(registration="KAA 123A",owner=self.owner)
        self.assignment=CrewAssignment.objects.create(vehicle=self.vehicle,route=self.route,driver=self.driver,starts_at=timezone.now()-timedelta(hours=1),created_by=self.staff)

    def test_staff_can_create_assignment_and_historical_snapshot_persists(self):
        self.client.force_authenticate(self.staff)
        future = timezone.now() + timedelta(days=1)
        resp=self.client.post("/api/transport/assignments/",{"vehicle":self.vehicle.id,"route":self.route.id,"driver":self.driver.id,"starts_at":future.isoformat(),"ends_at":(future+timedelta(hours=8)).isoformat()},format="json")
        self.assertEqual(resp.status_code,409) # one open vehicle/driver assignment
        self.assignment.status="ended"; self.assignment.ends_at=timezone.now(); self.assignment.save()
        future = timezone.now() + timedelta(days=1)
        resp=self.client.post("/api/transport/assignments/",{"vehicle":self.vehicle.id,"route":self.route.id,"driver":self.driver.id,"starts_at":future.isoformat(),"ends_at":(future+timedelta(hours=8)).isoformat()},format="json")
        self.assertEqual(resp.status_code,201)
        self.route.name="Renamed route"; self.route.save()
        self.assertEqual(CrewAssignment.objects.get(pk=resp.data["id"]).route_label,"Town - Market")
        self.assertTrue(AuditLog.objects.filter(target__contains="Transport assignment").exists())

    def test_crew_scope_and_collection_idempotency(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/transport/crew/today/").data["assignment"],None)
        self.client.force_authenticate(self.driver)
        self.assertEqual(self.client.get("/api/transport/crew/today/").data["assignment"]["id"],self.assignment.id)
        key=str(uuid.uuid4()); body={"assignment":self.assignment.id,"amount":"1250.50","notes":"Cash","client_key":key}
        one=self.client.post("/api/transport/crew/today/",body,format="json")
        two=self.client.post("/api/transport/crew/today/",body,format="json")
        self.assertEqual(one.status_code,201); self.assertEqual(two.status_code,200)
        self.assertTrue(two.data["duplicate"])
        self.assertEqual(TransportCollection.objects.count(),1)
        self.assertEqual(TransportCollection.objects.aggregate(total=__import__("django.db.models",fromlist=["Sum"]).Sum("amount"))["total"],Decimal("1250.50"))

    def test_collection_is_assignment_scoped(self):
        self.client.force_authenticate(self.other)
        response=self.client.post("/api/transport/crew/today/",{"assignment":self.assignment.id,"amount":"500","client_key":str(uuid.uuid4())},format="json")
        self.assertEqual(response.status_code,403)
        self.assertEqual(TransportCollection.objects.count(),0)

    def test_staff_role_assignment_endpoint_and_duplicate_key_conflict(self):
        self.client.force_authenticate(self.staff)
        response=self.client.post("/api/transport/roles/",{"user":self.other.id,"role":"driver","reason":"Test grant"},format="json")
        self.assertEqual(response.status_code,201)
        self.assertTrue(TransportRole.objects.filter(user=self.other,role="driver",active=True).exists())
        self.client.force_authenticate(self.driver)
        key=str(uuid.uuid4()); body={"assignment":self.assignment.id,"amount":"100","notes":"one","client_key":key}
        self.assertEqual(self.client.post("/api/transport/crew/today/",body,format="json").status_code,201)
        body["amount"]="101"
        self.assertEqual(self.client.post("/api/transport/crew/today/",body,format="json").status_code,409)
        self.assertEqual(TransportCollection.objects.count(),1)

    def test_staff_user_picker_includes_active_transport_roles_and_is_staff_only(self):
        self.client.force_authenticate(self.staff)
        response=self.client.get("/api/transport/staff/users/")
        self.assertEqual(response.status_code,200)
        users={row["id"]:row for row in response.data}
        self.assertEqual(users[self.owner.id]["transport_roles"],["owner"])
        self.assertEqual(users[self.driver.id]["transport_roles"],["driver"])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/transport/staff/users/").status_code,403)

    def test_staff_setup_workflow_creates_roles_route_vehicle_and_optional_conductor_assignment(self):
        self.client.force_authenticate(self.staff)
        owner_role = self.client.post("/api/transport/roles/", {"user": self.other.id, "role": "owner", "reason": "Acceptance test grant"}, format="json")
        driver_role = self.client.post("/api/transport/roles/", {"user": self.other.id, "role": "driver", "reason": "Acceptance test grant"}, format="json")
        self.assertEqual(owner_role.status_code, 201)
        self.assertIn(driver_role.status_code, (200, 201))
        route = self.client.post("/api/transport/routes/", {
            "name": "Operations acceptance route", "origin": "Synthetic start", "destination": "Synthetic end",
        }, format="json")
        self.assertEqual(route.status_code, 201)
        vehicle = self.client.post("/api/transport/vehicles/", {
            "registration": "TEST-OPS-NEW", "owner": self.other.id, "make_model": "Synthetic tuk tuk",
        }, format="json")
        self.assertEqual(vehicle.status_code, 201)
        assignment = self.client.post("/api/transport/assignments/", {
            "vehicle": vehicle.data["id"], "route": route.data["id"], "driver": self.other.id,
            "starts_at": timezone.now().isoformat(),
            "ends_at": (timezone.now() + timedelta(hours=8)).isoformat(),
        }, format="json")
        self.assertEqual(assignment.status_code, 201)
        self.assertIsNone(assignment.data["conductor"])
        self.assertEqual(assignment.data["route_name"], "Operations acceptance route")
        self.assertEqual(assignment.data["vehicle_registration"], "TEST-OPS-NEW")

    def test_today_excludes_future_and_expired_assignments(self):
        now=timezone.now()
        self.assignment.starts_at=now+timedelta(hours=1); self.assignment.ends_at=now+timedelta(hours=2); self.assignment.status="scheduled"; self.assignment.save()
        self.client.force_authenticate(self.driver)
        self.assertIsNone(self.client.get("/api/transport/crew/today/").data["assignment"])
        self.assignment.starts_at=now-timedelta(hours=3); self.assignment.ends_at=now-timedelta(hours=1); self.assignment.status="ended"; self.assignment.save()
        self.assertIsNone(self.client.get("/api/transport/crew/today/").data["assignment"])

    def test_schedule_conflicts_rejected_and_non_overlapping_future_schedule_allowed(self):
        self.client.force_authenticate(self.staff)
        now=timezone.now()
        self.assignment.status="ended"; self.assignment.ends_at=now; self.assignment.save()
        body={"vehicle":self.vehicle.id,"route":self.route.id,"driver":self.driver.id,"starts_at":(now+timedelta(hours=1)).isoformat(),"ends_at":(now+timedelta(hours=3)).isoformat()}
        first=self.client.post("/api/transport/assignments/",body,format="json")
        self.assertEqual(first.status_code,201)
        conflict=dict(body); conflict["starts_at"]=(now+timedelta(hours=2)).isoformat(); conflict["ends_at"]=(now+timedelta(hours=4)).isoformat()
        self.assertEqual(self.client.post("/api/transport/assignments/",conflict,format="json").status_code,409)
        after=dict(body); after["starts_at"]=(now+timedelta(hours=4)).isoformat(); after["ends_at"]=(now+timedelta(hours=5)).isoformat()
        self.assertEqual(self.client.post("/api/transport/assignments/",after,format="json").status_code,201)

    def test_assignment_label_snapshots_survive_vehicle_route_and_crew_renames(self):
        self.vehicle.registration="KBB 999Z"; self.vehicle.save(); self.route.name="New route"; self.route.save(); self.driver.first_name="Changed"; self.driver.save()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.vehicle_label,"KAA 123A")
        self.assertEqual(self.assignment.route_label,"Town - Market")
        self.assertEqual(self.assignment.driver_label,"Test Driver")

    def test_collection_requires_matching_active_role_and_exact_amount(self):
        self.client.force_authenticate(self.driver)
        url = "/api/transport/collections/"
        payload = {"assignment": self.assignment.id, "client_key": str(uuid.uuid4()), "amount": "500.51"}
        for amount in ("0", "-1.00", "1.001", "10000000000.00", "NaN", "1e99999"):
            with self.subTest(amount=amount):
                self.assertEqual(self.client.post(url, payload | {"amount": amount}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, payload | {"recorded_by": self.other.id}, format="json").status_code, 403)
        TransportRole.objects.filter(user=self.driver, role="driver").update(active=False)
        TransportRole.objects.create(user=self.driver, role="conductor")
        self.assertIsNone(self.client.get("/api/transport/crew/today/").data["assignment"])
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 403)
        self.assertEqual(TransportCollection.objects.count(), 0)

    def test_staff_ends_legacy_assignment_with_audit_without_closing_shift(self):
        self.client.force_authenticate(self.driver)
        url = f"/api/transport/assignments/{self.assignment.id}/end/"
        body = {"reason": "The driver has handed over the vehicle."}
        payload = {"assignment": self.assignment.id, "client_key": str(uuid.uuid4()), "amount": "31.20"}
        self.assertEqual(self.client.post(url, body, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/transport/collections/", payload, format="json").status_code, 201)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        response = self.client.post(url, body, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ended")
        self.assertNotEqual(response.data["shift_status"], "closed")
        self.assignment.refresh_from_db()
        self.assertIsNotNone(self.assignment.ends_at)
        self.assertTrue(AuditLog.objects.filter(details__reason=body["reason"], actor=self.staff).exists())
        self.client.force_authenticate(self.driver)
        self.assertFalse(self.client.get("/api/transport/crew/today/").data["assignment"]["can_record_collection"])
        self.assertEqual(self.client.post("/api/transport/collections/", payload, format="json").status_code, 200)
        new_payload = payload | {"client_key": str(uuid.uuid4())}
        self.assertEqual(self.client.post("/api/transport/collections/", new_payload, format="json").status_code, 409)
        end = self.assignment.ends_at
        self.assertEqual(self.client.post("/api/transport/shifts/close/", {"assignment": self.assignment.id}, format="json").status_code, 201)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.ends_at, end)


class TransportWorkflowAcceptanceTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="transport-accountant", password="test-pass", is_staff=True)
        StaffProfile.objects.create(user=self.staff, role="secretary", status="active")
        self.manager = User.objects.create_user(username="transport-system-manager", password="test-pass",
            is_staff=True, is_superuser=True)
        self.owner = User.objects.create_user(username="transport-owner-a", password="test-pass")
        self.second_owner = User.objects.create_user(username="transport-owner-b", password="test-pass")
        self.driver = User.objects.create_user(username="transport-driver-a", password="test-pass", first_name="Driver A")
        self.conductor = User.objects.create_user(username="transport-conductor", password="test-pass", first_name="Conductor")
        self.other = User.objects.create_user(username="transport-other", password="test-pass")
        for user, role in ((self.owner, "owner"), (self.second_owner, "owner"),
                           (self.driver, "driver"), (self.conductor, "conductor"), (self.other, "driver")):
            TransportRole.objects.create(user=user, role=role, active=True)
        self.route = TransportRoute.objects.create(name="Acceptance route")
        self.vehicle = Vehicle.objects.create(registration="TEST-WORKFLOW-1", owner=self.owner)
        now = timezone.now()
        ownership_start = VehicleOwnership.objects.get(vehicle=self.vehicle, ends_at__isnull=True).starts_at
        self.assignment = CrewAssignment.objects.create(vehicle=self.vehicle, route=self.route,
            driver=self.driver, conductor=self.conductor, starts_at=ownership_start,
            ends_at=now+timedelta(hours=5), status="active", created_by=self.staff)
        # This test operator performs two different authorized duties: treasury
        # expense review and clerk confirmation for this exact crew assignment.
        # Neither permission comes from the Django staff flag or title alone.
        for role in ("clerk", "treasurer"):
            StaffRoleGrant.objects.create(user=self.staff, role=role, granted_by=self.staff,
                reason="Synthetic transport workflow test role.")
        StaffDutyAssignment.objects.create(staff=self.staff, duty="cash_handover",
            crew_assignment=self.assignment, assigned_by=self.staff,
            reason="Synthetic cash handover test scope.")
        StaffDutyAssignment.objects.create(staff=self.staff, duty="transport_assignment",
            crew_assignment=self.assignment, assigned_by=self.staff,
            reason="Synthetic assignment management test scope.")

    def record_collection(self, amount="1000.00", client_key=None):
        self.client.force_authenticate(self.driver)
        return self.client.post("/api/transport/crew/today/", {
            "assignment": self.assignment.id, "amount": amount, "notes": "synthetic fares",
            "client_key": client_key or str(uuid.uuid4()),
        }, format="json")

    def report_expense(self, category, amount):
        self.client.force_authenticate(self.driver)
        return self.client.post("/api/transport/expenses/", {
            "assignment": self.assignment.id, "category": category, "amount": amount,
            "notes": "synthetic report", "client_key": str(uuid.uuid4()),
        }, format="json")

    def review_expense(self, expense_id, action="approve"):
        self.client.force_authenticate(self.staff)
        return self.client.post(f"/api/transport/expenses/{expense_id}/review/", {
            "action": action, "reason": "Synthetic acceptance review",
        }, format="json")

    def close_shift(self):
        self.client.force_authenticate(self.driver)
        return self.client.post("/api/transport/shifts/close/", {"assignment": self.assignment.id}, format="json")

    def test_close_without_approved_rule_keeps_amount_uncomputed_and_separate_from_payment(self):
        collection_key = str(uuid.uuid4())
        self.assertEqual(self.record_collection(client_key=collection_key).status_code, 201)
        expense = self.report_expense("fuel", "100.00")
        self.assertEqual(expense.status_code, 201)
        self.assertEqual(expense.data["status"], "reported")
        self.assertEqual(self.review_expense(expense.data["id"]).status_code, 200)

        closed = self.close_shift()
        self.assertEqual(closed.status_code, 201)
        self.assertEqual(closed.data["reported_gross"], "1000.00")
        self.assertEqual(closed.data["approved_expenses"], "100.00")
        self.assertIsNone(closed.data["expected_remittance"])
        self.assertEqual(closed.data["calculation_status"], "rule_required")
        duplicate = self.close_shift()
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(TransportShiftClosure.objects.count(), 1)
        self.assertEqual(TransportRemittance.objects.count(), 0)

        self.client.force_authenticate(self.driver)
        today = self.client.get("/api/transport/crew/today/")
        self.assertEqual(today.status_code, 200)
        self.assertEqual(today.data["assignment"]["shift_status"], "closed")
        blocked = self.client.post("/api/transport/remittances/", {
            "assignment": self.assignment.id, "amount": "900.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("deduction rule", blocked.data["detail"])
        after_close = self.client.post("/api/transport/crew/today/", {
            "assignment": self.assignment.id, "amount": "5.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.assertIn(after_close.status_code, (403, 409))
        self.client.force_authenticate(self.driver)
        retry_after_close = self.client.post("/api/transport/crew/today/", {
            "assignment": self.assignment.id, "amount": "1000.00", "notes": "synthetic fares",
            "client_key": collection_key,
        }, format="json")
        self.assertEqual(retry_after_close.status_code, 200)
        self.assertTrue(retry_after_close.data["duplicate"])
        self.assertEqual(TransportCollection.objects.count(), 1)

    def test_closing_at_exact_assignment_start_uses_a_valid_period_boundary(self):
        self.assertEqual(self.record_collection().status_code, 201)
        starts_at = timezone.now()
        self.assignment.starts_at = starts_at
        self.assignment.ends_at = starts_at + timedelta(hours=5)
        self.assignment.save(update_fields=["starts_at", "ends_at"])

        with patch("core.transport_views.timezone.now", return_value=starts_at):
            closed = self.close_shift()

        self.assertEqual(closed.status_code, 201)
        self.assignment.refresh_from_db()
        self.assertGreater(self.assignment.ends_at, starts_at)
        self.assertEqual(self.assignment.ends_at, self.assignment.shift.ends_at)

    def test_future_assignment_cannot_be_closed_early_by_staff(self):
        starts_at = timezone.now() + timedelta(hours=1)
        self.assignment.starts_at = starts_at
        self.assignment.ends_at = starts_at + timedelta(hours=5)
        self.assignment.status = "scheduled"
        self.assignment.save(update_fields=["starts_at", "ends_at", "status"])
        self.assignment.shift.starts_at = starts_at
        self.assignment.shift.status = "scheduled"
        self.assignment.shift.save(update_fields=["starts_at", "status"])

        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/transport/shifts/close/", {"assignment": self.assignment.id}, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(TransportShiftClosure.objects.filter(shift=self.assignment.shift).exists())

    def test_approved_rule_cash_handover_partial_confirmation_receipt_and_owner_summary(self):
        TransportDeductionRule.objects.create(version="acceptance-policy-v1", deductible_categories=["fuel"],
            approval_reference="SYNTHETIC-APPROVAL", active=True, approved_by=self.staff, approved_at=timezone.now())
        self.assertEqual(self.record_collection().status_code, 201)
        fuel = self.report_expense("fuel", "100.00")
        other = self.report_expense("repairs", "50.00")
        self.assertEqual(fuel.status_code, 201)
        self.assertEqual(other.status_code, 201)
        self.assertEqual(self.review_expense(fuel.data["id"]).status_code, 200)
        self.assertEqual(self.review_expense(other.data["id"]).status_code, 200)

        close = self.close_shift()
        self.assertEqual(close.data["approved_expenses"], "150.00")
        self.assertEqual(close.data["deductible_expenses"], "100.00")
        self.assertEqual(close.data["expected_remittance"], "900.00")
        self.assertEqual(close.data["deduction_rule_version"], "acceptance-policy-v1")

        self.client.force_authenticate(self.driver)
        remittance = self.client.post("/api/transport/remittances/", {
            "assignment": self.assignment.id, "amount": "900.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(remittance.status_code, 201)
        self.assertEqual(remittance.data["received_amount"], "0.00")
        wrong_amount = self.client.post("/api/transport/remittances/", {
            "assignment": self.assignment.id, "amount": "899.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(wrong_amount.status_code, 409)

        handover_payload = {"amount": "400.00", "client_key": str(uuid.uuid4())}
        handover = self.client.post(f"/api/transport/remittances/{remittance.data['id']}/cash/", handover_payload, format="json")
        self.assertEqual(handover.status_code, 201)
        self.assertEqual(handover.data["status"], "pending")
        self.assertIsNone(TransportPayment.objects.get(pk=handover.data["id"]).received_amount)
        duplicate_handover = self.client.post(f"/api/transport/remittances/{remittance.data['id']}/cash/", handover_payload, format="json")
        self.assertEqual(duplicate_handover.status_code, 200)
        self.assertTrue(duplicate_handover.data["duplicate"])
        self.assertEqual(TransportPayment.objects.filter(remittance__public_id=remittance.data["id"]).count(), 1)
        self.client.force_authenticate(self.staff)
        confirm = self.client.post("/api/transport/payment-queue/", {
            "payment_id": handover.data["id"], "confirm": True, "received_amount": "400.00", "reason": "Cash counted at clerk desk",
        }, format="json")
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.data["received_amount"], "400.00")
        remittance_row = TransportRemittance.objects.get(public_id=remittance.data["id"])
        self.assertEqual(remittance_row.status, "partial")
        duplicate_confirm = self.client.post("/api/transport/payment-queue/", {
            "payment_id": handover.data["id"], "confirm": True, "received_amount": "400.00", "reason": "Duplicate confirmation attempt",
        }, format="json")
        self.assertEqual(duplicate_confirm.status_code, 409)

        self.client.force_authenticate(self.driver)
        second_handover = self.client.post(f"/api/transport/remittances/{remittance.data['id']}/cash/", {
            "amount": "500.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(second_handover.status_code, 201)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post("/api/transport/payment-queue/", {
            "payment_id": second_handover.data["id"], "confirm": True, "received_amount": "500.00", "reason": "Second partial counted",
        }, format="json").status_code, 200)
        self.assertEqual(remittance_row.refresh_from_db(), None)
        self.assertEqual(remittance_row.status, "confirmed")
        self.assertEqual(TransportPayment.objects.filter(status="confirmed").count(), 2)
        self.assertEqual(TransportPayment.objects.filter(received_amount__isnull=True).count(), 0)

        confirmed_cash = TransportPayment.objects.get(remittance=remittance_row, received_amount="400.00")
        linked_entry = Transaction.objects.create(
            user=self.driver, type="repayment", account_type="loan", amount="400.00",
            note="Synthetic transport-linked account activity",
        )
        TransportPaymentAllocation.objects.create(
            payment=confirmed_cash, category="loan_repayment", amount="400.00",
            rule_version="acceptance-policy-v1", transaction=linked_entry,
            reviewed_by=self.staff, reviewed_at=timezone.now(),
        )

        self.client.force_authenticate(self.owner)
        owner_data = self.client.get("/api/transport/owner/")
        self.assertEqual(owner_data.status_code, 200)
        vehicle_data = owner_data.data["vehicles"][0]
        self.assertEqual(vehicle_data["reported_collections_today"], "1000.00")
        self.assertEqual(vehicle_data["reported_expenses_today"], "150.00")
        self.assertEqual(vehicle_data["confirmed_receipts"], "900.00")
        self.assertEqual(vehicle_data["pending_remittance_amount"], "0.00")
        linked = vehicle_data["remittances"][0]["payments"][0]["account_activity"]
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["transaction_id"], linked_entry.pk)
        self.assertEqual(linked[0]["transaction_type"], "repayment")
        self.assertEqual(linked[0]["account_type"], "loan")
        receipt = self.client.get(f"/api/transport/remittances/{remittance.data['id']}/receipt/")
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.data["received_amount"], "900.00")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/transport/owner/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/transport/owner/vehicles/{self.vehicle.id}/").status_code, 403)

    def test_cash_count_difference_is_confirmed_as_received_and_kept_in_review(self):
        TransportDeductionRule.objects.create(version="acceptance-policy-cash-v1", deductible_categories=[],
            approval_reference="SYNTHETIC-APPROVAL", active=True, approved_by=self.staff, approved_at=timezone.now())
        self.assertEqual(self.record_collection().status_code, 201)
        self.assertEqual(self.close_shift().status_code, 201)
        self.client.force_authenticate(self.driver)
        remittance = self.client.post("/api/transport/remittances/", {
            "assignment": self.assignment.id, "amount": "1000.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(remittance.status_code, 201)
        handover = self.client.post(f"/api/transport/remittances/{remittance.data['id']}/cash/", {
            "amount": "400.00", "client_key": str(uuid.uuid4()),
        }, format="json")
        self.client.force_authenticate(self.staff)
        confirmed = self.client.post("/api/transport/payment-queue/", {
            "payment_id": handover.data["id"], "confirm": True, "received_amount": "375.00",
            "reason": "Counted cash differs from submitted handover",
        }, format="json")
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.data["status"], "needs_review")
        payment = TransportPayment.objects.get(pk=handover.data["id"])
        self.assertEqual(payment.amount, Decimal("400.00"))
        self.assertEqual(payment.received_amount, Decimal("375.00"))
        self.assertEqual(payment.unallocated_amount, Decimal("375.00"))
        self.assertEqual(TransportRemittance.objects.get(public_id=remittance.data["id"]).status, "partial")
        queue = self.client.get("/api/transport/payment-queue/")
        item = next(row for row in queue.data if row.get("id") == payment.id)
        self.assertEqual(item["reported_amount"], "400.00")
        self.assertEqual(item["received_amount"], "375.00")
        self.assertIn("uncertain_or_disputed", item["queue_reasons"])

    def test_owner_history_is_scoped_to_effective_ownership_periods(self):
        self.client.force_authenticate(self.manager)
        active_transfer = self.client.post(f"/api/transport/vehicles/{self.vehicle.id}/owner/", {
            "owner": self.second_owner.id,
        }, format="json")
        self.assertEqual(active_transfer.status_code, 409)
        second_driver = User.objects.create_user(username="transport-driver-b", password="test-pass", first_name="Driver B")
        TransportRole.objects.create(user=second_driver, role="driver", active=True)
        ownership_boundary = timezone.now()
        self.assignment.status = "ended"
        self.assignment.ends_at = ownership_boundary
        self.assignment.save(update_fields=["status", "ends_at"])
        transfer = self.client.post(f"/api/transport/vehicles/{self.vehicle.id}/owner/", {
            "owner": self.second_owner.id,
        }, format="json")
        self.assertEqual(transfer.status_code, 200)
        next_assignment = self.client.post("/api/transport/assignments/", {
            "vehicle": self.vehicle.id, "route": self.route.id, "driver": second_driver.id,
            "starts_at": (ownership_boundary + timedelta(seconds=1)).isoformat(),
            "ends_at": (ownership_boundary + timedelta(hours=4)).isoformat(),
        }, format="json")
        self.assertEqual(next_assignment.status_code, 201)

        self.client.force_authenticate(self.owner)
        old_data = self.client.get(f"/api/transport/owner/vehicles/{self.vehicle.id}/")
        self.assertEqual(old_data.status_code, 200)
        self.assertEqual([row["id"] for row in old_data.data["assignments"]], [self.assignment.id])
        self.assertEqual(old_data.data["current_owner"], False)
        self.assertEqual(old_data.data["owner_label"], "No longer owned by you")

        self.client.force_authenticate(self.second_owner)
        new_data = self.client.get(f"/api/transport/owner/vehicles/{self.vehicle.id}/")
        self.assertEqual(new_data.status_code, 200)
        self.assertEqual([row["id"] for row in new_data.data["assignments"]], [next_assignment.data["id"]])
        self.assertNotIn(self.driver.get_full_name(), str(new_data.data))

    def test_duplicate_c2b_callback_is_idempotent_and_conflicting_receipt_is_queued(self):
        remittance = TransportRemittance.objects.create(requested_by=self.driver, payer=self.driver,
            assignment=self.assignment, shift=self.assignment.shift, vehicle=self.vehicle, route=self.route,
            amount=Decimal("500.00"), idempotency_key=uuid.uuid4())
        payload = {"TransID": "ACCEPT12345", "TransAmount": "300.00", "BillRefNumber": remittance.payment_reference,
            "MSISDN": "254700000001", "FirstName": "Synthetic", "LastName": "Payer"}
        first = self.client.post("/api/payments/mpesa/c2b/confirmation/", payload, format="json")
        second = self.client.post("/api/payments/mpesa/c2b/confirmation/", payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(TransportPayment.objects.filter(mpesa_receipt="ACCEPT12345").count(), 1)
        self.assertEqual(TransportPayment.objects.get(mpesa_receipt="ACCEPT12345").received_amount, Decimal("300.00"))
        conflict = dict(payload, TransAmount="350.00")
        self.assertEqual(self.client.post("/api/payments/mpesa/c2b/confirmation/", conflict, format="json").status_code, 200)
        self.assertEqual(TransportPayment.objects.filter(mpesa_receipt="ACCEPT12345").count(), 1)
        self.assertEqual(TransportPaymentReviewEvent.objects.filter(status="pending").count(), 1)
        self.client.force_authenticate(self.staff)
        queue = self.client.get("/api/transport/payment-queue/")
        self.assertEqual(queue.status_code, 200)
        self.assertTrue(any(row.get("kind") == "duplicate_callback" for row in queue.data))
        forbidden_manual_confirm = self.client.post("/api/transport/payment-queue/", {
            "payment_id": TransportPayment.objects.get(mpesa_receipt="ACCEPT12345").id,
            "confirm": True, "reason": "Do not permit staff to confirm electronic funds",
        }, format="json")
        self.assertEqual(forbidden_manual_confirm.status_code, 409)
