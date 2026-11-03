"""FactoryLogix connector tests. Everything here runs against a SIMULATED local server (fakeflx)."""
import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings

from apps.core.models import Role
from apps.core.tests.helpers import areas, user
from apps.flx import client, discovery, metadata, query
from apps.flx import status as st
from apps.flx.models import FlxEntitySet, FlxSchema, FlxState
from apps.flx.tests.fakeflx import FakeFlx

from apps.flx.tests.fakeflx import ROWS, SETS  # noqa: E402,F401


def flx_settings(url, **kw):
    base = dict(settings.GPV_FLX)
    base.update({"BASE_URL": url, "AUTH": "none", "TIMEOUT": 2, "CACHE_SECONDS": 0, "PROBE_DELAY_MS": 0, "BREAKER_FAILURES": 50})
    base.update(kw)
    return override_settings(GPV_FLX=base)


def cl(u):
    c = Client(HTTP_HOST="127.0.0.1")
    c.force_login(u)
    return c


class Base(TestCase):
    version = 4
    page_size = None

    def setUp(self):
        client.reset_runtime()
        self.fake = FakeFlx(version=self.version, sets=json.loads(json.dumps(SETS)), page_size=self.page_size, functions=["GetUnitHistory"])
        self.addCleanup(self.fake.stop)
        self.ov = flx_settings(self.fake.url)
        self.ov.enable()
        self.addCleanup(self.ov.disable)

    def connect(self):
        stages, schema = discovery.test_connection()
        self.assertIsNotNone(schema, stages)
        return schema


# ------------------------------------------------------------------ $metadata parser
class MetadataParserTests(TestCase):
    V4 = b'''<?xml version="1.0"?><edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><edmx:DataServices>
<Schema Namespace="A" Alias="Al" xmlns="http://docs.oasis-open.org/odata/ns/edm">
<EntityType Name="Base" Abstract="true"><Key><PropertyRef Name="Id"/></Key><Property Name="Id" Type="Edm.Int64" Nullable="false"/></EntityType>
<EntityType Name="Unit" BaseType="Al.Base"><Property Name="Serial" Type="Edm.String" MaxLength="40"/>
<NavigationProperty Name="Defects" Type="Collection(A.Defect)" Partner="Unit"/></EntityType>
<EntityType Name="Defect"><Key><PropertyRef Name="Code"/></Key><Property Name="Code" Type="Edm.String"/></EntityType>
<Function Name="History"><Parameter Name="serial" Type="Edm.String" Nullable="false"/><ReturnType Type="Collection(A.Unit)"/></Function>
<Action Name="Move"><Parameter Name="serial" Type="Edm.String"/></Action>
<EnumType Name="State"><Member Name="Open"/><Member Name="Closed"/></EnumType>
<EntityContainer Name="Svc"><EntitySet Name="Units" EntityType="A.Unit"><NavigationPropertyBinding Path="Defects" Target="Defects"/>
<Annotation Term="Org.OData.Capabilities.V1.TopSupported" Bool="false"/></EntitySet><EntitySet Name="Defects" EntityType="A.Defect"/>
<FunctionImport Name="History" Function="A.History"/><ActionImport Name="Move" Action="A.Move"/></EntityContainer>
<Annotations Target="A.Svc/Defects"><Annotation Term="Org.OData.Capabilities.V1.CountRestrictions"><Record><PropertyValue Property="Countable" Bool="false"/></Record></Annotation></Annotations>
</Schema></edmx:DataServices></edmx:Edmx>'''
    V2 = b'''<?xml version="1.0"?><edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
<edmx:DataServices m:DataServiceVersion="3.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
<Schema Namespace="F" xmlns="http://schemas.microsoft.com/ado/2009/11/edm">
<EntityType Name="Order"><Key><PropertyRef Name="No"/></Key><Property Name="No" Type="Edm.String"/>
<NavigationProperty Name="Units" Relationship="F.OrderUnits" FromRole="O" ToRole="U"/></EntityType>
<EntityType Name="Unit"><Key><PropertyRef Name="Sn"/></Key><Property Name="Sn" Type="Edm.String"/></EntityType>
<Association Name="OrderUnits"><End Role="O" Type="F.Order" Multiplicity="1"/><End Role="U" Type="F.Unit" Multiplicity="*"/></Association>
<EntityContainer Name="C"><EntitySet Name="Orders" EntityType="F.Order"/><EntitySet Name="Units" EntityType="F.Unit"/>
<FunctionImport Name="Trace" ReturnType="Collection(F.Unit)" EntitySet="Units" m:HttpMethod="GET"><Parameter Name="sn" Type="Edm.String" Mode="In"/></FunctionImport>
</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>'''

    def test_v4_inheritance_navigation_functions_and_capabilities(self):
        m = metadata.parse(self.V4)
        self.assertEqual((m["major"], m["odata_version"]), (4, "4.0"))
        u = m["entity_sets"]["Units"]
        self.assertEqual(u["keys"], ["Id"])  # inherited through an alias
        self.assertEqual(set(u["properties"]), {"Id", "Serial"})
        self.assertFalse(u["properties"]["Id"]["nullable"])
        self.assertEqual(u["navigation"]["Defects"], {"target_type": "A.Defect", "collection": True, "target_set": "Defects"})
        self.assertIs(u["declared_capabilities"]["TopSupported"], False)
        self.assertIs(m["entity_sets"]["Defects"]["declared_capabilities"]["CountRestrictions.Countable"], False)
        fi = {f["name"]: f for f in m["function_imports"]}
        self.assertEqual(fi["History"]["parameters"][0]["name"], "serial")
        self.assertEqual((fi["Move"]["kind"], fi["Move"]["http_method"]), ("action", "POST"))
        self.assertEqual(m["enum_types"]["A.State"], ["Open", "Closed"])

    def test_v2_associations_and_function_import(self):
        m = metadata.parse(self.V2)
        self.assertEqual((m["major"], m["odata_version"]), (2, "3.0"))
        self.assertEqual(m["entity_sets"]["Orders"]["navigation"]["Units"], {"target_type": "F.Unit", "collection": True})
        f = m["function_imports"][0]
        self.assertEqual((f["name"], f["http_method"], f["parameters"][0]["mode"]), ("Trace", "GET", "In"))

    def test_invalid_documents(self):
        for bad in (b"<html>login</html>", b"not xml", b"<root/>"):
            with self.assertRaises(metadata.MetadataError):
                metadata.parse(bad)


