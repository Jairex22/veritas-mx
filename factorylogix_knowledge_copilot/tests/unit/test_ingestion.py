import io

import openpyxl
import pytest

from core.errors import ExtractionError
from ingestion.chunking import chunk_pages
from ingestion.cleaning import clean_text, remove_repeated_headers
from ingestion.extractors import PageText, extract, ocr_available
from ingestion.pipeline import content_hash, pages_to_text, text_to_pages
from tests.conftest import MD_DOC, ROOT

DEMO = ROOT / "demo_data" / "documents"


def _extract(kind, data):
    return extract(kind, data, max_pages=50, max_rows=100, timeout=30)


def test_markdown_chunking_keeps_sections():
    chunks = chunk_pages([PageText(None, MD_DOC)])
    assert len(chunks) == 1
    assert chunks[0].section.endswith("Calibración del torquímetro de la estación T1")
    assert chunks[0].text.startswith("## Calibración")


def test_long_section_split_with_heading():
    body = "## Tema largo\n" + "\n\n".join(f"Párrafo {i} " + "x" * 300 for i in range(12))
    chunks = chunk_pages([PageText(None, body)], max_chars=800, overlap=100)
    assert len(chunks) > 3
    assert all(c.text.startswith("## Tema largo") for c in chunks)
    assert all(len(c.text) <= 1000 for c in chunks)


def test_pdf_extraction_with_pages():
    doc = _extract("pdf", (DEMO / "DEMO-MAN-014_production_quick_reference.pdf").read_bytes())
    assert doc.page_count == 2
    assert "Serialization" in doc.pages[0].text and "Fail" in doc.pages[1].text


def test_pdf_page_limit():
    data = (DEMO / "DEMO-MAN-014_production_quick_reference.pdf").read_bytes()
    with pytest.raises(ExtractionError):
        extract("pdf", data, max_pages=1, max_rows=10, timeout=30)


def test_docx_headings_become_markdown():
    doc = _extract("docx", (DEMO / "DEMO-MAN-005_genealogia_wip.docx").read_bytes())
    assert "## Dónde consultar la genealogía" in doc.text
    assert "### Pasos" in doc.text


def test_xlsx_and_csv_extraction():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Estación", "Operación"])
    ws.append(["ICT-01", "Prueba ICT"])
    buf = io.BytesIO()
    wb.save(buf)
    assert "Estación: ICT-01" in _extract("xlsx", buf.getvalue()).text
    faq = _extract("csv", (DEMO / "DEMO-FAQ-013_preguntas_frecuentes.csv").read_bytes()).text
    assert "## ¿Qué es la BOM en FactoryLogix?" in faq and "### Respuesta breve" in faq


def test_html_strips_scripts():
    doc = _extract("html", b"<h2>Tema</h2><script>alert(1)</script><p>Texto visible</p>")
    assert "alert" not in doc.text and "Texto visible" in doc.text and "## Tema" in doc.text


def test_image_without_ocr_is_reported():
    if ocr_available():
        pytest.skip("OCR instalado en este equipo")
    with pytest.raises(ExtractionError):
        _extract("image", b"\x89PNG\r\n\x1a\n0000")


def test_cleaning_and_headers():
    assert clean_text("a\x00b  c\r\n\n\n\nd") == "ab c\n\nd"
    pages = [PageText(i, f"EMPRESA DEMO\ncontenido {i}") for i in range(1, 5)]
    assert all("EMPRESA DEMO" not in p.text for p in remove_repeated_headers(pages))


def test_page_markers_roundtrip_and_hash_ignores_format():
    pages = [PageText(1, "uno"), PageText(2, "dos")]
    restored = text_to_pages(pages_to_text(pages))
    assert [(p.page, p.text.strip()) for p in restored] == [(1, "uno"), (2, "dos")]
    assert content_hash("Hola   Mundo") == content_hash("hola mundo")
