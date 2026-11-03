"""Portal del turno (piloto SMT). Synthetic data only; OData is a SIMULATED local service."""
import os
import sys
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.jobs import UserFacingError
from apps.core.models import AuditLog, Notification, Role, Shift
from apps.core.tests.helpers import areas, user
from apps.shift import calendar as cal
from apps.shift import odata, services
from apps.shift.counting import review, scope_counts
from apps.shift.models import (ChecklistTemplate, Downtime, DowntimeReason, Handover, HelpReason, HelpRequest, Line, MaterialRequest,
                               ODataConnection, OperationInstruction, ProductionEvent as PE, QualityObservation, ShiftPlan, ShiftReport,
                               Site, Station, SyncGap, SyncRun, UserContext)

sys.path.insert(0, str(Path(settings.BASE_DIR) / "tools"))
import fake_odata_server as fake  # noqa: E402

MAPPING = {"work_order": "Orden", "operation": "Operacion", "station": "Estacion", "part_number": "Parte", "serial": "Serie", "panel_id": "Panel",
           "side": "Lado", "qty": "Cantidad", "result": "Resultado", "attempt": "Intento", "event_at": "Instante", "modified_at": "Modificado"}


def cl(u):
    c = Client(HTTP_HOST="127.0.0.1")
    c.force_login(u)
    return c


class Base(TestCase):
    def setUp(self):
        self.a = areas()
        Shift.objects.all().delete()
        # a 24 h shift starting 00:00 (crosses midnight) keeps «current shift» deterministic in tests
        self.shift = Shift.objects.create(code="TD", name="Turno de prueba", start=time(0), end=time(0))
        site = Site.objects.create(code="S", name="Sitio de prueba", synthetic=True)
        self.line = Line.objects.create(site=site, area=self.a["SMT"], code="SMT-T", name="SMT prueba", pilot=True, synthetic=True)
        self.st_top = Station.objects.create(line=self.line, code="AOI-T", name="AOI Top", operation="AOI-T", side="top", sequence=1)
        self.st_cp = Station.objects.create(line=self.line, code="AOI-B", name="AOI Bottom", operation="AOI-B", side="bottom", sequence=2,
                                            is_count_point=True)
        self.op = user("op", Role.OPERATOR, ("SMT",))
        self.sup = user("sup", Role.SUPERVISOR, ("SMT",))
        self.sup_ens = user("sup_ens", Role.SUPERVISOR, ("ENS",))
        self.eng = user("eng", Role.ENGINEER, ("SMT",))
        self.admin = user("root", superuser=True)
        self.maint = Group.objects.create(name="Mantenimiento")
        self.boss = Group.objects.create(name="Supervisión")
        self.eng.groups.add(self.maint)
        self.sup.groups.add(self.boss)
        self.reason = HelpReason.objects.create(code="mant", label="Falla de equipo", group=self.maint, remind_minutes=10, escalate_minutes=30,
                                                escalate_group=self.boss, requires_verification=True)
        self.now = timezone.now()
        cur = cal.current(self.now)
        self.cur_shift, self.date, self.start, self.end = cur
        ShiftPlan.objects.create(line=self.line, shift=self.shift, date=self.date, work_order="OT-1", part_number="PN-1", target=Decimal("200"), unit="pz")

    def confirm(self, u, station=None, wo="OT-1"):
        return cl(u).post("/turno/contexto/", {"station": (station or self.st_cp).pk, "work_order": wo})

    def ev(self, **kw):
        d = dict(source=PE.Source.ODATA, kind=PE.Kind.INCREMENTAL, line=self.line, station=self.st_cp, operation="AOI-B", work_order="OT-1",
                 qty=Decimal(1), unit="pz", result="PASS", event_at=self.start + timedelta(minutes=5), recon_status=PE.Recon.CONFIRMED)
        d.update(kw)
        return PE.objects.create(**d)

    def manual(self, qty, lot="", minutes=5, uuid=None):
        e, _ = services.capture_manual(self.op, self.line, self.st_top, "OT-1", Decimal(qty), "pz", self.start + timedelta(minutes=minutes),
                                       self.start + timedelta(minutes=minutes + 60), "Fuente desconectada", lot_ref=lot, client_uuid=uuid)
        e.refresh_from_db()
        return e


