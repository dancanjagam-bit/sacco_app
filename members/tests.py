from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from members.models import Member

User = get_user_model()


class MemberEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member_user",
            password="memberpass",
            email="member@example.com",
        )
        self.member = Member.objects.create(
            user=self.user,
            member_number="SACCO000001",
            national_id="NID123456",
            phone_number="0712345678",
            gender="male",
            date_of_birth="1990-01-01",
            county="Nairobi",
            address="Test Address",
        )
        self.client.force_authenticate(user=self.user)

    def test_member_update_returns_success(self):
        response = self.client.put(
            f"/api/members/{self.member.id}/",
            {
                "phone_number": "0722000111",
                "county": "Kiambu",
                "address": "Updated Address",
                "status": "inactive",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.member.refresh_from_db()
        self.assertEqual(self.member.phone_number, "0722000111")
        self.assertEqual(self.member.county, "Kiambu")
        self.assertEqual(self.member.status, "inactive")
