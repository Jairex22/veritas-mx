"""Import pipeline: analyze -> preview/map -> validate -> commit -> (revert).

Guarantees
----------
* Deterministic parsing (see parsing.py); validation never writes production data.
* Re-importing a file never duplicates data: rows are matched by record key.
* Snapshot datasets supersede the current capture of each key (never summed).
* Commit runs in chunks; each chunk is atomic and every change keeps a before-image.
  If a chunk fails, previously applied chunks are compensated (reverted) automatically
  and the batch is marked FAILED, so a partial import is never left unidentified.
"""
import csv
import hashlib
import io
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.audit import audit
from apps.core.files import store_generated
from apps.core.jobs import UserFacingError
from apps.core.models import Area
from apps.core.permissions import allowed_area_ids

from .fields import DEFAULT_KEYS, FIELDS, RECORD_COLUMNS, REQUIRED
from .models import DatasetKind, ImportBatch, PlanChange, ProductionRecord, RecordChange, WorkOrder
from .parsing import ParseError, Warn, is_null, normalize_unit, parse_value
from .readers import read_file

PLAN_FIELDS = ["customer", "line", "part_number", "revision", "unit", "qty_planned", "priority", "start", "due", "status", "responsible", "notes"]


def _display(v):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


# ---------------------------------------------------------------- analysis
def analyze(stored_file, header_row=1, encoding=None, delimiter=None):
    data = stored_file.path.read_bytes()
    ext = stored_file.ext
    info = read_file(data, ext, header_row=header_row, encoding=encoding, delimiter=delimiter, max_rows=None)
    sheets = []
    for sd in info["sheets"]:
        sample = [[_display(c.value) if c.origin != "missing" else "⚠ fórmula sin valor" for c in infos] for _n, infos in sd.rows[:15]]
        sheets.append({
            "name": sd.name, "headers": sd.headers, "rows": sd.total_rows, "sample": sample,
            "formula_cells": sd.formula_cells, "formula_missing": sd.formula_missing, "formula_computed": sd.formula_computed,
            "features": sd.unsupported_features,
            "empty_headers": [i + 1 for i, h in enumerate(sd.headers) if not h],
            "duplicate_headers": sorted({h for h in sd.headers if h and sd.headers.count(h) > 1}),
        })
    previous = list(
        ImportBatch.objects.filter(file_sha256=stored_file.sha256, status=ImportBatch.Status.COMMITTED)
        .values("id", "dataset__name", "committed_at")
    )
    return {
        "file": stored_file.original_name, "ext": ext, "size": stored_file.size, "sha256": stored_file.sha256,
        "encoding": info.get("encoding"), "delimiter": info.get("delimiter"), "sheets": sheets,
        "previous_imports": [{"id": p["id"], "dataset": p["dataset__name"],
                              "when": timezone.localtime(p["committed_at"]).strftime("%Y-%m-%d %H:%M") if p["committed_at"] else ""}
                             for p in previous],
    }


# ---------------------------------------------------------------- row processing
class RowResult:
    __slots__ = ("row", "values", "errors", "warnings", "key", "area_id", "notes")

    def __init__(self, row):
        self.row = row
        self.values = {}
        self.errors = []  # (column, value, message)
        self.warnings = []
        self.key = None
        self.area_id = None
        self.notes = []


def _area_lookup():
    table = {}
    for a in Area.objects.all():
        table[a.code.lower()] = a.id
        table[a.name.lower()] = a.id
    return table


def _key_for(dataset, values, raw_row):
    fields = dataset.key_fields or DEFAULT_KEYS.get(dataset.kind, [])
    if not fields:
        joined = "␟".join(_display(v) for v in raw_row)
        return "h:" + hashlib.sha1(joined.encode("utf-8")).hexdigest()
    parts = []
    for f in fields:
        v = values.get(f)
        parts.append(_display(v).strip().upper() if f in ("work_order", "serial", "part_number", "line", "station", "shift") else _display(v).strip())
    if not any(parts):
        return None
    return "|".join(parts)[:400]


