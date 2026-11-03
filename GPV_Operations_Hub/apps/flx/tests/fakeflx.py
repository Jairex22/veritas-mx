"""SIMULATED OData service used ONLY by the automated tests. It is not FactoryLogix.

Entity-set names may reuse names from GPV's list, but every property, key and record here is
invented for the tests. Supports OData v4 and v2 payloads, authentication challenges, HTTP errors,
delays, server paging, $select/$filter/$orderby/$skip/$top/$count/$expand (minimal subset).
"""
import base64
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit


# SIMULATED data (invented for tests)
ROWS = [{"Serial": f"SN{i:03d}", "WorkOrder": "W0748" + str(i % 2), "Qty": i, "Station": "FCT" if i % 3 else "ICT", "When": f"2026-11-0{1 + i % 3}T10:00:00Z"}
        for i in range(7)]
SETS = {
    "WIP": {"keys": ["Serial"], "props": {"Serial": "Edm.String", "WorkOrder": "Edm.String", "Qty": "Edm.Int32", "Station": "Edm.String",
                                          "When": "Edm.DateTimeOffset"}, "rows": ROWS, "nav": {"Steps": "QualityT"}, "unsupported": ["$skip"]},
    "Quality": {"keys": ["Id"], "props": {"Id": "Edm.Int32"}, "status": 403},
    "Faults": {"keys": ["Id"], "props": {"Id": "Edm.Int32"}, "status": 500},
    "OEE": {"keys": ["Id"], "props": {"Id": "Edm.Int32"}, "rows": []},
    "Yield": {"keys": ["Id"], "props": {"Id": "Edm.Int32"}, "rows": [{"Id": 1, "Extra": "x"}]},
    "SMT": {"keys": ["Id"], "props": {"Id": "Edm.Int32"}, "missing_on_server": True},
    "Inventory": {"keys": ["Id"], "props": {"Id": "Edm.Int32"}, "html": True},
    "UserDetail": {"keys": ["Login"], "props": {"Login": "Edm.String", "Name": "Edm.String"}, "rows": [{"Login": "jdoe", "Name": "Juan Persona"}]},
}


