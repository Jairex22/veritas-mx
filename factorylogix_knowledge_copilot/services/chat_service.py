"""Servicio de chat: políticas, sentimiento, seguridad, RAG, linaje y registro de consultas."""
from __future__ import annotations

import json
import time
from datetime import timedelta

from core.config import Settings
from core.errors import CopilotError, RateLimitExceeded
from core.logging_setup import get_logger, redact
from core.text import detect_language
from core.utils import new_correlation_id, utcnow
from models.domain import Answer, AuthenticatedUser, Classification, SearchFilters, SentimentLabel
from rag.engine import RagEngine
from repositories.operations import ErrorRepository, QueryLogRepository
from security.injection import RuleMatcher
from security.rate_limit import RateLimiter
from security.rbac import require
from security.sanitize import clean_user_text
from sentiment.analyzer import SentimentAnalyzer
from services.audit_helper import Auditor

log = get_logger("chat")

SAFETY_ES = ("SITUACIÓN DE SEGURIDAD: detén la operación, aléjate del riesgo y avisa de inmediato a tu supervisor "
             "y al área de Seguridad/EHS. No intentes continuar el proceso en FactoryLogix hasta que el área "
             "responsable lo autorice.")
SAFETY_EN = ("SAFETY SITUATION: stop the operation, move away from the hazard and immediately notify your supervisor "
             "and Safety/EHS. Do not continue the process in FactoryLogix until the responsible area authorizes it.")
ACTION_ES = ("El asistente NO ejecuta transacciones en FactoryLogix (Proceed, Unproceed, Reroute, cierre de "
             "defectos ni cambios de producción). Solo muestra el procedimiento aprobado; la acción la realiza "
             "personal autorizado.")
ACTION_EN = ("The assistant does NOT execute FactoryLogix transactions (Proceed, Unproceed, Reroute, defect closure or "
             "production changes). It only shows the approved procedure; authorized personnel perform the action.")
INJECTION_ES = "Tu pregunta contiene instrucciones que el sistema ignora por seguridad. Solo se usan fuentes aprobadas."
INJECTION_EN = "Your question contains instructions the system ignores for security. Only approved sources are used."


