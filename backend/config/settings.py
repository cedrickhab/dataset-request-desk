"""Django settings for the Dataset Request Desk.

Local development reads an ignored .env at the repository root. Nothing in this
file carries a real secret value: SECRET_KEY and PERSONAL_ADMIN_PASSWORD come
from the environment, and the insecure fallback key is permitted only while
DEBUG is on.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off. "
            "See .env.example."
        )
    # Local development only; unreachable when DEBUG is off (checked above).
    SECRET_KEY = "insecure-development-key-not-for-deployment"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,api,web")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "accounts",
    "desk",
]

MIDDLEWARE = [
    "config.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.AccessLogMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "dataset_desk"),
        "USER": os.environ.get("POSTGRES_USER", "dataset_desk"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "0")),
        "OPTIONS": {
            # Analytics uses date_trunc and timestamp arithmetic; pinning the
            # session to UTC keeps day bucketing independent of server locale.
            "options": "-c timezone=UTC",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Session and CSRF cookies -------------------------------------------------
# Same-origin deployment behind a proxy, so Lax is sufficient and no CORS
# middleware is needed. Secure flags are driven by env so local HTTP works
# without weakening a TLS deployment.
SESSION_COOKIE_NAME = "datasetdesk_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", default=not DEBUG)
SESSION_COOKIE_AGE = int(os.environ.get("DJANGO_SESSION_COOKIE_AGE", 60 * 60 * 12))
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

CSRF_COOKIE_NAME = "csrftoken"
# The CSRF cookie is deliberately readable by JavaScript: the SPA echoes it
# back in the X-CSRFToken header. The session cookie stays HttpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", default=not DEBUG)
CSRF_USE_SESSIONS = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.CSRFSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "accounts.permissions.IsActiveAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "desk.pagination.DeskPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.errors.exception_handler",
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("LOGIN_THROTTLE_RATE", "10/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Dataset Request Desk API",
    "DESCRIPTION": "Internal platform for robot episode datasets and client requests.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["accounts.permissions.IsActiveAuthenticated"],
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Domain configuration -----------------------------------------------------
# Deadlines are judged against the client's local calendar date in Kigali, not
# the server's UTC date, so a request created late on a Kigali evening can still
# carry today's date as its deadline.
BUSINESS_TIME_ZONE = os.environ.get("BUSINESS_TIME_ZONE", "Africa/Kigali")

KNOWN_ROBOT_IDS = env_list(
    "KNOWN_ROBOT_IDS", "arm-01,arm-02,arm-03,mobile-01,humanoid-01"
)

IMPORT_MAX_UPLOAD_BYTES = int(os.environ.get("IMPORT_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
IMPORT_MAX_ROWS = int(os.environ.get("IMPORT_MAX_ROWS", 100_000))
IMPORT_MAX_REPORTED_ISSUES = int(os.environ.get("IMPORT_MAX_REPORTED_ISSUES", 1000))
EPISODE_MAX_DURATION_SECONDS = int(os.environ.get("EPISODE_MAX_DURATION_SECONDS", 3600))

# Reject oversized uploads before they are buffered to disk.
DATA_UPLOAD_MAX_MEMORY_SIZE = IMPORT_MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

ASSIGNMENT_MAX_PER_CALL = int(os.environ.get("ASSIGNMENT_MAX_PER_CALL", 100))
ANALYTICS_MAX_RANGE_DAYS = int(os.environ.get("ANALYTICS_MAX_RANGE_DAYS", 366))

EXPORT_MAX_ATTEMPTS = int(os.environ.get("EXPORT_MAX_ATTEMPTS", 3))
EXPORT_LEASE_SECONDS = int(os.environ.get("EXPORT_LEASE_SECONDS", 30))
EXPORT_FAILURE_RATE = float(os.environ.get("EXPORT_FAILURE_RATE", 0.2))
EXPORT_MIN_SLEEP_SECONDS = float(os.environ.get("EXPORT_MIN_SLEEP_SECONDS", 2.0))
EXPORT_MAX_SLEEP_SECONDS = float(os.environ.get("EXPORT_MAX_SLEEP_SECONDS", 5.0))
EXPORT_WORKER_POLL_SECONDS = float(os.environ.get("EXPORT_WORKER_POLL_SECONDS", 1.0))

PERSONAL_ADMIN_EMAIL = os.environ.get("PERSONAL_ADMIN_EMAIL", "")
# Read only; never logged, serialized or written back to disk.
PERSONAL_ADMIN_PASSWORD = os.environ.get("PERSONAL_ADMIN_PASSWORD", "")
PERSONAL_ADMIN_NAME = os.environ.get("PERSONAL_ADMIN_NAME", "Cedrick Admin")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "config.logging_formatters.JSONFormatter"},
        "plain": {"format": "%(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": os.environ.get("LOG_FORMAT", "json"),
        }
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        # django.request would emit a second line per 4xx/5xx; the access log
        # middleware already reports status for every request.
        "django.request": {"handlers": ["console"], "level": "CRITICAL", "propagate": False},
    },
}