# ------------------------------------------------------------------ connection, auth, safety
class ConnectionTests(Base):
    def test_staged_connection_reads_schema_and_registry(self):
        stages, schema = discovery.test_connection()
        self.assertTrue(all(s["ok"] for s in stages), stages)
        self.assertEqual([s["stage"] for s in stages], ["Configuración", "Métodos de autenticación", "Documento de servicio", "Lectura de $metadata"])
        # only stages that received a valid OData response may say CONNECTED
        self.assertEqual([s["state"] for s in stages], [st.OK, st.OK, st.CONNECTED, st.CONNECTED])
        self.assertEqual(schema.entity_set_count, len(SETS))
        self.assertEqual(FlxEntitySet.objects.get(name="WIP").category, "Producción")
        self.assertEqual(FlxEntitySet.objects.get(name="WIP").status, st.NOT_TESTED)  # catalog != permission
        self.assertEqual(schema.function_imports[0]["name"], "GetUnitHistory")
        self.assertIn("WIP", FlxState.get().service_doc_sets)

    def test_unreachable_is_never_connected(self):
        with flx_settings("http://127.0.0.1:9/odata/"):
            stages, schema = discovery.test_connection()
        self.assertIsNone(schema)
        self.assertEqual(stages[-1]["state"], st.UNREACHABLE)
        self.assertNotEqual(FlxState.get().last_status, st.CONNECTED)

    def test_html_root_is_bad_response_not_connected(self):
        self.fake.html_root = True
        stages, _s = discovery.test_connection()
        self.assertEqual(stages[2]["state"], st.CONNECTED)  # HTTP 200, but...
        self.assertEqual(FlxState.get().service_doc_sets, [])  # ...no OData document was recognized

    def test_only_get_and_url_pinning(self):
        self.connect()
        self.assertTrue(self.fake.calls and all(m == "GET" for m, _p, _h in self.fake.calls))
        with self.assertRaises(client.FlxError):
            client.resolve("http://evil.example/odata/WIP")
        with self.assertRaises(client.FlxError):
            client.resolve("../admin")
        with self.assertRaises(client.FlxError):
            client.resolve("/etc/passwd")
        self.assertTrue(client.resolve(self.fake.url + "WIP?$skiptoken=3").startswith(self.fake.url))
        src = (Path(client.__file__)).read_text()
        self.assertNotRegex(src, r'method="(POST|PUT|PATCH|DELETE|MERGE)"')

    def test_config_error_for_bad_base_url(self):
        with flx_settings("ftp://x/"):
            stages, _ = discovery.test_connection()
        self.assertEqual(stages[0]["state"], st.CONFIG_ERROR)


