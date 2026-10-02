"""Limpieza y normalización del texto extraído."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from ingestion.extractors import PageText

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​﻿]")
_SPACES = re.compile(r"[ \t ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _MANY_NEWLINES.sub("\n\n", text).strip()


def remove_repeated_headers(pages: list[PageText], min_pages: int = 3) -> list[PageText]:
    """Elimina líneas repetidas en más de la mitad de las páginas (encabezados/pies de página)."""
    if len(pages) < min_pages:
        return pages
    counter: Counter[str] = Counter()
    for page in pages:
        counter.update({line.strip() for line in page.text.splitlines() if 0 < len(line.strip()) < 120})
    repeated = {line for line, count in counter.items() if count > len(pages) / 2}
    if not repeated:
        return pages
    return [PageText(p.page, "\n".join(l for l in p.text.splitlines() if l.strip() not in repeated))
            for p in pages]


def clean_pages(pages: list[PageText]) -> list[PageText]:
    pages = remove_repeated_headers(pages)
    return [PageText(p.page, clean_text(p.text)) for p in pages]
