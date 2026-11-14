from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import AuditLog, StaffDutyAssignment, StaffRoleGrant
from core.models import Loan, Transaction
from core.transport_models import (
    CrewAssignment, TransportCollection, TransportPayment, TransportRemittance, TransportRoute, Vehicle,
)
from members.models import Member


class GovernanceTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.manager = users.create_user(username="governance-manager", is_superuser=True)
        cls.secretary = users.create_user(username="governance-secretary", is_member=False)
        cls.chairman = users.create_user(username="governance-chairman", is_member=False)
        cls.credit = users.create_user(username="governance-credit", is_member=False)
        cls.member = users.create_user(username="governance-member", is_member=True)
        Member.objects.create(
            user=cls.member, member_number="TEST-GOVERNANCE", national_id="SYNTH-GOVERNANCE",
            phone_number="254700000001", gender="other", date_of_birth="1990-01-01",
            county="Synthetic", address="Test only", status="active",
        )
        for user, role in ((cls.secretary, "secretary"), (cls.chairman, "chairman"), (cls.credit, "credit_officer")):
            StaffRoleGrant.objects.create(user=user, role=role, granted_by=cls.manager, reason="Synthetic test")

    def test_secretary_records_meeting_and_validates_updates(self):
        url = "/api/secretary/meetings/"
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.secretary)
        response = self.client.post(url, {
            "title": "Committee meeting", "meeting_type": "committee", "scheduled_at": "2026-11-24T09:00",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["scheduled_at"].utcoffset(), timedelta(hours=3))
        detail = f"{url}{response.data['id']}/"
        self.assertEqual(self.client.patch(detail, {"status": "invalid"}, format="json").status_code, 400)
        response = self.client.patch(detail, {
            "status": "completed", "minutes": "Members approved the agenda.", "quorum_met": False,
        }, format="json")
        self.assertEqual(response.data["status"], "completed")
        self.assertFalse(response.data["quorum_met"])
        self.assertTrue(AuditLog.objects.filter(actor=self.secretary, target__contains="Meeting").exists())

    def test_only_published_current_notices_reach_active_members(self):
        url = "/api/secretary/notices/"
        self.client.force_authenticate(self.secretary)
        draft = self.client.post(url, {"title": "Draft", "body": "Draft body"}, format="json")
        self.assertEqual(draft.status_code, 201)
        current = self.client.post(url, {
            "title": "Current notice", "body": "Current body", "status": "published",
        }, format="json")
        self.assertEqual(current.status_code, 201)
        expired = self.client.post(url, {
            "title": "Expired", "body": "Expired body", "status": "published",
            "expires_at": (timezone.now() - timedelta(days=1)).isoformat(),
        }, format="json")
        self.assertEqual(expired.status_code, 201)
        self.assertEqual(self.client.get("/api/notifications/").data["member_notices"], [])
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        visible = self.client.get("/api/notifications/").data["member_notices"]
        self.assertEqual([notice["title"] for notice in visible], ["Current notice"])
        Member.objects.filter(user=self.member).update(status="suspended")
        self.assertEqual(self.client.get("/api/notifications/").data["member_notices"], [])

    def test_arrears_uses_cumulative_schedule_and_current_credit_duty(self):
        now = timezone.now()
        loan = Loan.objects.create(
            user=self.member, amount="10.00", balance="9.00", interest="5.00", repayment_months=3,
            approved_at=now - relativedelta(months=4), status="approved",
        )
        other = Loan.objects.create(
            id=loan.pk * 10, user=self.member, amount="1.00", balance="1.00", repayment_months=1,
            approved_at=now - relativedelta(months=4), status="approved",
        )
        Transaction.objects.create(user=self.member, amount="1.50", type="repayment", note=f"Loan #{loan.pk}")
        Transaction.objects.create(user=self.member, amount="1.00", type="repayment", note=f"Loan #{other.pk}")
        url = "/api/admin/arrears/"
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.credit)
        self.assertEqual(self.client.get(url).data["loans"], [])
        StaffDutyAssignment.objects.create(
            staff=self.credit, loan=loan, duty="loan_appraisal",
            assigned_by=self.manager, reason="Synthetic scoped arrears review",
        )
        result = self.client.get(url).data
        self.assertEqual([row["loan_id"] for row in result["loans"]], [loan.pk])
        self.assertEqual(result["total_overdue_amount"], 9.00)
        self.assertEqual(result["loans"][0]["overdue_installments"], 3)

    def test_chairman_overview_counts_received_remittances_only(self):
        now = timezone.now()
        vehicle = Vehicle.objects.create(owner=self.member, registration="TEST-GOV-1")
        route = TransportRoute.objects.create(name="Synthetic route")
        assignment = CrewAssignment.objects.create(vehicle=vehicle, route=route, driver=self.member, starts_at=now)
        import uuid
        TransportCollection.objects.create(
            assignment=assignment, recorded_by=self.member, amount="350.00", client_key=uuid.uuid4(),
        )
        remittance = TransportRemittance.objects.create(
            requested_by=self.member, assignment=assignment, shift=assignment.shift,
            vehicle=vehicle, route=route, amount="300.00", idempotency_key=uuid.uuid4(),
        )
        TransportPayment.objects.create(
            remittance=remittance, method="cash", amount="100.00",
            received_amount="95.20", status="needs_review", confirmed_at=now,
        )
        TransportPayment.objects.create(remittance=remittance, method="cash", amount="200.00")
        Loan.objects.create(user=self.member, amount="100.00", balance="55.00", status="approved")
        url = "/api/admin/chairman/summary/"
        self.client.force_authenticate(self.credit)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.chairman)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["confirmed_remittances_this_month"], 95.20)
        self.assertEqual(response.data["loan_balance_outstanding"], 55.00)
        self.assertEqual(len(response.data["monthly_remittances"]), 6)
