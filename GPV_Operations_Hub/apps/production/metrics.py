"""Single metrics layer used by tables, dashboards, Excel/PDF reports and APIs.

All KPI definitions are documented in DEFINICIONES_KPI.md. Results always carry a status:
``ok``, ``not_calculable`` (e.g. target 0/unknown) or ``insufficient`` (missing inputs), plus a
human readable ``reason``. No KPI is estimated from data that does not exist.
"""
import calendar
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from apps.core.permissions import allowed_area_ids

from .models import Dataset, DatasetKind, ProductionRecord, WorkOrder

ZERO = Decimal("0")


@dataclass
class Filters:
    period: str = "month"  # today | week | month | range | all
    date_from: date | None = None
    date_to: date | None = None
    customer: str = ""
    area: str = ""  # area code
    line: str = ""
    shift: str = ""
    work_order: str = ""
    part_number: str = ""
    responsible: str = ""
    unit: str = ""
    late_only: bool = False
    station: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d):
        d = d or {}

        def g(k):
            v = d.get(k, "")
            if isinstance(v, list):
                v = v[0] if v else ""
            return str(v).strip() if v is not None else ""

        f = cls(period=g("period") or "month")
        for k in ("customer", "area", "line", "shift", "work_order", "part_number", "responsible", "unit", "station"):
            setattr(f, k, g(k))
        f.late_only = g("late_only") in ("1", "true", "on", "True")
        for k in ("date_from", "date_to"):
            v = g(k)
            if v:
                try:
                    setattr(f, k, date.fromisoformat(v))
                except ValueError:
                    pass
        if f.date_from or f.date_to:
            if f.period not in ("range",):
                f.period = "range"
        return f

    def to_dict(self):
        d = asdict(self)
        d.pop("extra", None)
        for k in ("date_from", "date_to"):
            d[k] = d[k].isoformat() if d[k] else ""
        return {k: v for k, v in d.items() if v not in ("", None, False)}

    def date_range(self):
        today = timezone.localdate()
        if self.period == "today":
            return today, today
        if self.period == "week":
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if self.period == "month":
            last = calendar.monthrange(today.year, today.month)[1]
            return today.replace(day=1), today.replace(day=last)
        if self.period == "range":
            return self.date_from, self.date_to
        return None, None

    def describe(self):
        start, end = self.date_range()
        parts = []
        labels = {"today": "Hoy", "week": "Semana actual", "month": "Mes actual", "all": "Todo el historial", "range": "Rango"}
        if start or end:
            parts.append(f"{labels.get(self.period, self.period)}: {start or '…'} a {end or '…'}")
        else:
            parts.append(labels.get(self.period, self.period))
        names = {"customer": "Cliente", "area": "Área", "line": "Línea", "shift": "Turno", "work_order": "Orden",
                 "part_number": "Parte", "responsible": "Responsable", "unit": "Unidad", "station": "Estación"}
        for k, label in names.items():
            v = getattr(self, k)
            if v:
                parts.append(f"{label}: {v}")
        if self.late_only:
            parts.append("Solo atrasadas")
        return " · ".join(parts)


def metric(value=None, status="ok", reason="", numerator=None, denominator=None, unit="", definition=""):
    return {"value": value, "status": status, "reason": reason, "numerator": numerator, "denominator": denominator,
            "unit": unit, "definition": definition}


def _f(x):
    return float(x) if x is not None else None


def pct(numerator, denominator, definition, zero_reason="Meta cero o desconocida: el cumplimiento no es calculable."):
    if denominator is None or denominator <= 0:
        return metric(None, "not_calculable", zero_reason, _f(numerator), _f(denominator), "%", definition)
    value = (Decimal(numerator) / Decimal(denominator) * 100).quantize(Decimal("0.01"))
    return metric(float(value), "ok", "", _f(numerator), _f(denominator), "%", definition)


# ---------------------------------------------------------------- querysets
def _area_scope(qs, user, f, field_name="area"):
    ids = allowed_area_ids(user)
    if ids is not None:
        qs = qs.filter(**{f"{field_name}__in": ids})
    if f.area:
        qs = qs.filter(**{f"{field_name}__code__iexact": f.area})
    return qs


