"""Análisis de sentimiento local y responsable (ES/EN), basado en léxico configurable.

Finalidad ÚNICA: adaptar el tono de la respuesta y detectar necesidad de escalamiento.
- No diagnostica salud mental ni infiere características protegidas.
- No se usa para evaluar, clasificar o sancionar empleados; no existen rankings.
- Se almacena solo la etiqueta, con expiración (retención configurable) y puede desactivarse.
"""
from __future__ import annotations

import re

from core.text import detect_language, normalize
from models.domain import SentimentLabel, SentimentResult

PURPOSE_ES = ("El análisis de sentimiento se usa únicamente para adaptar el tono de la respuesta y detectar "
              "urgencias que requieren escalamiento. No evalúa personas ni se usa para decisiones laborales.")
PURPOSE_EN = ("Sentiment analysis is used only to adapt the response tone and detect urgent situations that need "
              "escalation. It does not evaluate people and is never used for employment decisions.")

_PRIORITY = [SentimentLabel.URGENT, SentimentLabel.FRUSTRATED, SentimentLabel.CONFUSED, SentimentLabel.SATISFIED]
_KEYS = {SentimentLabel.URGENT: "urgent", SentimentLabel.FRUSTRATED: "frustrated",
         SentimentLabel.CONFUSED: "confused", SentimentLabel.SATISFIED: "satisfied"}


class SentimentAnalyzer:
    def __init__(self, lexicon: dict, enabled: bool = True):
        self.enabled = enabled
        self.negations = {normalize(n) for n in lexicon.get("negations", [])}
        self.lexicon: dict[str, dict[str, list[str]]] = {}
        for lang in ("es", "en"):
            entries = lexicon.get(lang, {})
            self.lexicon[lang] = {k: [normalize(p) for p in v] for k, v in entries.items()}

    def analyze(self, text: str) -> SentimentResult:
        language = detect_language(text)
        if not self.enabled:
            return SentimentResult(label=SentimentLabel.NEUTRAL.value, confidence=0.0, language=language,
                                   enabled=False)
        norm = f" {normalize(text)} "
        scores: dict[SentimentLabel, float] = {label: 0.0 for label in _PRIORITY}
        signals: list[str] = []
        for lang in ("es", "en"):
            for label in _PRIORITY:
                for phrase in self.lexicon.get(lang, {}).get(_KEYS[label], []):
                    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")
                    for match in pattern.finditer(norm):
                        before = norm[max(0, match.start() - 12):match.start()].split()
                        negated = bool(before) and before[-1] in self.negations and label == SentimentLabel.SATISFIED
                        if negated:
                            scores[SentimentLabel.FRUSTRATED] += 0.5
                            signals.append(f"negación + '{phrase}'")
                            continue
                        scores[label] += 1.0
                        signals.append(f"{_KEYS[label]}: '{phrase}'")
        exclamations = text.count("!")
        letters = [c for c in text if c.isalpha()]
        caps_ratio = (sum(1 for c in letters if c.isupper()) / len(letters)) if len(letters) >= 12 else 0.0
        if exclamations >= 2:
            scores[SentimentLabel.FRUSTRATED] += 0.3
            scores[SentimentLabel.URGENT] += 0.3
            signals.append("signos de exclamación repetidos")
        if caps_ratio > 0.6:
            scores[SentimentLabel.URGENT] += 0.4
            scores[SentimentLabel.FRUSTRATED] += 0.3
            signals.append("texto mayormente en mayúsculas")
        if text.count("?") >= 3:
            scores[SentimentLabel.CONFUSED] += 0.5
            signals.append("varias preguntas seguidas")

        best = max(_PRIORITY, key=lambda label: (scores[label], -_PRIORITY.index(label)))
        total = sum(scores.values())
        if scores[best] < 0.5:
            return SentimentResult(label=SentimentLabel.NEUTRAL.value, confidence=0.6, language=language,
                                   signals=signals[:5])
        confidence = min(0.95, 0.5 + 0.5 * scores[best] / (total or 1) * min(1.0, scores[best] / 2))
        return SentimentResult(label=best.value, confidence=round(confidence, 2), language=language,
                               signals=signals[:5])


def tone_guidance(label: str, language: str) -> dict[str, object]:
    """Ajustes de presentación según sentimiento (no cambia el contenido técnico)."""
    es = language != "en"
    if label == SentimentLabel.URGENT.value:
        return {"escalation_first": True, "brief_only": False, "short_steps": False,
                "preface": "Prioridad: primero acciones seguras y ruta de escalamiento." if es else
                "Priority: safe actions and escalation path first."}
    if label == SentimentLabel.FRUSTRATED.value:
        return {"escalation_first": False, "brief_only": False, "short_steps": False,
                "preface": "Entiendo que esto está afectando tu trabajo. Vamos directo a lo verificable." if es else
                "I understand this is affecting your work. Let's go straight to what can be verified."}
    if label == SentimentLabel.CONFUSED.value:
        return {"escalation_first": False, "brief_only": False, "short_steps": True,
                "preface": "Te muestro los pasos uno por uno." if es else "Here are the steps one at a time."}
    if label == SentimentLabel.SATISFIED.value:
        return {"escalation_first": False, "brief_only": True, "short_steps": False, "preface": ""}
    return {"escalation_first": False, "brief_only": False, "short_steps": False, "preface": ""}
