"""Evaluación RAG con el conjunto de referencia, en modo FTS5 y en modo de respaldo BM25 (sin FTS5)."""
import pytest

from services.container import build_container
from tests.conftest import make_settings, user_for

CATEGORIES = {"evidencia_es", "ingles", "fuera_de_dominio", "sin_evidencia", "documento_vencido", "contradiccion",
              "fuente_restringida", "prompt_injection", "contenido_en_revision", "usuario_sin_permisos"}


def test_eval_set_covers_required_scenarios(demo_container):
    categories = {case["category"] for case in demo_container.evaluation.load_cases()}
    assert CATEGORIES <= categories


def test_reference_set_passes(demo_container):
    result = demo_container.evaluation.run(user_for(demo_container, "Administrator"))
    failed = [d for d in result["details"] if not d["passed"]]
    assert not failed, failed
    summary = result["summary"]
    assert summary["retrieval_hit_rate"] >= 0.9 and summary["citation_precision"] >= 0.9
    assert summary["no_evidence_accuracy"] == 1.0 and summary["conflict_detection"] == 1.0
    assert all(r["passed"] for r in result["resilience"])


def test_bm25_fallback_without_fts5(tmp_path, monkeypatch):
    from database.connection import Database

    monkeypatch.setattr(Database, "has_fts5", property(lambda self: False))
    container = build_container(make_settings(tmp_path))
    assert container.health.checks()[1].detail.startswith("BM25 en Python")
    result = container.evaluation.run(user_for(container, "Administrator"))
    failed = [d["id"] for d in result["details"] if not d["passed"]]
    assert len(failed) <= 1, failed


@pytest.mark.parametrize("question,expected", [
    ("¿Qué es la serialización?", {"DEMO-FAQ-013", "DEMO-MAN-014"}),
    ("Why does a unit go back to Repair?", {"DEMO-KB-003"}),
    ("¿Qué hago si la etiqueta impresa no coincide con el serial?", {"DEMO-WI-004"}),
])
def test_additional_questions(demo_container, question, expected):
    c = demo_container
    answer, _ = c.engine.answer(question, "es", c.policy.clearance_for("Operator"))
    assert answer.answered and answer.sources[0].doc_code in expected
