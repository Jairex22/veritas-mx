"""Shared fixtures for the automated tests (synthetic data only)."""
import io
from datetime import time

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import Area, Profile, Role, Shift, StoredFile


def areas():
    out = {}
    for code in ("SMT", "ENS", "PRU", "EMP"):
        out[code], _ = Area.objects.get_or_create(code=code, defaults={"name": code})
    Shift.objects.get_or_create(code="T1", defaults={"name": "T1", "start": time(6), "end": time(14)})
    Shift.objects.get_or_create(code="T2", defaults={"name": "T2", "start": time(14), "end": time(22)})
    return out


def user(username, role=Role.OPERATOR, area_codes=("SMT",), superuser=False):
    User = get_user_model()
    if superuser:
        u = User.objects.create_superuser(username, f"{username}@example.invalid", "x-Pass-1234")
    else:
        u = User.objects.create_user(username, f"{username}@example.invalid", "x-Pass-1234")
    p, _ = Profile.objects.get_or_create(user=u)
    p.role = Role.ADMIN if superuser else role
    p.save()
    p.areas.set(Area.objects.filter(code__in=area_codes))
    return u


def dataset(code, kind, area, keys=None, station=""):
    from apps.production.fields import DEFAULT_KEYS
    from apps.production.models import Dataset

    return Dataset.objects.create(code=code, name=code, kind=kind, area=area, key_fields=keys or DEFAULT_KEYS[kind], finished_station=station,
                                  counts_as_production=kind in ("incremental", "snapshot"))


def run_import(owner, ds, data: bytes, name, mapping=None, options=None, mode="upsert", sheet="", commit=True):
    """Drive the real pipeline: store -> analyze -> map -> validate -> commit."""
    from apps.production.fields import auto_map
    from apps.production.importer import analyze, commit as do_commit, validate
    from apps.production.models import ImportBatch

    sf = StoredFile.create_from_bytes(data, name, owner=owner, source="import", area=ds.area)
    b = ImportBatch.objects.create(dataset=ds, source_file=sf, file_sha256=sf.sha256, created_by=owner, mode=mode, sheet=sheet,
                                   options={"header_row": 1, **(options or {})})
    b.analysis = analyze(sf)
    sheet_info = next((s for s in b.analysis["sheets"] if not sheet or s["name"] == sheet), b.analysis["sheets"][0])
    b.mapping = auto_map(sheet_info["headers"])
    b.mapping.update(mapping or {})
    b.save()
    result = validate(b, owner)
    stats = None
    if commit:
        b.refresh_from_db()
        stats = do_commit(b, owner)
    b.refresh_from_db()
    return b, result, stats


def upload(name, data, ctype="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=ctype)


def xlsx_bytes(sheets):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
