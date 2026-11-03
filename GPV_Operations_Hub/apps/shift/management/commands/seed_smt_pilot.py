"""SYNTHETIC example configuration for the SMT pilot (clearly marked «EJEMPLO»).

Real line, stations, operation codes, shift and OData URL are POR CONFIRMAR by GPV and are
configured by an administrator; nothing here describes GPV's real plant.
"""
from datetime import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Area, Shift
from apps.shift import calendar as cal
from apps.shift.models import (ChecklistTemplate, DowntimeReason, HelpReason, Line, ODataConnection, OperationInstruction, ShiftBreak, ShiftPlan,
                               Site, Station)

GROUPS = ["Mantenimiento", "Calidad", "Materiales", "Ingeniería de procesos", "Supervisión", "Pruebas"]
STATIONS = [  # code, name, operation, side, sequence, count point
    ("SMT-EJ-PRN", "Impresión de pasta (ejemplo)", "PRN", "", 10, False),
    ("SMT-EJ-SPI", "Inspección de pasta (ejemplo)", "SPI", "", 20, False),
    ("SMT-EJ-PNP-T", "Colocación Top (ejemplo)", "PNP-T", "top", 30, False),
    ("SMT-EJ-AOI-T", "AOI Top (ejemplo)", "AOI-T", "top", 40, False),
    ("SMT-EJ-PNP-B", "Colocación Bottom (ejemplo)", "PNP-B", "bottom", 50, False),
    ("SMT-EJ-AOI-B", "AOI final Bottom (ejemplo, punto de conteo)", "AOI-B", "bottom", 60, True),
]
HELP = [  # code, label, group, remind, escalate, escalate_group, verification
    ("mantenimiento", "Falla de equipo", "Mantenimiento", 10, 30, "Supervisión", True),
    ("calidad", "Duda de calidad", "Calidad", 10, 30, "Supervisión", False),
    ("material", "Falta material", "Materiales", 10, 25, "Supervisión", False),
    ("ingenieria", "Problema de programa / proceso", "Ingeniería de procesos", 15, 45, "Supervisión", True),
    ("pruebas", "Falla en prueba", "Pruebas", 15, 45, "Supervisión", False),
    ("supervisor", "Necesito al supervisor", "Supervisión", 5, 20, "", False),
]
DOWN = [("mant", "Falla de equipo"), ("material", "Falta de material"), ("cambio", "Cambio de modelo"), ("calidad", "Retención de calidad"),
        ("programa", "Programa / ajuste"), ("otro", "Otro (comentar)")]