# ------------------------------------------------------------------ Mi turno, context, roles (criteria 1-4)
class MyShiftTests(Base):
    def test_my_shift_without_station_asks_for_qr_and_shows_four_actions(self):
        html = cl(self.op).get("/turno/").content.decode()
        for t in ("Ver mi trabajo", "Necesito ayuda", "Imprimir etiqueta", "Revisar cierre de turno"):
            self.assertIn(t, html)
        self.assertIn("Escanea el QR de tu estación", html)

    def test_qr_identifies_station_only_and_needs_confirmation(self):
        r = cl(self.op).get(f"/turno/estacion/{self.st_cp.qr_token}/")
        self.assertContains(r, "identifica la <strong>estación</strong>")
        self.assertIsNone(UserContext.objects.get(user=self.op).station)  # GET never changes context
        self.assertEqual(Client(HTTP_HOST="127.0.0.1").get(f"/turno/estacion/{self.st_cp.qr_token}/").status_code, 302)  # login required
        self.confirm(self.op)
        ctx = UserContext.objects.get(user=self.op)
        self.assertEqual((ctx.station, ctx.work_order), (self.st_cp, "OT-1"))
        html = cl(self.op).get("/turno/").content.decode()
        self.assertIn("AOI-B", html)
        self.assertIn("Meta del turno", html)

    def test_order_change_requires_reason_and_is_logged(self):
        self.confirm(self.op)
        cl(self.op).post("/turno/contexto/", {"station": self.st_cp.pk, "work_order": "OT-2"})
        self.assertEqual(UserContext.objects.get(user=self.op).work_order, "OT-1")
        cl(self.op).post("/turno/contexto/", {"station": self.st_cp.pk, "work_order": "OT-2", "reason": "cambio de modelo"})
        self.assertEqual(UserContext.objects.get(user=self.op).work_order, "OT-2")
        self.assertTrue(self.op.contextchange_set.filter(field="work_order", new="OT-2", reason="cambio de modelo").exists())

    def test_station_of_other_area_is_rejected(self):
        self.assertEqual(cl(self.sup_ens).get(f"/turno/estacion/{self.st_cp.qr_token}/").status_code, 403)
        self.assertEqual(self.confirm(self.sup_ens).status_code, 403)

    def test_role_adapted_views_and_server_side_permissions(self):
        self.assertNotIn("/turno/supervisor/", cl(self.op).get("/turno/").content.decode())
        self.assertIn("/turno/supervisor/", cl(self.sup).get("/turno/").content.decode())
        for p in ("/turno/plan/", "/turno/conciliacion/", "/turno/supervisor/"):
            self.assertEqual(cl(self.op).get(p).status_code, 403, p)
        self.assertEqual(cl(self.sup).get("/turno/supervisor/").status_code, 200)
        self.assertEqual(cl(self.eng).post("/turno/fuentes/1/accion/", {"action": "sync"}).status_code, 403)

    def test_operator_lands_on_my_shift_after_login_when_pilot_exists(self):
        c = Client(HTTP_HOST="127.0.0.1")
        r = c.post("/entrar/", {"username": "op", "password": "x-Pass-1234"}, follow=True)
        self.assertEqual(r.redirect_chain[-1][0], "/turno/")
        self.assertEqual(c.get("/").status_code, 200)  # «Inicio» still reachable afterwards
        c2 = Client(HTTP_HOST="127.0.0.1")
        r = c2.post("/entrar/", {"username": "sup", "password": "x-Pass-1234"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.redirect_chain[-1][0], "/turno/")

    def test_serial_lookup_shows_history_in_order(self):
        self.ev(serial="SN-1", attempt=1, result="FAIL")
        self.ev(serial="SN-1", attempt=2, result="PASS", event_at=self.start + timedelta(minutes=9))
        html = cl(self.op).get("/turno/escanear/?code=SN-1").content.decode()
        self.assertIn("Historial de SN-1", html)
        self.assertLess(html.index("FAIL"), html.index("PASS"))
        self.assertContains(cl(self.op).get("/turno/escanear/?code=NOEXISTE"), "No se encontró")


# ------------------------------------------------------------------ counting rules (criteria 22-25)
class CountingTests(Base):
    def test_manual_capture_is_provisional_not_confirmed(self):
        m = self.manual(80)
        self.assertEqual(m.recon_status, PE.Recon.PENDING)
        c = scope_counts(self.line, "OT-1", self.start, self.end)
        self.assertEqual((c["confirmed"], c["provisional"]), (0, 80))

    def test_same_fact_manual_80_and_odata_80_is_80_not_160(self):
        self.ev(qty=Decimal(80), lot_ref="LOT-A", event_at=self.start + timedelta(minutes=30))
        m = self.manual(80, lot="LOT-A")
        self.assertEqual(m.recon_status, PE.Recon.RECONCILED)
        c = scope_counts(self.line, "OT-1", self.start, self.end)
        self.assertEqual((c["confirmed"], c["provisional"]), (80, 0))

    def test_two_independent_lots_are_160(self):
        self.ev(qty=Decimal(80), lot_ref="LOT-A", event_at=self.start + timedelta(minutes=30))
        m = self.manual(80, lot="LOT-B")
        self.assertIn(m.recon_status, (PE.Recon.PENDING, PE.Recon.REVIEW))
        review(m, self.sup, "distinct", note="lote B capturado por contingencia, verificado en piso")
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 160)

    def test_ambiguous_equal_quantity_without_reference_goes_to_review(self):
        auto = self.ev(qty=Decimal(80), event_at=self.start + timedelta(minutes=30))
        m = self.manual(80)
        self.assertEqual(m.recon_status, PE.Recon.REVIEW)
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 80)
        self.assertEqual(cl(self.op).get("/turno/conciliacion/").status_code, 403)
        r = cl(self.sup).post("/turno/conciliacion/", {"id": m.pk, "match": auto.pk, "decision": "same", "note": "mismo lote según bitácora"})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual((m.recon_status, m.reconciled_with_id), (PE.Recon.RECONCILED, auto.pk))
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 80)

    def test_top_and_bottom_of_same_panel_not_double_counted(self):
        for i in range(3):
            self.ev(station=self.st_top, operation="AOI-T", side="top", panel_id=f"P{i}")
            self.ev(panel_id=f"P{i}", side="bottom")
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 3)

    def test_unmapped_station_events_are_not_counted(self):
        self.ev(station=None, operation="DESCONOCIDA")
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 0)

    def test_panels_need_confirmed_factor(self):
        self.ev(qty=Decimal(5), unit="panel")
        self.line.panel_factor = 4
        self.line.save()
        c = scope_counts(self.line, "OT-1", self.start, self.end)
        self.assertTrue(c["issues"])  # factor not confirmed: not calculable, never guessed
        s = services.shift_summary(self.line, self.shift, self.date)
        self.assertEqual(s["orders"][0]["compliance"]["status"], "not_calculable")
        self.line.panel_factor_confirmed = True
        self.line.save()
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 20)

    def test_retests_are_not_extra_pieces_and_fpy_uses_first_attempt(self):
        self.ev(serial="S1", attempt=1, result="FAIL")
        self.ev(serial="S1", attempt=2, result="PASS", event_at=self.start + timedelta(minutes=8))
        self.ev(serial="S2", attempt=1, result="PASS")
        c = scope_counts(self.line, "OT-1", self.start, self.end)
        self.assertEqual((c["confirmed"], c["fpy"], c["retests"]), (2, 50.0, 1))

    def test_snapshot_replaces_previous(self):
        self.ev(kind=PE.Kind.SNAPSHOT, scope_key="OT-1", qty=Decimal(50), event_at=self.start + timedelta(minutes=10))
        self.ev(kind=PE.Kind.SNAPSHOT, scope_key="OT-1", qty=Decimal(70), event_at=self.start + timedelta(minutes=20))
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 70)

    def test_manual_capture_idempotent_by_client_uuid(self):
        a = self.manual(10, uuid="11111111-1111-1111-1111-111111111111")
        b = self.manual(10, uuid="11111111-1111-1111-1111-111111111111")
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(PE.objects.filter(source=PE.Source.MANUAL).count(), 1)

    def test_manual_capture_requires_reason_and_uses_count_point(self):
        with self.assertRaises(UserFacingError):
            services.capture_manual(self.op, self.line, self.st_top, "OT-1", Decimal(1), "pz", self.start, self.start, "")
        self.assertEqual(self.manual(5).operation, "AOI-B")