class AuthTests(TestCase):
    def setUp(self):
        client.reset_runtime()
        self.fake = FakeFlx(sets=json.loads(json.dumps(SETS)), auth=("basic", "svc", "S3cret-flx"))
        self.addCleanup(self.fake.stop)

    def test_detects_schemes_blocks_after_401_and_unblocks_on_new_credentials(self):
        with flx_settings(self.fake.url, AUTH="auto"):
            stages, schema = discovery.test_connection()
            self.assertIsNone(schema)
            self.assertIn("Basic", FlxState.get().auth_schemes_offered)
            self.assertEqual(stages[2]["state"], st.AUTH_REQUIRED)
            n = len(self.fake.calls)
            with self.assertRaises(client.FlxError) as cm:
                client.get("WIP?$top=1")
            self.assertEqual(cm.exception.state, st.AUTH_REQUIRED)
            self.assertEqual(len(self.fake.calls), n)  # persistent 401: not retried automatically
        with flx_settings(self.fake.url, AUTH="basic"), mock.patch.dict(os.environ, {"GPV_FLX_USER": "svc", "GPV_FLX_PASSWORD": "S3cret-flx"}):
            with self.assertLogs("gpv.flx", level="INFO") as logs:
                stages, schema = discovery.test_connection()
            self.assertIsNotNone(schema, stages)
            joined = "\n".join(logs.output)
            self.assertNotIn("S3cret-flx", joined)
            self.assertNotIn("Basic ", joined)
            self.assertNotIn("Authorization", joined)

    def test_wrong_password_reports_auth_required_once(self):
        with flx_settings(self.fake.url, AUTH="basic"), mock.patch.dict(os.environ, {"GPV_FLX_USER": "svc", "GPV_FLX_PASSWORD": "mala"}):
            stages, schema = discovery.test_connection()
            self.assertEqual(stages[-1]["state"], st.AUTH_REQUIRED)
            n = len(self.fake.calls)
            with self.assertRaises(client.FlxError):
                client.get("WIP?$top=1")
            self.assertEqual(len(self.fake.calls), n)
            client.clear_auth_block()  # admin «Reintentar autenticación»
            with self.assertRaises(client.FlxError):
                client.get("WIP?$top=1")
            self.assertEqual(len(self.fake.calls), n + 1)

    def test_basic_without_env_is_config_error(self):
        with flx_settings(self.fake.url, AUTH="basic"), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GPV_FLX_USER", None)
            with self.assertRaises(client.FlxError) as cm:
                client.get("", force=True)
        self.assertEqual(cm.exception.state, st.CONFIG_ERROR)

    def test_windows_integrated_needs_optional_package(self):
        try:
            import requests_negotiate_sspi  # noqa: F401
            self.skipTest("paquete instalado")
        except ImportError:
            pass
        with flx_settings(self.fake.url, AUTH="negotiate"):
            with self.assertRaises(client.FlxError) as cm:
                client.get("", force=True)
        self.assertEqual(cm.exception.state, st.CONFIG_ERROR)

    def test_negotiate_challenge_is_reported(self):
        f = FakeFlx(sets={}, auth=("negotiate",))
        self.addCleanup(f.stop)
        with flx_settings(f.url, AUTH="auto"):
            r = client.detect_auth()
        self.assertEqual(r["schemes"], ["Negotiate", "NTLM"])


