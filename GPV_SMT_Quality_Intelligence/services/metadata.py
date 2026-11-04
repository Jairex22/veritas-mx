"""Lectura de $metadata (EDMX/CSDL) de FactoryLogix.

Usa xml.etree con un documento cuyo tamaño ya fue limitado por el cliente.
Se rechazan DOCTYPE/ENTITY para evitar ataques de expansión de entidades XML.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from models.entities import KNOWN_ENTITIES, PropertyInfo


class MetadataError(ValueError):
    pass


@dataclass
class ODataMetadata:
    odata_version: str                       # "4" o "2"/"3"
    entity_sets: dict[str, str]              # EntitySet -> nombre de EntityType
    entity_types: dict[str, dict[str, PropertyInfo]] = field(default_factory=dict)

    def properties_for(self, entity_set: str) -> dict[str, PropertyInfo] | None:
        type_name = self.entity_sets.get(entity_set)
        if type_name is None:
            return None
        return self.entity_types.get(type_name.split(".")[-1])

    def compare_with_expected(self) -> dict[str, dict]:
        """Compara las entidades autorizadas contra lo que publica el servidor."""
        report: dict[str, dict] = {}
        for entity, expected in KNOWN_ENTITIES.items():
            real = self.properties_for(entity)
            if real is None:
                report[entity] = {"present": False, "missing": sorted(expected), "extra": [],
                                  "type_mismatches": []}
                continue
            mismatches = [
                {"property": n, "expected": p.edm_type, "actual": real[n].edm_type}
                for n, p in expected.items() if n in real and real[n].edm_type != p.edm_type
            ]
            report[entity] = {
                "present": True,
                "missing": sorted(set(expected) - set(real)),
                "extra": sorted(set(real) - set(expected)),
                "type_mismatches": mismatches,
                "properties": [{"name": p.name, "type": p.edm_type} for p in real.values()],
            }
        return report


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_metadata(xml_bytes: bytes) -> ODataMetadata:
    head = xml_bytes[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise MetadataError("El documento $metadata contiene DOCTYPE/ENTITY y fue rechazado")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise MetadataError(f"$metadata no es XML válido: {exc}") from exc
    if _local(root.tag) != "Edmx":
        raise MetadataError("El documento no es un EDMX de OData")

    version = root.attrib.get("Version", "")
    if version.startswith("4"):
        odata_version = "4"
    else:
        odata_version = "2"
        for el in root.iter():
            if _local(el.tag) == "DataServices":
                for k, v in el.attrib.items():
                    if k.endswith("DataServiceVersion") and v.startswith("3"):
                        odata_version = "3"

    entity_types: dict[str, dict[str, PropertyInfo]] = {}
    entity_sets: dict[str, str] = {}
    for el in root.iter():
        name = _local(el.tag)
        if name == "EntityType" and "Name" in el.attrib:
            props = {}
            for child in el:
                if _local(child.tag) == "Property" and "Name" in child.attrib:
                    pname = child.attrib["Name"]
                    props[pname] = PropertyInfo(pname, child.attrib.get("Type", "Edm.String"), True)
            entity_types[el.attrib["Name"]] = props
        elif name == "EntitySet" and "Name" in el.attrib:
            entity_sets[el.attrib["Name"]] = el.attrib.get("EntityType", "")
    if not entity_sets:
        raise MetadataError("$metadata no contiene EntitySets")
    return ODataMetadata(odata_version, entity_sets, entity_types)