def orders_queryset(user, f: Filters):
    qs = _area_scope(WorkOrder.objects.select_related("area"), user, f)
    start, end = f.date_range()
    if start or end:
        cond = Q()
        if start:
            cond &= Q(due__date__gte=start) | Q(due__isnull=True, start__date__gte=start)
        if end:
            cond &= Q(due__date__lte=end) | Q(due__isnull=True, start__date__lte=end) | Q(due__isnull=True, start__isnull=True)
        qs = qs.filter(cond)
    for attr, fld in (("customer", "customer__iexact"), ("line", "line__iexact"), ("work_order", "number__icontains"),
                      ("part_number", "part_number__icontains"), ("responsible", "responsible__icontains"), ("unit", "unit__iexact")):
        v = getattr(f, attr)
        if v:
            qs = qs.filter(**{fld: v})
    return qs


def records_queryset(user, f: Filters, kinds=None, use_dates=True):
    qs = ProductionRecord.objects.filter(is_current=True)
    if kinds:
        qs = qs.filter(dataset__kind__in=kinds)
    qs = _area_scope(qs, user, f)
    if use_dates:
        start, end = f.date_range()
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
    for attr, fld in (("customer", "customer__iexact"), ("line", "line__iexact"), ("shift", "shift__iexact"),
                      ("work_order", "work_order__icontains"), ("part_number", "part_number__icontains"),
                      ("responsible", "responsible__icontains"), ("unit", "unit__iexact"), ("station", "station__iexact")):
        v = getattr(f, attr)
        if v:
            qs = qs.filter(**{fld: v})
    return qs


# ---------------------------------------------------------------- production per order
def counting_datasets():
    return list(Dataset.objects.filter(counts_as_production=True, kind__in=[DatasetKind.INCREMENTAL, DatasetKind.SNAPSHOT]))


def good_by_order(user, numbers):
    """Return ({ORDER: {"good": Decimal, "dataset": name, "updated": dt}}, warnings).

    * Only records of the finished station count (dataset.finished_station). If a dataset has
      several stations and no finished station configured, it is excluded with a warning so
      the same piece is never counted at several stations.
    * Snapshot datasets contribute only current captures (never summed across captures).
    * If two counting datasets report the same order, only the most recently imported dataset
      is used and a warning is emitted (no double counting).
    """
    warnings = []
    numbers_up = {n.upper() for n in numbers}
    per = defaultdict(dict)
    ids = allowed_area_ids(user)
    for ds in counting_datasets():
        qs = ProductionRecord.objects.filter(dataset=ds, is_current=True)
        if ids is not None:
            qs = qs.filter(area__in=ids)
        if ds.finished_station:
            qs = qs.filter(station__iexact=ds.finished_station)
        else:
            stations = set(qs.exclude(station="").values_list("station", flat=True).distinct()[:3])
            if len(stations) > 1:
                warnings.append(
                    f"El dataset «{ds.name}» contiene varias estaciones ({', '.join(sorted(stations))}) y no tiene definida la estación "
                    "de producción terminada; no se suma para evitar contar la misma pieza varias veces."
                )
                continue
        rows = qs.exclude(work_order="").values("work_order").annotate(good=Sum("qty_good"), last=Max("updated"))
        for r in rows:
            key = r["work_order"].upper()
            if key in numbers_up:
                per[key][ds.pk] = {"good": r["good"] or ZERO, "dataset": ds.name, "updated": ds.last_import_at or r["last"],
                                   "rank": ds.last_import_at or r["last"]}
    result = {}
    for key, by_ds in per.items():
        if len(by_ds) > 1:
            names = ", ".join(sorted(v["dataset"] for v in by_ds.values()))
            warnings.append(f"La orden {key} aparece en varias fuentes ({names}); se usa la importada más recientemente.")
        best = max(by_ds.values(), key=lambda v: v["rank"] or timezone.make_aware(datetime(1990, 1, 1)))
        result[key] = best
    return result, warnings


def order_rows(user, f: Filters, now=None):
    now = now or timezone.now()
    orders = list(orders_queryset(user, f).order_by("due", "priority", "number"))
    goods, warnings = good_by_order(user, [o.number for o in orders])
    rows = []
    for o in orders:
        g = goods.get(o.number.upper())
        good = g["good"] if g else ZERO
        planned = o.qty_planned
        if planned is None or planned <= 0:
            comp = metric(None, "not_calculable", "Meta cero o desconocida.", _f(good), _f(planned), "%")
            pending = None
        else:
            comp = pct(good, planned, "buenas / meta × 100")
            pending = max(planned - good, ZERO)
        late = bool(o.due and o.due < now and pending is not None and pending > 0)
        if f.late_only and not late:
            continue
        rows.append({
            "id": o.pk, "number": o.number, "customer": o.customer, "area": o.area.code, "line": o.line, "part_number": o.part_number,
            "revision": o.revision, "unit": o.unit, "planned": planned, "good": good, "pending": pending, "compliance": comp,
            "priority": o.priority, "status": o.status, "responsible": o.responsible,
            "due": o.due, "start": o.start, "late": late,
            "source": g["dataset"] if g else "Sin producción registrada",
            "data_updated": g["updated"] if g else None,
            "plan_updated": o.updated,
        })
    return rows, warnings


