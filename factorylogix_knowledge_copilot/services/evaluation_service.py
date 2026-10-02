"""Evaluación del RAG con preguntas de referencia y pruebas de resiliencia del sistema."""
from __future__ import annotations

import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from connectors.base import (ConnectorAuthError, ConnectorServerError, ConnectorTimeout, ConnectorUnavailable)
from connectors.odata import ODataConnector
from connectors.simulator import SimulatedSession
from core.config import Settings
from core.text import normalize
from core.utils import now_iso
from database.connection import Database
from models.domain import SYSTEM_USER, AuthenticatedUser
from rag.engine import RagEngine
from rag.llm import grounding_score
from rag.retriever import HybridRetriever
from repositories.chunks import ChunkRepository
from repositories.operations import EvaluationRepository
from security.rbac import AccessPolicy, require
from services.audit_helper import Auditor
from services.export_service import html_report, to_csv_bytes


class _FailingLLM:
    name = "simulated-failing-llm"

    def available(self) -> bool:
        return True

    def generate(self, prompt: str, system: str = "") -> str:
        raise ConnectionError("LLM simulado caído")


def _answer_text(answer) -> str:
    """Contenido documental mostrado. En conflicto, solo las oraciones citadas (el resto es mensaje del sistema)."""
    if answer.conflicts:
        return "\n".join(f"{c.sentence_a}\n{c.sentence_b}" for c in answer.conflicts)
    parts = [answer.brief, *answer.steps, *answer.validate, *answer.expected, *answer.stop_when,
             *answer.escalate_when, *answer.warnings]
    return "\n".join(p for p in parts if p)


