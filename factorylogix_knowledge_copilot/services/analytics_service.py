"""Analítica responsable: métricas agregadas del conocimiento. Sin rankings ni métricas por empleado."""
from __future__ import annotations

from collections import Counter
from typing import Any

from core.text import normalize
from core.utils import today
from database.connection import Database
from governance.policies import validity_findings
from models.domain import AuthenticatedUser
from repositories.chunks import ChunkRepository
from repositories.documents import DocumentRepository
from security.rbac import require

ANALYTICS_NOTICE = ("Las métricas son agregadas y sirven para mejorar la base de conocimiento. No se muestran "
                    "rankings de empleados ni se usan para evaluación laboral.")


class AnalyticsService:
    def __init__(self, db: Database, docs: DocumentRepository, chunks: ChunkRepository, review_soon_days: int):
        self.db = db
        self.docs = docs
        self.chunks = chunks
        self.review_soon_days = review_soon_days

    def summary(self, user: AuthenticatedUser, since: str = "") -> dict[str, Any]:
        require(user, "analytics.view")
        where, params = ("WHERE created_at >= ?", [since]) if since else ("", [])
        rows = self.db.query(f"SELECT answered, latency_ms, conflict, topic, question, created_at, language, mode, "
                             f"confidence_level FROM query_log {where}", params)
        total = len(rows)
        unanswered = [r for r in rows if not r["answered"]]
        latencies = sorted(r["latency_ms"] for r in rows)
        p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0
        feedback = self.db.query("SELECT rating, COUNT(*) AS n FROM feedback GROUP BY rating")
        fb = {r["rating"]: r["n"] for r in feedback}
        topics = Counter(r["topic"] for r in rows if r["topic"]).most_common(10)
        candidates = Counter(" ".join(normalize(r["question"]).split())[:160] for r in unanswered).most_common(15)
        per_day = Counter(r["created_at"][:10] for r in rows)
        catalog = self.docs.catalog()
        findings = validity_findings(catalog, today(), self.review_soon_days)
        doc_usage = self.db.query(
            "SELECT d.doc_code, d.title, COUNT(*) AS uses FROM answer_sources a JOIN documents d ON d.id = a.document_id "
            "WHERE a.rank = 1 GROUP BY d.doc_code, d.title ORDER BY uses DESC LIMIT 10")
        errors = int(self.db.scalar("SELECT COUNT(*) FROM system_errors", default=0))
        published = [c for c in catalog if c.get("published_version_id") and c.get("is_active")]
        return {
            "total_questions": total,
            "unanswered": len(unanswered),
            "coverage": round((total - len(unanswered)) / total, 3) if total else 0.0,
            "avg_latency_ms": int(sum(latencies) / total) if total else 0,
            "p95_latency_ms": p95,
            "conflicts": sum(1 for r in rows if r["conflict"]),
            "feedback_up": fb.get("up", 0),
            "feedback_down": fb.get("down", 0),
            "top_topics": [{"tema": t, "consultas": n} for t, n in topics],
            "top_documents": doc_usage,
            "candidate_questions": [{"pregunta": q, "veces": n} for q, n in candidates],
            "per_day": [{"fecha": d, "consultas": n} for d, n in sorted(per_day.items())],
            "expired_or_overdue": [f.__dict__ for f in findings if f.severity == "critical"],
            "governance_warnings": [f.__dict__ for f in findings if f.severity == "warning"],
            "system_errors": errors,
            "index": {**self.chunks.counts(), "published_documents": len(published), "documents": len(catalog)},
            "by_language": dict(Counter(r["language"] for r in rows)),
            "by_mode": dict(Counter(r["mode"] for r in rows)),
            "confidence_levels": dict(Counter(r["confidence_level"] or "None" for r in rows)),
        }