class FakeFlx:
    def __init__(self, version=4, sets=None, auth=None, page_size=None, functions=None, foreign_next=False, html_root=False):
        self.version, self.sets, self.auth, self.page_size = version, sets or {}, auth, page_size
        self.functions = functions or []
        self.foreign_next, self.html_root = foreign_next, html_root
        self.calls = []
        self.lock = threading.Lock()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/odata/"

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def count(self, prefix=""):
        return sum(1 for m, p, _h in self.calls if p.startswith("/odata/" + prefix))

    # ------------------------------------------------------------ metadata
    def metadata(self):
        if self.version == 4:
            types, sets = [], []
            for name, s in self.sets.items():
                if s.get("not_in_metadata"):
                    continue
                props = "".join(f'<Property Name="{p}" Type="{t}"/>' for p, t in s["props"].items())
                navs = "".join(f'<NavigationProperty Name="{n}" Type="Collection(Sim.{t})"/>' for n, t in s.get("nav", {}).items())
                keys = "".join(f'<PropertyRef Name="{k}"/>' for k in s["keys"])
                types.append(f'<EntityType Name="{name}T"><Key>{keys}</Key>{props}{navs}</EntityType>')
                sets.append(f'<EntitySet Name="{name}" EntityType="Sim.{name}T"/>')
            fns = "".join(f'<Function Name="{f}"><Parameter Name="serial" Type="Edm.String"/><ReturnType Type="Edm.String"/></Function>' for f in self.functions)
            fis = "".join(f'<FunctionImport Name="{f}" Function="Sim.{f}"/>' for f in self.functions)
            return (f'<?xml version="1.0"?><edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><edmx:DataServices>'
                    f'<Schema Namespace="Sim" xmlns="http://docs.oasis-open.org/odata/ns/edm">{"".join(types)}{fns}'
                    f'<EntityContainer Name="C">{"".join(sets)}{fis}</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>')
        types, sets = [], []
        for name, s in self.sets.items():
            if s.get("not_in_metadata"):
                continue
            props = "".join(f'<Property Name="{p}" Type="{t}"/>' for p, t in s["props"].items())
            keys = "".join(f'<PropertyRef Name="{k}"/>' for k in s["keys"])
            types.append(f'<EntityType Name="{name}T"><Key>{keys}</Key>{props}</EntityType>')
            sets.append(f'<EntitySet Name="{name}" EntityType="Sim.{name}T"/>')
        fis = "".join(f'<FunctionImport Name="{f}" ReturnType="Edm.String" m:HttpMethod="GET"><Parameter Name="serial" Type="Edm.String" Mode="In"/></FunctionImport>'
                      for f in self.functions)
        return ('<?xml version="1.0"?><edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">'
                '<edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">'
                f'<Schema Namespace="Sim" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">{"".join(types)}'
                f'<EntityContainer Name="C" m:IsDefaultEntityContainer="true">{"".join(sets)}{fis}</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>')

    # ------------------------------------------------------------ handler
    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, body, ctype="application/json", headers=None):
                data = body.encode() if isinstance(body, str) else body
                try:
                    self._send(code, data, ctype, headers)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client gave up (timeout tests)

            def _send(self, code, data, ctype, headers):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def _write(self):
                with fake.lock:
                    fake.calls.append((self.command, self.path, dict(self.headers)))
                self.send(405, '{"error":"read only"}')

            do_POST = do_PUT = do_PATCH = do_DELETE = do_MERGE = _write

            def do_GET(self):
                with fake.lock:
                    fake.calls.append(("GET", self.path, dict(self.headers)))
                if fake.auth:
                    kind = fake.auth[0]
                    if kind == "basic":
                        exp = "Basic " + base64.b64encode(f"{fake.auth[1]}:{fake.auth[2]}".encode()).decode()
                        if self.headers.get("Authorization") != exp:
                            return self.send(401, '{"error":"auth"}', headers={"WWW-Authenticate": 'Basic realm="sim"'})
                    else:
                        return self.send(401, '{"error":"auth"}', headers={"WWW-Authenticate": "Negotiate, NTLM"})
                u = urlsplit(self.path)
                path = unquote(u.path)
                if not path.startswith("/odata"):
                    return self.send(404, "{}")
                rest = path[len("/odata"):].strip("/")
                if rest == "":
                    if fake.html_root:
                        return self.send(200, "<html>login</html>", "text/html")
                    names = [n for n, s in fake.sets.items() if not s.get("not_in_metadata")]
                    if fake.version == 4:
                        return self.send(200, json.dumps({"value": [{"name": n, "url": n} for n in names]}))
                    return self.send(200, json.dumps({"d": {"EntitySets": names}}))
                if rest == "$metadata":
                    return self.send(200, fake.metadata(), "application/xml", {"OData-Version": "4.0"} if fake.version == 4 else {"DataServiceVersion": "2.0"})
                name = rest.split("/")[0]
                s = fake.sets.get(name)
                if s is None or s.get("missing_on_server"):
                    return self.send(404, '{"error":{"message":"Resource not found"}}')
                if s.get("delay"):
                    time.sleep(s["delay"])
                if s.get("status"):
                    return self.send(s["status"], json.dumps({"error": {"message": "simulated error"}}))
                if s.get("fail_times", 0) > 0:
                    s["fail_times"] -= 1
                    return self.send(503, '{"error":"busy"}', headers={"Retry-After": "0"})
                if s.get("html"):
                    return self.send(200, "<html>proxy</html>", "text/html")
                q = dict(parse_qsl(u.query, keep_blank_values=True))
                for opt in s.get("unsupported", []):
                    if opt in q:
                        return self.send(400, json.dumps({"error": {"message": f"{opt} not supported"}}))
                rows = [dict(r) for r in s.get("rows", [])]
                if "$filter" in q:
                    rows = [r for r in rows if _match(r, q["$filter"])]
                if "$orderby" in q:
                    f, _, d = q["$orderby"].partition(" ")
                    rows.sort(key=lambda r: (r.get(f) is None, r.get(f)), reverse=d == "desc")
                total = len(rows)
                skip = int(q.get("$skip", 0)) + int(q.get("$skiptoken", 0))
                top = int(q.get("$top", 10 ** 6))
                if "$expand" in q and q["$expand"] not in s.get("nav", {}):
                    return self.send(400, '{"error":"bad expand"}')
                take = min(top, fake.page_size or top)
                page = rows[skip: skip + take]
                remaining_top = top - len(page)
                nxt = None
                if fake.page_size and remaining_top > 0 and skip + take < len(rows):
                    q2 = dict(q)
                    q2.pop("$skip", None)
                    q2["$skiptoken"] = str(skip + take)
                    q2["$top"] = str(remaining_top)
                    host = "evil.example:80" if fake.foreign_next else self.headers.get("Host")
                    nxt = f"http://{host}/odata/{name}?" + urlencode(q2)
                if "$select" in q:
                    keep = q["$select"].split(",")
                    page = [{k: r.get(k) for k in keep} for r in page]
                if fake.version == 4:
                    out = {"@odata.context": "$metadata#" + name, "value": page}
                    if q.get("$count") == "true":
                        out["@odata.count"] = total
                    if nxt:
                        out["@odata.nextLink"] = nxt
                else:
                    for r in page:
                        r["__metadata"] = {"type": "Sim." + name + "T"}
                    out = {"d": {"results": page}}
                    if q.get("$inlinecount") == "allpages":
                        out["d"]["__count"] = str(total)
                    if nxt:
                        out["d"]["__next"] = nxt
                return self.send(200, json.dumps(out))

        return H


def _lit(v):
    v = v.strip()
    if v.startswith("'"):
        return v[1:-1].replace("''", "'")
    if v in ("true", "false"):
        return v == "true"
    try:
        return int(v)
    except ValueError:
        return float(v.rstrip("MLmd"))


def _match(row, expr):
    for part in re.split(r"\s+and\s+", expr):
        part = part.strip()
        m = re.match(r"^contains\((\w+),('(?:[^']|'')*')\)$", part) or None
        if m:
            if _lit(m.group(2)) not in str(row.get(m.group(1), "")):
                return False
            continue
        m = re.match(r"^substringof\(('(?:[^']|'')*'),(\w+)\) eq true$", part)
        if m:
            if _lit(m.group(1)) not in str(row.get(m.group(2), "")):
                return False
            continue
        m = re.match(r"^startswith\((\w+),('(?:[^']|'')*')\)( eq true)?$", part)
        if m:
            if not str(row.get(m.group(1), "")).startswith(_lit(m.group(2))):
                return False
            continue
        m = re.match(r"^(\w+) (eq|ne|gt|ge|lt|le) (.+)$", part)
        if not m:
            return False
        a, op, b = row.get(m.group(1)), m.group(2), _lit(m.group(3))
        ok = {"eq": a == b, "ne": a != b, "gt": a is not None and a > b, "ge": a is not None and a >= b,
              "lt": a is not None and a < b, "le": a is not None and a <= b}[op]
        if not ok:
            return False
    return True
