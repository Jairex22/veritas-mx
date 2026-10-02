"""Normalización de texto, tokenización ligera y detección de idioma (ES/EN) sin dependencias."""
from __future__ import annotations

import re
import unicodedata

STOPWORDS_ES = {
    "a", "al", "algo", "alguna", "alguno", "ante", "antes", "aqui", "asi", "aun", "bajo", "bien", "cada", "como",
    "con", "cual", "cuales", "cuando", "de", "del", "desde", "donde", "dos", "el", "ella", "ellos", "en", "entre",
    "era", "es", "esa", "ese", "eso", "esta", "estan", "estar", "este", "esto", "estos", "fue", "ha", "hace",
    "hacer", "hago", "hay", "la", "las", "le", "les", "lo", "los", "mas", "me", "mi", "mis", "muy", "nada", "ni",
    "nos", "o", "otra", "otro", "para", "pero", "poco", "por", "porque", "puede", "puedo", "que", "quien", "se",
    "segun", "ser", "si", "sin", "sobre", "son", "su", "sus", "tambien", "tengo", "tiene", "todo", "tu", "un",
    "una", "uno", "unos", "y", "ya", "yo", "debo", "deberia", "existe", "hacemos", "sea", "sera", "cuanto",
    "cuantos", "veo", "ver", "sabe", "saber", "se", "esto", "favor", "hola", "necesito", "quiero", "consulto",
    "reviso", "significa", "diferencia", "regresa", "vez", "no",
}
STOPWORDS_EN = {
    "a", "about", "after", "all", "an", "and", "any", "are", "as", "at", "be", "been", "before", "but", "by", "can",
    "could", "do", "does", "for", "from", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "me",
    "my", "of", "on", "or", "our", "should", "so", "than", "that", "the", "their", "then", "there", "these", "this",
    "to", "was", "we", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
    "please", "need", "want", "not", "check", "know", "mean", "means", "between", "difference", "get", "use",
}
STOPWORDS = STOPWORDS_ES | STOPWORDS_EN

_ES_MARKERS = {"el", "la", "los", "las", "de", "que", "como", "por", "para", "una", "es", "del", "donde",
               "cual", "porque", "puedo", "no", "esta", "unidad", "orden", "operador", "hago", "reviso", "se"}
_EN_MARKERS = {"the", "how", "what", "is", "are", "does", "do", "why", "where", "which", "can", "unit", "order",
               "operator", "check", "i", "my", "of", "to", "not", "when"}

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-_/\.]*[a-z0-9]|[a-z0-9]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize(text: str) -> str:
    """Minúsculas, sin acentos, sin caracteres de control."""
    return strip_accents(_CONTROL_RE.sub(" ", text or "")).lower()


def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in _WORD_RE.findall(normalize(text)):
        tok = tok.strip(".-_/")
        if tok:
            tokens.append(tok)
    return tokens


def content_terms(text: str) -> list[str]:
    """Términos significativos (sin stopwords, longitud >= 2)."""
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) >= 2]


def term_key(term: str) -> str:
    """Clave de coincidencia aproximada: prefijo de 6 caracteres para palabras largas
    (certificado/certificacion/certification -> 'certif'), singular simple para cortas."""
    if len(term) > 7:
        return term[:6]
    if len(term) > 4 and term.endswith("es"):
        return term[:-2]
    if len(term) > 3 and term.endswith("s"):
        return term[:-1]
    return term


def detect_language(text: str) -> str:
    """Devuelve 'es' o 'en' con base en marcadores frecuentes y caracteres propios del español."""
    raw = text or ""
    tokens = tokenize(raw)
    es = sum(1 for t in tokens if t in _ES_MARKERS)
    en = sum(1 for t in tokens if t in _EN_MARKERS)
    if re.search(r"[ñ¿¡áéíóú]", raw.lower()):
        es += 2
    return "en" if en > es else "es"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\!\?;])\s+|\n+", text or "")
    return [p.strip(" -*\t") for p in parts if p and len(p.strip(" -*\t")) > 2]


def truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"
