from django.conf import settings

from .permissions import CAPABILITIES, has_cap


class _Caps:
    def __init__(self, user):
        self.user = user
        self._cache = {}

    def __getitem__(self, key):
        key = key.replace("__", ".")
        if key not in self._cache:
            self._cache[key] = key in CAPABILITIES and has_cap(self.user, key)
        return self._cache[key]

    def __contains__(self, key):
        return self[key]


def hub(request):
    from .models import SiteSetting

    user = getattr(request, "user", None)
    logo_id = ""
    try:
        logo_id = SiteSetting.get("logo_file_id", "")
    except Exception:  # database not migrated yet
        logo_id = ""
    return {
        "GPV_VERSION": settings.GPV_VERSION,
        "GPV_POLL_SECONDS": settings.GPV["POLL_SECONDS"],
        "GPV_LOGO_ID": logo_id,
        "caps": _Caps(user) if user is not None else {},
    }
