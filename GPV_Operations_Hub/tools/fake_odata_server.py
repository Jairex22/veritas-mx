"""SIMULATED OData v4 service for tests and demos. It is NOT FactoryLogix.

* Entity names, fields and the URL are invented for the simulation and must NOT be copied
  into a real configuration: the real ones come from the GPV FactoryLogix $metadata.
* Read-only: anything other than GET returns 405.
* Listens on 127.0.0.1 only.

Usage:  python tools/fake_odata_server.py [--port 8765] [--auth none|basic] [--deny-entity] [--fail-every N]
With --auth basic, the user/password are read from FAKE_ODATA_USER / FAKE_ODATA_PASSWORD.
"""
import argparse
import base64
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

METADATA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
 <edmx:DataServices>
  <Schema Namespace="Simulado" xmlns="http://docs.oasis-open.org/odata/ns/edm">
   <EntityType Name="EventoSimulado">
    <Key><PropertyRef Name="EventoId"/></Key>
    <Property Name="EventoId" Type="Edm.String" Nullable="false"/>
    <Property Name="Orden" Type="Edm.String"/>
    <Property Name="Operacion" Type="Edm.String"/>
    <Property Name="Estacion" Type="Edm.String"/>
    <Property Name="Parte" Type="Edm.String"/>
    <Property Name="Serie" Type="Edm.String"/>
    <Property Name="Panel" Type="Edm.String"/>
    <Property Name="Lado" Type="Edm.String"/>
    <Property Name="Cantidad" Type="Edm.Decimal"/>
    <Property Name="Resultado" Type="Edm.String"/>
    <Property Name="Intento" Type="Edm.Int32"/>
    <Property Name="Instante" Type="Edm.DateTimeOffset"/>
    <Property Name="Modificado" Type="Edm.DateTimeOffset"/>
   </EntityType>
   <EntityContainer Name="Contenedor">
    <EntitySet Name="EventosSimulados" EntityType="Simulado.EventoSimulado"/>
   </EntityContainer>
  </Schema>
 </edmx:DataServices>
</edmx:Edmx>"""


class Store:
    def __init__(self):
        self.rows = []
        self.lock = threading.Lock()
        self.calls = []

    def add(self, **kw):
        now = datetime.now(timezone.utc)
        row = {"EventoId": kw.pop("EventoId"), "Orden": "", "Operacion": "", "Estacion": "", "Parte": "", "Serie": "", "Panel": "", "Lado": "",
               "Cantidad": 1, "Resultado": "PASS", "Intento": 1, "Instante": now.isoformat(), "Modificado": now.isoformat()}
        row.update(kw)
        with self.lock:
            self.rows = [r for r in self.rows if r["EventoId"] != row["EventoId"]] + [row]
        return row

    def seed_demo(self, base=None, n=40):
        """Synthetic SMT events for the example line (AOI-B is the example count point)."""
        base = base or datetime.now(timezone.utc) - timedelta(hours=2)
        for i in range(n):
            t = base + timedelta(minutes=3 * i)
            for st, op, side in (("SMT-EJ-AOI-T", "AOI-T", "top"), ("SMT-EJ-AOI-B", "AOI-B", "bottom")):
                self.add(EventoId=f"SIM-{st}-{i:04d}", Orden="OT-EJ-1001", Operacion=op, Estacion=st, Parte="PN-EJ-500", Panel=f"PNL-EJ-{i:04d}",
                         Lado=side, Cantidad=1, Resultado="FAIL" if (op == "AOI-B" and i % 17 == 5) else "PASS", Intento=1,
                         Serie=f"SN-EJ-{i:05d}", Instante=t.isoformat(), Modificado=t.isoformat())


def make_handler(store, auth="none", deny_entity=False, fail_every=0):
    counter = {"n": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _deny_write(self):
            self._send(405, json.dumps({"error": "SIMULADO: solo lectura"}))

        do_POST = do_PUT = do_PATCH = do_DELETE = _deny_write

        def do_GET(self):
            store.calls.append(self.path)
            if auth == "basic":
                exp = "Basic " + base64.b64encode(f"{os.environ.get('FAKE_ODATA_USER', '')}:{os.environ.get('FAKE_ODATA_PASSWORD', '')}".encode()).decode()
                if self.headers.get("Authorization") != exp:
                    return self._send(401, json.dumps({"error": "auth"}))
            u = urlparse(self.path)
            p = u.path.rstrip("/")
            if p in ("/odata", ""):
                return self._send(200, json.dumps({"@odata.context": "$metadata", "value": [{"name": "EventosSimulados", "kind": "EntitySet", "url": "EventosSimulados"}]}))
            if p == "/odata/$metadata":
                return self._send(200, METADATA, "application/xml")
            if p == "/odata/EventosSimulados":
                if deny_entity:
                    return self._send(403, json.dumps({"error": "forbidden"}))
                counter["n"] += 1
                if fail_every and counter["n"] % fail_every == 0:
                    return self._send(503, json.dumps({"error": "SIMULADO: no disponible"}))
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                top = int(q.get("$top", "100"))
                skip = int(q.get("$skiptoken", "0"))
                with store.lock:
                    rows = list(store.rows)
                f = q.get("$filter", "")
                if " ge " in f:
                    field, val = f.split(" ge ", 1)
                    lim = datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
                    rows = [r for r in rows if datetime.fromisoformat(r[field.strip()]) >= lim]
                if q.get("$orderby"):
                    rows.sort(key=lambda r: (r[q["$orderby"]], r["EventoId"]))
                page = rows[skip: skip + top]
                if q.get("$select"):
                    keep = q["$select"].split(",")
                    page = [{k: r.get(k) for k in keep} for r in page]
                out = {"@odata.context": "$metadata#EventosSimulados", "value": page}
                if skip + top < len(rows):
                    from urllib.parse import urlencode

                    q2 = dict(q)
                    q2["$skiptoken"] = str(skip + top)
                    out["@odata.nextLink"] = f"http://{self.headers.get('Host')}/odata/EventosSimulados?" + urlencode(q2)
                return self._send(200, json.dumps(out))
            return self._send(404, json.dumps({"error": "not found"}))

    return H


def start(port=0, store=None, **kw):
    """Start in a background thread (tests). Returns (server, store, base_url)."""
    store = store or Store()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, **kw))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, store, f"http://127.0.0.1:{srv.server_address[1]}/odata/"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servicio OData SIMULADO (no es FactoryLogix).")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--auth", choices=["none", "basic"], default="none")
    ap.add_argument("--deny-entity", action="store_true")
    ap.add_argument("--fail-every", type=int, default=0)
    a = ap.parse_args()
    st = Store()
    st.seed_demo()
    srv, _s, url = start(a.port, st, auth=a.auth, deny_entity=a.deny_entity, fail_every=a.fail_every)
    print(f"OData SIMULADO en {url} (Ctrl+C para detener). No es FactoryLogix.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
