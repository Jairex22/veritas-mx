"""Report runs, scheduler and dashboard widget engine."""
import logging
import re
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.files import store_generated
from apps.core.jobs import UserFacingError, enqueue, job_handler, worker_id
from apps.core.models import SchedulerLease
from apps.core.notify import notify
from apps.core.permissions import allowed_area_ids

from .exporters import EXPORTERS
from .models import ReportOutput, ReportRun, ReportSchedule
from .snapshot import build_snapshot

log = logging.getLogger("gpv.reports")
EXT_LABEL = {"pdf": "PDF", "xlsx": "Excel", "csv": "CSV", "docx": "Word", "pptx": "PowerPoint"}


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def create_run(kind, filters, user, formats, title="", notes="", schedule=None, scheduled_for=None):
    formats = [f for f in formats if f in EXPORTERS] or ["pdf"]
    ids = allowed_area_ids(user)
    params = dict(filters or {})
    params["_area_ids"] = sorted(ids) if ids is not None else None
    return ReportRun.objects.create(kind=kind, title=title or "", params=params, formats=formats, author=user, notes=notes,
                                    schedule=schedule, scheduled_for=scheduled_for)


def generate_run(run, ctx=None):
    """Build one snapshot and export it to every requested format. Idempotent per run."""
    if run.status == ReportRun.Status.DONE:
        return run
    ReportRun.objects.filter(pk=run.pk).update(status=ReportRun.Status.RUNNING, attempts=run.attempts + 1, error="")
    user = run.author
    try:
        filters = {k: v for k, v in run.params.items() if not k.startswith("_")}
        if ctx:
            ctx.progress(10, "Tomando instantánea de datos")
        snap = build_snapshot(run.kind, filters, user, title=run.title, notes=run.notes)
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", (run.title or run.get_kind_display()))[:50]
        outputs = []
        for i, fmt in enumerate(run.formats):
            if ctx:
                ctx.progress(20 + int(70 * i / max(1, len(run.formats))), f"Generando {EXT_LABEL.get(fmt, fmt)}")
            data = EXPORTERS[fmt](snap)
            sf = store_generated(data, f"{base}_{stamp}.{fmt}", user)
            ReportOutput.objects.update_or_create(run=run, fmt=fmt, defaults={"file": sf})
            outputs.append(sf)
        ReportRun.objects.filter(pk=run.pk).update(status=ReportRun.Status.DONE, snapshot=snap, data_version=snap["data_version"],
                                                   finished=timezone.now(), title=snap["title"])
        run.refresh_from_db()
        if run.schedule_id:
            ReportSchedule.objects.filter(pk=run.schedule_id).update(last_run=run)
            recipients = list(run.schedule.recipients.all())
            notify(recipients, f"Reporte generado: {run.title}", f"{snap['period_text']} · datos {snap['data_version']}",
                   f"/analitica/reportes/{run.pk}/")
        return run
    except Exception as exc:
        msg = str(exc) if isinstance(exc, UserFacingError) else f"Error al generar: {exc.__class__.__name__}"
        ReportRun.objects.filter(pk=run.pk).update(status=ReportRun.Status.FAILED, error=msg, finished=timezone.now())
        if run.schedule_id:
            ReportSchedule.objects.filter(pk=run.schedule_id).update(last_run=run)
        log.exception("report run %s failed", run.pk)
        raise


@job_handler("reports.generate")
def job_generate(ctx):
    run = ReportRun.objects.select_related("author", "schedule").get(pk=ctx.params["run_id"])
    run = generate_run(run, ctx)
    return {"run_id": run.pk, "url": f"/analitica/reportes/{run.pk}/", "summary": run.title,
            "files": [{"name": o.file.original_name, "url": f"/archivos/{o.file.pk}/", "type": EXT_LABEL.get(o.fmt, o.fmt),
                       "size_h": human_size(o.file.size)} for o in run.outputs.select_related("file")]}


# ---------------------------------------------------------------- scheduler
def _local(dt):
    return timezone.localtime(dt)


def next_occurrence(schedule, after):
    """Next run time strictly after `after`, computed in America/Mexico_City."""
    local_after = _local(after)
    tz = local_after.tzinfo
    if schedule.frequency == ReportSchedule.Frequency.SHIFT:
        if not schedule.shift:
            return None
        t = schedule.shift.end
    else:
        t = schedule.time_of_day or datetime.min.time().replace(hour=6)
    day = local_after.date()
    for i in range(0, 15):
        d = day + timedelta(days=i)
        if schedule.frequency == ReportSchedule.Frequency.WEEKLY and schedule.weekday is not None and d.weekday() != schedule.weekday:
            continue
        cand = timezone.make_aware(datetime.combine(d, t), tz)
        if cand > after:
            return cand
    return None