def _infer_date_order(sd, idx):
    """Column-level evidence: a value like 25/03/2026 proves DD/MM for that file.
    Returns None when there is no evidence or evidence is contradictory (user must choose)."""
    import re as _re

    rx = _re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
    dmy = mdy = False
    cols = [idx[f] for f in ("date", "timestamp", "start", "due") if f in idx]
    for _n, infos in sd.rows:
        for col in cols:
            v = infos[col].value if col < len(infos) else None
            if isinstance(v, str):
                m = rx.match(v)
                if m:
                    a, b = int(m.group(1)), int(m.group(2))
                    dmy |= a > 12 and b <= 12
                    mdy |= b > 12 and a <= 12
    if dmy and not mdy:
        return "DMY"
    if mdy and not dmy:
        return "MDY"
    return None


def iter_rows(batch, user):
    """Parse every data row of the batch file. Yields RowResult."""
    data = batch.source_file.path.read_bytes()
    opts = dict(batch.options or {})
    opts.setdefault("unit_default", batch.dataset.unit_default)
    info = read_file(data, batch.source_file.ext, header_row=int(opts.get("header_row", 1)),
                     encoding=opts.get("encoding") or None, delimiter=opts.get("delimiter") or None,
                     sheet_names=[batch.sheet] if batch.sheet else None)
    sheets = info["sheets"]
    if not sheets:
        raise UserFacingError("El archivo no contiene hojas con datos.")
    sd = sheets[0]
    mapping = {f: h for f, h in (batch.mapping or {}).items() if h}
    missing_headers = [h for h in mapping.values() if h not in sd.headers]
    if missing_headers:
        raise UserFacingError(f"El archivo no tiene las columnas mapeadas: {', '.join(missing_headers)}. Revise el mapeo o el perfil.")
    idx = {f: sd.headers.index(h) for f, h in mapping.items()}
    max_rows = settings.GPV["IMPORT_MAX_ROWS"]
    if sd.total_rows > max_rows:
        raise UserFacingError(f"El archivo tiene {sd.total_rows} filas; el máximo configurado es {max_rows} (GPV_IMPORT_MAX_ROWS).")
    areas = _area_lookup()
    allowed = allowed_area_ids(user)
    if opts.get("date_order", "auto") == "auto":
        hint = _infer_date_order(sd, idx)
        if hint:
            opts["date_order"] = hint
    required = REQUIRED.get(batch.dataset.kind, [])
    for rownum, infos in sd.rows:
        rr = RowResult(rownum)
        raw_values = []
        # unit first: other quantities validate against the row unit
        row_opts = dict(opts)
        if "unit" in idx:
            u = infos[idx["unit"]].value if idx["unit"] < len(infos) else None
            row_opts["_row_unit"] = normalize_unit(u) if not is_null(u) else ""
        for field, col in idx.items():
            cell = infos[col] if col < len(infos) else None
            header = mapping[field]
            value = cell.value if cell else None
            raw_values.append(value)
            if cell is not None and cell.origin == "missing":
                rr.errors.append((header, cell.formula, cell.note))
                continue
            if cell is not None and cell.origin == "stored" and opts.get("warn_stored_formulas", True):
                rr.warnings.append(f"{header}: valor almacenado de fórmula {cell.formula}")
            if cell is not None and cell.origin == "computed":
                rr.notes.append(f"{header}: calculado por el sistema ({cell.formula})")
            if cell is not None and cell.note and cell.origin == "value":
                rr.notes.append(f"{header}: {cell.note}")
            w = Warn()
            try:
                parsed = parse_value(field, value, row_opts, w)
            except ParseError as exc:
                rr.errors.append((header, _display(value), str(exc)))
                continue
            rr.warnings.extend(w.items)
            if field == "unit" and parsed:
                parsed = normalize_unit(parsed)
            rr.values[field] = parsed
        for f in required:
            if rr.values.get(f) in (None, "") and not any(e[0] == mapping.get(f) for e in rr.errors):
                rr.errors.append((mapping.get(f, FIELDS[f][0]), "", f"Falta el dato obligatorio «{FIELDS[f][0]}» para este tipo de dataset."))
        # area
        area_txt = rr.values.pop("area", None)
        if area_txt:
            area_id = areas.get(str(area_txt).strip().lower())
            if area_id is None:
                rr.errors.append((mapping.get("area"), area_txt, f"Área desconocida «{area_txt}». Regístrela en Administración o corrija el archivo."))
        else:
            area_id = batch.dataset.area_id
            if area_id is None:
                rr.errors.append(("Área", "", "El dataset no tiene área por defecto y el archivo no trae columna de área."))
        if area_id is not None and allowed is not None and area_id not in allowed:
            rr.errors.append(("Área", area_txt or "", "No tiene permiso para importar datos de esta área."))
        rr.area_id = area_id
        if not rr.values.get("unit"):
            rr.values["unit"] = normalize_unit(batch.dataset.unit_default) or "pz"
        if batch.dataset.kind == DatasetKind.SERIAL and rr.values.get("result"):
            res = str(rr.values["result"]).strip().upper()
            res = {"OK": "PASS", "P": "PASS", "PASA": "PASS", "F": "FAIL", "NG": "FAIL", "FALLA": "FAIL", "NOK": "FAIL"}.get(res, res)
            if res not in ("PASS", "FAIL"):
                rr.errors.append((mapping.get("result"), rr.values["result"], "El resultado debe ser PASS/FAIL (o OK/NG)."))
            rr.values["result"] = res
        rr.key = _key_for(batch.dataset, rr.values, raw_values)
        if rr.key is None:
            rr.errors.append(("Clave", "", "Todos los campos clave están vacíos; no se puede identificar el registro."))
        yield rr


