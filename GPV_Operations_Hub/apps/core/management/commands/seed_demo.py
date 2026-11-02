"""Optional demo data. Never runs in production unless GPV_ALLOW_DEMO=true is set explicitly."""
import tempfile
from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Area, Profile, Role, Shift, StoredFile

DEMO_USERS = [
    ("supervisor1", "Sofía", "Supervisora", Role.SUPERVISOR, ["SMT", "ENS", "EMP"]),
    ("ingeniero1", "Iván", "Ingeniero", Role.ENGINEER, ["SMT", "ENS", "PRU", "EMP"]),
    ("operador1", "Oscar", "Operador", Role.OPERATOR, ["SMT"]),
    ("lector1", "Laura", "Lectora", Role.OPERATOR, ["ENS"]),
]


class Command(BaseCommand):
    help = "Carga datos de DEMOSTRACIÓN sintéticos (áreas, turnos, usuarios de prueba, importaciones, Kaizen, etiquetas). Opcional."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Contraseña para los usuarios demo (si se omite se genera y se muestra una vez).")
        parser.add_argument("--sin-usuarios", action="store_true", help="No crear usuarios demo.")

    def handle(self, *args, **opts):
        if not settings.GPV["ALLOW_DEMO"]:
            raise CommandError("Los datos de demostración están deshabilitados en este perfil (GPV_ALLOW_DEMO=false).")
        import secrets

        from apps.core.samples import label_templates, write_all

        pwd = opts.get("password") or ("Demo-" + secrets.token_urlsafe(8))
        with transaction.atomic():
            areas = {}
            for code, name in (("SMT", "Montaje superficial"), ("ENS", "Ensamble final"), ("PRU", "Pruebas"), ("EMP", "Empaque")):
                areas[code], _ = Area.objects.get_or_create(code=code, defaults={"name": name})
            for code, name, a, b in (("T1", "Primer turno", time(6), time(14)), ("T2", "Segundo turno", time(14), time(22)), ("T3", "Tercer turno", time(22), time(6))):
                Shift.objects.get_or_create(code=code, defaults={"name": name, "start": a, "end": b})
            User = get_user_model()
            users = {}
            if not opts["sin_usuarios"]:
                for username, first, last, role, codes in DEMO_USERS:
                    u, created = User.objects.get_or_create(username=username, defaults={"first_name": first, "last_name": last})
                    if created:
                        u.set_password(pwd)
                        u.save()
                    p, _ = Profile.objects.get_or_create(user=u)
                    p.role = role
                    p.shift = Shift.objects.get(code="T1")
                    p.save()
                    p.areas.set([areas[c] for c in codes])
                    users[username] = u
        admin = User.objects.filter(is_superuser=True).first() or users.get("supervisor1")
        if admin is None:
            raise CommandError("Cree primero un administrador (createsuperuser) o ejecute sin --sin-usuarios.")
        self._datasets(areas, admin)
        tmp = Path(tempfile.mkdtemp(dir=settings.TEMP_DIR))
        write_all(tmp, timezone.localdate())
        self._imports(tmp, admin)
        self._labels(admin, label_templates())
        self._extras(admin, users, areas, tmp)
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados."))
        if not opts["sin_usuarios"]:
            self.stdout.write("Usuarios demo: " + ", ".join(u[0] for u in DEMO_USERS) + f" · contraseña: {pwd}")
            self.stdout.write("Cambie o desactive estos usuarios antes de cualquier uso real.")

    def _datasets(self, areas, admin):
        from apps.production.models import Dataset

        specs = [
            ("plan", "Plan de producción", "plan", "SMT", ["work_order"], ""),
            ("produccion-turno", "Producción por turno", "incremental", "SMT", ["date", "shift", "line", "work_order", "station"], "FINAL"),
            ("avance-acumulado", "Avance acumulado (snapshot)", "snapshot", "EMP", ["work_order", "station"], "EMPAQUE"),
            ("seriales", "Resultados por serial", "serial", "PRU", ["serial", "station", "attempt"], ""),
            ("calidad", "Calidad por causa", "quality", "SMT", ["date", "shift", "line", "work_order", "cause"], ""),
        ]
        for code, name, kind, area, keys, station in specs:
            Dataset.objects.get_or_create(code=code, defaults={"name": name, "kind": kind, "area": areas[area], "key_fields": keys,
                                                               "finished_station": station, "created_by": admin,
                                                               "counts_as_production": kind in ("incremental", "snapshot")})

    def _import(self, path, dataset_code, admin, mapping_overrides=None, options=None, sheet=""):
        from apps.production.fields import auto_map
        from apps.production.importer import analyze, commit, validate
        from apps.production.models import Dataset, ImportBatch

        ds = Dataset.objects.get(code=dataset_code)
        sf = StoredFile.create_from_path(path, path.name, owner=admin, source="import", area=ds.area)
        b = ImportBatch.objects.create(dataset=ds, source_file=sf, file_sha256=sf.sha256, created_by=admin, sheet=sheet, mode="upsert",
                                       options={"header_row": 1, "allow_partial": True, **(options or {})})
        b.analysis = analyze(sf)
        b.mapping = auto_map(b.analysis["sheets"][0]["headers"])
        b.mapping.update(mapping_overrides or {})
        b.save()
        validate(b, admin)
        b.refresh_from_db()
        stats = commit(b, admin)
        self.stdout.write(f"  {path.name} → {ds.name}: {stats}")

    def _imports(self, tmp, admin):
        self._import(tmp / "plan_produccion.xlsx", "plan", admin, {"area": "Área", "revision": "Rev"}, {"date_order": "DMY"}, sheet="Plan")
        self._import(tmp / "produccion_turnos.csv", "produccion-turno", admin, {"qty_good": "Piezas buenas", "qty_reject": "Rechazos"})
        self._import(tmp / "produccion_turno3_ingles.csv", "produccion-turno", admin, {"qty_good": "Good", "qty_reject": "Reject"})
        self._import(tmp / "snapshot_10h.csv", "avance-acumulado", admin, {"qty_good": "Acumulado bueno"})
        self._import(tmp / "snapshot_14h.csv", "avance-acumulado", admin, {"qty_good": "Acumulado bueno"})
        self._import(tmp / "seriales_pruebas.csv", "seriales", admin, {"date": "Fecha", "cause": "Defecto"})
        self._import(tmp / "calidad_causas.csv", "calidad", admin, {"qty_reject": "Rechazo"})

    def _labels(self, admin, templates):
        from apps.labels.models import LabelTemplate, LabelTemplateVersion, Printer, SerialCounter

        SerialCounter.objects.get_or_create(name="serial-producto", defaults={"prefix": "GPV", "pad": 7, "next_value": 1})
        SerialCounter.objects.get_or_create(name="serial-trazabilidad", defaults={"prefix": "T", "pad": 8, "next_value": 1})
        Printer.objects.get_or_create(name="Navegador / PDF", defaults={"kind": Printer.Kind.BROWSER, "language": Printer.Language.PDF})
        for code, tpl in templates.items():
            t, created = LabelTemplate.objects.get_or_create(code=code, defaults={"name": tpl["name"], "owner": admin, "draft": tpl})
            if created:
                v = LabelTemplateVersion.objects.create(template=t, version=1, definition=tpl, published_by=admin, notes="Plantilla de ejemplo")
                t.published = v
                t.save(update_fields=["published"])

    def _extras(self, admin, users, areas, tmp):
        from apps.comms.models import Announcement
        from apps.documents.models import Document
        from apps.documents.services import describe
        from apps.kaizen.models import Improvement, KaizenAction, KaizenMeasure, KaizenTransition
        from apps.production.models import WorkOrder
        from apps.reports.models import Dashboard

        author = users.get("supervisor1", admin)
        if not Announcement.objects.exists():
            a = Announcement.objects.create(title="Arranque de semana: revisión de 5S", body="Recordatorio sintético: realizar la revisión 5S al inicio del turno.",
                                            priority="high", author=author, require_ack=True, valid_until=timezone.now() + timedelta(days=14))
            a.areas.set([areas["SMT"], areas["ENS"]])
        if not Improvement.objects.exists():
            k = Improvement.objects.create(title="Reducir cambio de modelo en SMT-1", problem="El cambio de modelo tarda 45 min.",
                                           current_state="Ajustes manuales de alimentadores.", objective="Bajar a 25 min.", area=areas["SMT"],
                                           responsible=users.get("ingeniero1", admin), proposer=users.get("operador1", admin), priority=1,
                                           whys=["Ajuste manual", "Sin preparación externa", "No hay carro de kitting", "", ""], root_cause="Preparación interna (SMED no aplicado)")
            KaizenTransition.objects.create(improvement=k, from_status="", to_status="proposal", user=k.proposer, comment="Registro")
            KaizenAction.objects.create(improvement=k, description="Preparar carro de kitting", owner=k.responsible, due=timezone.localdate() + timedelta(days=7))
            KaizenMeasure.objects.create(improvement=k, name="Tiempo de cambio", unit="min", source="Bitácora de línea SMT-1 (sintética)",
                                         before_from=timezone.localdate() - timedelta(days=30), before_to=timezone.localdate() - timedelta(days=16), before_value=45,
                                         after_from=timezone.localdate() - timedelta(days=15), after_to=timezone.localdate(), after_value=31)
        op = users.get("operador1")
        if op:
            for wo in WorkOrder.objects.filter(area=areas["SMT"])[:3]:
                wo.assigned_users.add(op)
        if not Dashboard.objects.exists():
            Dashboard.objects.create(name="Calidad por causa y línea", owner=admin, shared_all=True, config={"widgets": [
                {"title": "Rechazo por causa", "dimension": "cause", "measure": "qty_reject", "agg": "sum", "chart": "bar", "order": "value_desc", "limit": 10, "width": 1},
                {"title": "Buenas por turno", "dimension": "shift", "measure": "qty_good", "agg": "sum", "chart": "bar", "limit": 10, "width": 1},
                {"title": "Tasa de rechazo % por línea", "dimension": "line", "measure": "qty_reject", "agg": "sum", "chart": "table",
                 "calc": "qty_reject / (qty_good + qty_reject) * 100", "limit": 20, "width": 2}]})
        if not Document.objects.exists():
            for name in ("muestra_5_paginas.pdf", "presentacion_muestra.pptx", "documento_muestra.docx", "anexo_muestra.docx", "libro_muestra.xlsx", "datos_multilinea.csv"):
                p = tmp / name
                sf = StoredFile.create_from_path(p, name, owner=admin, visibility=StoredFile.Visibility.ALL)
                from apps.core.files import MIME
                sf.mime = MIME.get(sf.ext, "")
                sf.save()
                Document.objects.create(file=sf, title=name, owner=admin, tags="muestra", info=describe(sf.ext, p.read_bytes()))
