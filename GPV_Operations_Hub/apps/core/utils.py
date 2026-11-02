import json
import logging
import traceback
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse

from .jobs import UserFacingError

log = logging.getLogger("gpv.api")


class HubJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, set):
            return sorted(o)
        return str(o)


def json_ok(data=None, status=200, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return JsonResponse(payload, status=status, encoder=HubJSONEncoder, json_dumps_params={"ensure_ascii": False})


def json_error(message, status=400, **extra):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status, encoder=HubJSONEncoder, json_dumps_params={"ensure_ascii": False})


def api(view):
    """Wrap JSON endpoints: authentication, friendly errors, no stack traces to users."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_error("Su sesión expiró. Vuelva a iniciar sesión.", status=401)
        try:
            return view(request, *args, **kwargs)
        except UserFacingError as exc:
            return json_error(str(exc), status=400)
        except PermissionDenied as exc:
            return json_error(str(exc) or "No tiene permiso para esta operación.", status=403)
        except Exception as exc:  # pragma: no cover - defensive
            op = getattr(request, "op_id", "-")
            log.error("API error %s: %s\n%s", request.path, exc, traceback.format_exc())
            return json_error(
                f"Error interno. Referencia para soporte: {op}. Intente de nuevo o contacte al administrador.",
                status=500,
            )

    return wrapper


def read_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise UserFacingError("La solicitud no contiene datos JSON válidos.")


def paginate(request, qs, per_page=25):
    paginator = Paginator(qs, per_page)
    return paginator.get_page(request.GET.get("page"))


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