def grouped_compliance(rows):
    """Σ good / Σ planned (only rows with positive target; never an average of percentages)."""
    units = {r["unit"] for r in rows if r["planned"] and r["planned"] > 0}
    definition = "Σ cantidad buena / Σ cantidad planeada × 100 (órdenes con meta positiva)"
    if not rows:
        return metric(None, "insufficient", "No hay órdenes para los filtros seleccionados.", definition=definition, unit="%")
    if len(units) > 1:
        return metric(None, "not_calculable",
                      f"Las órdenes usan unidades distintas ({', '.join(sorted(units))}); filtre por unidad. No se convierten sin factor documentado.",
                      definition=definition, unit="%")
    valid = [r for r in rows if r["planned"] and r["planned"] > 0]
    if not valid:
        return metric(None, "not_calculable", "Ninguna orden tiene meta positiva.", definition=definition, unit="%")
    num = sum((r["good"] for r in valid), ZERO)
    den = sum((r["planned"] for r in valid), ZERO)
    m = pct(num, den, definition)
    excluded = len(rows) - len(valid)
    if excluded:
        m["reason"] = f"{excluded} órdenes sin meta excluidas del cálculo."
    m["unit_label"] = next(iter(units)) if units else ""
    return m


def pending_total(rows):
    valid = [r["pending"] for r in rows if r["pending"] is not None]
    return sum(valid, ZERO) if valid else None


# ---------------------------------------------------------------- quality
def quality_rates(user, f):
    qs = records_queryset(user, f, kinds=[DatasetKind.INCREMENTAL, DatasetKind.QUALITY])
    agg = qs.aggregate(good=Sum("qty_good"), reject=Sum("qty_reject"), scrap=Sum("qty_scrap"), rework=Sum("qty_rework"),
                       n_reject=Count("id", filter=Q(qty_reject__isnull=False)), n_scrap=Count("id", filter=Q(qty_scrap__isnull=False)))
    good, reject, scrap, rework = (agg[k] or ZERO for k in ("good", "reject", "scrap", "rework"))
    total = good + reject + scrap
    definition_s = "scrap / (buenas + rechazo + scrap) × 100, dispositions exclusivas del mismo periodo"
    definition_r = "rechazo / (buenas + rechazo + scrap) × 100"
    if not agg["n_scrap"]:
        scrap_m = metric(None, "insufficient", "Las fuentes no registran scrap en el periodo.", unit="%", definition=definition_s)
    else:
        scrap_m = pct(scrap, total, definition_s, "Sin unidades procesadas en el periodo.")
    if not agg["n_reject"]:
        reject_m = metric(None, "insufficient", "Las fuentes no registran rechazo en el periodo.", unit="%", definition=definition_r)
    else:
        reject_m = pct(reject, total, definition_r, "Sin unidades procesadas en el periodo.")
    return {"scrap_rate": scrap_m, "reject_rate": reject_m, "good": good, "reject": reject, "scrap": scrap, "rework": rework, "total": total}


def fpy(user, f):
    definition = "Seriales que pasan en el primer intento / seriales con primer intento × 100 (por estación)"
    qs = records_queryset(user, f, kinds=[DatasetKind.SERIAL])
    if not qs.exists():
        return metric(None, "insufficient", "No hay resultados por serial en el periodo; FPY requiere el primer intento de cada serial.",
                      unit="%", definition=definition)
    first = qs.filter(attempt=1)
    if not first.exists():
        return metric(None, "insufficient",
                      "Los resultados no indican el número de intento; no se puede deducir FPY de resultados finales tras reparación.",
                      unit="%", definition=definition)
    stations = list(first.values_list("station", flat=True).distinct()[:5])
    if len(stations) > 1 and not f.station:
        return metric(None, "not_calculable", f"Hay varias estaciones ({', '.join(stations)}); filtre una estación para calcular FPY.",
                      unit="%", definition=definition)
    total = first.values("serial").distinct().count()
    passed = first.filter(result="PASS").values("serial").distinct().count()
    m = pct(passed, total, definition, "Sin seriales en primer intento.")
    m["station"] = f.station or (stations[0] if stations else "")
    return m


