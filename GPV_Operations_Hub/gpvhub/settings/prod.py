"""Shared internal deployment profile (WSGI server, PostgreSQL recommended, HTTPS)."""
from .base import *  # noqa: F401,F403
from .base import _secret_key, env_bool

DEBUG = False
SECRET_KEY = _secret_key(allow_generate=False)
GPV["ALLOW_DEMO"] = env_bool("GPV_ALLOW_DEMO", False)  # noqa: F405

SESSION_COOKIE_SECURE = env_bool("GPV_SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = env_bool("GPV_SECURE_COOKIES", True)
SECURE_SSL_REDIRECT = env_bool("GPV_SSL_REDIRECT", False)  # usually handled by the TLS proxy
SECURE_HSTS_SECONDS = int(os.environ.get("GPV_HSTS_SECONDS", "0"))  # noqa: F405
if env_bool("GPV_BEHIND_TLS_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
