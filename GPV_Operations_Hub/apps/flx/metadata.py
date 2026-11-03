"""Parser for OData $metadata (EDMX) — OData v2/v3 (CSDL 1.0–3.0) and v4 (CSDL 4.0).

Everything returned here comes from the XML document: entity sets, entity types (with
inheritance resolved), keys, properties, navigation properties (v4 directly; v2/v3 through
Associations), function/action imports with their parameters, enum/complex types and the
capability annotations the service declares (Org.OData.Capabilities.V1). Nothing is assumed.
"""
import hashlib
import xml.etree.ElementTree as ET

MAX_METADATA_BYTES = 50 * 1024 * 1024
M_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
CAP = "Org.OData.Capabilities.V1."


class MetadataError(Exception):
    pass


def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _children(el, name):
    return [c for c in el if _tag(c) == name]


def _bool(v, default=None):
    if v is None:
        return default
    return str(v).strip().lower() == "true"


def _annotations(el):
    """Capability annotations declared inline: {"TopSupported": False, "CountRestrictions.Countable": True, ...}."""
    out = {}
    for a in _children(el, "Annotation"):
        term = a.attrib.get("Term", "")
        short = term.split("Capabilities.V1.", 1)[-1] if "Capabilities.V1." in term else None
        if short is None:
            continue
        if "Bool" in a.attrib:
            out[short] = _bool(a.attrib["Bool"])
        for rec in a.iter():
            if _tag(rec) == "PropertyValue":
                prop = rec.attrib.get("Property", "")
                if "Bool" in rec.attrib:
                    out[f"{short}.{prop}"] = _bool(rec.attrib["Bool"])
                else:
                    vals = [x.text for x in rec.iter() if _tag(x) in ("PropertyPath", "String") and x.text]
                    if vals:
                        out[f"{short}.{prop}"] = vals
    return out