def oee(user, f):
    definition = "Disponibilidad × Rendimiento × Calidad; requiere minutos planeados, paro, ciclo ideal y conteos"
    qs = records_queryset(user, f, kinds=[DatasetKind.INCREMENTAL])
    complete = qs.filter(planned_minutes__isnull=False, downtime_minutes__isnull=False, ideal_cycle_seconds__isnull=False, qty_good__isnull=False)
    if not complete.exists():
        return metric(None, "insufficient", "Datos insuficientes: faltan tiempo planeado, paros o ciclo ideal en las fuentes.",
                      unit="%", definition=definition)
    incomplete = qs.count() - complete.count()
    planned = run = ideal = good = total = ZERO
    for r in complete.values("planned_minutes", "downtime_minutes", "ideal_cycle_seconds", "qty_good", "qty_reject", "qty_scrap"):
        pm, dm = r["planned_minutes"], r["downtime_minutes"]
        cnt = (r["qty_good"] or ZERO) + (r["qty_reject"] or ZERO) + (r["qty_scrap"] or ZERO)
        planned += pm
        run += max(pm - dm, ZERO)
        ideal += r["ideal_cycle_seconds"] * cnt / 60
        good += r["qty_good"] or ZERO
        total += cnt
    if planned <= 0 or run <= 0 or total <= 0:
        return metric(None, "not_calculable", "Tiempo de operación o conteo total igual a cero.", unit="%", definition=definition)
    a, p, q = run / planned, ideal / run, good / total
    value = (a * p * q * 100).quantize(Decimal("0.01"))
    m = metric(float(value), "ok", f"{incomplete} registros sin insumos completos excluidos." if incomplete else "", unit="%", definition=definition)
    m["components"] = {"availability": float((a * 100).quantize(Decimal("0.01"))), "performance": float((p * 100).quantize(Decimal("0.01"))),
                       "quality": float((q * 100).quantize(Decimal("0.01")))}
    return m


# ---------------------------------------------------------------- series
DIMENSIONS = {
    "date": "Fecha", "shift": "Turno", "line": "Línea", "customer": "Cliente", "work_order": "Orden", "part_number": "Parte",
    "station": "Estación", "cause": "Causa", "area": "Área", "hour": "Hora", "week": "Semana", "month": "Mes",
}
MEASURES = {"qty_good": "Buenas", "qty_planned": "Planeadas (registro)", "qty_reject": "Rechazo", "qty_scrap": "Scrap",
            "qty_rework": "Retrabajo", "count": "Registros"}
AGGS = {"sum": "Suma", "avg": "Promedio", "min": "Mínimo", "max": "Máximo", "count": "Conteo", "count_distinct": "Conteo distinto"}


def series(user, f, dimension="date", measure="qty_good", agg="sum", kinds=None, limit=50, order="key"):
    """Aggregate production records by a whitelisted dimension/measure (no raw SQL)."""
    from django.db.models import Avg, Min
    from django.db.models.functions import ExtractHour, TruncMonth, TruncWeek

    if dimension not in DIMENSIONS or measure not in MEASURES or agg not in AGGS:
        raise ValueError("Dimensión, medida o agregación no permitida.")
    qs = records_queryset(user, f, kinds=kinds or [DatasetKind.INCREMENTAL])
    if dimension == "hour":
        qs = qs.exclude(timestamp__isnull=True).annotate(k=ExtractHour("timestamp"))
        dim = "k"
    elif dimension == "week":
        qs = qs.exclude(date__isnull=True).annotate(k=TruncWeek("date"))
        dim = "k"
    elif dimension == "month":
        qs = qs.exclude(date__isnull=True).annotate(k=TruncMonth("date"))
        dim = "k"
    elif dimension == "area":
        dim = "area__code"
    else:
        dim = dimension
    if measure == "count":
        agg_expr = Count("id")
    else:
        func = {"sum": Sum, "avg": Avg, "min": Min, "max": Max, "count": Count}.get(agg)
        if agg == "count_distinct":
            agg_expr = Count(measure, distinct=True)
        else:
            agg_expr = func(measure)
    rows = list(qs.values(dim).annotate(v=agg_expr).order_by(dim))
    out = []
    for r in rows:
        key = r[dim]
        if key in (None, ""):
            key = "(vacío)"
        if hasattr(key, "isoformat"):
            key = key.isoformat()[:10]
        out.append({"key": str(key), "value": float(r["v"]) if r["v"] is not None else None})
    if order == "value_desc":
        out.sort(key=lambda x: (x["value"] is None, -(x["value"] or 0)))
    return out[:limit] if limit else out


