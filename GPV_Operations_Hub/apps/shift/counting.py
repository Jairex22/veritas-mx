"""Counting rules and reconciliation (definitions in DEFINICIONES_DE_DATOS_Y_KPI.md).

Confirmed good units for a scope = events of the line's count-point station only
(passing Top and Bottom or other stations never adds pieces), current version only:
  * incremental events with a serial: distinct serials whose LATEST attempt passed
    (a retest is not another piece);
  * incremental events without serial: sum of qty (each event is an independent fact);
  * snapshots: the latest row per scope_key replaces the previous one (never summed).
Manual captures are shown apart as provisional until reconciled/accepted.
Panels are converted to pieces ONLY with a confirmed panel factor.
"""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit

from .models import EventRevision, ProductionEvent as PE

ZERO = Decimal("0")


def _to_unit(qty, unit, target_unit, line):
    """Return (qty_in_target_unit, ok, reason)."""
    if not target_unit or unit == target_unit:
        return qty, True, ""
    if unit == "panel" and target_unit == "pz":
        if line is not None and line.panel_factor and line.panel_factor_confirmed:
            return qty * line.panel_factor, True, ""
        return None, False, "Las cantidades vienen en paneles y no hay un factor de panelización confirmado; no se convierten."
    return None, False, f"Unidad «{unit}» no comparable con «{target_unit}»."


def count_good(events, line=None, target_unit="pz"):
    """events: queryset/list of ProductionEvent (confirmed sources). Returns dict."""
    serial_latest = {}
    snapshots = {}
    total = ZERO
    issues = set()
    first_attempts = {}
    unmapped = 0
    for e in events:
        if not e.is_current:
            continue
        if line is not None and (not e.station_id or not e.station.is_count_point):
            if not e.station_id:
                unmapped += 1  # never counted: an unmapped event could be Top+Bottom of the same piece
            continue
        if e.kind == PE.Kind.SNAPSHOT:
            cur = snapshots.get(e.scope_key)
            if cur is None or (e.event_at, e.version) > (cur.event_at, cur.version):
                snapshots[e.scope_key] = e
            continue
        if e.serial:
            prev = serial_latest.get(e.serial)
            if prev is None or ((e.attempt or 0), e.event_at) > ((prev.attempt or 0), prev.event_at):
                serial_latest[e.serial] = e
            if (e.attempt or 1) == 1:
                first_attempts[e.serial] = e.result
            continue
        q, ok, why = _to_unit(e.qty, e.unit, target_unit, line)
        if not ok:
            issues.add(why)
            continue
        if e.result in ("", "PASS"):
            total += q
    for e in serial_latest.values():
        if e.result in ("", "PASS"):
            q, ok, why = _to_unit(Decimal(1) if e.unit == "pz" else e.qty, e.unit, target_unit, line)
            if ok:
                total += q
            else:
                issues.add(why)
    for e in snapshots.values():
        q, ok, why = _to_unit(e.qty, e.unit, target_unit, line)
        if ok:
            total += q
        else:
            issues.add(why)
    fpy = None
    if first_attempts:
        fpy = round(100 * sum(1 for r in first_attempts.values() if r == "PASS") / len(first_attempts), 2)
    return {"good": total, "issues": sorted(issues), "fpy": fpy, "first_attempts": len(first_attempts), "unmapped": unmapped,
            "retests": sum(1 for e in serial_latest.values() if (e.attempt or 1) > 1)}


def scope_counts(line, work_order=None, start=None, end=None, target_unit="pz"):
    qs = PE.objects.filter(line=line, is_current=True).select_related("station")
    if work_order:
        qs = qs.filter(work_order__iexact=work_order)
    if start:
        qs = qs.filter(event_at__gte=start)
    if end:
        qs = qs.filter(event_at__lt=end)
    auto = qs.exclude(source=PE.Source.MANUAL)
    # only the count-point operation counts: filter in SQL (events of other stations never count)
    confirmed = count_good(auto.filter(station__is_count_point=True).only(
        "is_current", "station__is_count_point", "kind", "scope_key", "event_at", "version", "serial", "attempt", "result", "qty", "unit"),
        line, target_unit)
    confirmed["unmapped"] = auto.filter(station__isnull=True).count()
    manual = qs.filter(source=PE.Source.MANUAL)
    provisional = ZERO
    accepted = ZERO
    for m in manual:
        q, ok, why = _to_unit(m.qty, m.unit, target_unit, line)
        if not ok:
            confirmed["issues"].append(why)
            continue
        if m.recon_status in (PE.Recon.PENDING, PE.Recon.REVIEW):
            provisional += q
        elif m.recon_status == PE.Recon.ACCEPTED:
            accepted += q
    return {"confirmed": confirmed["good"] + accepted, "provisional": provisional, "issues": confirmed["issues"], "unmapped": confirmed["unmapped"],
            "fpy": confirmed["fpy"], "retests": confirmed["retests"],
            "pending_manual": manual.filter(recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW]).count()}


