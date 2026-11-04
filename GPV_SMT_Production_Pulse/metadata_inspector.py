"""OData ``$metadata`` inspector for the ProductivityOverTime entity set.

Responsibilities:
* Parse EDMX documents (OData V2/V3 ``2007/06`` and V4 OASIS namespaces).
* Locate the ``ProductivityOverTime`` EntitySet and resolve its EntityType
  (including namespace aliases and ``BaseType`` inheritance).
* Extract every declared property with its EDM type, keys and navigation properties.
* Read OData Capabilities annotations (TopSupported, FilterRestrictions, SortRestrictions,
  SelectSupport) and report them as *announced*, never as *tested*.
* Suggest candidate fields for each analytic role (timestamp, quantity, line, station, shift)
  using only properties that exist in the schema; roles without candidates are reported as
  ``NO DISPONIBLE``.
* Persist the validated schema locally (raw XML + JSON summary).

Three evidence levels are kept separate throughout the application:
``declared`` (exists in metadata) / ``announced`` (annotations claim support) /
``tested`` (a limited validation query succeeded, see ``capability_probe``).

Command line usage (no network unless ``--remote`` is given)::

    python metadata_inspector.py --file examples/metadata_sample.xml
    python metadata_inspector.py --remote
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from security import INTEGER_EDM_TYPES, NUMERIC_EDM_TYPES
from settings import ALLOWED_ENTITY_SET, FIELD_ROLES
from timeutil import iso_utc, utc_now

DATETIME_EDM_TYPES = frozenset({"Edm.DateTime", "Edm.DateTimeOffset", "Edm.Date"})

ROLE_LABELS_ES: dict[str, str] = {
    "timestamp": "Fecha / hora del registro",
    "quantity": "Cantidad producida",
    "line": "Línea SMT",
    "station": "Estación",
    "shift": "Turno",
    "project": "Proyecto",
    "work_order": "Orden de trabajo (WO)",
    "product": "Producto / número de parte",
}

# Name fragments used ONLY to rank existing properties as suggestions. They never
# create fields: a role with no matching property is reported as NO DISPONIBLE.
_ROLE_HINTS: dict[str, tuple[str, ...]] = {
    "timestamp": ("start", "time", "date", "period", "interval", "timestamp", "begin"),
    "quantity": ("qty", "quantity", "count", "produced", "output", "units", "boards", "panels",
                 "pass", "good", "total", "assemblies", "pieces"),
    "line": ("line", "linea"),
    "station": ("station", "machine", "workcell", "resource", "equipment", "estacion", "cell"),
    "shift": ("shift", "turno"),
    "project": ("project", "proyecto", "program"),
    "work_order": ("workorder", "work_order", "wonumber", "wo_", "ordennumber", "orden", "order"),
    "product": ("product", "partnumber", "part_number", "assembly", "producto", "sku", "item", "model"),
}


class MetadataError(Exception):
    """Metadata could not be parsed or is incompatible. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PropertyInfo:
    """A property declared in the EntityType."""

    name: str
    edm_type: str
    nullable: bool = True
    is_key: bool = False
    category: str = "other"  # datetime | numeric | string | boolean | other

    @staticmethod
    def categorize(edm_type: str) -> str:
        if edm_type in DATETIME_EDM_TYPES:
            return "datetime"
        if edm_type in NUMERIC_EDM_TYPES:
            return "numeric"
        if edm_type == "Edm.String":
            return "string"
        if edm_type == "Edm.Boolean":
            return "boolean"
        return "other"


@dataclass
class CapabilityAnnotations:
    """Capabilities announced by the service. ``None`` means not announced."""

    top_supported: bool | None = None
    filterable: bool | None = None
    non_filterable_properties: list[str] = field(default_factory=list)
    sortable: bool | None = None
    non_sortable_properties: list[str] = field(default_factory=list)
    select_supported: bool | None = None
    terms_found: list[str] = field(default_factory=list)

    @property
    def any_found(self) -> bool:
        return bool(self.terms_found)


