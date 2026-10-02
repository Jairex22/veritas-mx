"""Construcción extractiva de respuestas estructuradas (modo sin LLM).

Solo se copian oraciones de las fuentes recuperadas. Si una sección no existe en la fuente,
se deja vacía (la interfaz muestra "no especificado en la fuente") en lugar de inventar contenido.
"""
from __future__ import annotations

import re

from core.text import normalize, split_sentences, truncate
from models.domain import Answer, AnswerSource, RetrievedChunk
from rag.query import QueryTerms, coverage
from security.injection import InjectionDetector

SECTION_ALIASES = {
    "brief": ["respuesta breve", "resumen", "short answer", "summary", "respuesta"],
    "steps": ["pasos", "steps", "procedimiento", "procedure"],
    "validate": ["que validar", "validar", "what to check", "what to validate", "verificar", "verify"],
    "expected": ["resultado esperado", "expected result", "expected outcome"],
    "stop": ["cuando detenerse", "detenerse", "when to stop", "stop"],
    "escalate": ["cuando escalar", "escalar", "when to escalate", "escalation", "escalamiento"],
    "warnings": ["advertencias", "advertencia", "warnings", "warning", "precauciones", "caution"],
}
_CAUTION = re.compile(r"\b(advertencia|precaucion|nunca|no debe|no se debe|warning|caution|never|do not)\b")
_LIST_ITEM = re.compile(r"^\s*(?:\d+[\.\)]|[-•*])\s+")


def _section_key(heading: str) -> str | None:
    norm = normalize(heading).strip(" :")
    for key, aliases in SECTION_ALIASES.items():
        if any(norm == a or norm.startswith(a) for a in aliases):
            return key
    return None


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"intro": []}
    current = "intro"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("## ") or line.startswith("# "):
            continue
        if line.startswith(">"):
            continue
        if normalize(line).startswith(("palabras clave", "keywords")):
            continue
        if line.startswith("### "):
            current = _section_key(line[4:]) or "other"
            sections.setdefault(current, [])
            continue
        item = _LIST_ITEM.sub("", line).strip()
        if item:
            sections.setdefault(current, []).append(item)
    return sections


def _best_sentences(text: str, query: QueryTerms, limit: int) -> list[str]:
    candidates = [s for s in split_sentences(text) if not s.startswith("#") and len(s) > 25]
    scored = sorted(candidates, key=lambda s: coverage(query, s), reverse=True)
    return [s for s in scored[:limit] if coverage(query, s) > 0]


def to_source(hit: RetrievedChunk, excerpt_chars: int = 600) -> AnswerSource:
    return AnswerSource(
        chunk_id=hit.chunk_id, document_id=hit.document_id, version_id=hit.version_id, doc_code=hit.doc_code,
        title=hit.title, version_label=hit.version_label, source_type=hit.source_type,
        classification=hit.classification, section=hit.section, page=hit.page,
        excerpt=truncate(hit.text, excerpt_chars), relevance=round(hit.relevance, 3), is_demo=hit.is_demo,
        review_date=hit.review_date, expiration_date=hit.expiration_date)


def build_extractive(answer: Answer, hits: list[RetrievedChunk], query: QueryTerms, detector: InjectionDetector,
                     min_relevance: float) -> Answer:
    usable = [h for h in hits if h.relevance >= min_relevance]
    primary = usable[0]
    text, removed = detector.strip_suspicious(primary.text) if primary.injection_flag else (primary.text, 0)
    if removed:
        answer.notices.append("Se omitieron instrucciones sospechosas encontradas dentro del documento fuente.")
    sections = parse_sections(text)

    brief_items = sections.get("brief") or sections.get("intro") or []
    answer.brief = " ".join(brief_items[:3]) if brief_items else " ".join(_best_sentences(text, query, 2))
    answer.steps = sections.get("steps", [])
    if not answer.steps and not any(k in sections for k in ("validate", "expected", "stop", "escalate")):
        answer.steps = [_LIST_ITEM.sub("", l).strip() for l in text.splitlines() if _LIST_ITEM.match(l)][:12]
    answer.validate = sections.get("validate", [])
    answer.expected = sections.get("expected", [])
    answer.stop_when = sections.get("stop", [])
    answer.escalate_when = sections.get("escalate", [])
    warnings = list(sections.get("warnings", []))
    if not warnings:
        warnings = [s for s in split_sentences(text) if _CAUTION.search(normalize(s))
                    and s not in answer.stop_when and s not in answer.steps][:3]
    answer.warnings = warnings
    if not answer.brief:
        answer.brief = truncate(text.replace("\n", " "), 300)

    # Fuentes de respaldo: solo fragmentos casi tan relevantes como el principal (sin repetir sección).
    supporting, seen = [], set()
    for hit in usable:
        key = (hit.doc_code, hit.section)
        if key in seen or (hit is not primary and hit.relevance < 0.8 * primary.relevance):
            continue
        seen.add(key)
        supporting.append(hit)
    answer.sources = [to_source(h) for h in supporting[:4]]
    return answer
