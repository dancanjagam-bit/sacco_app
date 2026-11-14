"""Isolated local acceptance settings. Never use for deployment or live data."""
import os
from pathlib import Path

from .settings import *  # noqa: F401,F403


ACCEPTANCE_ROOT = Path(os.environ.get("SACCO_ACCEPTANCE_ROOT", BASE_DIR / ".recovery" / "transport-acceptance"))
ACCEPTANCE_ROOT.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SACCO_ACCEPTANCE_DB", str(ACCEPTANCE_ROOT / "acceptance.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}
MEDIA_ROOT = ACCEPTANCE_ROOT / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
WELFARE_PRIVATE_ROOT = ACCEPTANCE_ROOT / "welfare-private"
WELFARE_PAYOUT_PROVIDER = ""
LOGGING["handlers"]["file"]["filename"] = ACCEPTANCE_ROOT / "acceptance.log"

# Keep the acceptance stack local and incapable of sending real email or SMS.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST = EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = DEFAULT_FROM_EMAIL = ""
AT_USERNAME = AT_API_KEY = ""
MPESA_ENV = "sandbox"
MPESA_CONSUMER_KEY = MPESA_CONSUMER_SECRET = MPESA_PASSKEY = ""
MPESA_SHORTCODE = ""
MPESA_CALLBACK_BASE_URL = ""
TRANSPORT_C2B_CALLBACK_TOKEN = ""

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
    "http://127.0.0.1:3002",
    "http://localhost:3002",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
