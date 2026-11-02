"""System field catalog for imports (configurable mapping targets)."""
import re
import unicodedata

from .models import DatasetKind

TEXT, DATE, DATETIME, INT, DECIMAL = "text", "date", "datetime", "int", "decimal"

# name: (label, type, aliases)
FIELDS = {
    "date": ("Fecha", DATE, ["fecha", "date", "dia", "día", "fecha produccion", "fecha de produccion", "prod date"]),
    "timestamp": ("Fecha/hora", DATETIME, ["fecha hora", "timestamp", "hora", "fecha y hora", "datetime", "fecha captura", "capturado"]),
    "shift": ("Turno", TEXT, ["turno", "shift"]),
    "customer": ("Cliente", TEXT, ["cliente", "customer"]),
    "area": ("Área", TEXT, ["area", "área", "departamento"]),
    "line": ("Línea", TEXT, ["linea", "línea", "line", "celda"]),
    "work_order": ("Orden de trabajo", TEXT, ["orden", "orden de trabajo", "ot", "wo", "work order", "workorder", "no orden", "num orden"]),
    "part_number": ("Número de parte", TEXT, ["parte", "numero de parte", "número de parte", "no parte", "np", "part", "part number", "pn"]),
    "revision": ("Revisión", TEXT, ["revision", "revisión", "rev"]),
    "unit": ("Unidad", TEXT, ["unidad", "unit", "uom", "um"]),
    "qty_planned": ("Cantidad planeada", DECIMAL, ["meta", "plan", "planeado", "cantidad planeada", "qty plan", "planned", "target"]),
    "qty_good": ("Cantidad buena", DECIMAL, ["buenas", "buenos", "cantidad buena", "good", "ok", "producidas", "producido", "piezas buenas", "qty good"]),
    "qty_reject": ("Rechazo", DECIMAL, ["rechazo", "rechazos", "reject", "rechazadas", "ng"]),
    "qty_rework": ("Retrabajo", DECIMAL, ["retrabajo", "rework", "retrabajos"]),
    "qty_scrap": ("Scrap", DECIMAL, ["scrap", "desperdicio", "merma"]),
    "responsible": ("Responsable", TEXT, ["responsable", "owner", "encargado"]),
    "start": ("Inicio", DATETIME, ["inicio", "start", "fecha inicio"]),
    "due": ("Vencimiento", DATETIME, ["vencimiento", "due", "fecha compromiso", "entrega", "fecha entrega", "due date"]),
    "status": ("Estado", TEXT, ["estado", "status", "estatus"]),
    "notes": ("Observaciones", TEXT, ["observaciones", "notas", "comentarios", "notes", "comments"]),
    "serial": ("Serial", TEXT, ["serial", "serie", "numero de serie", "número de serie", "sn", "s/n"]),
    "station": ("Estación", TEXT, ["estacion", "estación", "station", "operacion", "operación"]),
    "result": ("Resultado", TEXT, ["resultado", "result", "pass/fail", "estatus prueba"]),
    "attempt": ("Intento", INT, ["intento", "attempt", "intento no", "try"]),
    "cause": ("Causa", TEXT, ["causa", "defecto", "cause", "defect", "motivo"]),
    "priority": ("Prioridad", INT, ["prioridad", "priority"]),
    "planned_minutes": ("Tiempo planeado (min)", DECIMAL, ["tiempo planeado", "minutos planeados", "planned minutes"]),
    "downtime_minutes": ("Paro (min)", DECIMAL, ["paro", "tiempo muerto", "downtime", "minutos paro"]),
    "ideal_cycle_seconds": ("Ciclo ideal (s)", DECIMAL, ["ciclo ideal", "ideal cycle", "ciclo ideal s"]),
    "lot": ("Lote", TEXT, ["lote", "lot"]),
}

REQUIRED = {
    DatasetKind.PLAN: ["work_order", "qty_planned"],
    DatasetKind.INCREMENTAL: ["date", "qty_good"],
    DatasetKind.SNAPSHOT: ["work_order", "qty_good"],
    DatasetKind.SERIAL: ["serial", "station", "result"],
    DatasetKind.QUALITY: ["date", "cause"],
    DatasetKind.GENERIC: [],
}

DEFAULT_KEYS = {
    DatasetKind.PLAN: ["work_order"],
    DatasetKind.INCREMENTAL: ["date", "shift", "line", "work_order", "station"],
    DatasetKind.SNAPSHOT: ["work_order", "station"],
    DatasetKind.SERIAL: ["serial", "station", "attempt"],
    DatasetKind.QUALITY: ["date", "shift", "line", "work_order", "cause"],
    DatasetKind.GENERIC: [],
}

# Fields stored as ProductionRecord columns (others go to ``extra``).
RECORD_COLUMNS = {
    "date", "timestamp", "shift", "customer", "line", "work_order", "part_number", "revision", "unit", "station",
    "serial", "result", "attempt", "cause", "responsible", "status", "qty_planned", "qty_good", "qty_reject",
    "qty_rework", "qty_scrap", "planned_minutes", "downtime_minutes", "ideal_cycle_seconds", "start", "due", "notes",
}


def normalize_header(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9/]+", " ", text.lower()).strip()
    return text


def auto_map(headers):
    """Suggest {field: header} by exact normalized alias match (never fuzzy guessing)."""
    norm = {normalize_header(h): h for h in headers if h}
    mapping = {}
    for field, (label, _t, aliases) in FIELDS.items():
        for candidate in [field, label] + aliases:
            key = normalize_header(candidate)
            if key in norm and norm[key] not in mapping.values():
                mapping[field] = norm[key]
                break
    return mapping