@dataclass
class EntitySchema:
    """Validated schema of the ProductivityOverTime entity set."""

    entity_set: str
    entity_type: str
    odata_version: str
    properties: list[PropertyInfo]
    keys: list[str]
    navigation_properties: list[str]
    capabilities: CapabilityAnnotations
    schema_hash: str
    warnings: list[str] = field(default_factory=list)
    retrieved_at: str = ""
    source: str = ""

    @property
    def property_names(self) -> list[str]:
        return [p.name for p in self.properties]

    def get(self, name: str | None) -> PropertyInfo | None:
        for prop in self.properties:
            if prop.name == name:
                return prop
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntitySchema":
        return cls(
            entity_set=data["entity_set"],
            entity_type=data["entity_type"],
            odata_version=data["odata_version"],
            properties=[PropertyInfo(**p) for p in data["properties"]],
            keys=list(data["keys"]),
            navigation_properties=list(data.get("navigation_properties", [])),
            capabilities=CapabilityAnnotations(**data.get("capabilities", {})),
            schema_hash=data["schema_hash"],
            warnings=list(data.get("warnings", [])),
            retrieved_at=data.get("retrieved_at", ""),
            source=data.get("source", ""),
        )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in element if _local(c.tag) == name]


def _iter(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (e for e in element.iter() if _local(e.tag) == name)


def _bool_attr(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def _detect_version(root: ET.Element) -> str:
    version = root.attrib.get("Version", "")
    if version.startswith("4"):
        return "4.0"
    for ds in _iter(root, "DataServices"):
        for key, val in ds.attrib.items():
            if _local(key) in ("DataServiceVersion", "MaxDataServiceVersion") and val:
                return "3.0" if val.startswith("3") else "2.0"
    return "4.0" if "oasis-open.org" in root.tag else "2.0"


def _annotation_bool(annotation: ET.Element) -> bool | None:
    if "Bool" in annotation.attrib:
        return _bool_attr(annotation.attrib["Bool"], False)
    for child in annotation:
        if _local(child.tag) == "Bool" and child.text:
            return child.text.strip().lower() == "true"
    return None


def _record_values(annotation: ET.Element) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for record in _iter(annotation, "Record"):
        for pv in _children(record, "PropertyValue"):
            prop = pv.attrib.get("Property", "")
            if "Bool" in pv.attrib:
                values[prop] = _bool_attr(pv.attrib["Bool"], False)
                continue
            paths = [p.text.strip() for p in _iter(pv, "PropertyPath") if p.text]
            if paths:
                values[prop] = paths
                continue
            bools = [b for b in pv if _local(b.tag) == "Bool" and b.text]
            if bools:
                values[prop] = bools[0].text.strip().lower() == "true"
        break
    return values


def _apply_annotation(caps: CapabilityAnnotations, annotation: ET.Element) -> None:
    term = annotation.attrib.get("Term", "")
    short = term.rsplit(".", 1)[-1]
    if "Capabilities" not in term:
        return
    caps.terms_found.append(term)
    if short == "TopSupported":
        caps.top_supported = _annotation_bool(annotation)
    elif short == "FilterRestrictions":
        rec = _record_values(annotation)
        if "Filterable" in rec:
            caps.filterable = bool(rec["Filterable"])
        caps.non_filterable_properties = list(rec.get("NonFilterableProperties", []))
    elif short == "SortRestrictions":
        rec = _record_values(annotation)
        if "Sortable" in rec:
            caps.sortable = bool(rec["Sortable"])
        caps.non_sortable_properties = list(rec.get("NonSortableProperties", []))
    elif short == "SelectSupport":
        rec = _record_values(annotation)
        if "Supported" in rec:
            caps.select_supported = bool(rec["Supported"])


def _reject_unsafe_xml(xml_bytes: bytes) -> None:
    head = xml_bytes[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in xml_bytes.upper():
        raise MetadataError("UNSAFE_XML", "El documento de metadata contiene declaraciones DTD/ENTITY no permitidas.")


def parse_metadata(xml_bytes: bytes, entity_set: str = ALLOWED_ENTITY_SET, source: str = "") -> EntitySchema:
    """Parse an EDMX document and return the validated schema of ``entity_set``.

    Raises:
        MetadataError: if the XML is invalid/unsafe or the entity set/type is missing.
    """
    if entity_set != ALLOWED_ENTITY_SET:
        raise MetadataError("FORBIDDEN_ENTITY", "Solo se permite inspeccionar ProductivityOverTime.")
    _reject_unsafe_xml(xml_bytes)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise MetadataError("INVALID_XML", f"La metadata no es XML válido: {exc}") from exc
    if _local(root.tag) != "Edmx":
        raise MetadataError("NOT_EDMX", "El documento recibido no es un EDMX de OData.")

    version = _detect_version(root)
    schemas = list(_iter(root, "Schema"))
    aliases: dict[str, str] = {}
    for schema in schemas:
        ns = schema.attrib.get("Namespace", "")
        if schema.attrib.get("Alias"):
            aliases[schema.attrib["Alias"]] = ns

    def qualify(name: str) -> str:
        if "." in name:
            prefix, _, short = name.rpartition(".")
            return f"{aliases.get(prefix, prefix)}.{short}"
        return name

    entity_types: dict[str, ET.Element] = {}
    for schema in schemas:
        ns = schema.attrib.get("Namespace", "")
        for et in _children(schema, "EntityType"):
            entity_types[f"{ns}.{et.attrib.get('Name', '')}"] = et

    set_element: ET.Element | None = None
    container_name = ""
    for container in _iter(root, "EntityContainer"):
        for es in _children(container, "EntitySet"):
            if es.attrib.get("Name") == entity_set:
                set_element = es
                container_name = container.attrib.get("Name", "")
                break
        if set_element is not None:
            break
    if set_element is None:
        raise MetadataError("ENTITY_SET_NOT_FOUND",
                            f"La metadata no declara el EntitySet {entity_set}.")

    type_name = qualify(set_element.attrib.get("EntityType", ""))
    if type_name not in entity_types:
        raise MetadataError("ENTITY_TYPE_NOT_FOUND",
                            f"No se encontró el EntityType {type_name} declarado por {entity_set}.")

    warnings: list[str] = []
    chain: list[ET.Element] = []
    current: str | None = type_name
    visited: set[str] = set()
    while current:
        if current in visited:
            warnings.append("Herencia circular detectada en BaseType; se detuvo la resolución.")
            break
        visited.add(current)
        element = entity_types.get(current)
        if element is None:
            warnings.append(f"BaseType {current} no encontrado; propiedades heredadas incompletas.")
            break
        chain.append(element)
        base = element.attrib.get("BaseType")
        current = qualify(base) if base else None

    keys: list[str] = []
    properties: list[PropertyInfo] = []
    navigation: list[str] = []
    for element in reversed(chain):  # base type first
        for key in _children(element, "Key"):
            keys.extend(ref.attrib["Name"] for ref in _children(key, "PropertyRef") if ref.attrib.get("Name"))
        for prop in _children(element, "Property"):
            edm_type = prop.attrib.get("Type", "")
            name = prop.attrib.get("Name", "")
            if not name:
                continue
            properties.append(PropertyInfo(
                name=name,
                edm_type=edm_type,
                nullable=_bool_attr(prop.attrib.get("Nullable"), True),
                category=PropertyInfo.categorize(edm_type),
            ))
        navigation.extend(n.attrib.get("Name", "") for n in _children(element, "NavigationProperty"))
    for prop in properties:
        prop.is_key = prop.name in keys
    if not properties:
        raise MetadataError("NO_PROPERTIES", f"El EntityType {type_name} no declara propiedades.")
    if not keys:
        warnings.append("El EntityType no declara clave (Key).")

    caps = CapabilityAnnotations()
    for annotation in _children(set_element, "Annotation"):
        _apply_annotation(caps, annotation)
    for annotations in _iter(root, "Annotations"):
        target = annotations.attrib.get("Target", "")
        if target.endswith(f"/{entity_set}") or target in (entity_set, f"{container_name}/{entity_set}"):
            for annotation in _children(annotations, "Annotation"):
                _apply_annotation(caps, annotation)

    canonical = json.dumps(
        {"set": entity_set, "type": type_name, "version": version,
         "props": [(p.name, p.edm_type, p.nullable) for p in properties], "keys": keys},
        sort_keys=True,
    )
    return EntitySchema(
        entity_set=entity_set,
        entity_type=type_name,
        odata_version=version,
        properties=properties,
        keys=keys,
        navigation_properties=[n for n in navigation if n],
        capabilities=caps,
        schema_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        warnings=warnings,
        retrieved_at=iso_utc(utc_now()),
        source=source,
    )


def role_type_compatible(role: str, prop: PropertyInfo) -> bool:
    """Whether a property's EDM type can serve a role."""
    if role == "timestamp":
        return prop.category == "datetime"
    if role == "quantity":
        return prop.category == "numeric"
    if role in ("line", "station", "shift", "project", "work_order", "product"):
        return prop.edm_type == "Edm.String" or prop.edm_type in INTEGER_EDM_TYPES
    return False


def suggest_roles(schema: EntitySchema) -> dict[str, list[str]]:
    """Rank existing, type-compatible properties for each role.

    Properties whose names match a hint come first; other compatible properties follow
    so an administrator can still choose them. Nothing outside the schema is ever returned.
    """
    suggestions: dict[str, list[str]] = {}
    for role in FIELD_ROLES:
        compatible = [p for p in schema.properties if role_type_compatible(role, p)]
        hints = _ROLE_HINTS[role]

        def score(p: PropertyInfo) -> tuple[int, int]:
            lname = p.name.lower()
            hit = next((i for i, h in enumerate(hints) if h in lname), len(hints))
            return (hit, 0 if not p.is_key else 1)

        ranked = sorted(compatible, key=score)
        suggestions[role] = [p.name for p in ranked]
    return suggestions


def best_guess_mapping(schema: EntitySchema) -> dict[str, str | None]:
    """Name-hint matches only (no fallback to arbitrary fields); a field is used once at most.

    Used as pre-selection in the UI and, when enabled, as an *auto-detected* (unconfirmed)
    mapping that the interface labels as pending confirmation by MES.
    """
    result: dict[str, str | None] = {}
    used: set[str] = set()
    suggestions = suggest_roles(schema)
    for role in FIELD_ROLES:
        hints = _ROLE_HINTS[role]
        match = None
        for name in suggestions[role]:
            if name not in used and any(h in name.lower() for h in hints):
                match = name
                break
        result[role] = match
        if match:
            used.add(match)
    return result


def validate_mapping(schema: EntitySchema, mapping: dict[str, str | None]) -> tuple[dict[str, str | None], list[str]]:
    """Return (clean_mapping, errors). Fields absent from metadata or of wrong type are dropped."""
    clean: dict[str, str | None] = {}
    errors: list[str] = []
    for role in FIELD_ROLES:
        name = mapping.get(role)
        if not name:
            clean[role] = None
            continue
        prop = schema.get(name)
        if prop is None:
            errors.append(f"{ROLE_LABELS_ES[role]}: el campo '{name}' no existe en la metadata.")
            clean[role] = None
        elif not role_type_compatible(role, prop):
            errors.append(f"{ROLE_LABELS_ES[role]}: el campo '{name}' es {prop.edm_type}, tipo no compatible.")
            clean[role] = None
        else:
            clean[role] = name
    used = [v for v in clean.values() if v]
    if len(used) != len(set(used)):
        errors.append("Un mismo campo no puede asignarse a dos funciones distintas.")
    return clean, errors


def availability_report(schema: EntitySchema | None, mapping: dict[str, str | None]) -> list[dict[str, Any]]:
    """Per-role availability: DISPONIBLE (mapped), CANDIDATOS (exist but unconfirmed) or NO DISPONIBLE."""
    rows: list[dict[str, Any]] = []
    suggestions = suggest_roles(schema) if schema else {r: [] for r in FIELD_ROLES}
    for role in FIELD_ROLES:
        mapped = mapping.get(role)
        if mapped and schema and schema.get(mapped):
            status = "DISPONIBLE"
        elif suggestions[role]:
            status = "SIN CONFIRMAR"
        else:
            status = "NO DISPONIBLE"
        rows.append({"role": role, "label": ROLE_LABELS_ES[role], "status": status,
                     "field": mapped, "candidates": suggestions[role]})
    return rows


def save_schema(schema: EntitySchema, raw_xml: bytes, directory: Path) -> Path:
    """Persist raw metadata and the validated JSON summary. Returns the JSON path."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata_raw.xml").write_bytes(raw_xml)
    json_path = directory / "schema_validated.json"
    tmp = json_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(schema.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(json_path)
    return json_path


def load_saved_schema(directory: Path) -> EntitySchema | None:
    path = directory / "schema_validated.json"
    if not path.exists():
        return None
    try:
        return EntitySchema.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def describe(schema: EntitySchema, mapping: dict[str, str | None] | None = None) -> str:
    """Plain-text report for the command line."""
    lines = [
        f"EntitySet : {schema.entity_set}",
        f"EntityType: {schema.entity_type}",
        f"OData     : {schema.odata_version}",
        f"Hash      : {schema.schema_hash}",
        f"Claves    : {', '.join(schema.keys) or '(ninguna)'}",
        "",
        "Propiedades declaradas en metadata:",
    ]
    for p in schema.properties:
        flags = []
        if p.is_key:
            flags.append("clave")
        if not p.nullable:
            flags.append("no nulo")
        lines.append(f"  - {p.name:<32} {p.edm_type:<20} [{p.category}] {' '.join(flags)}")
    if schema.navigation_properties:
        lines.append("Propiedades de navegación (NO se consultan): " + ", ".join(schema.navigation_properties))
    caps = schema.capabilities
    lines.append("")
    lines.append("Capacidades ANUNCIADAS en anotaciones (no comprobadas):")
    if not caps.any_found:
        lines.append("  (sin anotaciones de Capabilities)")
    else:
        lines.append(f"  TopSupported={caps.top_supported} Filterable={caps.filterable} "
                     f"Sortable={caps.sortable} SelectSupported={caps.select_supported}")
        if caps.non_filterable_properties:
            lines.append("  No filtrables: " + ", ".join(caps.non_filterable_properties))
    lines.append("")
    lines.append("Disponibilidad por función:")
    for row in availability_report(schema, mapping or {}):
        cands = ", ".join(row["candidates"][:5]) or "-"
        lines.append(f"  {row['label']:<28} {row['status']:<14} candidatos: {cands}")
    for w in schema.warnings:
        lines.append(f"ADVERTENCIA: {w}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspector de $metadata para ProductivityOverTime")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Archivo EDMX local")
    group.add_argument("--remote", action="store_true", help="Descargar $metadata del servidor configurado (1 solicitud GET)")
    parser.add_argument("--save", action="store_true", help="Guardar el esquema validado en data/metadata")
    args = parser.parse_args(argv)

    from settings import load_config

    config = load_config(overrides={"app": {"mode": "live"}})
    if args.file:
        raw = args.file.read_bytes()
        source = str(args.file.name)
    else:
        from odata_client import build_client

        client = build_client(config)
        result = client.fetch_metadata(session_id="cli")
        if not result.ok or result.body is None:
            print(f"ERROR: {result.message}")
            return 2
        raw = result.body
        source = config.odata.base_url + "$metadata"
    try:
        schema = parse_metadata(raw, source=source)
    except MetadataError as exc:
        print(f"ERROR [{exc.code}]: {exc.message}")
        return 1
    print(describe(schema, config.field_mapping))
    if args.save:
        path = save_schema(schema, raw, config.metadata_dir)
        print(f"\nEsquema guardado en {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
