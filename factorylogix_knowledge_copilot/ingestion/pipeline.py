"""Pipeline de ingesta: validación -> extracción -> limpieza -> hash -> detección -> fragmentos -> embeddings."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.config import Settings
from core.errors import ExtractionError
from core.text import normalize
from core.utils import sha256_text
from ingestion.chunking import Chunk, chunk_pages
from ingestion.cleaning import clean_pages
from ingestion.extractors import PageText, extract
from security.file_validation import ValidatedFile, validate_upload

_PAGE_MARK = re.compile(r"^\[\[page:(\d+)\]\]$", re.MULTILINE)


def pages_to_text(pages: list[PageText]) -> str:
    """Serializa páginas conservando su número para permitir reindexar sin el archivo original."""
    parts = []
    for page in pages:
        if page.page is not None:
            parts.append(f"[[page:{page.page}]]")
        parts.append(page.text)
    return "\n".join(parts).strip()


def text_to_pages(text: str) -> list[PageText]:
    if not _PAGE_MARK.search(text or ""):
        return [PageText(None, text or "")]
    pages: list[PageText] = []
    pieces = _PAGE_MARK.split(text)
    if pieces[0].strip():
        pages.append(PageText(None, pieces[0]))
    for i in range(1, len(pieces), 2):
        pages.append(PageText(int(pieces[i]), pieces[i + 1]))
    return pages


def display_text(text: str) -> str:
    return _PAGE_MARK.sub(lambda m: f"— Página {m.group(1)} —", text or "")


def content_hash(text: str) -> str:
    """Hash del contenido normalizado: detecta duplicados aunque cambie el formato del archivo."""
    return sha256_text(" ".join(normalize(display_text(text)).split()))


@dataclass
class PreparedContent:
    pages: list[PageText]
    text: str
    hash: str
    file: ValidatedFile | None
    page_count: int | None
    warnings: list[str] = field(default_factory=list)


class IngestionPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    def prepare_file(self, file_name: str, data: bytes) -> PreparedContent:
        vf = validate_upload(file_name, data, self.settings.get("ingestion.allowed_extensions", []),
                             float(self.settings.get("ingestion.max_file_mb", 25)))
        extracted = extract(vf.kind, data, max_pages=int(self.settings.get("ingestion.max_pdf_pages", 400)),
                            max_rows=int(self.settings.get("ingestion.max_spreadsheet_rows", 20000)),
                            timeout=float(self.settings.get("ingestion.extraction_timeout_seconds", 60)))
        prepared = self.prepare_pages(extracted.pages)
        prepared.file = vf
        prepared.page_count = extracted.page_count
        prepared.warnings = extracted.warnings + prepared.warnings
        return prepared

    def prepare_text(self, text: str) -> PreparedContent:
        return self.prepare_pages([PageText(None, text)])

    def prepare_pages(self, pages: list[PageText]) -> PreparedContent:
        cleaned = [p for p in clean_pages(pages) if p.text.strip()]
        text = pages_to_text(cleaned)
        if len(display_text(text).strip()) < 20:
            raise ExtractionError("No se encontró texto útil en el archivo.")
        return PreparedContent(pages=cleaned, text=text, hash=content_hash(text), file=None, page_count=None)

    def chunk(self, text: str) -> list[Chunk]:
        return chunk_pages(text_to_pages(text), int(self.settings.get("ingestion.chunk_max_chars", 1800)),
                           int(self.settings.get("ingestion.chunk_overlap_chars", 200)))
