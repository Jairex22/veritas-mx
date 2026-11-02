"""Deterministic value parsing for imports.

Nothing is guessed silently: ambiguous dates or decimal separators produce an error
asking the user to choose; damaged long serials are reported, never "repaired".
"""
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .fields import DATE, DATETIME, DECIMAL, FIELDS, INT, TEXT

NULLS = {"", "na", "n/a", "n/d", "nd", "null", "none", "nan", "-", "--", "#n/a", "sin dato"}
SCI_RE = re.compile(r"^[+-]?\d(?:[.,]\d+)?[eE]\+?\d+$")
DATE_RE = re.compile(
    r"^(?P<a>\d{1,4})[/\-.](?P<b>\d{1,2})[/\-.](?P<c>\d{1,4})(?:[ T](?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?(?:\.\d+)?\s*(?P<ampm>[ap]\.?\s?m\.?)?)?$",
    re.I,
)
UNIT_RE = re.compile(r"^(?P<num>[+-]?[\d.,\s]+)\s*(?P<unit>[a-zA-ZáéíóúÁÉÍÓÚ%]+\.?)$")
UNIT_ALIASES = {"pz": "pz", "pza": "pz", "pzas": "pz", "pzs": "pz", "pieza": "pz", "piezas": "pz", "pcs": "pz", "pc": "pz",
                "panel": "panel", "paneles": "panel", "pnl": "panel", "caja": "caja", "cajas": "caja", "box": "caja", "cj": "caja"}


class ParseError(Exception):
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


class Warn:
    """Collects non-blocking warnings for a cell."""

    def __init__(self):
        self.items = []

    def add(self, msg):
        self.items.append(msg)


def is_null(value):
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in NULLS:
        return True
    return False


def normalize_unit(text):
    t = str(text or "").strip().lower().rstrip(".")
    return UNIT_ALIASES.get(t, t)


def parse_decimal(value, decimal_sep="auto"):
    if isinstance(value, bool):
        raise ParseError("Valor booleano donde se esperaba un número.")
    if isinstance(value, (int, Decimal)):
        return Decimal(value), None
    if isinstance(value, float):
        return Decimal(repr(value)), None
    s = str(value).strip().replace(" ", " ")
    unit = None
    m = UNIT_RE.match(s)
    if m and not s.endswith("%"):
        s, unit = m.group("num").strip(), normalize_unit(m.group("unit"))
    if s.endswith("%"):
        raise ParseError(f"«{value}» es un porcentaje; esta columna espera una cantidad.", "percent")
    s = s.replace(" ", "")
    if SCI_RE.match(s):
        raise ParseError(f"«{value}» está en notación científica; la cantidad pudo perder precisión.", "scientific")
    has_dot, has_comma = "." in s, "," in s
    sep = decimal_sep
    if sep == "auto":
        if has_dot and has_comma:
            sep = "." if s.rfind(".") > s.rfind(",") else ","
        elif has_comma:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) == 3:
                raise ParseError(
                    f"«{value}» es ambiguo (¿mil o decimal?). Elija el separador decimal en las opciones de importación.",
                    "ambiguous_decimal",
                )
            sep = "," if len(parts) == 2 else "."
        elif has_dot:
            parts = s.split(".")
            if len(parts) > 2:
                sep = ","  # 1.234.567 -> thousands
            else:
                sep = "."
        else:
            sep = "."
    if sep == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ParseError(f"«{value}» no es un número válido.")
    if not d.is_finite():
        raise ParseError(f"«{value}» no es un número válido.")
    return d, unit


def _build_date(a, b, c, order):
    if len(a) == 4:  # ISO-like YYYY-MM-DD
        y, mo, d = int(a), int(b), int(c)
    else:
        y = int(c)
        if len(c) == 2:
            y += 2000
        if order == "MDY":
            mo, d = int(a), int(b)
        else:
            d, mo = int(a), int(b)
    return date(y, mo, d)


