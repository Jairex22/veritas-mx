"""División en fragmentos con contexto: respeta encabezados Markdown (#, ##, ###) y páginas.

Cada fragmento conserva la ruta de sección ("Documento > Tema") y antepone el encabezado del tema
para que sea autocontenido. Los temas largos se dividen por subsección y luego por párrafos con
solapamiento.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ingestion.extractors import PageText

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")


@dataclass
class Chunk:
    text: str
    section: str
    page: int | None


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p for p in re.split(r"\n(?=### )|\n\n", text) if p.strip()]
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > max_chars:
            parts.append(para[:max_chars])
            para = para[max_chars - overlap:]
        if current and len(current) + len(para) + 2 > max_chars:
            parts.append(current)
            tail = current[-overlap:] if overlap else ""
            current = (tail + "\n" + para) if tail and not para.startswith("### ") else para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        parts.append(current)
    return parts


def chunk_pages(pages: list[PageText], max_chars: int = 1800, overlap: int = 200) -> list[Chunk]:
    chunks: list[Chunk] = []
    h1 = ""
    for page in pages:
        h2 = ""
        buffer: list[str] = []

        def flush() -> None:
            body = "\n".join(buffer).strip()
            buffer.clear()
            if not body or len(body) < 20:
                return
            section = " > ".join(x for x in (h1, h2) if x)
            heading = f"## {h2}\n" if h2 and not body.startswith("## ") else ""
            for part in _split_long(body, max_chars, overlap):
                text = part if part.startswith("## ") else heading + part
                chunks.append(Chunk(text=text.strip(), section=section, page=page.page))

        for line in page.text.splitlines():
            match = _HEADING.match(line.strip())
            if match and len(match.group(1)) == 1:
                flush()
                h1, h2 = match.group(2).strip(), ""
                continue
            if match and len(match.group(1)) == 2:
                flush()
                h2 = match.group(2).strip()
                continue
            buffer.append(line)
        flush()
    return chunks