# ------------------------------------------------------------------ probes
class ProbeTests(Base):
    def test_probe_classifies_every_outcome_and_keeps_no_values(self):
        self.connect()
        self.fake.sets["OEE"]["delay"] = 0  # explicit
        with flx_settings(self.fake.url, TIMEOUT=2):
            discovery.probe()
        got = dict(FlxEntitySet.objects.values_list("name", "status"))
        self.assertEqual(got["WIP"], st.CONNECTED)
        self.assertEqual(got["Quality"], st.FORBIDDEN)
        self.assertEqual(got["Faults"], st.SERVER_ERROR)
        self.assertEqual(got["OEE"], st.NO_DATA)
        self.assertEqual(got["Yield"], st.SCHEMA_MISMATCH)
        self.assertEqual(got["SMT"], st.NOT_FOUND)
        self.assertEqual(got["Inventory"], st.BAD_RESPONSE)
        self.assertEqual(FlxEntitySet.objects.get(name="WIP").returned_properties, sorted(SETS["WIP"]["props"]))
        self.assertIn("$top=1", " ".join(p for _m, p, _h in self.fake.calls if "/WIP" in p))
        rep = json.dumps(discovery.report())
        for value in ("SN000", "Juan Persona", "jdoe"):
            self.assertNotIn(value, rep)  # structure only

    def test_timeout_is_classified(self):
        self.connect()
        self.fake.sets["OEE"]["delay"] = 2.5
        with flx_settings(self.fake.url, TIMEOUT=1):
            discovery.probe(["OEE"])
        self.assertEqual(FlxEntitySet.objects.get(name="OEE").status, st.TIMEOUT)

    def test_retry_on_503_then_success_and_circuit_breaker(self):
        self.connect()
        self.fake.sets["OEE"]["fail_times"] = 2
        r = client.get("OEE?$top=1", use_cache=False)
        self.assertEqual((r.status, r.attempts), (200, 3))
        with flx_settings(self.fake.url, BREAKER_FAILURES=2, BREAKER_COOLDOWN=60):
            for _ in range(2):
                with self.assertRaises(client.FlxError):
                    client.get("Faults?$top=1", use_cache=False)
            n = len(self.fake.calls)
            with self.assertRaises(client.FlxError) as cm:
                client.get("WIP?$top=1", use_cache=False)
            self.assertEqual(cm.exception.state, st.CIRCUIT_OPEN)
            self.assertEqual(len(self.fake.calls), n)
        client.reset_runtime()

    def test_403_is_not_retried(self):
        self.connect()
        n = self.fake.count("Quality")
        with self.assertRaises(client.FlxError):
            client.get("Quality?$top=1", use_cache=False)
        self.assertEqual(self.fake.count("Quality"), n + 1)

    def test_probe_requires_live_schema(self):
        discovery.load_schema_file(self.fake.metadata().encode(), None)
        with self.assertRaises(client.FlxError):
            discovery.probe()

    def test_capabilities_detect_unsupported_options(self):
        self.connect()
        discovery.probe(["WIP"])
        es = FlxEntitySet.objects.get(name="WIP")
        caps = discovery.test_capabilities(es)
        self.assertEqual({k: caps[k] for k in ("$top", "$select", "$orderby", "$skip", "$count", "$filter", "$expand")},
                         {"$top": True, "$select": True, "$orderby": True, "$skip": False, "$count": True, "$filter": True, "$expand": True})

    def test_schema_refresh_keeps_results_only_if_structure_unchanged(self):
        self.connect()
        discovery.probe(["WIP"])
        self.connect()
        self.assertEqual(FlxEntitySet.objects.get(schema__is_current=True, name="WIP").status, st.CONNECTED)
        self.fake.sets["WIP"]["props"]["New"] = "Edm.String"
        self.connect()
        self.assertEqual(FlxEntitySet.objects.get(schema__is_current=True, name="WIP").status, st.NOT_TESTED)


