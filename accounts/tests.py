from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from members.models import Member

User = get_user_model()


class RegistrationTests(APITestCase):
    def test_register_creates_user_and_member(self):
        url = "/api/register/"
        payload = {
            "username": "testuser123",
            "password": "strongpassword",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "national_id": "NID123456",
            "phone_number": "0712345678",
            "gender": "male",
            "date_of_birth": "1990-01-01",
            "county": "Nairobi",
            "address": "123 Test St",
        }
        response = self.client.post(url, payload, format='json')
        self.assertIn(response.status_code, (200, 201))
        self.assertIn('member_number', response.data)

        # Verify User exists
        self.assertTrue(User.objects.filter(username=payload['username']).exists())
        user = User.objects.get(username=payload['username'])

        # Verify Member exists and linked
        self.assertTrue(Member.objects.filter(user=user, national_id=payload['national_id']).exists())
        member = Member.objects.get(user=user)
        self.assertEqual(member.national_id, payload['national_id'])
