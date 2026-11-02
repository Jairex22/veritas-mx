import platform
import time
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Mide importación (validar + importar) y consultas de indicadores con un CSV sintético. Usar en una base de PRUEBA."

    def add_arguments(self, parser):
        parser.add_argument("--rows", type=int, default=100_000)
        parser.add_argument("--confirmar", action="store_true", help="Confirma que la base actual es de prueba.")

    def handle(self, *args, **o):
        if not o["confirmar"]:
            self.stderr.write("Ejecute en una base de prueba y agregue --confirmar.")
            return
        from django.contrib.auth import get_user_model

        from apps.core.models import Area, StoredFile
        from apps.production.fields import auto_map
        from apps.production.importer import analyze, commit, validate
        from apps.production.metrics import Filters, kpi_summary, order_rows, series
        from apps.production.models import Dataset, ImportBatch, WorkOrder

        path = Path("data/perf_produccion.csv")
        call_command("gen_perf_data", rows=o["rows"], output=str(path))
        area, _ = Area.objects.get_or_create(code="SMT", defaults={"name": "SMT"})
        user = get_user_model().objects.filter(is_superuser=True).first()
        ds, _ = Dataset.objects.get_or_create(code="perf", defaults={"name": "Perf", "kind": "incremental", "area": area,
                                                                     "key_fields": ["date", "shift", "line", "work_order", "station"], "finished_station": "FINAL"})
        if not WorkOrder.objects.filter(number="P000000").exists():
            WorkOrder.objects.bulk_create([WorkOrder(number=f"P{i:06d}", area=area, qty_planned=5000, line=f"L{i % 20 + 1:02d}") for i in range(2000)])
        res = {}
        t = time.perf_counter()
        sf = StoredFile.create_from_path(path, path.name, owner=user, source="import", area=area)
        b = ImportBatch.objects.create(dataset=ds, source_file=sf, file_sha256=sf.sha256, created_by=user, mode="upsert", options={"header_row": 1})
        b.analysis = analyze(sf)
        b.mapping = auto_map(b.analysis["sheets"][0]["headers"])
        b.mapping.update({"qty_good": "Buenas", "qty_reject": "Rechazo", "qty_scrap": "Scrap"})
        b.save()
        res["analizar_s"] = time.perf_counter() - t
        t = time.perf_counter()
        v = validate(b, user)
        res["validar_s"] = time.perf_counter() - t
        b.refresh_from_db()
        t = time.perf_counter()
        stats = commit(b, user)
        res["importar_s"] = time.perf_counter() - t
        for name, fn in (("kpi_summary_s", lambda: kpi_summary(user, Filters(period="all"))),
                         ("order_rows_s", lambda: order_rows(user, Filters(period="all"))),
                         ("serie_por_dia_s", lambda: series(user, Filters(period="all"), "date", "qty_good", "sum")),
                         ("serie_por_linea_s", lambda: series(user, Filters(period="all"), "line", "qty_good", "sum"))):
            t = time.perf_counter()
            fn()
            res[name] = time.perf_counter() - t
        self.stdout.write(f"Equipo: {platform.platform()} · Python {platform.python_version()} · BD {connection.vendor}")
        self.stdout.write(f"Filas: {o['rows']} · resultado: {stats} · errores de validación: {v['errors_total']}")
        for k, val in res.items():
            self.stdout.write(f"  {k}: {val:.2f}")
