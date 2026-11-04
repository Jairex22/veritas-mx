"""Parser OData, metadatos y construcción segura de filtros."""
import unittest
from datetime import datetime, timezone
from urllib.parse import unquote

from tests.helpers import metadata_bytes  # noqa: F401  (ajusta sys.path)
from models.entities import KNOWN_ENTITIES
from models.query import Filter, QuerySpec
from services.metadata import MetadataError, parse_metadata
from services.odata_client import parse_odata_payload
from services.odata_filters import FilterError, build_query_url, escape_string_literal, format_literal


class ParserTests(unittest.TestCase):
    def test_v4_value(self):
        rows, nxt = parse_odata_payload(b'{"@odata.context":"x","value":[{"Identifier":"A","@odata.etag":"1"}]}')
        self.assertEqual(rows, [{"Identifier": "A"}])
        self.assertIsNone(nxt)

    def test_v2_results_and_next(self):
        rows, nxt = parse_odata_payload(b'{"d":{"results":[{"a":1,"__metadata":{}}],"__next":"http://x/n"}}')
        self.assertEqual(rows, [{"a": 1}])
        self.assertEqual(nxt, "http://x/n")

    def test_empty_value_is_valid(self):
        self.assertEqual(parse_odata_payload(b'{"value":[]}')[0], [])

    def test_null_values_preserved(self):
        rows, _ = parse_odata_payload(b'{"value":[{"WorkOrder":null}]}')
        self.assertIsNone(rows[0]["WorkOrder"])

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_odata_payload(b"<html>Error</html>")

    def test_unexpected_structures(self):
        for raw in (b"[]", b'{"items":[]}', b'{"value":{}}', b'{"value":[1,2]}', b'{"error":{"message":"x"}}',
                    b'{"d":"text"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_odata_payload(raw)


class MetadataTests(unittest.TestCase):
    def test_parse_fixture(self):
        meta = parse_metadata(metadata_bytes())
        self.assertEqual(meta.odata_version, "4")
        self.assertIn("SMT", meta.entity_sets)
        smt = meta.properties_for("SMT")
        self.assertEqual(smt["EventDate"].edm_type, "Edm.DateTimeOffset")
        self.assertEqual(smt["ODataKey"].edm_type, "Edm.Guid")
        cmp = meta.compare_with_expected()
        for ent in KNOWN_ENTITIES:
            self.assertTrue(cmp[ent]["present"])
            self.assertEqual(cmp[ent]["missing"], [])

    def test_v3_detection(self):
        xml = (b'<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">'
               b'<edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
               b'm:DataServiceVersion="3.0"><Schema xmlns="http://schemas.microsoft.com/ado/2009/11/edm" Namespace="N">'
               b'<EntityType Name="SMT"><Property Name="Identifier" Type="Edm.String"/></EntityType>'
               b'<EntityContainer Name="C"><EntitySet Name="SMT" EntityType="N.SMT"/></EntityContainer>'
               b'</Schema></edmx:DataServices></edmx:Edmx>')
        meta = parse_metadata(xml)
        self.assertEqual(meta.odata_version, "3")
        self.assertIn("SMT", meta.compare_with_expected())
        self.assertIn("EventDate", meta.compare_with_expected()["SMT"]["missing"])

    def test_rejects_doctype_and_garbage(self):
        with self.assertRaises(MetadataError):
            parse_metadata(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
        with self.assertRaises(MetadataError):
            parse_metadata(b"not xml")
        with self.assertRaises(MetadataError):
            parse_metadata(b"<root/>")


class FilterTests(unittest.TestCase):
    base = "http://srv:6065/odata/"

    def test_escape_quotes(self):
        self.assertEqual(escape_string_literal("O'Brien"), "'O''Brien'")

    def test_injection_attempt_stays_inside_literal(self):
        evil = "X' or 1 eq 1 or Identifier eq '"
        url = build_query_url(self.base, QuerySpec("SMT", [Filter("Identifier", "eq", evil)]), None, "4")
        decoded = unquote(url.split("$filter=")[1].split("&")[0])
        self.assertEqual(decoded, "Identifier eq 'X'' or 1 eq 1 or Identifier eq '''")
        self.assertNotIn(" ", url)  # todo codificado

    def test_control_chars_and_length(self):
        with self.assertRaises(FilterError):
            escape_string_literal("A\nB")
        with self.assertRaises(FilterError):
            escape_string_literal("A" * 500)

    def test_unauthorized_field_entity_operator(self):
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("SMT", [Filter("Attempts", "eq", 1)]), None, "4")
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("ProductivityOverTime"), None, "4")
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("SMT", [Filter("Identifier", "substringof", "x")]), None, "4")

    def test_field_must_exist_in_metadata(self):
        props = {k: v for k, v in KNOWN_ENTITIES["SMT"].items() if k != "Batch"}
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("SMT", [Filter("Batch", "eq", "B")]), props, "4")

    def test_typed_literals(self):
        dt = datetime(2026, 11, 4, 21, 11, 8, tzinfo=timezone.utc)
        self.assertEqual(format_literal(dt, "Edm.DateTimeOffset", "4"), "2026-11-04T21:11:08Z")
        self.assertEqual(format_literal(dt, "Edm.DateTimeOffset", "3"), "datetimeoffset'2026-11-04T21:11:08Z'")
        g = "29a17d43-6e47-2f1b-0035-08df3a9d40d6"
        self.assertEqual(format_literal(g, "Edm.Guid", "4"), g)
        self.assertEqual(format_literal(g, "Edm.Guid", "2"), f"guid'{g}'")
        with self.assertRaises(FilterError):
            format_literal("not-a-guid' or 1 eq 1", "Edm.Guid", "4")
        with self.assertRaises(FilterError):
            format_literal(datetime(2026, 1, 1), "Edm.DateTimeOffset", "4")  # sin zona horaria

    def test_in_operator_limited(self):
        ids = [f"00000000-0000-4000-8000-{i:012d}" for i in range(11)]
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("QualityHistory", [Filter("DefectID", "in", ids)]), None, "4")
        url = build_query_url(self.base, QuerySpec("QualityHistory", [Filter("DefectID", "in", ids[:2])]), None, "4")
        self.assertIn("%20or%20", url)

    def test_full_url_shape(self):
        url = build_query_url(self.base, QuerySpec("SMT", [Filter("Identifier", "eq", "W07632100028")],
                                                   orderby=[("EventDate", "asc")], top=5), None, "4")
        self.assertTrue(url.startswith("http://srv:6065/odata/SMT?$filter="))
        self.assertIn("$orderby=EventDate%20asc", url)
        self.assertIn("$top=5", url)

    def test_top_bounds(self):
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("SMT", top=0), None, "4")
        with self.assertRaises(FilterError):
            build_query_url(self.base, QuerySpec("SMT", top=5000), None, "4")


if __name__ == "__main__":
    unittest.main()
