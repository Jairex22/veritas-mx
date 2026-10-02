"""Composición de la aplicación (inyección de dependencias). Independiente de la interfaz."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import yaml

from connectors.odata import ODataConnector, XTendConnector
from core.config import Settings, load_settings
from core.logging_setup import get_logger, setup_logging
from core.utils import now_iso
from database.connection import Database
from models.domain import SYSTEM_USER
from rag.embeddings import build_embedder
from rag.engine import RagConfig, RagEngine
from rag.llm import build_llm
from rag.query import Glossary
from rag.retriever import HybridRetriever
from repositories.audit import AuditRepository
from repositories.chunks import ChunkRepository
from repositories.documents import DocumentRepository
from repositories.operations import (ErrorRepository, EvaluationRepository, FeedbackRepository, IncidentRepository,
                                     QARepository, QueryLogRepository, SettingsRepository)
from repositories.users import UserRepository
from security.auth import AuthService
from security.injection import InjectionDetector
from security.rbac import AccessPolicy
from sentiment.analyzer import SentimentAnalyzer
from services.analytics_service import AnalyticsService
from services.audit_helper import Auditor
from services.backup_service import BackupService
from services.chat_service import ChatService
from services.connector_service import ConnectorService
from services.demo_loader import load_demo
from services.evaluation_service import EvaluationService
from services.feedback_service import FeedbackService
from services.health_service import HealthService
from services.incident_service import EmailNotifier, IncidentService
from services.knowledge_service import KnowledgeService
from services.settings_service import SettingsService
from services.user_service import UserService

log = get_logger("container")


@dataclass
class Container:
    settings: Settings
    db: Database
    audit_repo: AuditRepository
    auditor: Auditor
    policy: AccessPolicy
    auth: AuthService
    users: UserService
    settings_service: SettingsService
    knowledge: KnowledgeService
    chat: ChatService
    feedback: FeedbackService
    incidents: IncidentService
    analytics: AnalyticsService
    evaluation: EvaluationService
    connectors: ConnectorService
    health: HealthService
    engine: RagEngine
    retriever: HybridRetriever
    sentiment: SentimentAnalyzer
    errors: ErrorRepository
    backup: BackupService
    startup_warnings: list[str] = field(default_factory=list)
    bootstrap_password: str | None = None

    def apply_runtime(self) -> None:
        """Aplica cambios de configuración realizados desde la interfaz sin reiniciar."""
        s = self.settings
        self.engine.config = rag_config_from(s)
        llm, warnings = build_llm(s.get("llm.provider", "none"), s.get("llm.base_url", ""), s.get("llm.model", ""),
                                  float(s.get("llm.timeout_seconds", 60)), float(s.get("llm.temperature", 0.1)),
                                  int(s.get("llm.max_tokens", 700)))
        self.engine.llm = llm
        self.health.llm = llm
        self.startup_warnings.extend(w for w in warnings if w not in self.startup_warnings)
        self.retriever.top_k = int(s.get("rag.top_k", 6))
        self.sentiment.enabled = bool(s.get("sentiment.enabled", True))
        self.auth.idle = timedelta(minutes=int(s.get("security.session_idle_minutes", 30)))


def rag_config_from(s: Settings) -> RagConfig:
    return RagConfig(min_relevance=float(s.get("rag.min_relevance", 0.4)),
                     high_confidence=float(s.get("rag.high_confidence", 0.75)),
                     medium_confidence=float(s.get("rag.medium_confidence", 0.55)),
                     review_soon_days=int(s.get("rag.review_soon_days", 30)),
                     min_grounding=float(s.get("llm.min_grounding", 0.6)))


def _load_entities(root: Path) -> dict:
    path = root / "config" / "odata_entities.yaml"
    if not path.is_file():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("entities", {})


def build_container(settings: Settings | None = None, *, bootstrap: bool = True) -> Container:
    settings = settings or load_settings()
    settings.ensure_dirs()
    setup_logging(settings.path("paths.logs_dir"))
    db = Database(settings.path("paths.database"))
    db.init_schema()

    audit_repo = AuditRepository(db)
    auditor = Auditor(audit_repo)
    settings_service = SettingsService(settings, SettingsRepository(db), auditor)  # aplica overrides guardados
    policy = AccessPolicy(settings.get("access_matrix"))
    user_repo = UserRepository(db)
    auth = AuthService(user_repo, audit_repo, policy,
                       max_failed=int(settings.get("security.max_failed_logins", 5)),
                       lockout_minutes=int(settings.get("security.lockout_minutes", 15)),
                       login_rate_per_minute=int(settings.get("security.login_rate_limit_per_minute", 10)),
                       password_min_length=int(settings.get("security.password_min_length", 12)),
                       idle_minutes=int(settings.get("security.session_idle_minutes", 30)))

    warnings: list[str] = []
    embedder, w = build_embedder(settings.get("rag.embedding_provider", "hashing"),
                                 settings.path("rag.embedding_model_dir"), int(settings.get("rag.embedding_dim", 768)))
    warnings += w
    glossary = Glossary(settings.rules.get("glossary", []))
    detector = InjectionDetector(settings.rules.get("injection_patterns", []))
    docs = DocumentRepository(db)
    chunks = ChunkRepository(db)
    retriever = HybridRetriever(chunks, embedder, glossary, top_k=int(settings.get("rag.top_k", 6)),
                                candidate_pool=int(settings.get("rag.candidate_pool", 40)),
                                rrf_k=int(settings.get("rag.rrf_k", 60)), rerank=bool(settings.get("rag.rerank", True)))
    llm, w = build_llm(settings.get("llm.provider", "none"), settings.get("llm.base_url", ""),
                       settings.get("llm.model", ""), float(settings.get("llm.timeout_seconds", 60)),
                       float(settings.get("llm.temperature", 0.1)), int(settings.get("llm.max_tokens", 700)))
    warnings += w
    errors = ErrorRepository(db)
    query_log = QueryLogRepository(db)
    sentiment = SentimentAnalyzer(settings.rules.get("sentiment", {}), bool(settings.get("sentiment.enabled", True)))

    engine = RagEngine(retriever, detector, llm, rag_config_from(settings))

    knowledge = KnowledgeService(settings, docs, chunks, auditor, embedder, retriever, detector, QARepository(db))
    chat = ChatService(settings, engine, sentiment, query_log, errors, auditor)
    feedback = FeedbackService(FeedbackRepository(db), query_log, knowledge, auditor)
    incidents = IncidentService(settings, IncidentRepository(db), auditor, EmailNotifier(settings))
    analytics = AnalyticsService(db, docs, chunks, int(settings.get("rag.review_soon_days", 30)))
    odata_cfg = settings.get("connectors.odata", {}) or {}
    odata = ODataConnector(
        enabled=bool(odata_cfg.get("enabled", False)), base_url=odata_cfg.get("base_url", ""),
        entities=_load_entities(settings.root), allowed_hosts=odata_cfg.get("allowed_hosts", []),
        timeout=float(odata_cfg.get("timeout_seconds", 10)), max_retries=int(odata_cfg.get("max_retries", 2)),
        backoff=float(odata_cfg.get("backoff_seconds", 1.0)),
        failure_threshold=int(odata_cfg.get("circuit_failure_threshold", 3)),
        reset_seconds=float(odata_cfg.get("circuit_reset_seconds", 60)),
        cache_ttl=float(odata_cfg.get("cache_ttl_seconds", 120)), max_rows=int(odata_cfg.get("max_rows", 200)),
        verify_tls=bool(odata_cfg.get("verify_tls", True)), token=settings.secret("FLKC_ODATA_TOKEN"),
        username=settings.secret("FLKC_ODATA_USERNAME"), password=settings.secret("FLKC_ODATA_PASSWORD"))
    connectors = ConnectorService(odata, XTendConnector(), auditor)
    health = HealthService(settings, db, chunks, audit_repo, embedder, llm, connectors, warnings)
    evaluation = EvaluationService(settings, engine, EvaluationRepository(db), auditor, policy)
    users = UserService(settings, user_repo, auditor)

    container = Container(settings=settings, db=db, audit_repo=audit_repo, auditor=auditor, policy=policy, auth=auth,
                          users=users, settings_service=settings_service, knowledge=knowledge, chat=chat,
                          feedback=feedback, incidents=incidents, analytics=analytics, evaluation=evaluation,
                          connectors=connectors, health=health, engine=engine, retriever=retriever,
                          sentiment=sentiment, errors=errors, backup=BackupService(settings, auditor),
                          startup_warnings=warnings)
    if bootstrap:
        _bootstrap(container)
    return container


def _bootstrap(c: Container) -> None:
    c.bootstrap_password = c.users.ensure_initial_admin()
    demo_env = str(c.settings.get("app.environment", "DEMO")).upper() == "DEMO"
    if demo_env and c.settings.get("demo.create_demo_users", False):
        c.users.ensure_demo_users()
    if demo_env and c.settings.get("demo.load_demo_data", False) and not c.knowledge.docs.catalog(True):
        stats = load_demo(c.knowledge, c.settings.path("paths.demo_dir"))
        log.info("demo data loaded %s", stats)
        if stats["failed"]:
            c.startup_warnings.append(f"{stats['failed']} documentos DEMO no se pudieron cargar (ver logs).")
    c.knowledge.run_lifecycle(SYSTEM_USER)
    QueryLogRepository(c.db).purge_expired_sentiment(now_iso())