def pareto(user, f):
    qs = records_queryset(user, f, kinds=[DatasetKind.QUALITY, DatasetKind.INCREMENTAL]).exclude(cause="")
    rows = list(qs.values("cause").annotate(rej=Sum("qty_reject"), scr=Sum("qty_scrap"), n=Count("id")))
    items = []
    for r in rows:
        qty = (r["rej"] or ZERO) + (r["scr"] or ZERO)
        items.append({"key": r["cause"], "value": float(qty) if qty else float(r["n"]), "basis": "piezas" if qty else "registros"})
    items.sort(key=lambda x: -x["value"])
    total = sum(i["value"] for i in items) or 1
    acc = 0
    for i in items:
        acc += i["value"]
        i["cumulative_pct"] = round(acc / total * 100, 2)
    return items


def projection(user, f, order_row, window_days=7, now=None):
    """Linear run-rate projection for one order (an estimate, never confirmed production)."""
    now = now or timezone.now()
    if order_row["pending"] is None:
        return {"status": "not_calculable", "reason": "Orden sin meta positiva."}
    if order_row["pending"] == 0:
        return {"status": "ok", "reason": "Orden completa.", "projected_date": None}
    since = timezone.localdate(now) - timedelta(days=window_days)
    qs = ProductionRecord.objects.filter(is_current=True, work_order__iexact=order_row["number"], dataset__kind=DatasetKind.INCREMENTAL,
                                         dataset__counts_as_production=True, date__gte=since)
    agg = qs.aggregate(total=Sum("qty_good"), days=Count("date", distinct=True))
    if not agg["days"]:
        return {"status": "insufficient", "reason": f"Sin producción incremental en los últimos {window_days} días."}
    rate = (agg["total"] or ZERO) / agg["days"]
    if rate <= 0:
        return {"status": "insufficient", "reason": "Ritmo observado igual a cero."}
    days_needed = order_row["pending"] / rate
    projected = timezone.localdate(now) + timedelta(days=float(days_needed))
    return {
        "status": "estimate", "rate_per_day": float(rate.quantize(Decimal("0.01"))), "window_days": window_days,
        "observed_days": agg["days"], "projected_date": projected.isoformat(),
        "formula": "fecha = hoy + pendiente / (producción buena de la ventana / días con producción)",
        "assumptions": "Ritmo constante igual al promedio de días con producción; no considera paros, calendario ni cambios de turno.",
    }


def data_freshness(user):
    last = Dataset.objects.aggregate(last=Max("last_import_at"))["last"]
    last_wo = WorkOrder.objects.aggregate(last=Max("updated"))["last"]
    return {"last_import": last, "last_plan_change": last_wo}


def data_version():
    from .models import ImportBatch

    agg = ProductionRecord.objects.aggregate(n=Count("id"), m=Max("updated"))
    last_batch = ImportBatch.objects.filter(status__in=["committed", "reverted", "partial_reverted"]).aggregate(m=Max("id"))["m"] or 0
    wo = WorkOrder.objects.aggregate(m=Max("updated"), n=Count("id"))
    stamp = f"L{last_batch}-R{agg['n']}-{(agg['m'] or timezone.now()).strftime('%Y%m%d%H%M%S')}-O{wo['n']}-{(wo['m'] or timezone.now()).strftime('%Y%m%d%H%M%S')}"
    return stamp


def kpi_summary(user, f: Filters):
    rows, warnings = order_rows(user, f)
    comp = grouped_compliance(rows)
    pend = pending_total(rows)
    q = quality_rates(user, f)
    importing = False
    from .models import ImportBatch

    if ImportBatch.objects.filter(status=ImportBatch.Status.COMMITTING).exists():
        importing = True
        warnings.append("Hay una importación en curso; los indicadores pueden cambiar al terminar.")
    fresh = data_freshness(user)
    return {
        "filters": f.to_dict(), "filters_text": f.describe(),
        "orders": len(rows),
        "planned_total": float(sum((r["planned"] for r in rows if r["planned"]), ZERO)),
        "good_total": float(sum((r["good"] for r in rows), ZERO)),
        "pending_total": float(pend) if pend is not None else None,
        "late_count": sum(1 for r in rows if r["late"]),
        "compliance": comp,
        "scrap_rate": q["scrap_rate"], "reject_rate": q["reject_rate"],
        "fpy": fpy(user, f), "oee": oee(user, f),
        "warnings": warnings, "importing": importing,
        "last_import": fresh["last_import"], "last_plan_change": fresh["last_plan_change"],
        "data_version": data_version(),
    }