def _comparable(values):
    return {k: _display(v) for k, v in values.items() if k in RECORD_COLUMNS or k == "extra"}


def _record_values(rec):
    return {f: getattr(rec, f) for f in RECORD_COLUMNS}


def _in_scope(rec_values, scope):
    d = rec_values.get("date")
    if scope.get("date_from") and (d is None or d.isoformat() < scope["date_from"]):
        return False
    if scope.get("date_to") and (d is None or d.isoformat() > scope["date_to"]):
        return False
    if scope.get("line") and (rec_values.get("line") or "").upper() != scope["line"].upper():
        return False
    return True


def plan_changes(batch, user, keep_rows=False):
    """Validate the batch and compute what would change. Writes nothing."""
    ds = batch.dataset
    stats = {"read": 0, "accepted": 0, "rejected": 0, "skipped": 0, "updated": 0, "created": 0,
             "unchanged": 0, "superseded": 0, "removed": 0, "warnings": 0}
    errors, warnings, preview_changes = [], [], []
    seen = {}
    rows = []
    if ds.kind == DatasetKind.PLAN:
        existing = {wo.number.upper(): wo for wo in WorkOrder.objects.all()}
    else:
        existing = {}
        for rec in ProductionRecord.objects.filter(dataset=ds, is_current=True).only(*(["id", "record_key", "area_id", "extra"] + list(RECORD_COLUMNS))):
            existing[rec.record_key] = rec
    mode = batch.mode
    if ds.kind == DatasetKind.SNAPSHOT:
        mode = "snapshot"
    for rr in iter_rows(batch, user):
        stats["read"] += 1
        if rr.key and rr.key in seen and not rr.errors:
            rr.errors.append(("Clave", rr.key, f"Clave duplicada dentro del archivo (también en la fila {seen[rr.key]}). Corrija o elimine la fila repetida."))
        if rr.errors:
            stats["rejected"] += 1
            for col, val, msg in rr.errors:
                errors.append({"sheet": batch.sheet or "CSV", "row": rr.row, "column": col or "", "value": _display(val)[:120], "message": msg})
            continue
        seen[rr.key] = rr.row
        if rr.warnings:
            stats["warnings"] += 1
            for w in rr.warnings[:3]:
                warnings.append({"row": rr.row, "message": w})
        stats["accepted"] += 1
        action = "create"
        diff = {}
        if ds.kind == DatasetKind.PLAN:
            number = str(rr.values.get("work_order")).strip()
            wo = existing.get(number.upper())
            if wo is not None:
                for f in PLAN_FIELDS:
                    if f in rr.values and rr.values[f] is not None and _display(getattr(wo, f)) != _display(rr.values[f]):
                        diff[f] = (_display(getattr(wo, f)), _display(rr.values[f]))
                if rr.area_id != wo.area_id:
                    diff["area"] = (str(wo.area_id), str(rr.area_id))
                action = "unchanged" if not diff else ("skip" if mode == "append" else "update")
        else:
            cur = existing.get(rr.key)
            if cur is not None:
                new_cmp = _comparable(rr.values)
                old_cmp = {k: _display(getattr(cur, k)) for k in new_cmp}
                diff = {k: (old_cmp[k], new_cmp[k]) for k in new_cmp if old_cmp[k] != new_cmp[k]}
                if cur.area_id != rr.area_id:
                    diff["area"] = (str(cur.area_id), str(rr.area_id))
                if not diff:
                    action = "unchanged"
                elif mode == "snapshot":
                    ts_new, ts_old = rr.values.get("timestamp") or rr.values.get("date"), cur.timestamp or cur.date
                    if ts_new is not None and ts_old is not None and type(ts_new) is type(ts_old) and ts_new < ts_old:
                        stats["accepted"] -= 1
                        stats["rejected"] += 1
                        errors.append({"sheet": batch.sheet or "CSV", "row": rr.row, "column": "Fecha/hora", "value": _display(ts_new),
                                       "message": f"La captura es más antigua que la vigente ({_display(ts_old)}); no reemplaza datos más recientes."})
                        continue
                    action = "supersede"
                elif mode == "append":
                    action = "skip"
                else:
                    action = "update"
        key_stat = {"create": "created", "update": "updated", "unchanged": "unchanged", "skip": "skipped", "supersede": "superseded"}[action]
        stats[key_stat] += 1
        if action in ("update", "supersede", "skip") and len(preview_changes) < 200:
            preview_changes.append({"row": rr.row, "key": rr.key, "action": action, "diff": {k: list(v) for k, v in list(diff.items())[:8]}})
        if keep_rows:
            rows.append((rr, action))
    removed = []
    if mode == "replace" and ds.kind != DatasetKind.PLAN:
        scope = batch.scope or {}
        if not (scope.get("date_from") or scope.get("date_to") or scope.get("line")):
            raise UserFacingError("El modo «Reemplazar alcance» requiere definir un alcance (rango de fechas y/o línea).")
        allowed = allowed_area_ids(user)
        for key, rec in existing.items():
            if key in seen:
                continue
            if _in_scope(_record_values(rec), scope):
                if allowed is not None and rec.area_id not in allowed:
                    raise UserFacingError("El alcance incluye registros de áreas sin permiso; restrinja el alcance.")
                removed.append(rec.id)
        stats["removed"] = len(removed)
    result = {"stats": stats, "errors": errors[:1000], "errors_total": len(errors), "warnings": warnings[:300],
              "changes": preview_changes, "mode": mode}
    if keep_rows:
        result["_rows"] = rows
        result["_existing"] = existing
        result["_removed"] = removed
        result["_all_errors"] = errors
    return result


