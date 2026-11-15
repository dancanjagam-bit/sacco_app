from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.urls import reverse
from PIL import Image, PngImagePlugin
from rest_framework.test import APITestCase

from accounts.services.kyc_privacy import request_erasure
from members.models import Member, MemberProfilePhoto


class ProfilePhotoTests(APITestCase):
    def create_member(self, suffix):
        user = get_user_model().objects.create_user(username=f"photo_member_{suffix}")
        return Member.objects.create(
            user=user, member_number=f"P{suffix}", national_id=f"1234567{suffix}",
            phone_number="0712345678", gender="other", date_of_birth=date(1990, 1, 1),
            county="Nairobi", address="Test address",
        )

    def setUp(self):
        self.member = self.create_member(1)
        self.other = self.create_member(2)
        self.url = reverse("profile-photo")

    def upload(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("Private metadata", "Do not retain")
        source = BytesIO()
        Image.new("RGBA", (1024, 768), "blue").save(source, "PNG", pnginfo=info)
        return SimpleUploadedFile("sample.png", source.getvalue(), content_type="image/png")

    def test_upload_is_private_and_can_be_removed(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.force_authenticate(self.member.user)
        self.assertFalse(self.client.get(reverse("profile")).data["has_profile_photo"])
        self.assertEqual(self.client.post(self.url, {"photo": self.upload()}, format="multipart").status_code, 200)
        self.assertTrue(self.client.get(reverse("profile")).data["has_profile_photo"])
        response = self.client.get(self.url)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        with Image.open(BytesIO(response.content)) as photo:
            self.assertEqual(photo.size, (512, 384))
            self.assertNotIn("Private metadata", photo.info)

        self.client.force_authenticate(self.other.user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertTrue(MemberProfilePhoto.objects.filter(member=self.member).exists())

        self.client.force_authenticate(self.member.user)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertFalse(self.client.get(reverse("profile")).data["has_profile_photo"])

    def test_rejects_invalid_image_without_replacing_existing_photo(self):
        self.client.force_authenticate(self.member.user)
        self.client.post(self.url, {"photo": self.upload()}, format="multipart")
        original = self.client.get(self.url).content
        invalid = SimpleUploadedFile("invalid.jpg", b"<svg/>", content_type="image/jpeg")
        response = self.client.post(self.url, {"photo": invalid}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(self.url).content, original)

    def test_account_erasure_removes_the_profile_photo(self):
        self.client.force_authenticate(self.member.user)
        self.assertEqual(self.client.post(self.url, {"photo": self.upload()}, format="multipart").status_code, 200)
        result = request_erasure(self.member.user)
        self.assertIn("profile_photo", result["files_removed"])
        self.assertFalse(MemberProfilePhoto.objects.filter(member=self.member).exists())

    @patch.dict("os.environ", {"RENDER": "true"})
    def test_render_readiness_requires_access_to_the_table(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["profile_photos_ready"])
        with patch("sacco.urls.MemberProfilePhoto.objects.exists", side_effect=DatabaseError):
            self.assertEqual(self.client.get("/api/health/").status_code, 503)
