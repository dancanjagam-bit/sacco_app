"""
Member endpoint tests.

Note: The member detail PUT endpoint requires admin/staff permission.
A regular member cannot update another member's profile (or their own
through this endpoint) — they use the /api/profile/ endpoint instead.
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from members.models import Member

User = get_user_model()


class MemberEndpointTests(APITestCase):

    def setUp(self):
        # Admin user — has staff permission to call member endpoints
        self.admin = User.objects.create_superuser(
            username="admin_user",
            password="AdminPass1",
            email="admin@test.com",
        )
        # Regular member user
        self.user = User.objects.create_user(
            username="member_user",
            password="MemberPass1",
            email="member@test.com",
        )
        # Member profile with valid Kenyan data
        self.member = Member.objects.create(
            user=self.user,
            member_number="SACCO000001",
            national_id="12345678",       # 8 digits, numbers only
            phone_number="0712345678",    # valid Kenyan Airtel number
            gender="male",
            date_of_birth="1990-01-01",
            county="Nairobi",             # valid Kenyan county
            address="123 Test Street",
        )

    def test_member_list_requires_admin(self):
        """A regular member cannot list all members."""
        self.client.force_authenticate(user=self.user)
        res = self.client.get("/api/members/")
        self.assertEqual(res.status_code, 403)

    def test_admin_can_list_members(self):
        """Admin can retrieve the paginated member list."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/members/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("results", res.data)
        self.assertEqual(res.data["total"], 1)

    def test_admin_can_view_member_detail(self):
        """Admin can retrieve an individual member's full profile."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/members/{self.member.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["member_number"], "SACCO000001")
        self.assertEqual(res.data["national_id"], "12345678")

    def test_admin_can_update_member(self):
        """Admin can update a member's mutable fields."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.put(
            f"/api/members/{self.member.id}/",
            {
                "phone_number": "0722000111",
                "county":       "Kiambu",
                "address":      "Updated Address",
                "status":       "inactive",
            },
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Update failed {res.status_code}: {res.data}")
        self.assertEqual(res.status_code, 200)

        self.member.refresh_from_db()
        self.assertEqual(self.member.phone_number, "0722000111")
        self.assertEqual(self.member.county,       "Kiambu")
        self.assertEqual(self.member.status,       "inactive")

    def test_regular_member_cannot_update_member(self):
        """A regular member cannot call the admin member update endpoint."""
        self.client.force_authenticate(user=self.user)
        res = self.client.put(
            f"/api/members/{self.member.id}/",
            {"phone_number": "0733000000"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_nonexistent_member_returns_404(self):
        """Requesting a member ID that doesn't exist returns 404."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/members/99999/")
        self.assertEqual(res.status_code, 404)

    def test_admin_can_suspend_member(self):
        """Admin can suspend a member via the suspend endpoint."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/members/{self.member.id}/suspend/",
            {"action": "suspend", "reason": "Test suspension"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Suspend failed {res.status_code}: {res.data}")
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, "suspended")
        # Django user should be inactive (blocks API access)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_admin_can_reinstate_member(self):
        """Admin can reinstate a suspended member."""
        # First suspend
        self.member.status = "suspended"
        self.member.save()
        self.user.is_active = False
        self.user.save()

        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/members/{self.member.id}/suspend/",
            {"action": "reinstate"},
            format="json",
        )
        if res.status_code != 200:
            self.fail(f"Reinstate failed {res.status_code}: {res.data}")
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, "active")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