def errors_csv(errors):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Hoja", "Fila", "Columna", "Valor", "Error"])
    for e in errors:
        w.writerow([e["sheet"], e["row"], e["column"], _safe_csv(e["value"]), e["message"]])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _safe_csv(value):
    """Prevent spreadsheet formula injection when the CSV is opened in Excel."""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def validate(batch, user):
    result = plan_changes(batch, user)
    batch.analysis = {**(batch.analysis or {}), "validation": {k: v for k, v in result.items() if not k.startswith("_")}}
    if result["errors_total"]:
        ef = store_generated(errors_csv(plan_changes_errors_all(batch, user, result)), f"errores_lote_{batch.pk}.csv", user,
                             parent=batch.source_file)
        batch.error_file = ef
    else:
        batch.error_file = None
    batch.stats = result["stats"]
    batch.status = ImportBatch.Status.VALIDATED
    batch.save()
    return result


def plan_changes_errors_all(batch, user, result):
    if result["errors_total"] <= len(result["errors"]):
        return result["errors"]
    return plan_changes(batch, user, keep_rows=True)["_all_errors"]


# ---------------------------------------------------------------- commit
def _db_value(field, value):
    """CharField/TextField columns are NOT NULL: empty text is stored as ''."""
    if value is None and FIELDS[field][1] == "text":
        return ""
    return value


def _record_kwargs(ds, batch, rr, user):
    kw = {k: _db_value(k, v) for k, v in rr.values.items() if k in RECORD_COLUMNS}
    extra = {k: _display(v) for k, v in rr.values.items() if k not in RECORD_COLUMNS}
    return dict(dataset=ds, batch=batch, last_batch=batch, record_key=rr.key, row_number=rr.row, area_id=rr.area_id,
                extra=extra, entered_by=user, updated=timezone.now(), **kw)


