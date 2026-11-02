"""Local development / demonstration profile (runserver, SQLite)."""
from .base import *  # noqa: F401,F403
from .base import _secret_key, env_bool

DEBUG = env_bool("GPV_DEBUG", True)
SECRET_KEY = _secret_key(allow_generate=True)
GPV["ALLOW_DEMO"] = env_bool("GPV_ALLOW_DEMO", True)  # noqa: F405
