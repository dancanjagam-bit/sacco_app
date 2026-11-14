"""Temporary settings for local browser verification; never use in deployment."""
import os

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Keep the established browser test DB as the default, while allowing
        # a separate disposable DB for local runtime checks.
        "NAME": os.environ.get(
            "SACCO_BROWSER_TEST_DB",
            str(BASE_DIR / "sacco_auth_browser_test.sqlite3"),
        ),
    }
}
EMAIL_HOST = ""
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
DEFAULT_FROM_EMAIL = ""
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AT_USERNAME = ""
AT_API_KEY = ""
