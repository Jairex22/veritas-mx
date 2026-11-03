"""Normalization of OData JSON payloads (v4 and v2/v3 verbose/light)."""
import re
from datetime import datetime, timezone as dt_tz

from . import status as st
from .client import FlxError

META_KEYS = ("__metadata", "__deferred", "odata.", "@odata.", "@")
_V2_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")


def rows_of(data):
    """Return (rows, next_link, count) or raise FlxError(BAD_RESPONSE)."""
    if isinstance(data, dict) and isinstance(data.get("value"), list):  # v4 / v3 light
        cnt = data.get("@odata.count", data.get("odata.count"))
        return data["value"], data.get("@odata.nextLink") or data.get("odata.nextLink"), _int(cnt)
    if isinstance(data, dict) and "d" in data:  # v2 / v3 verbose
        d = data["d"]
        if isinstance(d, dict) and isinstance(d.get("results"), list):
            return d["results"], d.get("__next"), _int(d.get("__count"))
        if isinstance(d, list):
            return d, None, None
        if isinstance(d, dict):  # single entity
            return [d], None, None
    raise FlxError(st.BAD_RESPONSE, "La respuesta no tiene la estructura OData esperada («value» o «d.results»).")


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def property_names(row):
    return sorted(k for k in row if not k.startswith(META_KEYS) and "@odata." not in k)


def normalize_value(v):
    if isinstance(v, str):
        m = _V2_DATE.match(v)
        if m:
            return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=dt_tz.utc).isoformat()
    if isinstance(v, dict) and "__deferred" in v:
        return None  # navigation link not expanded
    return v


def normalize_row(row):
    return {k: normalize_value(v) for k, v in row.items() if not k.startswith(META_KEYS) and "@odata." not in k}