class EvaluationService:
    def __init__(self, settings: Settings, engine: RagEngine, repo: EvaluationRepository, audit: Auditor,
                 policy: AccessPolicy):
        self.settings = settings
        self.engine = engine
        self.repo = repo
        self.audit = audit
        self.policy = policy

    def load_cases(self) -> list[dict[str, Any]]:
        path = self.settings.root / "config" / "eval_set.yaml"
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("cases", [])

    def run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        clearance = self.policy.clearance_for(case.get("role", "Operator"))
        started = time.perf_counter()
        answer, _ = self.engine.answer(case["question"], "en" if normalize(case["question"]).startswith(
            ("how", "what", "why", "where", "which")) else "es", clearance, use_llm=False)
        latency = (time.perf_counter() - started) * 1000
        cited = [s.doc_code for s in answer.sources]
        expected = case.get("expected_docs", []) or []
        forbidden = case.get("forbidden_docs", []) or []
        expect_answer = case.get("expect_answer", True)
        text = _answer_text(answer)
        faithfulness = grounding_score(text, [s.excerpt for s in answer.sources]) if answer.answered else 1.0
        # Para respuestas extractivas comparamos contra el fragmento completo citado.
        if answer.answered:
            faithfulness = max(faithfulness, grounding_score(
                text, [h["text"] for h in self._chunk_texts([s.chunk_id for s in answer.sources])]))
        leak = [d for d in cited if d in forbidden]
        must_not = [m for m in case.get("must_not_contain", []) if normalize(m) in normalize(text)]
        answered_ok = (expect_answer == "any") or (bool(answer.answered) == bool(expect_answer))
        retrieval_hit = bool(expected) and any(d in cited for d in expected)
        primary_ok = bool(expected) and bool(cited) and cited[0] in expected
        conflict_ok = (not case.get("expect_conflict")) or bool(answer.conflicts)
        hallucination = (expect_answer is False and answer.answered) or (answer.answered and faithfulness < 0.6)
        passed = answered_ok and not leak and not must_not and conflict_ok and not hallucination \
            and (not expected or not expect_answer or retrieval_hit)
        return {"id": case["id"], "category": case.get("category", ""), "role": case.get("role", ""),
                "question": case["question"], "answered": answer.answered, "expected_answer": expect_answer,
                "cited": ", ".join(cited), "expected_docs": ", ".join(expected), "retrieval_hit": retrieval_hit,
                "primary_citation_ok": primary_ok, "faithfulness": round(faithfulness, 3),
                "relevance": round(answer.sources[0].relevance, 3) if answer.sources else 0.0,
                "confidence": answer.confidence.level if answer.confidence else "None",
                "conflict_detected": bool(answer.conflicts), "conflict_ok": conflict_ok,
                "access_leak": ", ".join(leak), "forbidden_text": ", ".join(must_not),
                "hallucination": hallucination, "latency_ms": round(latency, 1), "passed": passed}

    def _chunk_texts(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        repo = self.engine.retriever.chunks
        return [c for c in (repo.get(cid) for cid in chunk_ids) if c]

    def resilience_checks(self) -> list[dict[str, Any]]:
        results = []
        # 1) LLM caído: debe responder en modo extractivo
        failing = RagEngine(self.engine.retriever, self.engine.detector, _FailingLLM(), self.engine.config)
        answer, _ = failing.answer("¿Cómo reviso el estado de una Work Order?", "es",
                                   SYSTEM_USER.clearance, use_llm=True)
        results.append({"check": "Servicio LLM no disponible", "passed": answer.answered and answer.mode == "extractive",
                        "detail": f"answered={answer.answered} mode={answer.mode}"})
        # 2) Índice vacío
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "empty.db")
            db.init_schema()
            empty = HybridRetriever(ChunkRepository(db), self.engine.retriever.embedder, self.engine.retriever.glossary)
            engine = RagEngine(empty, self.engine.detector, self.engine.llm, self.engine.config)
            answer, _ = engine.answer("¿Cómo reviso el estado de una Work Order?", "es", SYSTEM_USER.clearance)
            results.append({"check": "Índice vacío", "passed": not answer.answered,
                            "detail": answer.brief[:90]})
        # 3) Conector OData: sin conexión, 401, 500, timeout (sesiones simuladas, sin red)
        expectations = [("offline", ConnectorUnavailable, "OData sin conexión"), (401, ConnectorAuthError, "HTTP 401"),
                        (500, ConnectorServerError, "HTTP 500"), ("timeout", ConnectorTimeout, "Timeout")]
        for mode, exc_type, label in expectations:
            session = SimulatedSession(mode)
            connector = ODataConnector(enabled=True, base_url="https://fl.demo.local/odata",
                                       entities={"WIP": {"key_fields": ["WorkOrderNumber"], "select": []}},
                                       allowed_hosts=["fl.demo.local"], max_retries=1, backoff=0, session=session,
                                       sleep=lambda _s: None)
            try:
                connector.query("WIP", "WorkOrderNumber", "WO-DEMO-1")
                ok, detail = False, "no lanzó error"
            except exc_type as exc:
                ok, detail = True, f"{exc.user_message} (intentos={session.calls})"
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, type(exc).__name__
            results.append({"check": f"Conector: {label}", "passed": ok and set(session.methods) <= {"GET"},
                            "detail": detail})
        return results

    def run(self, user: AuthenticatedUser, correlation_id: str = "") -> dict[str, Any]:
        require(user, "eval.run")
        started = now_iso()
        details = [self.run_case(case) for case in self.load_cases()]
        resilience = self.resilience_checks()
        summary = self.summarize(details, resilience)
        run_id = self.repo.save(started, user.username, summary, details + [{"resilience": resilience}])
        summary["run_id"] = run_id
        self.audit(user, "eval.run", "evaluation", run_id, "success",
                   details=f"cases={len(details)} passed={summary['cases_passed']}", correlation_id=correlation_id)
        return {"summary": summary, "details": details, "resilience": resilience}

    @staticmethod
    def summarize(details: list[dict[str, Any]], resilience: list[dict[str, Any]]) -> dict[str, Any]:
        def ratio(items, pred):
            items = list(items)
            return round(sum(1 for i in items if pred(i)) / len(items), 3) if items else None

        with_expected = [d for d in details if d["expected_docs"] and d["expected_answer"] is True]
        negatives = [d for d in details if d["expected_answer"] is False]
        answered = [d for d in details if d["answered"]]
        latencies = sorted(d["latency_ms"] for d in details) or [0]
        return {
            "cases": len(details),
            "cases_passed": sum(1 for d in details if d["passed"]),
            "retrieval_hit_rate": ratio(with_expected, lambda d: d["retrieval_hit"]),
            "citation_precision": ratio(with_expected, lambda d: d["primary_citation_ok"]),
            "faithfulness_avg": round(statistics.mean(d["faithfulness"] for d in answered), 3) if answered else None,
            "relevance_avg": round(statistics.mean(d["relevance"] for d in answered), 3) if answered else None,
            "coverage": ratio(with_expected, lambda d: d["answered"]),
            "no_evidence_accuracy": ratio(negatives, lambda d: not d["answered"]),
            "hallucination_rate": ratio(details, lambda d: d["hallucination"]),
            "conflict_detection": ratio([d for d in details if d["category"] == "contradiccion"],
                                        lambda d: d["conflict_detected"]),
            "access_control_leaks": sum(1 for d in details if d["access_leak"]),
            "latency_p50_ms": latencies[len(latencies) // 2],
            "latency_p95_ms": latencies[int(0.95 * (len(latencies) - 1))],
            "resilience_passed": f"{sum(1 for r in resilience if r['passed'])}/{len(resilience)}",
        }

    def history(self, user: AuthenticatedUser) -> list[dict[str, Any]]:
        require(user, "eval.view")
        return self.repo.list()

    def export(self, result: dict[str, Any], reports_dir: Path) -> tuple[Path, Path]:
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_iso().replace(":", "").replace("-", "")[:15]
        csv_path = reports_dir / f"evaluacion_rag_{stamp}.csv"
        csv_path.write_bytes(to_csv_bytes(result["details"]))
        html_path = reports_dir / f"evaluacion_rag_{stamp}.html"
        html_path.write_text(html_report("Evaluación RAG - FactoryLogix Knowledge Copilot",
                                         [("Resumen", result["summary"]), ("Resiliencia", result["resilience"]),
                                          ("Casos", result["details"])],
                                         banner="Resultados sobre datos DEMO. No representan desempeño en producción."),
                             encoding="utf-8")
        return csv_path, html_path

