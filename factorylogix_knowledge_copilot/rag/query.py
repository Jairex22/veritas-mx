"""Análisis de consultas: términos significativos, expansión bilingüe por glosario y cobertura."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.text import content_terms, normalize, term_key, tokenize


@dataclass
class QueryTerms:
    """Cada concepto es un conjunto de claves alternativas (sinónimos); basta una coincidencia."""

    original: list[str]
    concepts: list[set[str]] = field(default_factory=list)
    expansion_text: str = ""

    @property
    def search_terms(self) -> list[str]:
        terms: list[str] = []
        for concept in self.concepts:
            for key in sorted(concept):
                for part in key.split():
                    if part not in terms:
                        terms.append(part)
        return terms


class Glossary:
    def __init__(self, groups: list[list[str]]):
        self.groups = [[normalize(term) for term in group] for group in groups]

    def match_groups(self, normalized_query: str) -> list[list[str]]:
        padded = f" {' '.join(tokenize(normalized_query))} "
        return [g for g in self.groups if any(f" {' '.join(tokenize(t))} " in padded for t in g)]


def analyze(question: str, glossary: Glossary) -> QueryTerms:
    terms = content_terms(question)
    norm = " ".join(tokenize(question))
    groups = glossary.match_groups(norm)
    concepts: list[set[str]] = []
    covered: set[str] = set()
    for group in groups:
        concept = {" ".join(term_key(t) for t in phrase.split()) for phrase in group}
        concepts.append(concept)
        for phrase in group:
            covered.update(tokenize(phrase))
    for term in terms:
        if term not in covered:
            concepts.append({term_key(term)})
    expansion = " ".join(phrase for group in groups for phrase in group)
    return QueryTerms(original=terms, concepts=concepts, expansion_text=expansion)


def _phrase_present(key_phrase: str, tokens: list[str], token_keys: set[str]) -> bool:
    parts = key_phrase.split()
    if len(parts) == 1:
        key = parts[0]
        if key in token_keys:
            return True
        return len(key) >= 4 and any(tok.startswith(key) for tok in tokens)
    keys = [term_key(t) for t in tokens]
    n = len(parts)
    for i in range(len(keys) - n + 1):
        if all(keys[i + j] == parts[j] or (len(parts[j]) >= 4 and tokens[i + j].startswith(parts[j]))
               for j in range(n)):
            return True
    return False


def coverage(query: QueryTerms, text: str) -> float:
    """Fracción de conceptos de la consulta presentes en el texto (0..1)."""
    if not query.concepts:
        return 0.0
    tokens = tokenize(text)
    token_keys = {term_key(t) for t in tokens}
    hits = sum(1 for concept in query.concepts if any(_phrase_present(k, tokens, token_keys) for k in concept))
    return hits / len(query.concepts)
