import csv
import io

import pytest

from core.errors import ValidationError
from rag.llm import NullLLM, OllamaLLM, build_llm, grounding_score, validate_local_url
from services.export_service import html_report, to_csv_bytes


def test_llm_url_must_be_local_or_private():
    assert validate_local_url("http://127.0.0.1:11434")
    assert validate_local_url("http://10.1.2.3:8080")
    with pytest.raises(ValidationError):
        validate_local_url("http://8.8.8.8:11434")
    with pytest.raises(ValidationError):
        validate_local_url("ftp://localhost")


def test_build_llm_never_fails():
    llm, warnings = build_llm("ollama", "http://8.8.8.8", "m", 5, 0.1, 100)
    assert isinstance(llm, NullLLM) and warnings
    assert not NullLLM().available()


def test_ollama_unavailable_without_server():
    llm = OllamaLLM("http://127.0.0.1:9", "m", 1, 0.1, 10)
    assert llm.available() is False


def test_grounding_score():
    sources = ["La Work Order se consulta en la vista de órdenes de trabajo buscando por número."]
    assert grounding_score("La Work Order se consulta buscando por número [S1].", sources) == 1.0
    assert grounding_score("Reinicia el servidor de base de datos Oracle inmediatamente.", sources) == 0.0


def test_csv_formula_injection_neutralized():
    data = to_csv_bytes([{"a": "=HYPERLINK(\"http://x\")", "b": "+1", "c": "@SUM(A1)", "d": "normal"}])
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[1] == ["'=HYPERLINK(\"http://x\")", "'+1", "'@SUM(A1)", "normal"]


def test_html_report_escapes_content():
    html = html_report("<b>t</b>", [("x", {"k": "<script>alert(1)</script>"}), ("y", "<img onerror=1>")])
    assert "<script>" not in html and "&lt;script&gt;" in html and "<img" not in html