class Command(BaseCommand):
    help = "Carga una configuración SINTÉTICA de ejemplo para el piloto SMT (línea, estaciones, motivos, grupos y fuente OData simulada)."

    def add_arguments(self, parser):
        parser.add_argument("--odata-url", default="http://127.0.0.1:8765/odata/",
                            help="URL del servicio OData SIMULADO (tools/fake_odata_server.py). No es FactoryLogix.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.GPV["ALLOW_DEMO"]:
            raise CommandError("Los datos de ejemplo están deshabilitados en este perfil (GPV_ALLOW_DEMO=false).")
        area, _ = Area.objects.get_or_create(code="SMT", defaults={"name": "Montaje superficial"})
        for code, name, a, b in (("T1", "Primer turno", time(6), time(14)), ("T2", "Segundo turno", time(14), time(22)), ("T3", "Tercer turno", time(22), time(6))):
            Shift.objects.get_or_create(code=code, defaults={"name": name, "start": a, "end": b})
        for code, s, e in (("T1", time(10), time(10, 30)), ("T2", time(18), time(18, 30)), ("T3", time(2), time(2, 30))):
            sh = Shift.objects.get(code=code)
            ShiftBreak.objects.get_or_create(shift=sh, start=s, defaults={"end": e, "label": "Comida (ejemplo)"})
        groups = {g: Group.objects.get_or_create(name=g)[0] for g in GROUPS}
        site, _ = Site.objects.get_or_create(code="GPV-EJ", defaults={"name": "GPV Americas (EJEMPLO)", "synthetic": True})
        line, _ = Line.objects.get_or_create(code="SMT-EJEMPLO", defaults={"site": site, "area": area, "name": "Línea SMT de ejemplo (sintética)", "pilot": True,
                                                                            "count_unit": "pz", "panel_factor": 2, "panel_factor_confirmed": False,
                                                                            "synthetic": True})
        for code, name, op, side, seq, cp in STATIONS:
            Station.objects.get_or_create(line=line, code=code, defaults={"name": name, "operation": op, "side": side, "sequence": seq,
                                                                          "is_count_point": cp, "synthetic": True})
        for i, (code, label, g, rem, esc, eg, ver) in enumerate(HELP):
            HelpReason.objects.get_or_create(code=code, defaults={"label": label, "group": groups[g], "remind_minutes": rem, "escalate_minutes": esc,
                                                                  "escalate_group": groups.get(eg), "requires_verification": ver, "sequence": i})
        for code, label in DOWN:
            DowntimeReason.objects.get_or_create(code=code, defaults={"label": label})
        ChecklistTemplate.objects.get_or_create(name="Arranque de línea SMT (ejemplo)", defaults={
            "kind": "startup", "line": line, "items": [
                {"text": "Programa correcto para la parte de la orden", "rule": "Regla de ejemplo: comparar con la hoja de la orden", "evidence": False,
                 "fail_group": "Ingeniería de procesos"},
                {"text": "Pasta dentro de vida útil", "rule": "Regla de ejemplo POR CONFIRMAR", "evidence": True, "fail_group": "Calidad"},
                {"text": "Alimentadores cargados según lista", "rule": "", "evidence": False, "fail_group": "Materiales"}]})
        OperationInstruction.objects.get_or_create(title="Inspección visual AOI (ejemplo)", revision="EJ-1", defaults={
            "line": line, "operation": "AOI-B", "steps": [{"text": "Revise las alertas de AOI antes de liberar el panel."},
                                                          {"text": "Registre una observación de calidad si duda (no es disposición)."}]})
        conn, created = ODataConnection.objects.get_or_create(name="OData SIMULADO (no es FactoryLogix)", defaults={
            "service_url": opts["odata_url"], "auth_type": "none", "entity_set": "EventosSimulados", "key_fields": ["EventoId"],
            "mapping": {"work_order": "Orden", "operation": "Operacion", "station": "Estacion", "part_number": "Parte", "serial": "Serie",
                        "panel_id": "Panel", "side": "Lado", "qty": "Cantidad", "result": "Resultado", "attempt": "Intento", "event_at": "Instante",
                        "modified_at": "Modificado"},
            "watermark_field": "Modificado", "time_field": "Instante", "line": line, "synthetic": True, "enabled": False})
        cur = cal.current()
        if cur:
            ShiftPlan.objects.get_or_create(line=line, shift=cur[0], date=cur[1], work_order="OT-EJ-1001",
                                            defaults={"part_number": "PN-EJ-500", "target": 120, "unit": "pz", "source": "ejemplo", "reason": "Meta de ejemplo"})
        User = get_user_model()
        for username, gs in (("ingeniero1", ["Mantenimiento", "Ingeniería de procesos", "Pruebas"]), ("supervisor1", ["Supervisión", "Calidad", "Materiales"])):
            u = User.objects.filter(username=username).first()
            if u:
                u.groups.add(*[groups[g] for g in gs])
        self.stdout.write(self.style.SUCCESS(
            f"Piloto SMT de EJEMPLO cargado: línea {line.code}, {line.stations.count()} estaciones, {HelpReason.objects.count()} motivos de ayuda. "
            f"Fuente «{conn.name}» apunta a {conn.service_url} (desactivada hasta diagnosticarla)."))
        self.stdout.write("QR de estaciones (identifican la estación, no a la persona):")
        for s in line.stations.all():
            self.stdout.write(f"  {s.code}: /turno/estacion/{s.qr_token}/")