def _snapshot_before(rec):
    data = {f: _display(getattr(rec, f)) if getattr(rec, f) is not None else None for f in RECORD_COLUMNS}
    data["area_id"] = rec.area_id
    data["extra"] = rec.extra
    data["last_batch_id"] = rec.last_batch_id
    return data


def commit(batch, user, ctx=None):
    if batch.status not in (ImportBatch.Status.VALIDATED, ImportBatch.Status.DRAFT):
        raise UserFacingError(f"El lote está en estado «{batch.get_status_display()}» y no puede importarse.")
    updated_rows = ImportBatch.objects.filter(pk=batch.pk, status__in=[ImportBatch.Status.VALIDATED, ImportBatch.Status.DRAFT]).update(
        status=ImportBatch.Status.COMMITTING)
    if updated_rows != 1:
        raise UserFacingError("Este lote ya se está importando (doble envío bloqueado).")
    batch.refresh_from_db()
    try:
        plan = plan_changes(batch, user, keep_rows=True)
        if plan["stats"]["rejected"] and not (batch.options or {}).get("allow_partial", False):
            raise UserFacingError(
                f"Hay {plan['stats']['rejected']} filas con errores. Corríjalas o active «Importar solo filas válidas»."
            )
        ds = batch.dataset
        rows = plan["_rows"]
        chunk = settings.GPV["IMPORT_CHUNK_ROWS"]
        total = max(len(rows), 1)
        for start in range(0, len(rows), chunk):
            part = rows[start:start + chunk]
            with transaction.atomic():
                if ds.kind == DatasetKind.PLAN:
                    _apply_plan_chunk(batch, user, part)
                else:
                    _apply_record_chunk(batch, user, part, plan["_existing"])
            if ctx:
                ctx.progress(5 + int(90 * (start + len(part)) / total), f"Importando filas {start + len(part)} de {len(rows)}")
        if plan["_removed"]:
            with transaction.atomic():
                for rec in ProductionRecord.objects.filter(id__in=plan["_removed"], is_current=True):
                    RecordChange.objects.create(batch=batch, record=rec, action=RecordChange.Action.REMOVE, before=_snapshot_before(rec))
                    rec.is_current = False
                    rec.last_batch = batch
                    rec.save(update_fields=["is_current", "last_batch"])
        with transaction.atomic():
            ds.refresh_from_db()
            ds.version = F("version") + 1
            ds.last_import_at = timezone.now()
            ds.save(update_fields=["version", "last_import_at"])
            ds.refresh_from_db()
            batch.status = ImportBatch.Status.COMMITTED
            batch.committed_at = timezone.now()
            batch.stats = plan["stats"]
            batch.dataset_version = ds.version
            batch.save()
        audit(user, "import.committed", batch, f"Importación lote #{batch.pk} en {ds.name}: {plan['stats']}", area=ds.area)
        return plan["stats"]
    except Exception as exc:
        # compensate whatever chunks were applied, then mark FAILED (never silently partial)
        compensated = _compensate(batch)
        if compensated == 0 and isinstance(exc, UserFacingError):
            # nothing was applied: keep the batch editable so the user can fix and retry
            ImportBatch.objects.filter(pk=batch.pk).update(status=ImportBatch.Status.VALIDATED, error_message=str(exc))
            raise
        ImportBatch.objects.filter(pk=batch.pk).update(
            status=ImportBatch.Status.FAILED,
            error_message=(str(exc) if isinstance(exc, UserFacingError) else "Error interno durante la importación.")
            + (f" Se revirtieron {compensated} cambios aplicados parcialmente." if compensated else " No se aplicaron cambios."),
        )
        raise


def _apply_record_chunk(batch, user, part, existing):
    ds = batch.dataset
    new_objs, changes = [], []
    for rr, action in part:
        if action in ("unchanged", "skip"):
            continue
        cur = existing.get(rr.key)
        if action == "create":
            new_objs.append(ProductionRecord(**_record_kwargs(ds, batch, rr, user)))
        elif action == "update":
            before = _snapshot_before(cur)
            for k, v in rr.values.items():
                if k in RECORD_COLUMNS:
                    setattr(cur, k, _db_value(k, v))
            cur.area_id = rr.area_id
            cur.extra = {k: _display(v) for k, v in rr.values.items() if k not in RECORD_COLUMNS}
            cur.last_batch = batch
            cur.row_number = rr.row
            cur.updated = timezone.now()
            cur.save()
            changes.append(RecordChange(batch=batch, record=cur, action=RecordChange.Action.UPDATE, before=before))
        elif action == "supersede":
            before = _snapshot_before(cur)
            ProductionRecord.objects.filter(pk=cur.pk).update(is_current=False, last_batch=batch)
            changes.append(RecordChange(batch=batch, record=cur, action=RecordChange.Action.SUPERSEDE, before=before))
            new_objs.append(ProductionRecord(**_record_kwargs(ds, batch, rr, user)))
    if new_objs:
        created = ProductionRecord.objects.bulk_create(new_objs, batch_size=1000)
        changes.extend(RecordChange(batch=batch, record=r, action=RecordChange.Action.CREATE) for r in created)
    if changes:
        RecordChange.objects.bulk_create(changes, batch_size=1000)