# ------------------------------------------------------------------ OData connector (criteria 21, 26-28)
class ODataTests(Base):
    def setUp(self):
        super().setUp()
        self.srv, self.store, self.url = fake.start(0)
        self.addCleanup(self.srv.shutdown)
        t0 = self.start + timedelta(minutes=1)
        for i in range(23):
            self.store.add(EventoId=f"E{i}", Orden="OT-1", Operacion="AOI-B", Estacion="AOI-B", Panel=f"P{i}", Cantidad=1,
                           Instante=(t0 + timedelta(minutes=i)).isoformat(), Modificado=(t0 + timedelta(minutes=i)).isoformat())
        self.conn = ODataConnection.objects.create(name="Simulada", service_url=self.url, entity_set="EventosSimulados", key_fields=["EventoId"],
                                                   mapping=MAPPING, watermark_field="Modificado", time_field="Instante", page_size=5, synthetic=True,
                                                   line=self.line)

    def test_staged_diagnosis_distinguishes_index_metadata_and_entity_permission(self):
        stages, meta = odata.diagnose(self.conn)
        self.assertTrue(odata.diagnosis_ok(stages), stages)
        self.assertIn("EventosSimulados", meta["entity_sets"])
        # index + $metadata OK but the entity set is forbidden: must NOT be declared connected
        srv2, _s, url2 = fake.start(0, self.store, deny_entity=True)
        self.addCleanup(srv2.shutdown)
        self.conn.service_url = url2
        stages, _m = odata.diagnose(self.conn)
        self.assertFalse(odata.diagnosis_ok(stages))
        self.assertTrue(stages[0]["ok"] and stages[1]["ok"])
        self.assertEqual(stages[-1]["kind"], "forbidden")
        # wrong credentials are reported as authentication, never as "connected"
        srv3, _s, url3 = fake.start(0, self.store, auth="basic")
        self.addCleanup(srv3.shutdown)
        self.conn.service_url, self.conn.auth_type = url3, "basic"
        with mock.patch.dict(os.environ, {"GPV_ODATA_USER": "u", "GPV_ODATA_PASSWORD": "mala", "FAKE_ODATA_USER": "u", "FAKE_ODATA_PASSWORD": "buena"}):
            stages, _m = odata.diagnose(self.conn)
        self.assertEqual(stages[-1]["kind"], "auth")
        with mock.patch.dict(os.environ, {"GPV_ODATA_USER": "u", "GPV_ODATA_PASSWORD": "buena", "FAKE_ODATA_USER": "u", "FAKE_ODATA_PASSWORD": "buena"}):
            stages, _m = odata.diagnose(self.conn)
        self.assertTrue(odata.diagnosis_ok(stages))
        # unreachable server
        self.conn.service_url, self.conn.auth_type = "http://127.0.0.1:9/odata/", "none"
        stages, _m = odata.diagnose(self.conn)
        self.assertEqual(stages[0]["kind"], "connectivity")

    def test_mapping_must_exist_in_metadata(self):
        self.conn.mapping = dict(MAPPING, qty="CampoInventado")
        stages, _m = odata.diagnose(self.conn)
        self.assertFalse(odata.diagnosis_ok(stages))
        self.assertIn("CampoInventado", stages[-1]["detail"])

    def test_paging_and_repeated_sync_do_not_duplicate(self):
        run = odata.sync_once(self.conn)
        self.assertEqual((run.status, run.pages, run.created), ("ok", 5, 23))
        self.conn.refresh_from_db()
        run2 = odata.sync_once(self.conn)  # overlapping window re-reads recent rows
        self.assertEqual(run2.created, 0)
        self.assertEqual(PE.objects.filter(connection=self.conn).count(), 23)
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 23)
        self.assertTrue(all(c.startswith("/odata") for c in self.store.calls))

    def test_source_correction_creates_new_version(self):
        odata.sync_once(self.conn)
        self.conn.refresh_from_db()
        self.store.add(EventoId="E3", Orden="OT-1", Operacion="AOI-B", Estacion="AOI-B", Panel="P3", Cantidad=1, Resultado="FAIL",
                       Instante=(self.start + timedelta(minutes=4)).isoformat(), Modificado=timezone.now().isoformat())
        run = odata.sync_once(self.conn)
        self.assertEqual(run.updated, 1)
        e = PE.objects.get(connection=self.conn, external_key="E3")
        self.assertEqual((e.version, e.result), (2, "FAIL"))
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 22)

    def test_failure_keeps_last_data_backs_off_and_capture_still_works(self):
        odata.sync_once(self.conn)
        self.conn.refresh_from_db()
        self.conn.validated_at, self.conn.enabled = timezone.now(), True
        self.conn.save()
        wm = self.conn.watermark
        self.conn.service_url = "http://127.0.0.1:9/odata/"
        self.conn.save()
        run = odata.sync_once(self.conn)
        self.conn.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(self.conn.watermark, wm)  # progress not advanced on failure
        self.assertGreater(self.conn.next_attempt_at, timezone.now())  # backoff, no retry storm
        self.assertEqual(self.conn.health(), "disconnected")
        self.assertEqual(list(odata.due_connections()), [])
        self.assertEqual(scope_counts(self.line, "OT-1", self.start, self.end)["confirmed"], 23)  # last data kept, never zero
        s = services.shift_summary(self.line, self.shift, self.date)
        self.assertTrue(any("Desconectado" in b for b in s["blocking"]))
        self.confirm(self.op)
        r = cl(self.op).post("/turno/captura/", {"qty": "5", "start": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                                                 "end": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "reason": "OData caído"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(PE.objects.filter(source=PE.Source.MANUAL).count(), 1)

    def test_client_is_read_only_and_secrets_never_reach_browser_or_db(self):
        with self.assertRaises(odata.ODataError):
            odata.ReadOnlyClient(self.conn).get(self.url, method="POST")
        self.conn.auth_type = "basic"
        self.conn.save()
        with mock.patch.dict(os.environ, {"GPV_ODATA_USER": "usuario-x", "GPV_ODATA_PASSWORD": "S3cr3t-no-debe-salir"}):
            odata.diagnose(self.conn)
            for p in ("/turno/fuentes/", f"/turno/fuentes/{self.conn.pk}/", "/turno/api/estado/", "/turno/"):
                self.assertNotIn("S3cr3t-no-debe-salir", cl(self.admin).get(p).content.decode(), p)
        from django.core import serializers

        self.assertNotIn("S3cr3t", serializers.serialize("json", ODataConnection.objects.all()))
        self.assertNotIn(self.url, cl(self.op).get("/turno/").content.decode())  # browser never gets the OData address

    def test_ui_diagnose_then_enable_and_sync(self):
        c = cl(self.admin)
        self.assertContains(c.post(f"/turno/fuentes/{self.conn.pk}/accion/", {"action": "toggle"}, follow=True), "solo se activa tras un diagnóstico")
        c.post(f"/turno/fuentes/{self.conn.pk}/accion/", {"action": "diagnose"})
        self.conn.refresh_from_db()
        self.assertIsNotNone(self.conn.validated_at)
        c.post(f"/turno/fuentes/{self.conn.pk}/accion/", {"action": "toggle"})
        self.conn.refresh_from_db()
        self.assertTrue(self.conn.enabled)
        from apps.shift.service_loop import tick

        tick()
        self.assertEqual(SyncRun.objects.filter(status="ok").count(), 1)
        tick()  # not due yet (refresh 60 s): no overlapping/extra cycle
        self.assertEqual(SyncRun.objects.count(), 1)

    def test_gap_after_computer_off_is_reported(self):
        odata.sync_once(self.conn)
        self.conn.refresh_from_db()
        odata.sync_once(self.conn, now=timezone.now() + timedelta(hours=3))
        g = SyncGap.objects.get()
        self.assertTrue(g.recoverable)  # watermark-based: the gap is re-read
        self.conn.watermark_field = ""
        self.conn.window_hours = 2
        self.conn.save()
        self.conn.refresh_from_db()
        odata.sync_once(self.conn, now=timezone.now() + timedelta(hours=8))
        self.assertFalse(SyncGap.objects.order_by("-id").first().recoverable)


# ------------------------------------------------------------------ report, close-out, handover (criteria 5-9, 27)
class ReportTests(Base):
    def setUp(self):
        super().setUp()
        ShiftPlan.objects.all().delete()
        Shift.objects.all().delete()
        self.shift = Shift.objects.create(code="N", name="Nocturno", start=time(22), end=time(6))  # crosses midnight
        self.date = timezone.localdate() - timedelta(days=2)
        self.start, self.end = cal.window(self.shift, self.date)
        ShiftPlan.objects.create(line=self.line, shift=self.shift, date=self.date, work_order="OT-1", target=Decimal(10), unit="pz")
        Line.objects.filter(pk=self.line.pk).update(created=self.start - timedelta(days=1))
        self.line.refresh_from_db()

    def test_no_backfill_before_line_creation(self):
        from apps.shift.service_loop import tick

        Line.objects.filter(pk=self.line.pk).update(created=timezone.now())
        tick()
        self.assertFalse(ShiftReport.objects.filter(line=self.line).exists())

    def test_midnight_window(self):
        self.assertEqual(self.end - self.start, timedelta(hours=8))
        self.assertEqual(timezone.localtime(self.end).date(), self.date + timedelta(days=1))

    def test_drafts_generated_once_by_process_even_after_restart(self):
        from apps.shift.service_loop import tick

        self.ev(event_at=self.start + timedelta(hours=7))  # 05:00 next day belongs to this shift
        tick()
        tick()  # second run (e.g. after restart) does not duplicate
        r = ShiftReport.objects.get(shift=self.shift, date=self.date)
        self.assertEqual(r.snapshot["orders"][0]["good"], 1.0)
        self.assertEqual(ShiftReport.objects.filter(shift=self.shift).values("date").distinct().count(),
                         ShiftReport.objects.filter(shift=self.shift).count())
        self.assertEqual(Handover.objects.filter(shift=self.shift, date=self.date).count(), 1)

    def test_review_close_flow_with_exceptions_and_pdf(self):
        d = Downtime.objects.create(line=self.line, station=self.st_cp, started_at=self.start + timedelta(hours=1),
                                    ended_at=self.start + timedelta(hours=2), started_by=self.op)
        r = services.generate_report(self.line, self.shift, self.date)
        self.assertEqual(r.status, ShiftReport.Status.PENDING_DATA)
        with self.assertRaises(UserFacingError):
            services.review(r, self.sup)  # downtime without reason
        self.assertEqual(cl(self.op).post(f"/turno/cierre/?line={self.line.pk}&r={r.pk}", {"action": "review"}).status_code, 403)
        c = cl(self.sup)
        c.post(f"/turno/cierre/?line={self.line.pk}&r={r.pk}", {"action": "downtime_reason", "id": d.pk,
                                                               "reason": DowntimeReason.objects.create(code="m", label="Mant").pk})
        with self.assertRaises(UserFacingError):
            services.close(r, self.sup)  # must be reviewed first
        services.review(r, self.sup)
        services.close(r, self.sup)  # no OData connection and no pending manual: nothing blocking
        r.refresh_from_db()
        self.assertEqual(r.status, ShiftReport.Status.CLOSED)
        self.assertTrue(r.pdf.path.read_bytes().startswith(b"%PDF"))
        self.assertEqual(c.get(f"/turno/reporte/{r.pk}.pdf").status_code, 200)
        self.assertEqual(c.get(f"/turno/reporte/{r.pk}.xlsx").status_code, 200)
        self.assertEqual(cl(self.sup_ens).get(f"/turno/reporte/{r.pk}.pdf").status_code, 403)

    def test_report_screen_pdf_and_excel_show_same_figures(self):
        import io

        from openpyxl import load_workbook
        from pypdf import PdfReader

        for i in range(7):
            self.ev(event_at=self.start + timedelta(minutes=10 + i), serial=f"S{i}", attempt=1)
        r = services.generate_report(self.line, self.shift, self.date)
        o = r.snapshot["orders"][0]
        self.assertEqual((o["good"], o["target"], o["compliance"]["value"]), (7.0, 10.0, 70.0))
        c = cl(self.sup)
        self.assertContains(c.get(f"/turno/cierre/?line={self.line.pk}&r={r.pk}"), "70.0 %")
        wb = load_workbook(io.BytesIO(c.get(f"/turno/reporte/{r.pk}.xlsx").content))
        cells = [v for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v is not None]
        self.assertIn("OT-1", cells)
        self.assertTrue({7, 10, 70} <= {int(v) for v in cells if isinstance(v, (int, float))})
        text = " ".join(pg.extract_text() for pg in PdfReader(io.BytesIO(c.get(f"/turno/reporte/{r.pk}.pdf").content)).pages)
        self.assertIn("OT-1", text)
        self.assertIn("70", text)
        self.assertIn(f"rev{r.revision}-", text)  # same data version in the document

    def test_pending_manual_blocks_close_unless_reason(self):
        services.capture_manual(self.op, self.line, self.st_cp, "OT-1", Decimal(3), "pz", self.start + timedelta(minutes=5),
                                self.start + timedelta(minutes=50), "contingencia")
        r = services.generate_report(self.line, self.shift, self.date)
        services.review(r, self.sup)
        with self.assertRaises(UserFacingError):
            services.close(r, self.sup, "corto")
        services.close(r, self.sup, "Se cierra con captura pendiente por instrucción de gerencia")
        r.refresh_from_db()
        self.assertTrue(r.snapshot["closed_with_pending"])

    def test_late_data_creates_new_revision(self):
        r = services.generate_report(self.line, self.shift, self.date)
        services.review(r, self.sup)
        services.close(r, self.sup)
        self.ev(event_at=self.start + timedelta(hours=3), received_at=timezone.now() + timedelta(seconds=5))
        new = services.late_data_revisions(timezone.now())
        self.assertEqual([x.revision for x in new], [2])
        self.assertEqual(services.late_data_revisions(timezone.now()), [])  # once
        r.refresh_from_db()
        self.assertEqual(r.status, ShiftReport.Status.CLOSED)  # closed revision preserved

    def test_handover_receipt_does_not_close_incidents(self):
        h = HelpRequest.objects.create(reason=self.reason, line=self.line, station=self.st_cp, created_by=self.op, group=self.maint)
        HelpRequest.objects.filter(pk=h.pk).update(created=self.start + timedelta(hours=1))
        services.generate_report(self.line, self.shift, self.date)
        ho = Handover.objects.get()
        self.assertEqual(len(ho.summary["open_help"]), 1)
        cl(self.sup).post("/turno/relevo/", {"id": ho.pk, "action": "receive"})
        ho.refresh_from_db()
        h.refresh_from_db()
        self.assertIsNotNone(ho.received_at)
        self.assertEqual(h.status, "reported")


# ------------------------------------------------------------------ help, downtime, materials, quality, instructions (criteria 10-20)
class FloorTests(Base):
    def test_help_request_routing_dedupe_flow_and_verification(self):
        self.confirm(self.op)
        c = cl(self.op)
        c.post("/turno/ayuda/", {"reason": "mant", "comment": "Alimentador atorado", "client_uuid": "22222222-2222-2222-2222-222222222222"})
        h = HelpRequest.objects.get()
        self.assertEqual((h.group, h.station, h.work_order), (self.maint, self.st_cp, "OT-1"))
        self.assertTrue(Notification.objects.filter(user=self.eng, url=f"/turno/ayuda/{h.pk}/").exists())
        self.assertFalse(Notification.objects.filter(user=self.sup_ens).exists())
        c.post("/turno/ayuda/", {"reason": "mant", "comment": "repetido", "client_uuid": "22222222-2222-2222-2222-222222222222"})
        self.assertEqual(HelpRequest.objects.count(), 1)  # double tap / resend does not duplicate
        self.assertContains(c.get("/turno/ayuda/?motivo=mant"), "Relacionar con esta")
        with self.assertRaises(UserFacingError):
            services.advance_help(h, self.op, "received")  # operator is not in the group
        services.advance_help(h, self.eng, "received")
        services.advance_help(h, self.eng, "in_progress")
        with self.assertRaises(UserFacingError):
            services.advance_help(h, self.eng, "resolved", "")
        services.advance_help(h, self.eng, "resolved", "Se limpió el alimentador")
        with self.assertRaises(UserFacingError):
            services.advance_help(h, self.eng, "verified")  # resolver cannot verify own fix
        services.advance_help(h, self.op, "verified", "Funciona")
        self.assertEqual(h.status, "verified")
        self.assertEqual(h.events.count(), 5)

    def test_offline_json_resend_is_idempotent(self):
        self.confirm(self.op)
        c = cl(self.op)
        body = {"reason": "mant", "comment": "sin red", "client_uuid": "33333333-3333-3333-3333-333333333333"}
        r1 = c.post("/turno/ayuda/", body, content_type="application/json").json()
        r2 = c.post("/turno/ayuda/", body, content_type="application/json").json()
        self.assertEqual((r1["data"]["id"], r1["data"]["created"], r2["data"]["created"]), (r2["data"]["id"], True, False))

    def test_reminder_and_escalation_are_internal_and_once(self):
        h = HelpRequest.objects.create(reason=self.reason, line=self.line, station=self.st_cp, created_by=self.op, group=self.maint)
        later = timezone.now() + timedelta(minutes=31)
        from django.core import mail

        self.assertEqual(services.remind_and_escalate(later), 2)
        h.refresh_from_db()
        self.assertEqual(h.escalation_level, 1)
        self.assertTrue(Notification.objects.filter(user=self.sup, title__startswith="Escalamiento").exists())
        self.assertEqual(services.remind_and_escalate(later), 0)
        self.assertEqual(len(mail.outbox), 0)  # nothing external

    def test_downtime_start_stop_correct(self):
        self.confirm(self.op)
        c = cl(self.op)
        c.post("/turno/paros/", {"action": "start"})
        c.post("/turno/paros/", {"action": "start"})
        self.assertEqual(Downtime.objects.count(), 1)  # no second open downtime
        d = Downtime.objects.get()
        rs = DowntimeReason.objects.create(code="x", label="Falla")
        c.post("/turno/paros/", {"action": "end", "id": d.pk, "reason": rs.pk})
        d.refresh_from_db()
        self.assertIsNotNone(d.ended_at)
        c.post("/turno/paros/", {"action": "correct", "id": d.pk, "why": ""})
        d.refresh_from_db()
        self.assertFalse(d.corrected)
        st = timezone.localtime(d.started_at - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
        c.post("/turno/paros/", {"action": "correct", "id": d.pk, "why": "Se inició antes", "started_at": st})
        d.refresh_from_db()
        self.assertTrue(d.corrected)
        self.assertEqual(len(d.history), 1)

    def test_material_request_is_not_inventory(self):
        mat = Group.objects.create(name="Materiales")
        self.confirm(self.op)
        cl(self.op).post("/turno/materiales/", {"action": "create", "material": "PN-RES-10K", "qty": "500", "unit": "pz"})
        m = MaterialRequest.objects.get()
        self.assertEqual(m.group, mat)
        cl(self.op).post("/turno/materiales/", {"id": m.pk, "to": "delivered"})
        m.refresh_from_db()
        self.assertEqual(m.status, "requested")
        cl(self.sup).post("/turno/materiales/", {"id": m.pk, "to": "received"})
        m.refresh_from_db()
        self.assertEqual(m.status, "received")
        self.assertContains(cl(self.op).get("/turno/materiales/"), "no</strong> es un movimiento")

    def test_quality_observation_vs_disposition(self):
        self.confirm(self.op)
        cl(self.op).post("/turno/calidad/", {"action": "create", "category": "Soldadura", "description": "puente"})
        q = QualityObservation.objects.get()
        self.assertEqual(q.status, "observation")
        self.assertEqual(cl(self.op).post("/turno/calidad/", {"id": q.pk, "to": "scrap"}).status_code, 403)
        cl(self.sup).post("/turno/calidad/", {"id": q.pk, "to": "rework", "official_reference": "MRB-EJ-1"})
        q.refresh_from_db()
        self.assertEqual((q.status, q.disposition_by), ("rework", self.sup))
        self.assertTrue(AuditLog.objects.filter(action="shift.quality_disposition").exists())

    def test_instructions_only_approved_and_checklist_failure_creates_pending(self):
        OperationInstruction.objects.create(line=self.line, operation="AOI-B", title="Vigente", revision="B")
        OperationInstruction.objects.create(line=self.line, operation="AOI-B", title="Vieja", revision="A", status="obsolete")
        self.confirm(self.op)
        html = cl(self.op).get("/turno/instrucciones/").content.decode()
        self.assertIn("Vigente", html)
        self.assertIn("OBSOLETA", html)
        self.assertIn("no equivale a estar capacitado", html)
        t = ChecklistTemplate.objects.create(name="Arranque", kind="startup", line=self.line,
                                             items=[{"text": "Programa correcto", "fail_group": "Mantenimiento"}, {"text": "Pasta", "evidence": True}])
        r = cl(self.op).post(f"/turno/lista/{t.pk}/", {"item0": "no", "note0": "programa v2", "item1": "ok"})
        self.assertEqual(r.status_code, 302)  # evidence missing -> rejected
        self.assertEqual(t.runs.count() if hasattr(t, "runs") else 0, 0)
        cl(self.op).post(f"/turno/lista/{t.pk}/", {"item0": "no", "note0": "programa v2", "item1": "ok", "note1": "lote 7 vigente"})
        h = HelpRequest.objects.get()
        self.assertEqual(h.group, self.maint)

    def test_repeated_help_links_to_kaizen(self):
        for _ in range(3):
            HelpRequest.objects.create(reason=self.reason, line=self.line, station=self.st_cp, created_by=self.op, group=self.maint)
        h = HelpRequest.objects.first()
        r = cl(self.sup).post(f"/turno/ayuda/{h.pk}/", {"action": "kaizen"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(HelpRequest.objects.filter(kaizen__isnull=False).count(), 3)

    def test_label_from_context_once_and_scanner_guard(self):
        from apps.core.samples import label_templates
        from apps.labels.models import LabelTemplate, LabelTemplateVersion, PrintJob, SerialCounter

        SerialCounter.objects.get_or_create(name="serial-producto", defaults={"prefix": "GPV", "pad": 7, "next_value": 1})
        SerialCounter.objects.get_or_create(name="serial-trazabilidad", defaults={"prefix": "T", "pad": 8, "next_value": 1})
        tpl = list(label_templates().values())[0]
        t = LabelTemplate.objects.create(code="ctx", name="Contexto", owner=self.admin, draft=tpl)
        t.published = LabelTemplateVersion.objects.create(template=t, version=1, definition=tpl, published_by=self.admin)
        t.save()
        self.line.label_templates.add(t)
        self.confirm(self.op)
        self.assertContains(cl(self.op).get("/turno/etiqueta/"), "Contexto")
        page = cl(self.op).get(f"/etiquetas/{t.pk}/imprimir/?source=shift")
        self.assertContains(page, "OT-1")
        body = {"source": "shift", "mode": "all", "copies": "1", "confirm_total": "1", "idempotency_key": "k-ctx-1"}
        for p in tpl.get("prompts", []):
            body[f"prompt_{p['name']}"] = p.get("default") or "X"
        r1 = cl(self.op).post(f"/etiquetas/api/{t.pk}/imprimir/", body).json()
        r2 = cl(self.op).post(f"/etiquetas/api/{t.pk}/imprimir/", body).json()
        self.assertTrue(r1["ok"], r1)
        self.assertEqual(r1["data"]["job"], r2["data"]["job"])
        self.assertEqual(PrintJob.objects.count(), 1)
        js = (Path(settings.BASE_DIR) / "static/gpv/js/printwizard.js").read_text()
        self.assertIn('e.key !== "Enter"', js)

    def test_area_screen_read_only(self):
        self.ev()
        r = cl(self.op).get(f"/turno/api/pantalla/{self.line.code}/").json()
        self.assertEqual(r["data"]["orders"][0]["good"], 1.0)
        self.assertEqual(cl(self.sup_ens).get(f"/turno/api/pantalla/{self.line.code}/").status_code, 403)
        self.assertEqual(cl(self.op).post(f"/turno/api/pantalla/{self.line.code}/").status_code, 405)

    def test_service_lease_prevents_overlap(self):
        from apps.shift.service_loop import acquire, release

        self.assertTrue(acquire("A"))
        self.assertFalse(acquire("B"))
        release("A")
        self.assertTrue(acquire("B"))

    def test_all_shift_pages_render_for_each_role(self):
        self.confirm(self.op)
        self.confirm(self.sup)
        pages = ["/turno/", "/turno/contexto/", "/turno/trabajo/", "/turno/escanear/?code=OT-1", "/turno/ayuda/", "/turno/paros/", "/turno/materiales/",
                 "/turno/captura/", "/turno/cierre/", "/turno/relevo/", "/turno/instrucciones/", "/turno/calidad/", "/turno/fuentes/",
                 f"/turno/pantalla/{self.line.code}/", "/turno/etiqueta/"]
        for u in (self.op, self.sup, self.eng, self.admin):
            c = cl(u)
            for p in pages:
                self.assertEqual(c.get(p).status_code, 200, (u.username, p))
        for p in ("/turno/supervisor/", "/turno/plan/", "/turno/conciliacion/"):
            self.assertEqual(cl(self.sup).get(p).status_code, 200, p)


class ODataFormatTests(TestCase):
    """OData v2/v3 shapes (no real v2 server was available: format-level tests only)."""

    def test_v2_page_metadata_and_literals(self):
        rows, nxt = odata.parse_page(b'{"d": {"results": [{"Id": "1", "__metadata": {}}], "__next": "http://x/odata/S?$skiptoken=1"}}')
        self.assertEqual((rows[0]["Id"], nxt), ("1", "http://x/odata/S?$skiptoken=1"))
        rows, nxt = odata.parse_page(b'{"d": [{"Id": "2"}]}')
        self.assertEqual((rows[0]["Id"], nxt), ("2", None))
        with self.assertRaises(odata.ODataError):
            odata.parse_page(b"<html>login</html>")
        edmx = b'''<?xml version="1.0"?><edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
<edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
<Schema Namespace="N" xmlns="http://schemas.microsoft.com/ado/2008/09/edm"><EntityType Name="T"><Key><PropertyRef Name="Id"/></Key>
<Property Name="Id" Type="Edm.Int32"/><Property Name="When" Type="Edm.DateTime"/></EntityType>
<EntityContainer Name="C"><EntitySet Name="Ts" EntityType="N.T"/></EntityContainer></Schema></edmx:DataServices></edmx:Edmx>'''
        meta = odata.parse_metadata(edmx)
        self.assertEqual(meta["version"], "2.0")
        self.assertEqual(meta["entity_sets"]["Ts"]["keys"], ["Id"])
        from datetime import datetime, timezone as tz

        d = datetime(2026, 11, 3, 12, 0, tzinfo=tz.utc)
        self.assertEqual(odata._literal_datetime(d, "2.0"), "datetime'2026-11-03T12:00:00'")
        self.assertEqual(odata._literal_datetime(d, "4.0"), "2026-11-03T12:00:00Z")
        self.assertEqual(odata._dt("/Date(1793707200000)/"), datetime.fromtimestamp(1793707200, tz=tz.utc))
