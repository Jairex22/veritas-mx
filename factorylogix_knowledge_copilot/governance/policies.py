"""Reglas de gobierno: vigencia, retención, completitud de metadatos y reportes de calidad de fuentes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from core.utils import parse_date, parse_dt

REQUIRED_METADATA = ["doc_code", "title", "description", "source_type", "owner", "approver", "area",
                     "fl_module", "classification", "retention_policy"]


@dataclass
class GovernanceFinding:
    severity: str  # info | warning | critical
    doc_code: str
    title: str
    issue: str


def missing_metadata(doc: dict[str, Any]) -> list[str]:
    return [f for f in REQUIRED_METADATA if not str(doc.get(f) or "").strip()]


def validity_findings(catalog: list[dict[str, Any]], today_: date, soon_days: int) -> list[GovernanceFinding]:
    findings: list[GovernanceFinding] = []
    for doc in catalog:
        code, title = doc["doc_code"], doc["title"]
        if not doc.get("published_version_id"):
            findings.append(GovernanceFinding("info", code, title, "Sin versión publicada"))
            continue
        if not doc.get("is_active"):
            findings.append(GovernanceFinding("info", code, title, "Documento desactivado"))
        if not str(doc.get("owner") or "").strip():
            findings.append(GovernanceFinding("critical", code, title, "Fuente sin propietario"))
        review = parse_date(doc.get("review_date"))
        expiration = parse_date(doc.get("expiration_date"))
        if review is None:
            findings.append(GovernanceFinding("warning", code, title, "Sin fecha de revisión"))
        elif review < today_:
            findings.append(GovernanceFinding("critical", code, title, f"Revisión vencida desde {review}"))
        elif review <= today_ + timedelta(days=soon_days):
            findings.append(GovernanceFinding("warning", code, title, f"Revisión próxima: {review}"))
        if expiration is not None:
            if expiration <= today_:
                findings.append(GovernanceFinding("critical", code, title, f"Expirado el {expiration}"))
            elif expiration <= today_ + timedelta(days=soon_days):
                findings.append(GovernanceFinding("warning", code, title, f"Expira pronto: {expiration}"))
        missing = missing_metadata(doc)
        if missing:
            findings.append(GovernanceFinding("warning", code, title, "Metadatos incompletos: " + ", ".join(missing)))
    return findings


def retention_actions(versions: list[dict[str, Any]], policies: dict[str, dict[str, int]],
                      today_: date) -> list[dict[str, Any]]:
    """Versiones elegibles para eliminación según la política (requiere autorización humana)."""
    actions = []
    for v in versions:
        if v.get("deleted_at") or v["status"] not in {"Archived", "Rejected", "Expired"}:
            continue
        policy = policies.get(v.get("retention_policy") or "", {})
        delete_after = policy.get("delete_after_days")
        if not delete_after:
            continue
        reference = parse_dt(v.get("archived_at") or v.get("decided_at") or v.get("created_at"))
        if reference and reference.date() + timedelta(days=int(delete_after)) <= today_:
            actions.append({"version_id": v["id"], "doc_code": v["doc_code"], "version": v["version_label"],
                            "status": v["status"], "policy": v.get("retention_policy"),
                            "eligible_since": (reference.date() + timedelta(days=int(delete_after))).isoformat()})
    return actions


def access_matrix_rows(clearance: dict[str, tuple[str, ...]]) -> list[dict[str, str]]:
    levels = ["Public", "Internal", "Confidential", "Restricted"]
    return [{"Rol": role, **{lvl: ("✔" if lvl in allowed else "—") for lvl in levels}}
            for role, allowed in clearance.items()]
