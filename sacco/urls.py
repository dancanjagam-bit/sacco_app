import os

from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.auth_views import custom_token_obtain
from members.models import MemberProfilePhoto
from .seo import (
    GOOGLE_VERIFICATION_FILENAME,
    NonIndexableReactView,
    google_verification,
    robots_txt,
    sitemap_xml,
)

def health(request):
    if os.environ.get("RENDER") != "true":
        return JsonResponse({"status": "ok", "service": "sacco-backend"})
    try:
        MemberProfilePhoto.objects.exists()
    except DatabaseError:
        return JsonResponse({"status": "unavailable", "service": "sacco-backend"}, status=503)
    return JsonResponse({"status": "ok", "service": "sacco-backend", "profile_photos_ready": True})


urlpatterns = [
    path("admin/", admin.site.urls),

    # Health check endpoint for Render / uptime monitoring
    path("api/health/", health),

    # API
    path("api/", include("accounts.urls")),
    path("api/", include("core.urls")),
    path("api/", include("members.urls")),
    path("api/accounting/", include("accounting.urls")),
    path("api/", include("core.payments_urls")),
    path("api/token/", custom_token_obtain, name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # Public SEO endpoints (must precede the SPA catch-all below)
    path("robots.txt", robots_txt, name="robots"),
    path("sitemap.xml", sitemap_xml, name="sitemap"),
    path(GOOGLE_VERIFICATION_FILENAME, google_verification, name="google-site-verification"),
]

# User uploads, including identity documents, are intentionally not exposed as
# a public media directory. Serve them only through authenticated views/storage.

# In production, serve the React SPA for every non-API route.
# WhiteNoise handles /static/ — this catch-all handles React Router paths.
if not settings.DEBUG:
    urlpatterns += [
        path("", TemplateView.as_view(template_name="index.html"), name="public-home"),
        re_path(r"^(?!api/|admin/|static/|media/).*$",
                NonIndexableReactView.as_view(template_name="index.html"),
                name="react-app"),
    ]
