"""Performance measurement of the shift portal with SYNTHETIC data (development tool).

  .venv\\Scripts\\python.exe tools\\perf_shift.py --events 20000

Uses a temporary data folder (SQLite) and the SIMULATED OData service; never touches real data.
Prints: full sync time (pages of 500), incremental re-sync time, and server time of the pages
an operator/supervisor refreshes every cycle.
"""
import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=20000)
    ap.add_argument("--repeat", type=int, default=20)
    a = ap.parse_args()
    os.environ["GPV_DATA_DIR"] = tempfile.mkdtemp(prefix="gpv_perf_")
    os.environ.setdefault("GPV_ENV", "dev")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gpvhub.settings")
    import django

    django.setup()
    from datetime import time as dtime, timedelta

    from django.core.management import call_command
    from django.test import Client
    from django.utils import timezone

    call_command("migrate", verbosity=0)
    from apps.core.models import Area, Shift
    from apps.core.tests.helpers import user
    from apps.core.models import Role
    from apps.shift import calendar as cal
    from apps.shift import odata
    from apps.shift.models import Line, ODataConnection, ShiftPlan, Site, Station, UserContext
    import fake_odata_server as fake

    area = Area.objects.create(code="SMT", name="SMT")
    shift = Shift.objects.create(code="TD", name="24 h", start=dtime(0), end=dtime(0))
    line = Line.objects.create(site=Site.objects.create(code="S", name="S", synthetic=True), area=area, code="SMT-P", name="P", pilot=True, synthetic=True)
    Station.objects.create(line=line, code="AOI-T", name="T", operation="AOI-T", side="top")
    cp = Station.objects.create(line=line, code="AOI-B", name="B", operation="AOI-B", side="bottom", is_count_point=True)
    cur_shift, date, start, end = cal.current()
    for i in range(10):
        ShiftPlan.objects.create(line=line, shift=shift, date=date, work_order=f"OT-{i}", target=5000, unit="pz")
    srv, store, url = fake.start(0)
    step = max((timezone.now() - start).total_seconds() / max(a.events, 1), 0.01)
    for i in range(a.events):
        t = (start + timedelta(seconds=i * step)).isoformat()
        st = "AOI-B" if i % 2 else "AOI-T"
        store.rows.append({"EventoId": f"E{i}", "Orden": f"OT-{i % 10}", "Operacion": st, "Estacion": st, "Parte": "PN", "Serie": f"S{i // 2}",
                           "Panel": "", "Lado": "", "Cantidad": 1, "Resultado": "FAIL" if i % 97 == 0 else "PASS", "Intento": 1, "Instante": t, "Modificado": t})
    conn = ODataConnection.objects.create(name="perf", service_url=url, entity_set="EventosSimulados", key_fields=["EventoId"],
                                          mapping={"work_order": "Orden", "operation": "Operacion", "station": "Estacion", "serial": "Serie",
                                                   "qty": "Cantidad", "result": "Resultado", "attempt": "Intento", "event_at": "Instante",
                                                   "modified_at": "Modificado"},
                                          watermark_field="Modificado", time_field="Instante", page_size=500, max_pages=1000, synthetic=True)
    t0 = time.perf_counter()
    run = odata.sync_once(conn)
    full = time.perf_counter() - t0
    conn.refresh_from_db()
    t0 = time.perf_counter()
    run2 = odata.sync_once(conn)
    inc = time.perf_counter() - t0
    op = user("op", Role.OPERATOR, ("SMT",))
    sup = user("sup", Role.SUPERVISOR, ("SMT",))
    UserContext.objects.create(user=op, station=cp, work_order="OT-1")
    res = {}
    for who, u, paths in (("operador", op, ["/turno/", "/turno/api/estado/", "/turno/trabajo/"]),
                          ("supervisor", sup, ["/turno/supervisor/", f"/turno/api/pantalla/{line.code}/", "/turno/cierre/"])):
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(u)
        for p in paths:
            c.get(p)
            ts = []
            for _ in range(a.repeat):
                t0 = time.perf_counter()
                r = c.get(p)
                ts.append((time.perf_counter() - t0) * 1000)
                assert r.status_code == 200, (p, r.status_code)
            ts.sort()
            res[(who, p)] = (statistics.median(ts), ts[int(len(ts) * 0.95) - 1])
    srv.shutdown()
    print(f"Eventos sintéticos: {a.events} · base SQLite temporal · Python {sys.version.split()[0]}")
    print(f"Sincronización completa: {run.read} leídos en {run.pages} páginas, {run.created} nuevos · {full:.2f} s")
    print(f"Re-sincronización incremental (solape 10 min): {run2.read} leídos, {run2.created} nuevos · {inc:.2f} s")
    for (who, p), (med, p95) in res.items():
        print(f"{who:10s} {p:32s} mediana {med:7.1f} ms · p95 {p95:7.1f} ms ({a.repeat} solicitudes)")


if __name__ == "__main__":
    main()