def _apply_plan_chunk(batch, user, part):
    reason = f"Importación lote #{batch.pk} ({batch.source_file.original_name})"
    for rr, action in part:
        if action in ("unchanged", "skip"):
            continue
        number = str(rr.values["work_order"]).strip()
        if action == "create":
            wo = WorkOrder.objects.create(
                number=number, area_id=rr.area_id, source_batch=batch, last_batch=batch,
                **{f: rr.values[f] for f in PLAN_FIELDS if rr.values.get(f) not in (None, "")},
            )
            PlanChange.objects.create(work_order=wo, field="*", old_value=None, new_value="creada", reason=reason, user=user,
                                      batch=batch, created_order=True)
        else:
            wo = WorkOrder.objects.select_for_update().get(number__iexact=number)
            for f in PLAN_FIELDS:
                if f in rr.values and rr.values[f] is not None and _display(getattr(wo, f)) != _display(rr.values[f]):
                    PlanChange.objects.create(work_order=wo, field=f, old_value=_display(getattr(wo, f)), new_value=_display(rr.values[f]),
                                              reason=reason, user=user, batch=batch)
                    setattr(wo, f, rr.values[f])
            if rr.area_id != wo.area_id:
                PlanChange.objects.create(work_order=wo, field="area", old_value=str(wo.area_id), new_value=str(rr.area_id), reason=reason,
                                          user=user, batch=batch)
                wo.area_id = rr.area_id
            wo.last_batch = batch
            wo.version += 1
            wo.updated = timezone.now()
            wo.save()


# ---------------------------------------------------------------- revert
def _restore_fields(rec, before):
    from .parsing import parse_value

    for f in RECORD_COLUMNS:
        raw = before.get(f)
        if raw is None:
            setattr(rec, f, None if f not in ("shift", "customer", "line", "work_order", "part_number", "revision", "unit", "station",
                                                "serial", "result", "cause", "responsible", "status", "notes") else "")
            continue
        ftype = FIELDS[f][1]
        if ftype == "text":
            setattr(rec, f, raw)
        elif ftype == "int":
            setattr(rec, f, int(raw))
        elif ftype == "decimal":
            setattr(rec, f, Decimal(raw))
        elif ftype == "date":
            from datetime import date

            setattr(rec, f, date.fromisoformat(raw))
        else:
            from datetime import datetime

            setattr(rec, f, datetime.fromisoformat(raw))
    rec.area_id = before.get("area_id")
    rec.extra = before.get("extra") or {}
    rec.last_batch_id = before.get("last_batch_id")


def _compensate(batch):
    """Undo all applied changes of a failing batch (no conflict checks needed: same batch)."""
    n = 0
    with transaction.atomic():
        for ch in RecordChange.objects.filter(batch=batch, action=RecordChange.Action.CREATE).select_related("record"):
            ch.record.delete()
            n += 1
        for ch in RecordChange.objects.filter(batch=batch).exclude(action=RecordChange.Action.CREATE).select_related("record"):
            rec = ch.record
            _restore_fields(rec, ch.before or {})
            rec.is_current = True
            rec.save()
            n += 1
        RecordChange.objects.filter(batch=batch).delete()
        for pc in PlanChange.objects.filter(batch=batch).select_related("work_order").order_by("-ts", "-id"):
            wo = pc.work_order
            if pc.created_order:
                wo.delete()
            elif pc.field == "area":
                wo.area_id = int(pc.old_value)
                wo.save()
            else:
                _set_plan_field(wo, pc.field, pc.old_value)
                wo.save()
            n += 1
    return n


