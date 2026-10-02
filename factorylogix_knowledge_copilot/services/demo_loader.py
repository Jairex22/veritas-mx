"""Carga de datos DEMO claramente identificados (is_demo=1, prefijo DEMO-)."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import yaml

from core.logging_setup import get_logger
from core.utils import today
from models.domain import SYSTEM_USER
from schemas.validation import DocumentMetadataInput
from services.knowledge_service import KnowledgeService

log = get_logger("demo")

DEMO_AUTHOR = replace(SYSTEM_USER, id="demo-author", username="demo.loader", display_name="Cargador DEMO")
DEMO_APPROVER = replace(SYSTEM_USER, id="demo-approver", username="demo.approver", display_name="Aprobador DEMO")


def load_demo(knowledge: KnowledgeService, demo_dir: Path) -> dict[str, int]:
    manifest_path = demo_dir.parent / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    stats = {"loaded": 0, "skipped": 0, "failed": 0}
    start = today()
    for item in manifest.get("documents", []):
        if knowledge.docs.get_by_code(item["doc_code"]):
            stats["skipped"] += 1
            continue
        path = demo_dir / item["file"]
        try:
            target = item.get("target", "published")
            effective = start - timedelta(days=60)
            meta = DocumentMetadataInput(
                doc_code=item["doc_code"], title=item["title"], description=item["description"],
                source_type=item["source_type"], owner=f"DEMO Owner {item['area']}", approver="DEMO Aprobador",
                area=item["area"], fl_module=item["fl_module"], classification=item["classification"],
                retention_policy="demo", tags=item.get("tags", ""), language=item.get("language", "es"),
                effective_date=effective.isoformat(), review_date=(start + timedelta(days=180)).isoformat(),
                change_note="Carga inicial DEMO")
            report = knowledge.ingest_file(DEMO_AUTHOR, path.name, path.read_bytes(), meta, is_demo=True)
            if target in {"published", "expired", "under_review"}:
                knowledge.submit_for_review(DEMO_AUTHOR, report.version_id)
            if target in {"published", "expired"}:
                knowledge.approve(DEMO_APPROVER, report.version_id, "Aprobación DEMO",
                                  acknowledge_injection=bool(report.injection_matches))
                knowledge.publish(DEMO_APPROVER, report.version_id, "Publicación DEMO", skip_checks=True)
            if target == "expired":
                knowledge.update_version_dates(DEMO_APPROVER, report.version_id,
                                               (start - timedelta(days=400)).isoformat(),
                                               (start - timedelta(days=100)).isoformat(),
                                               (start - timedelta(days=30)).isoformat(),
                                               "DEMO: documento vencido de ejemplo")
            stats["loaded"] += 1
        except Exception as exc:  # noqa: BLE001 - un documento DEMO defectuoso no debe impedir el arranque
            log.error("demo load failed doc=%s error=%s", item.get("doc_code"), type(exc).__name__)
            stats["failed"] += 1
    knowledge.run_lifecycle(DEMO_APPROVER)
    return stats