# ------------------------------------------------------------------ query engine
class QueryTests(Base):
    page_size = 3

    def ready(self):
        self.connect()
        discovery.probe(["WIP"])
        es = FlxEntitySet.objects.get(schema__is_current=True, name="WIP")
        discovery.test_capabilities(es)
        es.refresh_from_db()
        return es

    def test_literals_and_injection_safety(self):
        self.assertEqual(query.literal("a'b", "Edm.String", 4), "'a''b'")
        self.assertEqual(query.literal("x' or 1 eq 1 or 'a", "Edm.String", 4), "'x'' or 1 eq 1 or ''a'")
        self.assertEqual(query.literal("5", "Edm.Int32", 4), "5")
        self.assertEqual(query.literal("5.5", "Edm.Decimal", 2), "5.5M")
        self.assertEqual(query.literal("2026-11-03T12:00:00Z", "Edm.DateTimeOffset", 4), "2026-11-03T12:00:00Z")
        self.assertEqual(query.literal("2026-11-03T12:00:00Z", "Edm.DateTime", 2), "datetime'2026-11-03T12:00:00'")
        self.assertTrue(query.literal("12345678-1234-1234-1234-1234567890ab", "Edm.Guid", 2).startswith("guid'"))
        for bad in (("x", "Edm.Int32"), ("5.5", "Edm.Int32"), ("hoy", "Edm.DateTime"), ("x", "Edm.Guid")):
            with self.assertRaises(ValueError):
                query.literal(bad[0], bad[1], 4)

    def test_validation_against_schema_and_verified_capabilities(self):
        es = self.ready()
        with self.assertRaises(query.QueryError):
            query.validate(query.QuerySpec("WIP", select=["NoExiste"]), es)
        with self.assertRaises(query.QueryError):
            query.validate(query.QuerySpec("WIP", filters=[("Qty", "contains", "1")]), es)  # contains only for text
        with self.assertRaises(query.QueryError):
            query.validate(query.QuerySpec("WIP", filters=[("Qty", "like", "1")]), es)
        with self.assertRaises(query.QueryError):
            query.validate(query.QuerySpec("WIP", top=10_000), es)
        es.capabilities = {"$top": True}
        with self.assertRaises(query.QueryError):
            query.validate(query.QuerySpec("WIP", filters=[("Serial", "eq", "SN1")]), es)  # $filter not verified
        quality = FlxEntitySet.objects.get(schema__is_current=True, name="Quality")
        with self.assertRaises(query.QueryError):
            query.validate(query.QuerySpec("Quality"), quality)  # never probed as readable

    def test_server_paging_follows_next_links(self):
        es = self.ready()
        res = query.run(query.QuerySpec("WIP", top=7, orderby=[("Serial", "asc")]), es, use_cache=False)
        self.assertEqual(([r["Serial"] for r in res["rows"]], res["pages"], res["truncated"]), ([f"SN{i:03d}" for i in range(7)], 3, False))
        res = query.run(query.QuerySpec("WIP", top=5), es, use_cache=False)
        self.assertEqual(len(res["rows"]), 5)
        self.assertEqual(res["source"]["entity_set"], "WIP")
        res = query.run(query.QuerySpec("WIP", filters=[("WorkOrder", "eq", "W07481"), ("Station", "contains", "C")], select=["Serial", "WorkOrder"],
                                        count=True, top=50), es, use_cache=False)
        self.assertEqual({r["WorkOrder"] for r in res["rows"]}, {"W07481"})
        self.assertEqual(set(res["rows"][0]), {"Serial", "WorkOrder"})
        self.assertEqual(res["count"], 3)

    def test_foreign_next_link_is_rejected(self):
        es = self.ready()
        self.fake.foreign_next = True
        with self.assertRaises(client.FlxError):
            query.run(query.QuerySpec("WIP", top=7), es, use_cache=False)

    def test_short_cache_avoids_repeated_calls(self):
        es = self.ready()
        with flx_settings(self.fake.url, CACHE_SECONDS=30):
            query.run(query.QuerySpec("WIP", top=2), es)
            n = len(self.fake.calls)
            query.run(query.QuerySpec("WIP", top=2), es)
            self.assertEqual(len(self.fake.calls), n)


class V2QueryTests(QueryTests):
    version = 2

    def test_v2_payload_substringof_and_dates(self):
        es = self.ready()
        res = query.run(query.QuerySpec("WIP", filters=[("Station", "contains", "IC")], top=10), es, use_cache=False)
        self.assertEqual({r["Station"] for r in res["rows"]}, {"ICT"})
        self.assertNotIn("__metadata", res["rows"][0])
        self.assertTrue(any("substringof" in p for _m, p, _h in self.fake.calls))


