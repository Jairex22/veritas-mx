"""Fusión cronológica de eventos SMT, creación de defectos e historial de calidad."""
from __future__ import annotations

from services.timeparse import parse_odata_datetime, sort_key


def build_timeline(smt_rows: list[dict], quality_rows: list[dict], history_rows: list[dict]) -> list[dict]:
    items = []
    for i, r in enumerate(smt_rows):
        items.append({
            "kind": "SMT_EVENT", "source": "SMT", "ref": f"SMT#{i + 1}",
            "time": r.get("EventDate"), "title": r.get("OperationName") or "(operación sin nombre)",
            "details": {k: r.get(k) for k in ("Batch", "Assembly", "AssemblyRevision", "WorkOrder", "Process",
                                              "Attempts", "Placements") if r.get(k) not in (None, "")},
        })
    seen_defects = set()
    for r in quality_rows:
        did = (r.get("DefectID") or "").lower()
        if did in seen_defects:
            continue
        seen_defects.add(did)
        items.append({
            "kind": "DEFECT_CREATED", "source": "Quality", "ref": f"DEF:{r.get('DefectID')}",
            "time": r.get("DateCreated"),
            "title": f"Defecto registrado: {r.get('AegisInspectionCodeName') or r.get('SymptomDescription') or r.get('DefectComment') or 'sin descripción'}",
            "details": {k: r.get(k) for k in ("DefectID", "DefectStatus", "SourceOperation", "InspectionWorkstation",
                                              "Line", "DefectReference", "DefectComment") if r.get(k) not in (None, "")},
        })
    for i, r in enumerate(history_rows):
        items.append({
            "kind": "DEFECT_HISTORY", "source": "QualityHistory", "ref": f"QH#{i + 1}",
            "time": r.get("DefectHistoryTime"),
            "title": f"Historial de defecto: estado {r.get('DefectHistoryStatus')!s}",
            "details": {k: r.get(k) for k in ("DefectID", "DefectHistoryOperation", "DefectHistoryWorkstation",
                                              "DefectHistoryOperator", "DefectHistoryComment") if r.get(k) not in (None, "")},
        })
    for it in items:
        dt = parse_odata_datetime(it["time"])
        it["_sort"] = sort_key(dt)
        it["time_verified"] = dt is not None and dt.tzinfo is not None
    items.sort(key=lambda x: (x["_sort"], {"SMT_EVENT": 0, "DEFECT_CREATED": 1, "DEFECT_HISTORY": 2}[x["kind"]]))
    for it in items:
        it.pop("_sort")
    return items
