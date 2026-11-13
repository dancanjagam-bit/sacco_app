import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

# ─────────────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────────────
DEBUG      = os.getenv("DEBUG", "True").lower() in {"1", "true", "yes", "on"}
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY must be set when DEBUG=False.")
    SECRET_KEY = "django-insecure-local-development-only"
if not DEBUG and (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5):
    raise RuntimeError("SECRET_KEY must be a unique value of at least 50 characters in production.")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise RuntimeError("Set explicit ALLOWED_HOSTS before running with DEBUG=False.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─────────────────────────────────────────────────────────────────────────────
# Applications
# ─────────────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    # ── Local apps first so their management commands override Django's builtins ──
    "accounts",
    "core",
    "members",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # serves static files in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF    = "sacco.urls"
WSGI_APPLICATION = "sacco.wsgi.application"
AUTH_USER_MODEL  = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.CaseInsensitiveModelBackend",
]

# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS":    [BASE_DIR / "frontend" / "build"],   # React build for production
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────
if os.getenv("USE_POSTGRES", "0").lower() in {"1", "true", "yes", "on"}:
    DATABASES = {
        "default": {
            "ENGINE":   "django.db.backends.postgresql",
            "NAME":     os.getenv("DB_NAME",     "sacco"),
            "USER":     os.getenv("DB_USER",     "sacco"),
            "PASSWORD": os.getenv("DB_PASSWORD", "sacco"),
            "HOST":     os.getenv("DB_HOST",     "localhost"),
            "PORT":     os.getenv("DB_PORT",     "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME":   BASE_DIR / "db.sqlite3",
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# Password validation
# ─────────────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Internationalisation
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE     = "Africa/Nairobi"   # Kenya Standard Time (UTC+3)
USE_I18N      = True
USE_TZ        = True

# ─────────────────────────────────────────────────────────────────────────────
# Static & media files
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL  = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL   = "media/"
MEDIA_ROOT  = BASE_DIR / "media"

# WhiteNoise — serve compressed static files efficiently
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Serve the React production build from Django
WHITENOISE_ROOT = BASE_DIR / "frontend" / "build"

# ─────────────────────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────────────────────
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS  = False
    CORS_ALLOWED_ORIGINS    = [
        o.strip()
        for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]

CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# ─────────────────────────────────────────────────────────────────────────────
# DRF
# ─────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ─────────────────────────────────────────────────────────────────────────────
# JWT (SimpleJWT)
# ─────────────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME":  timedelta(days=30),
    "ROTATE_REFRESH_TOKENS":   True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES":       ("Bearer",),
    "UPDATE_LAST_LOGIN":       True,
}

# ─────────────────────────────────────────────────────────────────────────────
# Email backend
# ─────────────────────────────────────────────────────────────────────────────
if os.getenv("EMAIL_HOST"):
    EMAIL_BACKEND  = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST     = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT     = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS  = os.getenv("EMAIL_USE_TLS", "True").lower() in {"1", "true", "yes"}
    EMAIL_HOST_USER     = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL  = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
else:
    # Avoid printing password-reset codes and financial notices to local logs.
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style":  "{",
        },
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class":     "logging.handlers.RotatingFileHandler",
            "filename":  LOGS_DIR / "sacco.log",
            "maxBytes":  10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level":    "INFO",
    },
    "loggers": {
        "django": {
            "handlers":  ["console", "file"],
            "level":     os.getenv("DJANGO_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
        "sacco": {
            "handlers":  ["console", "file"],
            "level":     "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Security (production hardening — automatically applied when DEBUG=False)
# ─────────────────────────────────────────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    SECURE_SSL_REDIRECT            = True
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_BROWSER_XSS_FILTER      = True
    X_FRAME_OPTIONS                = "DENY"
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    SECURE_PROXY_SSL_HEADER        = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_REFERRER_POLICY         = "same-origin"
    SESSION_COOKIE_HTTPONLY        = True
    CSRF_COOKIE_HTTPONLY           = True
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ─────────────────────────────────────────────────────────────────────────────
# SACCO organisation details (used in statements, branding, emails)
# ─────────────────────────────────────────────────────────────────────────────
SACCO_NAME       = os.getenv("SACCO_NAME",       "Nairobi West Transport Cooperative Society")
SACCO_SHORT_NAME = os.getenv("SACCO_SHORT_NAME", "NW Transport")
SACCO_ADDRESS    = os.getenv("SACCO_ADDRESS",    "Nairobi West, Nairobi County, Kenya")
SACCO_PHONE      = os.getenv("SACCO_PHONE",      "0758007127")
SACCO_EMAIL      = os.getenv("SACCO_EMAIL",      "info@nwtcs.co.ke")
SACCO_PAYBILL    = os.getenv("SACCO_PAYBILL",    os.getenv("MPESA_SHORTCODE", "174379"))

# ─────────────────────────────────────────────────────────────────────────────
# File upload limits
# ─────────────────────────────────────────────────────────────────────────────
ID_DOC_MAX_MB = int(os.getenv("ID_DOC_MAX_MB", "5"))
KYC_DOCUMENT_RETENTION_DAYS = int(os.getenv("KYC_DOCUMENT_RETENTION_DAYS", "730"))

# ─────────────────────────────────────────────────────────────────────────────
# Africa's Talking (SMS)
# ─────────────────────────────────────────────────────────────────────────────
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY  = os.getenv("AT_API_KEY",  "")
# Set AT_USERNAME to your real username and AT_API_KEY to your API key in .env
# For sandbox testing: AT_USERNAME=sandbox, AT_API_KEY=your-sandbox-key

# ─────────────────────────────────────────────────────────────────────────────
# ID Verification — name matching
# ─────────────────────────────────────────────────────────────────────────────
NAME_MATCH_THRESHOLD = int(os.getenv("NAME_MATCH_THRESHOLD", "75"))

# ─────────────────────────────────────────────────────────────────────────────
# CRB (Credit Reference Bureau)
# ─────────────────────────────────────────────────────────────────────────────
CRB_PROVIDER             = os.getenv("CRB_PROVIDER", "stub")
CRB_API_KEY              = os.getenv("CRB_API_KEY", "")
CRB_API_URL              = os.getenv("CRB_API_URL", "")
CRB_FLAG_SCORE_THRESHOLD = int(os.getenv("CRB_FLAG_SCORE_THRESHOLD", "500"))

# ─────────────────────────────────────────────────────────────────────────────
# Daraja / M-Pesa (Safaricom)
# Docs: https://developer.safaricom.co.ke/Documentation
# ─────────────────────────────────────────────────────────────────────────────
MPESA_ENV             = os.getenv("MPESA_ENV", "sandbox")   # "sandbox" | "production"
MPESA_CONSUMER_KEY    = os.getenv("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE       = os.getenv("MPESA_SHORTCODE", "174379")   # sandbox default
MPESA_PASSKEY         = os.getenv("MPESA_PASSKEY", "")

# Public HTTPS base URL Daraja will POST callbacks to (no trailing slash).
# In dev: expose via ngrok and set e.g. https://abc123.ngrok.io
MPESA_CALLBACK_BASE_URL = os.getenv("MPESA_CALLBACK_BASE_URL", "")

# One-time registration fee (KES) charged on a member's first payment.
# Set to 0 to disable the fee requirement.
MPESA_REGISTRATION_FEE = int(os.getenv("MPESA_REGISTRATION_FEE", "500"))

# Daraja API base URLs (resolved automatically from MPESA_ENV)
MPESA_BASE_URL = (
    "https://sandbox.safaricom.co.ke"
    if MPESA_ENV == "sandbox"
    else "https://api.safaricom.co.ke"
)

# ─────────────────────────────────────────────────────────────────────────────
# Smile Identity — face / biometric verification
# ─────────────────────────────────────────────────────────────────────────────
SMILE_IDENTITY_API_KEY    = os.getenv("SMILE_IDENTITY_API_KEY", "")
SMILE_IDENTITY_PARTNER_ID = os.getenv("SMILE_IDENTITY_PARTNER_ID", "")
SMILE_IDENTITY_ENV        = os.getenv("SMILE_IDENTITY_ENV", "sandbox")
SMILE_IDENTITY_API_URL    = os.getenv("SMILE_IDENTITY_API_URL", "")
FACE_MATCH_THRESHOLD      = int(os.getenv("FACE_MATCH_THRESHOLD", "70"))