class ChatService:
    def __init__(self, settings: Settings, engine: RagEngine, sentiment: SentimentAnalyzer, query_log: QueryLogRepository,
                 errors: ErrorRepository, audit: Auditor):
        self.settings = settings
        self.engine = engine
        self.sentiment = sentiment
        self.query_log = query_log
        self.errors = errors
        self.audit = audit
        rules = settings.rules
        self.safety = RuleMatcher(rules.get("safety_patterns", []))
        self.actions = RuleMatcher(rules.get("production_action_patterns", []))
        self.escalation_keywords = RuleMatcher([k for k in rules.get("escalation_keywords", [])])
        self.limiter = RateLimiter(int(settings.get("security.chat_rate_limit_per_minute", 30)), 60)

    def escalation_route(self, language: str) -> str:
        key = "escalation.default_route_en" if language == "en" else "escalation.default_route_es"
        return str(self.settings.get(key, ""))

    def ask(self, user: AuthenticatedUser, question: str, filters: SearchFilters | None = None,
            correlation_id: str = "") -> Answer:
        require(user, "chat.query")
        correlation_id = correlation_id or new_correlation_id()
        started = time.perf_counter()
        if not self.limiter.allow(user.id):
            self.audit(user, "chat.query", "query", "-", "denied", reason="rate limit", correlation_id=correlation_id)
            raise RateLimitExceeded()
        question = clean_user_text(question, int(self.settings.get("security.max_question_chars", 1500)))
        if len(question) < 3:
            raise CopilotError("Escribe una pregunta más completa.")
        language = detect_language(question)
        sentiment = self.sentiment.analyze(question)

        try:
            answer, retrieval = self.engine.answer(question, language, user.clearance, filters,
                                                   use_llm=self.settings.get("llm.provider", "none") != "none")
        except Exception as exc:  # noqa: BLE001 - nunca cerrar la app por un error de RAG
            log.exception("rag failure cid=%s", correlation_id)
            self.errors.record("rag", exc, correlation_id)
            answer = self.engine.no_evidence(Answer(question=question, language=language, answered=False))
            answer.notices.append("Error interno al consultar el índice. Se registró con ID " + correlation_id)
            retrieval = None

        answer.correlation_id = correlation_id
        answer.sentiment = sentiment if sentiment.enabled else None
        answer.escalation_route = self.escalation_route(language)
        es = language != "en"

        if self.safety.find(question):
            answer.safety_stop = True
            answer.warnings.insert(0, SAFETY_ES if es else SAFETY_EN)
            answer.system_inference.append("Se detectaron palabras de riesgo físico: se prioriza detener y escalar.")
        if self.actions.find(question):
            answer.production_action_request = True
            answer.notices.insert(0, ACTION_ES if es else ACTION_EN)
        if self.engine.detector.scan(question).flagged:
            answer.injection_in_question = True
            answer.notices.insert(0, INJECTION_ES if es else INJECTION_EN)
            self.audit(user, "chat.prompt_injection_attempt", "query", "-", "flagged", correlation_id=correlation_id)
        if self.escalation_keywords.find(question) and sentiment.label != SentimentLabel.URGENT.value:
            answer.system_inference.append("La pregunta menciona un impacto operativo: considera escalar.")

        self._audit_classified_access(user, answer, question, filters, correlation_id)
        answer.latency_ms = int((time.perf_counter() - started) * 1000)
        answer.query_id = self._log(user, answer, filters, correlation_id, retrieval)
        log.info("query id=%s answered=%s chars=%d latency_ms=%d", answer.query_id, answer.answered,
                 len(question), answer.latency_ms)
        return answer

    def _audit_classified_access(self, user: AuthenticatedUser, answer: Answer, question: str,
                                 filters: SearchFilters | None, correlation_id: str) -> None:
        restricted = [s for s in answer.sources if s.classification == Classification.RESTRICTED.value]
        if restricted:
            self.audit(user, "rag.restricted_source_access", "document",
                       ",".join(s.doc_code for s in restricted), "success", correlation_id=correlation_id)
        if len(user.clearance) == len(Classification.values()):
            return
        try:
            probe = self.engine.retriever.retrieve(question, Classification.values(), filters, top_k=3)
        except Exception:  # noqa: BLE001 - la sonda de auditoría nunca debe afectar la respuesta
            return
        hidden = [h for h in probe.hits if h.classification not in user.clearance
                  and h.relevance >= self.engine.config.min_relevance]
        if hidden:
            # No se revela nada al usuario: solo queda evidencia para auditoría.
            self.audit(user, "rag.restricted_source_denied", "document", ",".join(h.doc_code for h in hidden[:3]),
                       "denied", reason="clasificación no autorizada para el rol", correlation_id=correlation_id)

    def _log(self, user: AuthenticatedUser, answer: Answer, filters: SearchFilters | None, correlation_id: str,
             retrieval) -> str:
        retention_days = int(self.settings.get("sentiment.retention_days", 30))
        sentiment_label = answer.sentiment.label if answer.sentiment else None
        expires = (utcnow() + timedelta(days=retention_days)).replace(microsecond=0).isoformat() \
            if sentiment_label else None
        topic = ""
        if answer.answered and answer.sources:
            topic = answer.sources[0].section.split(" > ")[-1][:120]
        record = {
            "user_id": user.id, "role": user.role, "correlation_id": correlation_id,
            "question": redact(answer.question)[:1500], "language": answer.language,
            "answered": int(answer.answered),
            "confidence": answer.confidence.score if answer.confidence else None,
            "confidence_level": answer.confidence.level if answer.confidence else None,
            "latency_ms": answer.latency_ms, "mode": answer.mode, "conflict": int(bool(answer.conflicts)),
            "topic": topic, "filters": json.dumps(filters.active() if filters else {}),
            "sentiment_label": sentiment_label, "sentiment_expires_at": expires,
        }
        sources = [{"chunk_id": s.chunk_id, "version_id": s.version_id, "document_id": s.document_id,
                    "rank": i, "score": s.relevance} for i, s in enumerate(answer.sources, start=1)]
        try:
            return self.query_log.insert(record, sources)
        except Exception as exc:  # noqa: BLE001
            self.errors.record("query_log", exc, correlation_id)
            return ""
