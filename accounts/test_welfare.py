from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APITestCase

from accounting.models import JournalEntry, LedgerAccount
from accounting.services import post_journal_entry, reverse_journal_entry
from members.models import Member
from .access import access_snapshot
from .models import AuditLog, StaffRoleGrant
from .welfare_models import WelfareDocument, WelfarePolicy


class WelfareTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.manager = users.create_user(username="welfare-manager", is_superuser=True)
        cls.officer = users.create_user(username="welfare-officer")
        cls.member = users.create_user(username="welfare-member", is_member=True)
        cls.other = users.create_user(username="welfare-other", is_member=True)
        StaffRoleGrant.objects.create(user=cls.officer, role="welfare_officer", granted_by=cls.manager, reason="Test")
        for number, user in enumerate((cls.member, cls.other), 1):
            Member.objects.create(user=user, member_number=f"TESTW{number}", national_id=f"TESTW{number}",
                                  phone_number=f"25470000000{number}", gender="other", date_of_birth="1990-01-01",
                                  county="Test", address="Test", status="active")

    def create_request(self, amount="100.00"):
        self.client.force_authenticate(self.member)
        response = self.client.post(reverse("welfare-requests"), {
            "category": "medical", "description": "Synthetic request", "requested_amount": amount,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_member_scope_committee_grant_and_approval_provider_boundary(self):
        item = self.create_request()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("welfare-requests")).data, [])
        self.assertEqual(self.client.get(reverse("welfare-requests") + "?scope=committee").status_code, 403)
        url = reverse("welfare-decide", args=[item])
        self.assertEqual(self.client.post(url, {"action": "approve", "reason": "Test"}, format="json").status_code, 403)
        self.client.force_authenticate(self.officer)
        self.assertIn("welfare_officer", [row["id"] for row in access_snapshot(self.officer)["workspaces"]])
        self.assertEqual(self.client.get(reverse("welfare-requests") + "?scope=committee").data[0]["id"], item)
        self.assertEqual(self.client.post(url, {"action": "approve", "reason": "Test"}, format="json").status_code, 409)
        WelfarePolicy.objects.create(version="test", approval_reference="Synthetic minute", approved_by=self.manager,
            active=True, benefits={"medical": {"maximum_benefit": "150.00", "minimum_contributions": "0.00"}})
        response = self.client.post(url, {"action": "approve", "reason": "Verified synthetic request"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["payout_status"], "awaiting_provider")
        self.assertEqual(response.data["approved_amount"], "100.00")
        self.assertFalse(JournalEntry.objects.exists())
        self.assertTrue(AuditLog.objects.filter(actor=self.officer, details__operation="welfare_decided").exists())
        self.assertEqual(self.client.post(url, {"action": "approve", "reason": "Retry"}, format="json").status_code, 409)

    def test_contribution_history_uses_posted_member_attributed_credit(self):
        asset = LedgerAccount.objects.create(code="TWA", name="Cash", classification="asset", normal_balance="debit")
        fund = LedgerAccount.objects.create(code="TWF", name="Welfare fund", classification="liability",
                                            normal_balance="credit", system_key="welfare_contributions")
        entry = post_journal_entry(idempotency_key="wf-1", source_type="test", source_reference="wf-1",
            description="Synthetic contribution", actor=self.manager,
            lines=[{"account_id": asset.pk, "debit": "25"}, {"account_id": fund.pk, "credit": "25"}])
        self.client.force_authenticate(self.manager)
        payload = {"member": self.member.member_profile.pk, "journal_line": entry.lines.get(account=fund).pk,
                   "reason": "Synthetic receipt attribution"}
        self.assertEqual(self.client.post(reverse("welfare-attribute-contribution"), payload, format="json").status_code, 201)
        self.assertEqual(self.client.post(reverse("welfare-attribute-contribution"), payload, format="json").status_code, 200)
        self.client.force_authenticate(self.member)
        self.assertEqual(Decimal(self.client.get(reverse("welfare-contributions")).data[0]["amount"]), Decimal("25.00"))
        reverse_journal_entry(entry_id=entry.pk, idempotency_key="wf-2", reason="Synthetic reversal", actor=self.manager)
        self.assertEqual(self.client.get(reverse("welfare-contributions")).data, [])

    def test_welfare_upload_is_validated_and_only_visible_to_owner_or_committee(self):
        item = self.create_request()
        upload_url = reverse("welfare-upload", args=[item])
        field = WelfareDocument._meta.get_field("file")
        original_storage = field.storage
        with TemporaryDirectory() as directory:
            field.storage = FileSystemStorage(location=directory)
            try:
                fake = SimpleUploadedFile("unsafe.pdf", b"<script>alert(1)</script>", content_type="application/pdf")
                self.assertEqual(self.client.post(upload_url, {"document": fake}, format="multipart").status_code, 400)
                image = BytesIO()
                Image.new("RGB", (400, 250)).save(image, format="PNG")
                doc = SimpleUploadedFile("synthetic.png", image.getvalue(), content_type="image/png")
                uploaded = self.client.post(upload_url, {"document": doc}, format="multipart")
                self.assertEqual(uploaded.status_code, 201, uploaded.data)
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.get(uploaded.data["url"]).status_code, 404)
                for viewer in (self.member, self.officer):
                    self.client.force_authenticate(viewer)
                    download = self.client.get(uploaded.data["url"])
                    self.assertEqual(download.status_code, 200)
                    self.assertIn("attachment", download["Content-Disposition"])
                    self.assertEqual(download["Cache-Control"], "private, no-store")
                    download.close()
            finally:
                field.storage = original_storage
