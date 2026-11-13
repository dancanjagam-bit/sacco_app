from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.auth_views import custom_token_obtain

urlpatterns = [
    path("admin/", admin.site.urls),

    # API
    path("api/", include("accounts.urls")),
    path("api/", include("core.urls")),
    path("api/", include("members.urls")),
    path("api/", include("core.payments_urls")),
    path("api/token/", custom_token_obtain, name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]

# User uploads, including identity documents, are intentionally not exposed as
# a public media directory. Serve them only through authenticated views/storage.

# In production, serve the React SPA for every non-API route.
# WhiteNoise handles /static/ — this catch-all handles React Router paths.
if not settings.DEBUG:
    urlpatterns += [
        re_path(r"^(?!api/|admin/|static/|media/).*$",
                TemplateView.as_view(template_name="index.html"),
                name="react-app"),
    ]
