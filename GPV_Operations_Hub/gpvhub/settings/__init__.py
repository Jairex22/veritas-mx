"""Settings loader.

GPV_ENV selects the profile: ``dev`` (default), ``prod`` or ``test``.
Values come from environment variables and, optionally, a ``.env`` file in the
project root (parsed by :mod:`gpvhub.settings.envfile`, no third-party package).
"""
import os

from .envfile import load_env_file

load_env_file()

_env = os.environ.get("GPV_ENV", "dev").strip().lower()

if _env == "prod":
    from .prod import *  # noqa: F401,F403
elif _env == "test":
    from .test import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
