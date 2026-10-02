"""Confianza compuesta: relevancia + autoridad + vigencia + respaldo, con topes por conflicto/DEMO.

La similitud textual sola NUNCA produce confianza alta: se ponderan calidad, vigencia y
aprobación de las fuentes. El puntaje se limita a 95 % (no se promete precisión del 100 %).
"""
from __future__ import annotations

from datetime import date

from core.utils import parse_date
from models.domain import ConfidenceResult, ConflictInfo, RetrievedChunk, SourceType


def _freshness(hit: RetrievedChunk, today_: date, review_soon_days: int) -> tuple[float, str]:
    review = parse_date(hit.review_date)
    if review is None:
        return 0.6, "fuente sin fecha de revisión"
    if review < today_:
        return 0.4, "revisión vencida"
    if (review - today_).days <= review_soon_days:
        return 0.85, "revisión próxima"
    return 1.0, ""


def compute_confidence(hits: list[RetrievedChunk], conflicts: list[ConflictInfo], *, min_relevance: float,
                       high: float, medium: float, today_: date, review_soon_days: int = 30) -> ConfidenceResult:
    if not hits or hits[0].relevance < min_relevance:
        return ConfidenceResult(score=0.0, level="None", reasons=["sin evidencia suficiente"])
    top = hits[0]
    try:
        authority = SourceType(top.source_type).authority
    except ValueError:
        authority = 0.5
    freshness, fresh_reason = _freshness(top, today_, review_soon_days)
    supporting_docs = {h.document_id for h in hits[:4] if h.relevance >= min_relevance}
    support = 1.0 if len(supporting_docs) >= 2 else 0.7
    relevance = min(1.0, top.relevance)

    score = 0.5 * relevance + 0.2 * authority + 0.15 * freshness + 0.15 * support
    reasons = []
    if fresh_reason:
        reasons.append(fresh_reason)
    if relevance < 0.6:
        reasons.append("coincidencia parcial con la pregunta")
    level = "High" if score >= high else "Medium" if score >= medium else "Low"
    if top.is_demo and level == "High":
        level = "Medium"
        score = min(score, high - 0.01)  # el porcentaje mostrado debe ser coherente con el nivel
        reasons.append("contenido DEMO (no oficial)")
    if conflicts:
        level = "Low"
        score = min(score, medium - 0.01)
        reasons.append("fuentes aprobadas en conflicto")
    score = min(score, 0.95)
    return ConfidenceResult(score=round(score, 3), level=level, reasons=reasons, components={
        "relevance": round(relevance, 3), "authority": authority, "freshness": freshness, "support": support})