def _set_plan_field(wo, field, text):
    from datetime import datetime

    if text in (None, ""):
        value = None if field in ("qty_planned", "start", "due") else ("" if field != "priority" else 3)
    elif field == "qty_planned":
        value = Decimal(text)
    elif field == "priority":
        value = int(text)
    elif field in ("start", "due"):
        value = datetime.fromisoformat(text)
    else:
        value = text
    setattr(wo, field, value)


def revert(batch, user, reason):
    """Revert a committed batch without destroying later changes.

    A record (or plan field) modified after this batch by another batch or a manual edit is
    left untouched and reported as a conflict.
    """
    if batch.status != ImportBatch.Status.COMMITTED:
        raise UserFacingError("Solo se pueden revertir lotes en estado «Importado».")
    conflicts, restored, deleted = [], 0, 0
    with transaction.atomic():
        locked = ImportBatch.objects.select_for_update().get(pk=batch.pk)
        if locked.status != ImportBatch.Status.COMMITTED:
            raise UserFacingError("El lote ya fue revertido.")
        creates = RecordChange.objects.filter(batch=batch, action=RecordChange.Action.CREATE).select_related("record")
        for ch in creates:
            rec = ch.record
            if rec.last_batch_id != batch.pk:
                conflicts.append(f"Registro {rec.record_key}: modificado después por el lote #{rec.last_batch_id}; se conserva.")
                continue
            rec.delete()
            deleted += 1
        for ch in RecordChange.objects.filter(batch=batch).exclude(action=RecordChange.Action.CREATE).select_related("record"):
            rec = ch.record
            if rec.last_batch_id != batch.pk:
                conflicts.append(f"Registro {rec.record_key}: modificado después por el lote #{rec.last_batch_id}; se conserva.")
                continue
            if ch.action in (RecordChange.Action.SUPERSEDE, RecordChange.Action.REMOVE):
                if ProductionRecord.objects.filter(dataset=rec.dataset, record_key=rec.record_key, is_current=True).exists():
                    conflicts.append(f"Registro {rec.record_key}: existe una versión vigente posterior; no se reactiva la anterior.")
                    continue
                rec.is_current = True
            _restore_fields(rec, ch.before or {})
            if ch.action in (RecordChange.Action.SUPERSEDE, RecordChange.Action.REMOVE):
                rec.is_current = True
            rec.save()
            restored += 1
        # plan changes
        for pc in PlanChange.objects.filter(batch=batch).select_related("work_order").order_by("-ts", "-id"):
            wo = pc.work_order
            later = PlanChange.objects.filter(work_order=wo, ts__gt=pc.ts).exclude(batch=batch).exists()
            if later:
                conflicts.append(f"Orden {wo.number}: cambió después ({pc.field}); se conserva el valor actual.")
                continue
            if pc.created_order:
                if ProductionRecord.objects.filter(work_order__iexact=wo.number, is_current=True).exists():
                    conflicts.append(f"Orden {wo.number}: tiene producción registrada; se conserva la orden.")
                    continue
                wo.delete()
                deleted += 1
                continue
            if pc.field == "area":
                wo.area_id = int(pc.old_value)
            else:
                _set_plan_field(wo, pc.field, pc.old_value)
            wo.version += 1
            wo.save()
            PlanChange.objects.create(work_order=wo, field=pc.field, old_value=pc.new_value, new_value=pc.old_value,
                                      reason=f"Reversión lote #{batch.pk}: {reason}", user=user)
            restored += 1
        status = ImportBatch.Status.PARTIAL_REVERTED if conflicts else ImportBatch.Status.REVERTED
        locked.status = status
        locked.reverted_at = timezone.now()
        locked.reverted_by = user
        locked.stats = {**locked.stats, "revert": {"restored": restored, "deleted": deleted, "conflicts": len(conflicts)}}
        locked.analysis = {**locked.analysis, "revert_conflicts": conflicts[:500], "revert_reason": reason}
        locked.save()
        ds = batch.dataset
        ds.version = F("version") + 1
        ds.save(update_fields=["version"])
    audit(user, "import.reverted", batch, f"Reversión lote #{batch.pk}: {restored} restaurados, {deleted} eliminados, {len(conflicts)} conflictos. Motivo: {reason}")
    return {"restored": restored, "deleted": deleted, "conflicts": conflicts}