def acquire_lease(holder, seconds=90):
    now = timezone.now()
    SchedulerLease.objects.get_or_create(name="reports")
    got = SchedulerLease.objects.filter(name="reports").filter(
        models_q_free(now) | models_q_holder(holder)).update(holder=holder, expires_at=now + timedelta(seconds=seconds))
    return got == 1


def models_q_free(now):
    from django.db.models import Q

    return Q(expires_at__isnull=True) | Q(expires_at__lt=now)


def models_q_holder(holder):
    from django.db.models import Q

    return Q(holder=holder)


def release_lease(holder):
    SchedulerLease.objects.filter(name="reports", holder=holder).update(expires_at=None, holder="")


def scheduler_tick(now=None, holder=None):
    """Create due runs. Safe to call repeatedly or concurrently: each (schedule, occurrence)
    pair is protected by a unique constraint, so a retry never duplicates a report.

    Missed occurrences (server off) produce a single catch-up run for the most recent
    occurrence; older missed ones are recorded as skipped.
    """
    now = now or timezone.now()
    created = []
    for sch in ReportSchedule.objects.filter(active=True, next_run_at__isnull=False, next_run_at__lte=now):
        occurrence = sch.next_run_at
        skipped = 0
        nxt = next_occurrence(sch, occurrence)
        while nxt is not None and nxt <= now:  # collapse missed occurrences
            occurrence = nxt
            skipped += 1
            nxt = next_occurrence(sch, occurrence)
        filters = dict(sch.filters or {})
        try:
            with transaction.atomic():
                run = create_run(sch.kind, filters, sch.created_by, sch.formats, title=sch.name, schedule=sch, scheduled_for=occurrence)
                if skipped:
                    run.params["_skipped_missed_occurrences"] = skipped
                    run.save(update_fields=["params"])
        except IntegrityError:
            run = None  # already created by a previous/concurrent tick
        ReportSchedule.objects.filter(pk=sch.pk).update(next_run_at=next_occurrence(sch, max(now, occurrence)))
        if run is not None:
            enqueue("reports.generate", {"run_id": run.pk}, sch.created_by, idempotency_key=f"report-run-{run.pk}")
            created.append(run)
    return created


def retry_run(run, user):
    if run.status != ReportRun.Status.FAILED:
        raise UserFacingError("Solo se pueden reintentar reportes fallidos.")
    ReportRun.objects.filter(pk=run.pk).update(status=ReportRun.Status.PENDING)
    job, _ = enqueue("reports.generate", {"run_id": run.pk}, user, idempotency_key=f"report-run-{run.pk}-retry-{run.attempts}")
    return job


# ---------------------------------------------------------------- dashboard widgets
CALC_TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<name>[a-z_]+)|(?P<op>[-+*/()]))")


def safe_calc(expr, values):
    """Evaluate +, -, *, / and parentheses over whitelisted aggregated measures. No eval()."""
    from apps.production.metrics import MEASURES

    pos, toks = 0, []
    expr = expr.strip()
    while pos < len(expr):
        m = CALC_TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise UserFacingError(f"Expresión no válida cerca de «{expr[pos:pos + 10]}».")
        if m.group("name") and m.group("name") not in MEASURES:
            raise UserFacingError(f"Campo «{m.group('name')}» no permitido. Use: {', '.join(MEASURES)}.")
        toks.append(m)
        pos = m.end()
    i = 0

    def peek():
        return toks[i] if i < len(toks) else None

    def atom():
        nonlocal i
        t = peek()
        if t is None:
            raise UserFacingError("Expresión incompleta.")
        i += 1
        if t.group("num"):
            return float(t.group("num"))
        if t.group("name"):
            v = values.get(t.group("name"))
            return None if v is None else float(v)
        if t.group("op") == "(":
            v = expr_()
            if peek() is None or peek().group("op") != ")":
                raise UserFacingError("Falta cerrar un paréntesis.")
            i += 1
            return v
        if t.group("op") == "-":
            v = atom()
            return None if v is None else -v
        raise UserFacingError("Expresión no válida.")

    def term():
        nonlocal i
        v = atom()
        while peek() is not None and peek().group("op") in ("*", "/"):
            op = peek().group("op")
            i += 1
            w = atom()
            if v is None or w is None:
                v = None
            elif op == "*":
                v = v * w
            else:
                v = None if w == 0 else v / w
        return v

    def expr_():
        nonlocal i
        v = term()
        while peek() is not None and peek().group("op") in ("+", "-"):
            op = peek().group("op")
            i += 1
            w = term()
            v = None if v is None or w is None else (v + w if op == "+" else v - w)
        return v

    result = expr_()
    if i != len(toks):
        raise UserFacingError("Expresión no válida (símbolos sobrantes).")
    return result


