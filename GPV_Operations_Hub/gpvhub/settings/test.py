"""Automated test profile."""
from .base import *  # noqa: F401,F403
from .base import DATA_DIR

DEBUG = False
SECRET_KEY = "test-only-not-secret"
GPV["JOBS_MODE"] = "inline"  # noqa: F405
GPV["ALLOW_DEMO"] = True  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ALLOWED_HOSTS = ["*"]
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):  # noqa: F405
    # A file-based test DB lets thread-concurrency tests share the same database.
    DATABASES["default"]["TEST"] = {"NAME": str(DATA_DIR / "test_gpvhub.sqlite3")}  # noqa: F405
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
