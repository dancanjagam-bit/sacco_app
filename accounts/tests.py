from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from members.models import Member

User = get_user_model()


class RegistrationTests(APITestCase):

    VALID_PAYLOAD = {
        "username":         "testuser123",
        "password":         "Strongpass1",       # 8+ chars, has letter AND number
        "confirm_password": "Strongpass1",        # must match password
        "first_name":       "Test",
        "last_name":        "User",
        "email":            "test@example.com",
        "national_id":      "12345678",            # 8 digits, numbers only
        "phone_number":     "0712345678",          # valid Kenyan Airtel number
        "gender":           "male",
        "date_of_birth":    "1990-01-01",          # 18+ years old
        "county":           "Nairobi",             # valid Kenyan county
        "address":          "123 Test Street, Nairobi",
    }

    def test_register_creates_user_and_member(self):
        """Successful registration returns 201, creates User and linked Member."""
        response = self.client.post(
            "/api/register/",
            self.VALID_PAYLOAD,
            format="json",
        )

        # Show errors if the request failed (makes debugging easy)
        if response.status_code not in (200, 201):
            self.fail(
                f"Registration returned {response.status_code}. "
                f"Errors: {response.data}"
            )

        self.assertIn(response.status_code, (200, 201))
        self.assertIn("member_number", response.data)
        self.assertTrue(response.data["member_number"].startswith("SACCO"))

        # User was created
        self.assertTrue(
            User.objects.filter(username=self.VALID_PAYLOAD["username"]).exists()
        )
        user = User.objects.get(username=self.VALID_PAYLOAD["username"])
        self.assertEqual(user.first_name, self.VALID_PAYLOAD["first_name"])
        self.assertEqual(user.last_name,  self.VALID_PAYLOAD["last_name"])
        self.assertEqual(user.email,      self.VALID_PAYLOAD["email"].lower())

        # Member profile was created and linked to user
        self.assertTrue(Member.objects.filter(user=user).exists())
        member = Member.objects.get(user=user)
        self.assertEqual(member.national_id,  self.VALID_PAYLOAD["national_id"])
        self.assertEqual(member.phone_number, "0712345678")
        self.assertEqual(member.county,       "Nairobi")
        self.assertEqual(member.gender,       self.VALID_PAYLOAD["gender"])
        self.assertEqual(member.status,       "active")

    def test_duplicate_username_rejected(self):
        """Registering a second account with the same username returns 400."""
        self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")

        payload2 = {**self.VALID_PAYLOAD, "email": "other@example.com", "national_id": "87654321"}
        response = self.client.post("/api/register/", payload2, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_duplicate_national_id_rejected(self):
        """Two members cannot share the same National ID."""
        self.client.post("/api/register/", self.VALID_PAYLOAD, format="json")

        payload2 = {**self.VALID_PAYLOAD, "username": "otheruser", "email": "other2@example.com"}
        response = self.client.post("/api/register/", payload2, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("national_id", response.data)

    def test_invalid_password_no_number(self):
        """Password without a number is rejected."""
        payload = {**self.VALID_PAYLOAD, "password": "StrongPass", "confirm_password": "StrongPass"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_password_mismatch_rejected(self):
        """Mismatched password and confirm_password is rejected."""
        payload = {**self.VALID_PAYLOAD, "confirm_password": "WrongPass1"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.data)

    def test_invalid_national_id_rejected(self):
        """National ID with letters is rejected."""
        payload = {**self.VALID_PAYLOAD, "national_id": "NID123456", "username": "user2", "email": "u2@test.com"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("national_id", response.data)

    def test_invalid_phone_rejected(self):
        """Non-Kenyan phone number format is rejected."""
        payload = {**self.VALID_PAYLOAD, "phone_number": "1234567890", "username": "user3", "email": "u3@test.com", "national_id": "11111111"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone_number", response.data)

    def test_underage_rejected(self):
        """Members under 18 are rejected."""
        from datetime import date, timedelta
        dob = (date.today() - timedelta(days=365*17)).isoformat()
        payload = {**self.VALID_PAYLOAD, "date_of_birth": dob, "username": "user4", "email": "u4@test.com", "national_id": "22222222"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_of_birth", response.data)

    def test_invalid_county_rejected(self):
        """A county not in Kenya's 47 counties is rejected."""
        payload = {**self.VALID_PAYLOAD, "county": "London", "username": "user5", "email": "u5@test.com", "national_id": "33333333"}
        response = self.client.post("/api/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("county", response.data)
