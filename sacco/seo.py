"""Public crawler endpoints and the single Search Console ownership file."""

from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_safe
from django.views.generic import TemplateView


GOOGLE_VERIFICATION_FILENAME = "google40b1f54e0b70526a.html"


@require_safe
def google_verification(request):
    verification_file = settings.BASE_DIR / "verification" / GOOGLE_VERIFICATION_FILENAME
    return HttpResponse(
        verification_file.read_bytes(),
        content_type="text/html; charset=utf-8",
    )


class NonIndexableReactView(TemplateView):
    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response.headers["X-Robots-Tag"] = "noindex"
        return response


def robots_txt(request):
    # Crawlers must be able to read the noindex header on non-home SPA pages.
    # API and admin data are protected independently by Django permissions.
    body = (
        "User-agent: *\n"
        "Disallow: /api/\n"
        "Disallow: /admin/\n"
        "Disallow: /media/\n"
        f"\nSitemap: {settings.SITE_CANONICAL_URL}/sitemap.xml\n"
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    homepage = escape(f"{settings.SITE_CANONICAL_URL}/")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{homepage}</loc></url>\n"
        "</urlset>\n"
    )
    return HttpResponse(body, content_type="application/xml; charset=utf-8")