# ---------------------------------------------------------------- reconciliation
def candidates(manual):
    """Automatic events that could be the same fact as a manual capture."""
    qs = PE.objects.filter(is_current=True, line=manual.line, work_order__iexact=manual.work_order).exclude(source=PE.Source.MANUAL)
    if manual.operation:
        qs = qs.filter(operation__iexact=manual.operation)
    start, end = manual.event_at, manual.period_end or manual.event_at
    return [e for e in qs if start - timezone.timedelta(minutes=30) <= e.event_at <= end + timezone.timedelta(minutes=30)]


def reconcile(manual, user=None):
    """Apply the verified rule to one manual capture.

    Rule (CONCILIACION_CAPTURA_ODATA.md): the SAME fact is proven only by a shared physical
    reference (lot/panel/label ref or serial) plus same order (and operation when known) and
    compatible quantity/unit. Equal totals alone are NOT proof: such cases go to review.
    """
    if manual.source != PE.Source.MANUAL or manual.recon_status not in (PE.Recon.PENDING, PE.Recon.REVIEW):
        return manual.recon_status
    cands = candidates(manual)
    ref_matches = [e for e in cands if manual.lot_ref and (e.lot_ref == manual.lot_ref or e.panel_id == manual.lot_ref)]
    if manual.serial:
        ref_matches += [e for e in cands if e.serial == manual.serial and e not in ref_matches]
    with transaction.atomic():
        before = {"recon_status": manual.recon_status, "reconciled_with": manual.reconciled_with_id}
        if len(ref_matches) == 1 and ref_matches[0].unit == manual.unit and ref_matches[0].qty == manual.qty:
            manual.recon_status = PE.Recon.RECONCILED
            manual.reconciled_with = ref_matches[0]
            note = f"Conciliado automáticamente con evento OData {ref_matches[0].external_key} (misma referencia {manual.lot_ref or manual.serial})."
        elif ref_matches:
            manual.recon_status = PE.Recon.REVIEW
            note = "La referencia coincide pero cantidad/unidad o número de candidatos no: requiere revisión."
        elif any(e.qty == manual.qty and e.unit == manual.unit for e in cands):
            manual.recon_status = PE.Recon.REVIEW
            note = "Existe un registro automático con la misma cantidad pero sin referencia común: puede ser el mismo hecho o un lote distinto. Requiere revisión."
        else:
            manual.recon_status = PE.Recon.PENDING
            note = "Sin equivalente automático por ahora."
        if before["recon_status"] != manual.recon_status:
            manual.save(update_fields=["recon_status", "reconciled_with"])
            EventRevision.objects.create(event=manual, action="reconcile", before=before, user=user, note=note[:300])
    return manual.recon_status


def review(manual, user, decision, match=None, note=""):
    """Authorized reviewer decision: 'same' (link to match), 'distinct' (accept as additional) or 'reject'."""
    from apps.core.jobs import UserFacingError

    if manual.source != PE.Source.MANUAL:
        raise UserFacingError("Solo se revisan capturas manuales.")
    before = {"recon_status": manual.recon_status, "reconciled_with": manual.reconciled_with_id}
    if decision == "same":
        if match is None or match.source == PE.Source.MANUAL:
            raise UserFacingError("Seleccione el registro automático equivalente.")
        manual.recon_status, manual.reconciled_with = PE.Recon.RECONCILED, match
    elif decision == "distinct":
        manual.recon_status, manual.reconciled_with = PE.Recon.ACCEPTED, None
    elif decision == "reject":
        manual.recon_status, manual.reconciled_with = PE.Recon.REJECTED, None
    else:
        raise UserFacingError("Decisión no válida.")
    if len(note.strip()) < 5:
        raise UserFacingError("Indique el motivo de la decisión.")
    manual.save(update_fields=["recon_status", "reconciled_with"])
    EventRevision.objects.create(event=manual, action=f"review:{decision}", before=before, user=user, note=note[:300])
    audit(user, "shift.reconcile_review", manual, f"Captura manual #{manual.pk}: {manual.get_recon_status_display()} · {note}")
    return manual


def reconcile_pending(line=None):
    qs = PE.objects.filter(source=PE.Source.MANUAL, recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW])
    if line is not None:
        qs = qs.filter(line=line)
    changed = defaultdict(int)
    for m in qs:
        changed[reconcile(m)] += 1
    return dict(changed)
