"""Metadata processing and field detection (requirements 1, 2)."""
import unittest

from _support import SAMPLE_METADATA, TempDirMixin  # noqa: F401  (sets sys.path)
from metadata_inspector import (MetadataError, availability_report, best_guess_mapping, load_saved_schema,
                                parse_metadata, save_schema, suggest_roles, validate_mapping)

V2_METADATA = b"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
 <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" m:DataServiceVersion="2.0">
  <Schema Namespace="Legacy" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
   <EntityType Name="Base"><Key><PropertyRef Name="Id"/></Key><Property Name="Id" Type="Edm.Int32" Nullable="false"/></EntityType>
   <EntityType Name="Prod" BaseType="Legacy.Base">
     <Property Name="StartTime" Type="Edm.DateTime"/>
     <Property Name="Qty" Type="Edm.Decimal"/>
   </EntityType>
   <EntityContainer Name="C" m:IsDefaultEntityContainer="true">
     <EntitySet Name="ProductivityOverTime" EntityType="Legacy.Prod"/>
   </EntityContainer>
  </Schema>
 </edmx:DataServices>
</edmx:Edmx>"""

NO_SET = SAMPLE_METADATA.replace(b'EntitySet Name="ProductivityOverTime"', b'EntitySet Name="SomethingElse"')


class MetadataParsingTests(TempDirMixin, unittest.TestCase):
    def test_v4_entity_set_and_properties(self):
        schema = parse_metadata(SAMPLE_METADATA)
        self.assertEqual(schema.entity_set, "ProductivityOverTime")
        self.assertEqual(schema.entity_type, "Demo.Simulated.SimulatedProductivityRecord")  # alias resolved
        self.assertEqual(schema.odata_version, "4.0")
        self.assertEqual(schema.keys, ["RecordId"])
        self.assertIn("GoodCount", schema.property_names)
        self.assertEqual(schema.get("IntervalStart").category, "datetime")
        self.assertEqual(schema.get("GoodCount").category, "numeric")
        self.assertFalse(schema.get("RecordId").nullable)
        self.assertEqual(schema.navigation_properties, ["SimulatedDetails"])

    def test_only_productivity_entity_is_read(self):
        schema = parse_metadata(SAMPLE_METADATA)
        self.assertNotIn("DetailId", schema.property_names)  # SimulatedOtherEntity ignored

    def test_capability_annotations_are_announced_only(self):
        caps = parse_metadata(SAMPLE_METADATA).capabilities
        self.assertTrue(caps.top_supported)
        self.assertTrue(caps.filterable)
        self.assertEqual(caps.non_filterable_properties, ["RejectCount"])
        self.assertIsNone(caps.sortable)  # not announced -> None, never assumed

    def test_v2_with_inheritance(self):
        schema = parse_metadata(V2_METADATA)
        self.assertEqual(schema.odata_version, "2.0")
        self.assertEqual(schema.property_names, ["Id", "StartTime", "Qty"])
        self.assertEqual(schema.keys, ["Id"])
        self.assertFalse(schema.capabilities.any_found)

    def test_missing_entity_set(self):
        with self.assertRaises(MetadataError) as ctx:
            parse_metadata(NO_SET)
        self.assertEqual(ctx.exception.code, "ENTITY_SET_NOT_FOUND")

    def test_invalid_and_unsafe_xml(self):
        with self.assertRaises(MetadataError):
            parse_metadata(b"<not-xml")
        with self.assertRaises(MetadataError) as ctx:
            parse_metadata(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>')
        self.assertEqual(ctx.exception.code, "UNSAFE_XML")
        with self.assertRaises(MetadataError):
            parse_metadata(b"<root/>")

    def test_forbidden_entity(self):
        with self.assertRaises(MetadataError):
            parse_metadata(SAMPLE_METADATA, entity_set="SimulatedOtherEntity")

    def test_save_and_load(self):
        schema = parse_metadata(SAMPLE_METADATA)
        save_schema(schema, SAMPLE_METADATA, self.tmp / "meta")
        loaded = load_saved_schema(self.tmp / "meta")
        self.assertEqual(loaded.schema_hash, schema.schema_hash)
        self.assertTrue((self.tmp / "meta" / "metadata_raw.xml").exists())


class FieldDetectionTests(unittest.TestCase):
    def setUp(self):
        self.schema = parse_metadata(SAMPLE_METADATA)

    def test_suggestions_only_use_existing_compatible_fields(self):
        roles = suggest_roles(self.schema)
        names = set(self.schema.property_names)
        for candidates in roles.values():
            self.assertTrue(set(candidates) <= names)
        self.assertEqual(roles["timestamp"][0], "IntervalStart")
        self.assertNotIn("LineName", roles["quantity"])   # strings never offered as quantity

    def test_best_guess(self):
        self.assertEqual(best_guess_mapping(self.schema)["quantity"], "GoodCount")

    def test_missing_role_reported_no_disponible(self):
        schema = parse_metadata(V2_METADATA)
        report = {r["role"]: r for r in availability_report(schema, {})}
        # Only the integer key could technically hold a line id: offered, never auto-selected.
        self.assertEqual(report["line"]["status"], "SIN CONFIRMAR")
        self.assertEqual(report["line"]["candidates"], ["Id"])
        self.assertIsNone(best_guess_mapping(schema)["line"])
        self.assertIsNone(best_guess_mapping(schema)["shift"])
        no_strings = parse_metadata(V2_METADATA.replace(b'Type="Edm.Int32"', b'Type="Edm.Guid"'))
        report = {r["role"]: r for r in availability_report(no_strings, {})}
        self.assertEqual(report["line"]["status"], "NO DISPONIBLE")
        self.assertEqual(report["shift"]["status"], "NO DISPONIBLE")

    def test_validate_mapping_rejects_invented_or_wrong_type(self):
        clean, errors = validate_mapping(self.schema, {"timestamp": "Invented", "quantity": "LineName", "line": "LineName"})
        self.assertIsNone(clean["timestamp"])
        self.assertIsNone(clean["quantity"])
        self.assertEqual(clean["line"], "LineName")
        self.assertEqual(len(errors), 2)

    def test_validate_mapping_rejects_duplicates(self):
        _, errors = validate_mapping(self.schema, {"line": "LineName", "station": "LineName"})
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
