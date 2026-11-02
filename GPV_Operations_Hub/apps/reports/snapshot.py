"""Builds the consistent report snapshot (a JSON document).

Every exporter (PDF, XLSX, CSV, DOCX, PPTX) renders *only* this snapshot, so all formats show
identical numbers for the same filters and data version.
"""
from collections import defaultdict
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from apps.production.metrics import (Filters, grouped_compliance, kpi_summary, order_rows, pareto, pending_total, series)

from .models import ReportKind

COMPLIANCE_REFERENCE = 95.0  # documented reference for automatic observations


def _num(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return v


def _kpi(label, m):
    return {"label": label, "value": m.get("value"), "status": m.get("status"), "reason": m.get("reason", ""),
            "unit": m.get("unit", ""), "definition": m.get("definition", ""), "numerator": m.get("numerator"),
            "denominator": m.get("denominator")}


def _plain(label, value, unit="", definition=""):
    return {"label": label, "value": _num(value), "status": "ok" if value is not None else "not_calculable",
            "reason": "" if value is not None else "Sin datos", "unit": unit, "definition": definition,
            "numerator": None, "denominator": None}


ORDER_COLUMNS = [
    {"key": "number", "label": "Orden"}, {"key": "customer", "label": "Cliente"}, {"key": "area", "label": "Área"},
    {"key": "line", "label": "Línea"}, {"key": "part_number", "label": "Parte"}, {"key": "unit", "label": "Unidad"},
    {"key": "planned", "label": "Meta", "num": True}, {"key": "good", "label": "Buenas", "num": True},
    {"key": "pending", "label": "Pendiente", "num": True}, {"key": "compliance", "label": "Cumplimiento %", "num": True},
    {"key": "due", "label": "Vencimiento"}, {"key": "late", "label": "Atrasada"}, {"key": "status", "label": "Estado"},
    {"key": "source", "label": "Fuente"},
]


def order_table_rows(rows):
    out = []
    for r in rows:
        comp = r["compliance"]
        out.append([
            r["number"], r["customer"], r["area"], r["line"], r["part_number"], r["unit"], _num(r["planned"]), _num(r["good"]),
            _num(r["pending"]), comp["value"] if comp["status"] == "ok" else "No calculable",
            timezone.localtime(r["due"]).strftime("%Y-%m-%d %H:%M") if r["due"] else "", "Sí" if r["late"] else "No",
            r["status"], r["source"],
        ])
    return out


def _line_table(rows):
    by_line = defaultdict(list)
    for r in rows:
        by_line[(r["area"], r["line"] or "(sin línea)")].append(r)
    table = []
    for (area, line), items in sorted(by_line.items()):
        comp = grouped_compliance(items)
        pend = pending_total(items)
        table.append([area, line, len(items), _num(sum((i["planned"] or 0 for i in items), Decimal(0))),
                      _num(sum((i["good"] for i in items), Decimal(0))), _num(pend),
                      comp["value"] if comp["status"] == "ok" else "No calculable", sum(1 for i in items if i["late"])])
    return table


LINE_COLUMNS = [{"key": "area", "label": "Área"}, {"key": "line", "label": "Línea"}, {"key": "orders", "label": "Órdenes", "num": True},
                {"key": "planned", "label": "Meta", "num": True}, {"key": "good", "label": "Buenas", "num": True},
                {"key": "pending", "label": "Pendiente", "num": True}, {"key": "compliance", "label": "Cumplimiento %", "num": True},
                {"key": "late", "label": "Atrasadas", "num": True}]


def observations(kpis, rows, line_table):
    """Rule-based observations: only facts computed from the data, never inferred causes."""
    obs = []
    comp = kpis["compliance"]
    if comp["status"] == "ok" and comp["value"] < COMPLIANCE_REFERENCE:
        obs.append(f"El cumplimiento agrupado es {comp['value']:.2f} %, por debajo de la referencia de {COMPLIANCE_REFERENCE:.0f} %.")
    elif comp["status"] == "ok":
        obs.append(f"El cumplimiento agrupado es {comp['value']:.2f} % (referencia {COMPLIANCE_REFERENCE:.0f} %).")
    else:
        obs.append(f"Cumplimiento no calculable: {comp['reason']}")
    if kpis["late_count"]:
        obs.append(f"Hay {kpis['late_count']} órdenes vencidas con pendiente positivo.")
    pend_lines = [r for r in line_table if isinstance(r[5], (int, float)) and r[5] > 0]
    if pend_lines:
        top = max(pend_lines, key=lambda r: r[5])
        obs.append(f"La línea {top[1]} ({top[0]}) concentra el mayor pendiente: {top[5]:g}.")
    no_target = sum(1 for r in rows if r["compliance"]["status"] != "ok")
    if no_target:
        obs.append(f"{no_target} órdenes sin meta positiva no se incluyen en el cumplimiento.")
    if kpis.get("last_import"):
        age_h = (timezone.now() - kpis["last_import"]).total_seconds() / 3600
        if age_h > 24:
            obs.append(f"Los datos de producción tienen {age_h:.0f} horas desde la última importación.")
    else:
        obs.append("No hay importaciones de producción registradas.")
    return obs


def _incidents(user, f):
    from django.contrib.contenttypes.models import ContentType

    from apps.comms.models import Comment
    from apps.production.models import WorkOrder

    ct = ContentType.objects.get_for_model(WorkOrder)
    start, end = f.date_range()
    qs = Comment.objects.filter(kind="incident", content_type=ct).select_related("author")
    if start:
        qs = qs.filter(created__date__gte=start)
    if end:
        qs = qs.filter(created__date__lte=end)
    from apps.core.permissions import allowed_area_ids

    ids = allowed_area_ids(user)
    out = []
    for c in qs[:100]:
        wo = WorkOrder.objects.filter(pk=c.object_id).first()
        if wo is None or (ids is not None and wo.area_id not in ids):
            continue
        out.append(f"{timezone.localtime(c.created):%Y-%m-%d %H:%M} · Orden {wo.number} · {c.author.username}: {c.body[:200]}"
                   f" ({'resuelta' if c.resolved else 'abierta'})")
    return out


def build_snapshot(kind, filters: dict, user, title="", notes=""):
    f = Filters.from_dict(filters)
    outermost = not connection.in_atomic_block  # isolation can only be set as the first statement
    with transaction.atomic():
        if connection.vendor == "postgresql" and outermost:
            with connection.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return _build(kind, f, user, title, notes)


def _build(kind, f, user, title, notes):
    from apps.production.metrics import data_version

    now = timezone.localtime()
    kpis = kpi_summary(user, f)
    rows, _w = order_rows(user, f)
    line_table = _line_table(rows)
    snap = {
        "kind": kind, "kind_label": ReportKind(kind).label, "title": title or ReportKind(kind).label,
        "period_text": f.describe(), "filters": f.to_dict(), "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "America/Mexico_City", "author": (user.get_full_name() or user.username) if user else "sistema",
        "data_version": data_version(), "notes": notes, "warnings": kpis["warnings"], "kpis": [], "tables": [], "charts": [],
        "observations": [], "incidents": [],
        "last_import": timezone.localtime(kpis["last_import"]).strftime("%Y-%m-%d %H:%M") if kpis["last_import"] else "",
    }
    base_kpis = [
        _kpi("Cumplimiento agrupado", kpis["compliance"]),
        _plain("Meta total", kpis["planned_total"]),
        _plain("Buenas", kpis["good_total"]),
        _plain("Pendiente", kpis["pending_total"], definition="Σ máx(meta − buenas, 0) por orden"),
        _plain("Órdenes atrasadas", kpis["late_count"], definition="Vencimiento superado y pendiente > 0"),
        _plain("Órdenes", kpis["orders"]),
    ]
    if kind in (ReportKind.DAILY, ReportKind.WEEKLY, ReportKind.BY_LINE, ReportKind.LATE):
        snap["kpis"] = base_kpis + ([_kpi("Scrap", kpis["scrap_rate"]), _kpi("Rechazo", kpis["reject_rate"])] if kind == ReportKind.DAILY else [])
        if kind == ReportKind.LATE:
            late_rows = [r for r in rows if r["late"]]
            snap["tables"].append({"title": "Órdenes atrasadas", "columns": ORDER_COLUMNS, "rows": order_table_rows(late_rows)})
        elif kind == ReportKind.BY_LINE or kind == ReportKind.WEEKLY:
            snap["tables"].append({"title": "Cumplimiento por línea", "columns": LINE_COLUMNS, "rows": line_table})
            snap["tables"].append({"title": "Detalle de órdenes", "columns": ORDER_COLUMNS, "rows": order_table_rows(rows)})
        else:
            snap["tables"].append({"title": "Avance por orden", "columns": ORDER_COLUMNS, "rows": order_table_rows(rows)})
            snap["tables"].append({"title": "Cumplimiento por línea", "columns": LINE_COLUMNS, "rows": line_table})
        snap["charts"].append({"title": "Meta vs. buenas por línea", "type": "bar",
                               "categories": [f"{r[0]}/{r[1]}" for r in line_table],
                               "series": [{"name": "Meta", "values": [r[3] or 0 for r in line_table]},
                                          {"name": "Buenas", "values": [r[4] or 0 for r in line_table]}]})
        dim = "shift" if kind == ReportKind.DAILY else "date"
        s = series(user, f, dim, "qty_good", "sum")
        snap["charts"].append({"title": "Producción buena por " + ("turno" if dim == "shift" else "día"), "type": "bar" if dim == "shift" else "line",
                               "categories": [p["key"] for p in s], "series": [{"name": "Buenas", "values": [p["value"] or 0 for p in s]}]})
        snap["observations"] = observations(kpis, rows, line_table)
        snap["incidents"] = _incidents(user, f)
    elif kind == ReportKind.QUALITY:
        snap["kpis"] = [_kpi("Scrap", kpis["scrap_rate"]), _kpi("Rechazo", kpis["reject_rate"]), _kpi("FPY", kpis["fpy"]), _kpi("OEE", kpis["oee"])]
        p = pareto(user, f)
        snap["tables"].append({"title": "Pareto de causas", "columns": [{"key": "cause", "label": "Causa"}, {"key": "qty", "label": "Cantidad", "num": True},
                                                                        {"key": "basis", "label": "Base"}, {"key": "cum", "label": "% acumulado", "num": True}],
                               "rows": [[i["key"], i["value"], i["basis"], i["cumulative_pct"]] for i in p]})
        snap["charts"].append({"title": "Pareto de causas", "type": "bar", "categories": [i["key"] for i in p[:15]],
                               "series": [{"name": "Cantidad", "values": [i["value"] for i in p[:15]]}]})
        obs = []
        for k in snap["kpis"]:
            if k["status"] != "ok":
                obs.append(f"{k['label']}: {k['reason']}")
            else:
                obs.append(f"{k['label']}: {k['value']:.2f} %.")
        if p:
            obs.append(f"La causa con mayor frecuencia registrada es «{p[0]['key']}» ({p[0]['value']:g} {p[0]['basis']}). "
                       "Esta observación describe los registros; no establece la causa raíz.")
        snap["observations"] = obs
        snap["incidents"] = _incidents(user, f)
    elif kind == ReportKind.KAIZEN:
        from apps.kaizen.models import Improvement, Status

        from apps.core.permissions import filter_by_area

        qs = filter_by_area(Improvement.objects.select_related("area", "responsible"), user)
        if f.area:
            qs = qs.filter(area__code__iexact=f.area)
        items = list(qs)
        counts = {s.label: sum(1 for i in items if i.status == s.value) for s in Status}
        snap["kpis"] = [_plain(label, n) for label, n in counts.items()]
        snap["tables"].append({"title": "Mejoras Kaizen", "columns": [
            {"key": "code", "label": "Código"}, {"key": "title", "label": "Título"}, {"key": "area", "label": "Área"},
            {"key": "status", "label": "Estado"}, {"key": "resp", "label": "Responsable"}, {"key": "target", "label": "Fecha objetivo"},
            {"key": "actions", "label": "Acciones pendientes", "num": True}],
            "rows": [[i.code, i.title, i.area.code, i.get_status_display(), i.responsible.username if i.responsible else "",
                      i.target_date.isoformat() if i.target_date else "", i.actions.filter(done_at__isnull=True).count()] for i in items]})
        snap["charts"].append({"title": "Mejoras por estado", "type": "bar", "categories": list(counts.keys()),
                               "series": [{"name": "Mejoras", "values": list(counts.values())}]})
        overdue = [i for i in items if i.target_date and i.target_date < timezone.localdate() and i.status not in ("closed", "rejected")]
        snap["observations"] = [f"{len(items)} mejoras en el alcance; {len(overdue)} con fecha objetivo vencida y sin cerrar."]
    return snap
