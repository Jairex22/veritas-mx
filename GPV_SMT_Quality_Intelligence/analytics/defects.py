"""Agrupación de defectos por DefectID.

Reglas:
- Un defecto = un DefectID único. Las filas de QualityHistory nunca se cuentan como defectos.
- Closed no significa PASS. Un resultado vacío tampoco.
- Estados históricos no estándar (p. ej. "False") se conservan sin interpretar.
"""
from __future__ import annotations

from services.timeparse import parse_odata_datetime, sort_key

KNOWN_HISTORY_STATUSES = {"open", "closed"}


def _key(defect_id) -> str:
    return (defect_id or "").strip().lower()


def group_defects(quality_rows: list[dict], history_rows: list[dict], history_available: bool) -> list[dict]:
    by_id: dict[str, dict] = {}
    for r in quality_rows:
        k = _key(r.get("DefectID"))
        if not k:
            k = f"sin-id:{len(by_id)}"
        entry = by_id.setdefault(k, {"defect_id": r.get("DefectID"), "quality_rows": 0, "record": r})
        entry["quality_rows"] += 1
    hist: dict[str, list[dict]] = {}
    for h in history_rows:
        hist.setdefault(_key(h.get("DefectID")), []).append(h)

    out = []
    for k, e in by_id.items():
        r = e["record"]
        entries = sorted(hist.get(k, []), key=lambda h: sort_key(parse_odata_datetime(h.get("DefectHistoryTime"))))
        status = (r.get("DefectStatus") or "").strip()
        closed_entries = [h for h in entries if str(h.get("DefectHistoryStatus")).lower() == "closed"]
        uninterpreted = sorted({str(h.get("DefectHistoryStatus")) for h in entries
                                if str(h.get("DefectHistoryStatus")).lower() not in KNOWN_HISTORY_STATUSES})
        created = parse_odata_datetime(r.get("DateCreated"))
        if created is None and entries:
            created = parse_odata_datetime(entries[0].get("DefectHistoryTime"))
        closed_at = parse_odata_datetime(closed_entries[-1].get("DefectHistoryTime")) if closed_entries else None
        ttc = None
        if created and closed_at and created.tzinfo and closed_at.tzinfo and closed_at >= created:
            ttc = round((closed_at - created).total_seconds() / 60, 2)

        notes = []
        if status.lower() == "open":
            classification = "ACTIVE"
        elif status.lower() == "closed":
            classification = "CLOSED"
            if history_available and not closed_entries:
                classification = "HISTORY_INCOMPLETE"
                notes.append("Estado Closed sin registro histórico de cierre")
        else:
            classification = "UNKNOWN_STATUS"
            notes.append(f"Estado de defecto no reconocido: {status or '(vacío)'}")
        if not history_available:
            notes.append("QualityHistory no disponible: historial no verificable")
            if classification == "CLOSED":
                classification = "HISTORY_INCOMPLETE"
        if uninterpreted:
            notes.append("Estados históricos no interpretados: " + ", ".join(uninterpreted))
        if e["quality_rows"] > 1:
            notes.append(f"{e['quality_rows']} filas de Quality para el mismo DefectID (contado una vez)")

        last = closed_entries[-1] if closed_entries else (entries[-1] if entries else {})
        out.append({
            "defect_id": e["defect_id"],
            "status": status or None,
            "classification": classification,
            "description": r.get("AegisInspectionCodeName") or r.get("SymptomDescription"),
            "category": r.get("AegisCategoryName") or r.get("SymptomCategory"),
            "comment": r.get("DefectComment"),
            "reference": r.get("DefectReference"),
            "part_number": r.get("DefectPartNumber"),
            "source_operation": r.get("SourceOperation"),
            "current_operation": r.get("CurrentOperation"),
            "inspection_workstation": r.get("InspectionWorkstation"),
            "line_registered": r.get("Line"),
            "identifier": r.get("Identifier"),
            "assembly": r.get("Assembly"),
            "batch": r.get("BatchName"),
            "lot": r.get("Lot"),
            "date_created": r.get("DateCreated"),
            "closed_at": closed_entries[-1].get("DefectHistoryTime") if closed_entries else None,
            "closed_operation": last.get("DefectHistoryOperation") if closed_entries else None,
            "closed_workstation": last.get("DefectHistoryWorkstation") if closed_entries else None,
            "closed_operator": last.get("DefectHistoryOperator") if closed_entries else None,
            "time_to_close_min": ttc,
            "history_entries": len(entries),
            "history": entries,
            "notes": notes,
        })
    out.sort(key=lambda d: sort_key(parse_odata_datetime(d["date_created"])))
    return out


def summarize_defects(defects: list[dict]) -> dict:
    def count_by(field: str) -> list[dict]:
        acc: dict[str, int] = {}
        for d in defects:
            key = d.get(field) or "(no registrado)"
            acc[key] = acc.get(key, 0) + 1
        return [{"key": k, "count": v} for k, v in sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))]

    ttcs = [d["time_to_close_min"] for d in defects if d["time_to_close_min"] is not None]
    return {
        "unique_defects": len(defects),
        "active": sum(1 for d in defects if d["classification"] == "ACTIVE"),
        "closed": sum(1 for d in defects if d["classification"] == "CLOSED"),
        "history_incomplete": sum(1 for d in defects if d["classification"] == "HISTORY_INCOMPLETE"),
        "unknown_status": sum(1 for d in defects if d["classification"] == "UNKNOWN_STATUS"),
        "by_status": count_by("status"),
        "by_assembly": count_by("assembly"),
        "by_batch": count_by("batch"),
        "by_operation": count_by("source_operation"),
        "by_line": count_by("line_registered"),
        "by_reference": count_by("reference"),
        "by_category": count_by("category"),
        "by_description": count_by("description"),
        "avg_time_to_close_min": round(sum(ttcs) / len(ttcs), 2) if ttcs else None,
        "time_to_close_samples": len(ttcs),
    }