def parse_date_text(s, date_order="auto"):
    """Return (date, time|None)."""
    m = DATE_RE.match(s.strip())
    if not m:
        raise ParseError(f"«{s}» no es una fecha reconocida (use DD/MM/AAAA, MM/DD/AAAA o AAAA-MM-DD).")
    a, b, c = m.group("a"), m.group("b"), m.group("c")
    order = date_order
    if len(a) != 4:
        if order in ("auto", "YMD"):
            ai, bi = int(a), int(b)
            if ai > 12 and bi <= 12:
                order = "DMY"
            elif bi > 12 and ai <= 12:
                order = "MDY"
            elif ai == bi:
                order = "DMY"
            else:
                raise ParseError(
                    f"La fecha «{s}» es ambigua (día/mes). Seleccione el orden de fecha (DD/MM o MM/DD) en las opciones.",
                    "ambiguous_date",
                )
    try:
        d = _build_date(a, b, c, order)
    except ValueError:
        raise ParseError(f"«{s}» no es una fecha válida (día o mes fuera de rango).")
    t = None
    if m.group("h"):
        h, mi, sec = int(m.group("h")), int(m.group("m")), int(m.group("s") or 0)
        ampm = (m.group("ampm") or "").lower().replace(".", "").replace(" ", "")
        if ampm == "pm" and h < 12:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
        try:
            t = time(h, mi, sec)
        except ValueError:
            raise ParseError(f"«{s}» tiene una hora inválida.")
    return d, t


def parse_value(field, value, opts, warn: Warn):
    """Parse one cell for a system field. Returns python value or None."""
    if is_null(value):
        return None
    ftype = FIELDS[field][1]
    date_order = opts.get("date_order", "auto")
    if ftype == TEXT:
        if isinstance(value, float):
            if value.is_integer():
                if abs(value) >= 1e15:
                    warn.add(
                        f"El valor numérico {value:.0f} tiene 16 o más dígitos: Excel/CSV solo conserva 15 dígitos significativos. "
                        "Los dígitos perdidos no pueden recuperarse; exporte la columna como texto desde la fuente."
                    )
                    raise ParseError("Serial/clave numérica posiblemente dañada (más de 15 dígitos).", "damaged_number")
                return str(int(value))
            return repr(value)
        if isinstance(value, int) and not isinstance(value, bool):
            if abs(value) >= 10 ** 15:
                raise ParseError(
                    f"El número {value} tiene más de 15 dígitos guardado como número: verifique que no esté dañado; "
                    "guarde la columna como texto en la fuente.",
                    "damaged_number",
                )
            return str(value)
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return value.isoformat()
        s = str(value).strip()
        if field in ("serial", "work_order", "part_number") and SCI_RE.match(s):
            raise ParseError(
                f"«{s}» está en notación científica: el valor original ya se perdió al guardarse como número. "
                "No es posible recuperar los dígitos; vuelva a exportar la columna como texto.",
                "damaged_number",
            )
        return s[:400]
    if ftype in (DECIMAL, INT):
        if ftype == INT and isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        d, unit = parse_decimal(value, opts.get("decimal_sep", "auto"))
        if unit:
            expected = normalize_unit(opts.get("_row_unit") or opts.get("unit_default") or "")
            if expected and unit != expected:
                raise ParseError(f"«{value}» está en «{unit}» pero el registro usa «{expected}». No se convierte sin un factor documentado.", "unit_mismatch")
        if ftype == INT:
            if d != d.to_integral_value():
                raise ParseError(f"«{value}» debe ser un entero.")
            return int(d)
        if field.startswith("qty_") and d < 0:
            raise ParseError(f"Cantidad negativa ({value}) no permitida.")
        return d
    if ftype in (DATE, DATETIME):
        if isinstance(value, datetime):
            d, t = value.date(), value.time()
        elif isinstance(value, date):
            d, t = value, None
        elif isinstance(value, (int, float)):
            raise ParseError(f"«{value}» es un número, no una fecha. Verifique el formato de la columna.")
        else:
            d, t = parse_date_text(str(value), date_order)
        if not (1990 <= d.year <= 2100):
            raise ParseError(f"Año fuera de rango en «{value}».")
        if ftype == DATE:
            return d
        naive = datetime.combine(d, t or time(23, 59, 59) if field == "due" else (t or time(0, 0)))
        return timezone.make_aware(naive)
    raise ParseError("Tipo no soportado")