def validate_plan_join(key):
    """Joining records to the plan is only allowed on a key unique on the plan side (N:1)."""
    from django.db.models import Count

    from apps.production.models import WorkOrder

    if key == "work_order":
        dup = WorkOrder.objects.values("number").annotate(n=Count("id")).filter(n__gt=1).exists()
        if dup:
            return {"ok": False, "message": "Hay órdenes duplicadas en el plan; la unión multiplicaría cantidades."}
        return {"ok": True, "message": "Relación validada: registros (N) → orden del plan (1) por número de orden."}
    if key == "part_number":
        dup = WorkOrder.objects.exclude(part_number="").values("part_number").annotate(n=Count("id")).filter(n__gt=1).exists()
        if dup:
            return {"ok": False, "message": "Un número de parte aparece en varias órdenes: la unión sería N:N y multiplicaría cantidades. Use la orden como clave."}
        return {"ok": True, "message": "Relación validada por número de parte (único en el plan)."}
    return {"ok": False, "message": "Clave de unión no permitida."}


def widget_data(user, widget, filters):
    from apps.production.metrics import AGGS, DIMENSIONS, MEASURES, Filters, order_rows, series

    f = Filters.from_dict(filters)
    dim = widget.get("dimension", "date")
    measure = widget.get("measure", "qty_good")
    agg = widget.get("agg", "sum")
    if dim not in DIMENSIONS or measure not in MEASURES or agg not in AGGS:
        raise UserFacingError("Configuración de widget no válida (dimensión/medida/agregación).")
    limit = min(int(widget.get("limit") or 30), 200)
    order = widget.get("order", "key")
    pts = series(user, f, dim, measure, agg, limit=None, order=order)
    info = {}
    if widget.get("calc"):
        needed = set(re.findall(r"[a-z_]+", widget["calc"])) & set(MEASURES)
        per = {}
        for m in needed:
            for p in series(user, f, dim, m, "sum", limit=None):
                per.setdefault(p["key"], {})[m] = p["value"]
        pts = [{"key": k, "value": safe_calc(widget["calc"], vals)} for k, vals in per.items()]
        pts.sort(key=lambda p: p["key"])
        if order == "value_desc":
            pts.sort(key=lambda p: -(p["value"] or 0))
        info["calc"] = widget["calc"]
    if widget.get("join_plan"):
        key = widget.get("join_key", "work_order")
        j = validate_plan_join(key)
        info["join"] = j
        if j["ok"] and dim == "work_order":
            rows, _ = order_rows(user, Filters(period="all"))
            planned = {r["number"].upper(): float(r["planned"]) if r["planned"] is not None else None for r in rows}
            for p in pts:
                p["planned"] = planned.get(p["key"].upper())
    return {"points": pts[:limit], "dimension": DIMENSIONS[dim], "measure": MEASURES[measure], "agg": AGGS[agg], **info}


def run_scheduler_loop(stop_after=None, tick_seconds=30):
    """Blocking loop used by ``manage.py run_scheduler``."""
    import time

    holder = worker_id()
    ticks = 0
    try:
        while True:
            if acquire_lease(holder, seconds=tick_seconds * 3):
                for sch in ReportSchedule.objects.filter(active=True, next_run_at__isnull=True):
                    ReportSchedule.objects.filter(pk=sch.pk).update(next_run_at=next_occurrence(sch, timezone.now()))
                created = scheduler_tick(holder=holder)
                if created:
                    log.info("scheduler created %d runs", len(created))
            else:
                log.info("another scheduler holds the lease; waiting")
            # shift portal service (own lease: OData sync never overlaps even if run_shift_service also runs)
            try:
                from apps.shift import service_loop

                if service_loop.acquire(holder, seconds=tick_seconds * 4):
                    service_loop.tick()
            except Exception:
                log.exception("shift service tick failed")
            ticks += 1
            if stop_after and ticks >= stop_after:
                break
            time.sleep(tick_seconds)
    finally:
        release_lease(holder)
        try:
            from apps.shift import service_loop

            service_loop.release(holder)
        except Exception:
            pass
