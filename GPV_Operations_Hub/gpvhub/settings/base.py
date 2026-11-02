"""Base settings shared by every profile."""
import os
import secrets
from pathlib import Path

from .envfile import PROJECT_ROOT, env_bool, env_int, env_list

BASE_DIR = PROJECT_ROOT
GPV_VERSION = "1.0.1"

# Runtime data lives outside of the static/public folders.
DATA_DIR = Path(os.environ.get("GPV_DATA_DIR", BASE_DIR / "data")).resolve()
PRIVATE_MEDIA_ROOT = DATA_DIR / "private"
TEMP_DIR = DATA_DIR / "tmp"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
for _d in (DATA_DIR, PRIVATE_MEDIA_ROOT, TEMP_DIR, BACKUP_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _secret_key(allow_generate):
    key = os.environ.get("GPV_SECRET_KEY", "").strip()
    if key:
        return key
    if not allow_generate:
        raise RuntimeError(
            "GPV_SECRET_KEY no está definido. Copie .env.example a .env y genere una clave "
            "con: python manage.py gpv_genkey"
        )
    # Development convenience: a random key persisted in data/ (never shipped in the ZIP).
    key_file = DATA_DIR / "dev_secret_key.txt"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(50), encoding="utf-8")
    return key_file.read_text(encoding="utf-8").strip()


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.core",
    "apps.comms",
    "apps.production",
    "apps.reports",
    "apps.sheets",
    "apps.documents",
    "apps.labels",
    "apps.kaizen",
]

MIDDLEWARE = [
    "apps.core.middleware.OperationIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.PasswordChangeRequiredMiddleware",
]

ROOT_URLCONF = "gpvhub.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.hub",
            ],
        },
    },
]

WSGI_APPLICATION = "gpvhub.wsgi.application"

DB_ENGINE = os.environ.get("GPV_DB_ENGINE", "sqlite").lower()
if DB_ENGINE in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("GPV_DB_NAME", "gpvhub"),
            "USER": os.environ.get("GPV_DB_USER", "gpvhub"),
            "PASSWORD": os.environ.get("GPV_DB_PASSWORD", ""),
            "HOST": os.environ.get("GPV_DB_HOST", "localhost"),
            "PORT": os.environ.get("GPV_DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("GPV_DB_CONN_MAX_AGE", 60),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.environ.get("GPV_SQLITE_PATH", DATA_DIR / "gpvhub.sqlite3")),
            "OPTIONS": {
                "timeout": 30,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True  # stored in UTC, displayed in America/Mexico_City

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = DATA_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("GPV_SESSION_SECONDS", 10 * 60 * 60)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Upload limits
GPV_MAX_UPLOAD_MB = env_int("GPV_MAX_UPLOAD_MB", 50)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_TEMP_DIR = str(TEMP_DIR)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000

# Hub specific configuration
GPV = {
    "POLL_SECONDS": env_int("GPV_POLL_SECONDS", 30),
    "JOBS_MODE": os.environ.get("GPV_JOBS_MODE", "inline").lower(),  # inline | worker
    "JOB_TIMEOUT_SECONDS": env_int("GPV_JOB_TIMEOUT_SECONDS", 900),
    "JOB_MAX_ATTEMPTS": env_int("GPV_JOB_MAX_ATTEMPTS", 2),
    "IMPORT_MAX_ROWS": env_int("GPV_IMPORT_MAX_ROWS", 500000),
    "IMPORT_CHUNK_ROWS": env_int("GPV_IMPORT_CHUNK_ROWS", 2000),
    "SOFFICE_PATH": os.environ.get("GPV_SOFFICE_PATH", ""),
    "SOFFICE_TIMEOUT": env_int("GPV_SOFFICE_TIMEOUT", 120),
    "TESSERACT_PATH": os.environ.get("GPV_TESSERACT_PATH", ""),
    "MAX_PDF_PAGES": env_int("GPV_MAX_PDF_PAGES", 2000),
    "MAX_ZIP_ENTRIES": env_int("GPV_MAX_ZIP_ENTRIES", 5000),
    "MAX_UNCOMPRESSED_MB": env_int("GPV_MAX_UNCOMPRESSED_MB", 500),
    "SHEET_MAX_CELLS": env_int("GPV_SHEET_MAX_CELLS", 300000),
    "PRINTER_TIMEOUT": env_int("GPV_PRINTER_TIMEOUT", 8),
    "ALLOW_DEMO": env_bool("GPV_ALLOW_DEMO", False),
    "SCHEDULER_TICK_SECONDS": env_int("GPV_SCHEDULER_TICK_SECONDS", 30),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"opid": {"()": "apps.core.logging_utils.OperationIdFilter"}},
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(op_id)s] %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard", "filters": ["opid"]},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "gpvhub.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "standard",
            "filters": ["opid"],
        },
    },
    "root": {"handlers": ["console", "file"], "level": os.environ.get("GPV_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"level": "ERROR"},
        "django.server": {"level": "WARNING"},
    },
}

ALLOWED_HOSTS = env_list("GPV_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("GPV_CSRF_TRUSTED_ORIGINS", "")

# When DEBUG is off and no reverse proxy serves /static/, Django serves the collected files
# (run "manage.py collectstatic"). Disable if IIS/nginx serves STATIC_ROOT.
GPV_SERVE_STATIC = env_bool("GPV_SERVE_STATIC", True)
