"""Motor RAG: recuperación -> conflictos -> confianza -> respuesta (extractiva o LLM local verificada)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.logging_setup import get_logger
from core.utils import today
from models.domain import Answer, SearchFilters
from rag.answer_builder import build_extractive
from rag.confidence import compute_confidence
from rag.conflicts import detect_conflicts
from rag.llm import LLMProvider, build_prompt, grounding_score
from rag.query import coverage
from rag.retriever import HybridRetriever, RetrievalResult
from security.injection import InjectionDetector

log = get_logger("rag")

NO_EVIDENCE_ES = ("No encontré información aprobada suficiente para confirmar esta respuesta. "
                  "Consulta a MES, Producto o al supervisor responsable.")
NO_EVIDENCE_EN = ("I could not find enough approved information to confirm this answer. "
                  "Please consult MES, Product Engineering or the responsible supervisor.")


@dataclass
class RagConfig:
    min_relevance: float = 0.40
    high_confidence: float = 0.75
    medium_confidence: float = 0.55
    review_soon_days: int = 30
    min_grounding: float = 0.6


class RagEngine:
    def __init__(self, retriever: HybridRetriever, detector: InjectionDetector, llm: LLMProvider,
                 config: RagConfig):
        self.retriever = retriever
        self.detector = detector
        self.llm = llm
        self.config = config

    def no_evidence(self, answer: Answer) -> Answer:
        answer.answered = False
        answer.brief = NO_EVIDENCE_EN if answer.language == "en" else NO_EVIDENCE_ES
        return answer

    def answer(self, question: str, language: str, clearance: Iterable[str], filters: SearchFilters | None = None,
               include_version_ids: Iterable[str] = (), use_llm: bool = True) -> tuple[Answer, RetrievalResult]:
        answer = Answer(question=question, language=language, answered=False)
        result = self.retriever.retrieve(question, clearance, filters, include_version_ids)
        hits = self._discount_suspicious(result)
        answer.debug = {"eligible_chunks": result.eligible_count, "lexical": result.lexical_count,
                        "vector": result.vector_count,
                        "candidates": [{"doc": h.doc_code, "section": h.section, "relevance": round(h.relevance, 3),
                                        "coverage": round(h.coverage, 3), "cosine": round(h.vector_score, 3),
                                        "final": round(h.final_score, 3)} for h in hits]}
        if result.eligible_count == 0:
            answer.notices.append("El índice no contiene documentos aprobados y vigentes para tu rol.")
        if not hits or hits[0].relevance < self.config.min_relevance:
            answer.confidence = compute_confidence([], [], min_relevance=self.config.min_relevance,
                                                   high=self.config.high_confidence,
                                                   medium=self.config.medium_confidence, today_=today())
            return self.no_evidence(answer), result

        conflicts = detect_conflicts(hits, self.config.min_relevance)
        answer.conflicts = conflicts
        answer.confidence = compute_confidence(hits, conflicts, min_relevance=self.config.min_relevance,
                                               high=self.config.high_confidence,
                                               medium=self.config.medium_confidence, today_=today(),
                                               review_soon_days=self.config.review_soon_days)
        build_extractive(answer, hits, result.query, self.detector, self.config.min_relevance)
        answer.answered = True
        if any(s.is_demo for s in answer.sources):
            answer.notices.append("Fuente DEMO: no es un procedimiento oficial. Debe sustituirse por documentos "
                                  "aprobados de la empresa.")
        if conflicts:
            # No se elige ninguna fuente: se retiran los pasos y se pide escalamiento.
            es = language != "en"
            answer.brief = ("Las fuentes aprobadas se contradicen sobre este tema (ver detalle del conflicto). "
                            "No se muestra un procedimiento hasta que el propietario lo resuelva." if es else
                            "Approved sources contradict each other on this topic (see conflict detail). No procedure "
                            "is shown until the owner resolves it.")
            answer.steps, answer.validate, answer.expected = [], [], []
            answer.stop_when = ["Detente: no actúes con base en ninguna de las fuentes en conflicto." if es else
                                "Stop: do not act on either conflicting source."]
            answer.escalate_when = ["Escala a Producto/MES con las dos fuentes en conflicto." if es else
                                    "Escalate to Product/MES with both conflicting sources."]
            answer.system_inference.append("Contradicción detectada automáticamente entre fuentes aprobadas.")
            answer.notices.append("Se detectaron fuentes aprobadas que se contradicen. No se eligió ninguna: "
                                  "escala a Producto/MES para resolver el conflicto antes de actuar.")

        if use_llm and not conflicts and self.llm.available():
            self._llm_brief(answer, hits)
        return answer, result

    def _discount_suspicious(self, result: RetrievalResult) -> list:
        """La relevancia de fragmentos con instrucciones sospechosas se recalcula sin esas oraciones,
        para que una pregunta maliciosa no "coincida" con el texto inyectado."""
        changed = False
        for hit in result.hits:
            if hit.injection_flag:
                clean, removed = self.detector.strip_suspicious(hit.text)
                if removed:
                    cov = coverage(result.query, f"{hit.title} {hit.section} {clean}")
                    hit.relevance = max(0.0, hit.relevance - 0.65 * (hit.coverage - cov))
                    hit.coverage = cov
                    changed = True
        if changed:
            result.hits.sort(key=lambda h: (-h.relevance, h.priority))
        return result.hits

    def _llm_brief(self, answer: Answer, hits) -> None:
        usable = [h for h in hits if h.relevance >= self.config.min_relevance][:4]
        sources = []
        for h in usable:
            text, _ = self.detector.strip_suspicious(h.text)
            sources.append((f"{h.doc_code} v{h.version_label}", text))
        try:
            generated = self.llm.generate(build_prompt(answer.question, answer.language, sources))
        except Exception as exc:  # noqa: BLE001 - LLM caído: continuar en modo extractivo
            log.warning("LLM no disponible durante la generación: %s", type(exc).__name__)
            answer.notices.append("El LLM local no respondió; se utilizó el modo extractivo.")
            return
        if not generated or "SIN_EVIDENCIA" in generated:
            answer.notices.append("El LLM local no confirmó la respuesta; se muestran extractos de las fuentes.")
            return
        score = grounding_score(generated, [t for _, t in sources])
        answer.debug["grounding"] = round(score, 3)
        if score < self.config.min_grounding or self.detector.scan(generated).flagged:
            answer.notices.append("La redacción del LLM no superó la verificación de fidelidad; se muestra el "
                                  "texto extractivo.")
            return
        answer.brief = generated
        answer.mode = "llm"
        answer.system_inference.append("Resumen redactado por LLM local a partir de las fuentes citadas "
                                       "(verificado por fidelidad léxica).")