def parse(xml_bytes):
    if len(xml_bytes) > MAX_METADATA_BYTES:
        raise MetadataError("El documento $metadata excede el tamaño máximo permitido.")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise MetadataError(f"$metadata no es XML válido: {e}")
    if _tag(root) != "Edmx":
        raise MetadataError("El documento no es un EDMX ($metadata).")
    edmx_version = root.attrib.get("Version", "")
    odata_version = edmx_version
    for ds in root.iter():
        if _tag(ds) == "DataServices":
            odata_version = ds.attrib.get(f"{{{M_NS}}}DataServiceVersion") or (edmx_version if edmx_version.startswith("4") else odata_version)
    major = 4 if edmx_version.startswith("4") else 2
    types, complex_types, enums, assocs, functions, actions = {}, {}, {}, {}, {}, {}
    containers = []
    aliases = {}
    target_annotations = {}
    for schema in [e for e in root.iter() if _tag(e) == "Schema"]:
        ns = schema.attrib.get("Namespace", "")
        if schema.attrib.get("Alias"):
            aliases[schema.attrib["Alias"]] = ns
        for el in schema:
            t = _tag(el)
            name = el.attrib.get("Name", "")
            full = f"{ns}.{name}"
            if t == "EntityType":
                props = {}
                for p in _children(el, "Property"):
                    props[p.attrib["Name"]] = {"type": p.attrib.get("Type", ""), "nullable": _bool(p.attrib.get("Nullable"), True),
                                               "max_length": p.attrib.get("MaxLength")}
                navs = {}
                for n in _children(el, "NavigationProperty"):
                    if major == 4:
                        nt = n.attrib.get("Type", "")
                        navs[n.attrib["Name"]] = {"target": nt[11:-1] if nt.startswith("Collection(") else nt,
                                                  "collection": nt.startswith("Collection("), "partner": n.attrib.get("Partner")}
                    else:
                        navs[n.attrib["Name"]] = {"relationship": n.attrib.get("Relationship"), "from": n.attrib.get("FromRole"),
                                                  "to": n.attrib.get("ToRole")}
                keys = [r.attrib["Name"] for k in _children(el, "Key") for r in _children(k, "PropertyRef")]
                types[full] = {"name": name, "base": el.attrib.get("BaseType"), "abstract": _bool(el.attrib.get("Abstract"), False),
                               "keys": keys, "properties": props, "navigation": navs}
            elif t == "ComplexType":
                complex_types[full] = {p.attrib["Name"]: p.attrib.get("Type", "") for p in _children(el, "Property")}
            elif t == "EnumType":
                enums[full] = [m.attrib.get("Name") for m in _children(el, "Member")]
            elif t == "Association":
                assocs[full] = {e.attrib.get("Role"): {"type": e.attrib.get("Type"), "multiplicity": e.attrib.get("Multiplicity")}
                                for e in _children(el, "End")}
            elif t in ("Function", "Action"):
                (functions if t == "Function" else actions).setdefault(full, []).append({
                    "bound": _bool(el.attrib.get("IsBound"), False),
                    "parameters": [{"name": p.attrib.get("Name"), "type": p.attrib.get("Type"), "nullable": _bool(p.attrib.get("Nullable"), True)}
                                   for p in _children(el, "Parameter")],
                    "returns": next((r.attrib.get("Type") for r in _children(el, "ReturnType")), None)})
            elif t == "EntityContainer":
                containers.append((ns, el))
            elif t == "Annotations":
                target_annotations.setdefault(el.attrib.get("Target", ""), {}).update(_annotations(el))

    def resolve(tname):
        for a, n in aliases.items():
            if tname.startswith(a + "."):
                tname = n + tname[len(a):]
        return tname

    def flat(tname, seen=()):
        t = types.get(resolve(tname))
        if t is None or tname in seen:
            return {"keys": [], "properties": {}, "navigation": {}}
        if t["base"]:
            b = flat(t["base"], seen + (tname,))
            return {"keys": t["keys"] or b["keys"], "properties": {**b["properties"], **t["properties"]},
                    "navigation": {**b["navigation"], **t["navigation"]}}
        return {"keys": t["keys"], "properties": dict(t["properties"]), "navigation": dict(t["navigation"])}

    entity_sets, imports = {}, []
    for ns, c in containers:
        cname = c.attrib.get("Name", "")
        for es in _children(c, "EntitySet"):
            name = es.attrib["Name"]
            et = resolve(es.attrib.get("EntityType", ""))
            info = flat(et)
            navs = {}
            for nname, n in info["navigation"].items():
                if major == 4:
                    navs[nname] = {"target_type": n["target"], "collection": n["collection"]}
                else:
                    a = assocs.get(resolve(n.get("relationship") or ""), {})
                    end = a.get(n.get("to"), {})
                    navs[nname] = {"target_type": end.get("type"), "collection": end.get("multiplicity") == "*"}
            bindings = {b.attrib.get("Path"): b.attrib.get("Target") for b in _children(es, "NavigationPropertyBinding")}
            for nname, tgt in bindings.items():
                if nname in navs:
                    navs[nname]["target_set"] = tgt
            caps = {}
            for target in (f"{ns}.{cname}/{name}", f"{cname}/{name}"):
                caps.update(target_annotations.get(target, {}))
            caps.update(_annotations(es))
            entity_sets[name] = {"entity_type": et, "keys": info["keys"], "properties": info["properties"], "navigation": navs,
                                 "declared_capabilities": caps}
        for fi in _children(c, "FunctionImport"):
            if major == 4:
                ref = resolve(fi.attrib.get("Function", ""))
                overloads = functions.get(ref, [{}])
                imports.append({"name": fi.attrib.get("Name"), "kind": "function", "http_method": "GET", "entity_set": fi.attrib.get("EntitySet"),
                                "parameters": overloads[0].get("parameters", []), "returns": overloads[0].get("returns"), "definition": ref})
            else:
                imports.append({"name": fi.attrib.get("Name"), "kind": "function", "entity_set": fi.attrib.get("EntitySet"),
                                "http_method": fi.attrib.get(f"{{{M_NS}}}HttpMethod") or "GET (no declarado)",
                                "parameters": [{"name": p.attrib.get("Name"), "type": p.attrib.get("Type"), "mode": p.attrib.get("Mode")}
                                               for p in _children(fi, "Parameter")],
                                "returns": fi.attrib.get("ReturnType")})
        for ai in _children(c, "ActionImport"):
            ref = resolve(ai.attrib.get("Action", ""))
            overloads = actions.get(ref, [{}])
            imports.append({"name": ai.attrib.get("Name"), "kind": "action", "http_method": "POST", "entity_set": ai.attrib.get("EntitySet"),
                            "parameters": overloads[0].get("parameters", []), "returns": overloads[0].get("returns"), "definition": ref})
    return {"edmx_version": edmx_version, "odata_version": odata_version or ("4.0" if major == 4 else ""), "major": major,
            "entity_sets": entity_sets, "function_imports": imports, "complex_types": complex_types, "enum_types": enums,
            "entity_type_count": len(types), "sha256": hashlib.sha256(xml_bytes).hexdigest(), "size": len(xml_bytes)}
