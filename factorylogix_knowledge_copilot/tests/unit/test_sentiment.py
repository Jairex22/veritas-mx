import pytest

from core.config import load_settings
from sentiment.analyzer import SentimentAnalyzer, tone_guidance


@pytest.fixture(scope="module")
def analyzer():
    return SentimentAnalyzer(load_settings(environ={}).rules["sentiment"])


@pytest.mark.parametrize("text,label", [
    ("¡Urgente! La línea parada, el cliente esperando", "Urgent"),
    ("Otra vez no funciona, ya intenté todo", "Frustrated"),
    ("No entiendo qué significa In Process", "Confused"),
    ("Gracias, funcionó perfecto", "Satisfied"),
    ("¿Cómo reviso el estado de una Work Order?", "Neutral"),
    ("Line down, customer waiting, this is urgent", "Urgent"),
    ("It still not working again", "Frustrated"),
    ("Thanks, that worked", "Satisfied"),
])
def test_labels(analyzer, text, label):
    assert analyzer.analyze(text).label == label


def test_result_fields_and_language(analyzer):
    result = analyzer.analyze("I don't understand what WIP means")
    assert result.language == "en" and 0 < result.confidence <= 0.95 and result.signals


def test_negated_satisfaction_is_not_satisfied(analyzer):
    assert analyzer.analyze("no funciono la solucion").label != "Satisfied"


def test_can_be_disabled():
    disabled = SentimentAnalyzer(load_settings(environ={}).rules["sentiment"], enabled=False)
    result = disabled.analyze("URGENTE línea parada")
    assert result.enabled is False and result.label == "Neutral"


def test_tone_guidance():
    assert tone_guidance("Urgent", "es")["escalation_first"]
    assert tone_guidance("Satisfied", "es")["brief_only"]
    assert tone_guidance("Confused", "en")["short_steps"]
