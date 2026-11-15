from xml.etree import ElementTree

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(DEBUG=False, ALLOWED_HOSTS=["nwtcs.onrender.com"])
class PublicSEOTests(SimpleTestCase):
    def test_verification_returns_original_file_to_anonymous_https_client(self):
        url = "/google40b1f54e0b70526a.html"
        self.assertEqual(reverse("google-site-verification"), url)

        response = self.client.get(url, secure=True, HTTP_HOST="nwtcs.onrender.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
        expected = b"google-site-verification: google40b1f54e0b70526a.html"
        self.assertEqual(response.content, expected)
        self.assertEqual(
            response.content, (settings.BASE_DIR / "verification" / url[1:]).read_bytes()
        )

    def test_source_directory_is_not_publicly_served(self):
        response = self.client.get(
            "/media/verification/google40b1f54e0b70526a.html",
            secure=True,
            HTTP_HOST="nwtcs.onrender.com",
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(SITE_CANONICAL_URL="https://nwtcs.onrender.com")
    def test_sitemap_lists_only_the_homepage(self):
        response = self.client.get("/sitemap.xml", secure=True, HTTP_HOST="nwtcs.onrender.com")
        self.assertEqual(response.status_code, 200)
        sitemap = ElementTree.fromstring(response.content)
        urls = sitemap.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        self.assertEqual([url.text for url in urls], ["https://nwtcs.onrender.com/"])

    def test_member_api_requires_authentication(self):
        response = self.client.get("/api/members/", secure=True, HTTP_HOST="nwtcs.onrender.com")
        self.assertIn(response.status_code, (401, 403))
