"""Detección de prompt injection y de solicitudes de acciones de producción.

El contenido de documentos se trata siempre como DATOS. Las oraciones sospechosas se marcan,
se excluyen de las respuestas y del contexto enviado a cualquier LLM, y requieren revisión humana.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.text import normalize, split_sentences


@dataclass
class InjectionReport:
    flagged: bool
    matches: list[str] = field(default_factory=list)


class RuleMatcher:
    def __init__(self, patterns: list[str]):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

    def find(self, text: str) -> list[str]:
        norm = normalize(text)
        found = []
        for pattern in self.patterns:
            match = pattern.search(norm)
            if match:
                found.append(match.group(0)[:80])
        return found


class InjectionDetector:
    def __init__(self, patterns: list[str]):
        self.matcher = RuleMatcher(patterns)

    def scan(self, text: str) -> InjectionReport:
        matches = self.matcher.find(text or "")
        return InjectionReport(flagged=bool(matches), matches=sorted(set(matches)))

    def strip_suspicious(self, text: str) -> tuple[str, int]:
        """Elimina oraciones con patrones de inyección. Devuelve (texto limpio, oraciones removidas)."""
        kept, removed = [], 0
        for line in (text or "").splitlines():
            if self.matcher.find(line):
                sentences = split_sentences(line)
                safe = [s for s in sentences if not self.matcher.find(s)]
                removed += len(sentences) - len(safe)
                if safe:
                    kept.append(" ".join(safe))
            else:
                kept.append(line)
        return "\n".join(kept), removed