# ------------------------------------------------------------------ web: roles, Connection Center, CLI
class WebTests(Base):
    def setUp(self):
        super().setUp()
        areas()
        self.op = user("op", Role.OPERATOR)
        self.tec = user("tec", Role.TECHNICIAN)
        self.eng = user("eng", Role.ENGINEER)
        self.admin = user("root", superuser=True)

    def test_role_permissions(self):
        self.assertEqual(cl(self.op).get("/factorylogix/").status_code, 403)
        self.assertEqual(cl(self.tec).get("/factorylogix/").status_code, 200)
        self.assertEqual(cl(self.tec).post("/factorylogix/accion/", {"action": "test"}).status_code, 403)
        self.assertEqual(cl(self.eng).post("/factorylogix/accion/", {"action": "test"}).status_code, 403)
        self.assertNotIn('href="/factorylogix/"', cl(self.op).get("/?inicio=1").content.decode())
        self.assertIn('href="/factorylogix/"', cl(self.tec).get("/").content.decode())

    def test_center_flow_test_probe_capabilities_query_csv(self):
        a = cl(self.admin)
        self.assertContains(a.get("/factorylogix/"), "Aún no se ha leído el $metadata")
        a.post("/factorylogix/accion/", {"action": "test", "schema": "1"})
        page = a.get("/factorylogix/").content.decode()
        self.assertIn("CONNECTED", page)
        self.assertIn("GetUnitHistory", page)
        self.assertIn("ActiveProductTracking", page)  # listed by GPV, absent from this metadata
        r = a.post("/factorylogix/accion/", {"action": "probe"})
        self.assertEqual(r.status_code, 400)  # explicit authorization checkbox required
        r = a.post("/factorylogix/accion/", {"action": "probe", "confirm": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(FlxEntitySet.objects.get(schema__is_current=True, name="Quality").status, st.FORBIDDEN)
        a.post("/factorylogix/entidad/WIP/accion/", {"action": "caps"})
        self.assertEqual(cl(self.tec).post("/factorylogix/entidad/WIP/consulta/", {"top": "5"}).status_code, 403)
        r = cl(self.eng).post("/factorylogix/entidad/WIP/consulta/", {"top": "3", "select": ["Serial"], "f0_prop": "WorkOrder", "f0_op": "eq",
                                                                        "f0_value": "W07480"})
        d = r.json()
        self.assertTrue(d["ok"], d)
        self.assertTrue(all(set(x) == {"Serial"} for x in d["data"]["rows"]))
        self.assertEqual(d["data"]["source"]["origin"], "FactoryLogix OData (lectura)")
        r = cl(self.eng).post("/factorylogix/entidad/WIP/consulta/", {"top": "3", "format": "csv"})
        body = r.content.decode("utf-8-sig")
        self.assertTrue(body.startswith("# Fuente: FactoryLogix OData"))
        r = cl(self.eng).post("/factorylogix/entidad/WIP/consulta/", {"top": "3", "f0_prop": "Qty", "f0_op": "eq", "f0_value": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(cl(self.eng).get("/factorylogix/entidad/WIP/").status_code, 200)
        rep = a.get("/factorylogix/reporte.json")
        self.assertNotIn("SN00", rep.content.decode())
        self.assertTrue(all(m == "GET" for m, _p, _h in self.fake.calls))

    def test_upload_metadata_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        a = cl(self.admin)
        a.post("/factorylogix/accion/", {"action": "upload", "metadata": SimpleUploadedFile("m.xml", self.fake.metadata().encode(), "application/xml")})
        s = FlxSchema.objects.get(is_current=True)
        self.assertEqual((s.source, s.entity_set_count), ("file", len(SETS)))
        self.assertEqual(len(self.fake.calls), 0)  # no server contact
        self.assertContains(a.get("/factorylogix/"), "sin verificar acceso")

    def test_cli_diagnose_writes_reports_and_requires_confirmation(self):
        out = tempfile.mkdtemp()
        with self.assertRaises(CommandError):
            call_command("flx_diagnose", "--sondear", stdout=StringIO())
        buf = StringIO()
        call_command("flx_diagnose", "--sondear", "--confirmar-sondeo", "--entidades", "WIP,Quality", "--salida", out, stdout=buf)
        files = sorted(Path(out).iterdir())
        self.assertEqual({f.suffix for f in files}, {".json", ".md"})
        rep = json.loads(next(f for f in files if f.suffix == ".json").read_text(encoding="utf-8"))
        self.assertEqual({e["name"]: e["status"] for e in rep["entity_sets"] if e["name"] in ("WIP", "Quality")},
                         {"WIP": st.CONNECTED, "Quality": st.FORBIDDEN})
        self.assertNotIn("SN00", json.dumps(rep))
        self.assertIn("[OK ] Lectura de $metadata", buf.getvalue())
