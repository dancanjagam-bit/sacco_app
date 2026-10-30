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
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me-in-production")
DEBUG      = os.getenv("DEBUG", "True").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─────────────────────────────────────────────────────────────────────────────
# Applications
# ─────────────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
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

    "accounts",
    "core",
    "members",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS":    [],
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
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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

# ─────────────────────────────────────────────────────────────────────────────
# Africa's Talking (SMS)
# ─────────────────────────────────────────────────────────────────────────────
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY  = os.getenv("AT_API_KEY",  "")
# Set AT_USERNAME to your real username and AT_API_KEY to your API key in .env
# For sandbox testing: AT_USERNAME=sandbox, AT_API_KEY=your-sandbox-key
