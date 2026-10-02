"""Detección de contradicciones entre fuentes aprobadas.

Heurísticas conservadoras (no reemplazan la revisión humana):
- numérica: oraciones casi equivalentes con cifras distintas ("máximo 3 reintentos" vs "máximo 5").
- polaridad: oraciones casi equivalentes donde una niega y la otra afirma.
Si hay conflicto, el sistema NO elige una fuente: muestra ambas y solicita escalamiento.
"""
from __future__ import annotations

import re

from core.text import STOPWORDS, split_sentences, term_key, tokenize
from models.domain import ConflictInfo, RetrievedChunk

_NEGATIONS = {"no", "nunca", "never", "not", "prohibido", "jamas", "sin", "dont", "don't", "cannot"}
_NUMBER = re.compile(r"\b\d+(?:[\.,]\d+)?\b")


def _sentence_profile(sentence: str) -> tuple[set[str], set[str], bool]:
    tokens = tokenize(sentence)
    words = {term_key(t) for t in tokens if t not in STOPWORDS and not t.isdigit() and t not in _NEGATIONS}
    numbers = set(_NUMBER.findall(sentence))
    negated = any(t in _NEGATIONS for t in tokens)
    return words, numbers, negated


def _sentences(text: str) -> list[str]:
    lines = [l for l in text.splitlines() if not l.strip().startswith("#") and "palabras clave" not in l.lower()]
    return [s for s in split_sentences("\n".join(lines)) if len(s) > 15]


def detect_conflicts(hits: list[RetrievedChunk], min_relevance: float, min_jaccard: float = 0.5,
                     max_pairs: int = 4) -> list[ConflictInfo]:
    relevant = [h for h in hits if h.relevance >= min_relevance and h.coverage >= 0.5]
    conflicts: list[ConflictInfo] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(relevant):
        for b in relevant[i + 1:]:
            if a.document_id == b.document_id:
                continue
            pair = tuple(sorted((a.doc_code, b.doc_code)))
            if pair in seen:
                continue
            for sa in _sentences(a.text):
                wa, na, nega = _sentence_profile(sa)
                if len(wa) < 3:
                    continue
                for sb in _sentences(b.text):
                    wb, nb, negb = _sentence_profile(sb)
                    if len(wb) < 3:
                        continue
                    jaccard = len(wa & wb) / len(wa | wb)
                    if jaccard < min_jaccard:
                        continue
                    kind = ""
                    if na and nb and na != nb:
                        kind = "numeric"
                    elif nega != negb and jaccard >= 0.6:
                        kind = "polarity"
                    if kind:
                        conflicts.append(ConflictInfo(doc_a=f"{a.doc_code} v{a.version_label}",
                                                      doc_b=f"{b.doc_code} v{b.version_label}",
                                                      sentence_a=sa[:300], sentence_b=sb[:300], kind=kind))
                        seen.add(pair)
                        break
                if pair in seen:
                    break
            if len(conflicts) >= max_pairs:
                return conflicts
    return conflicts
