"""
Motor de puntaje operativo — Diccionario y explicación completa en
`DICCIONARIO_INDICADORES.md` y `FORMULA_PUNTAJE.md`.

FÓRMULA (pesos por defecto, configurables desde Configuración > Puntaje):

    puntaje = calidad_norm      × 0.35   (FPY normalizado por estación/producto)
            + ciclo_norm        × 0.25   (cumplimiento contra tiempo estándar)
            + productividad_norm× 0.20   (unidades/hora normalizada por complejidad)
            + consistencia_norm × 0.10   (estabilidad del tiempo de ciclo, 1 - CV)
            + retrabajo_norm    × 0.10   (100 - tasa de retrabajo, con piso en 0)

Reglas aplicadas SIEMPRE, en este orden:

1. Los tiempos muertos autorizados (DowntimeEvent.is_authorized=True) se excluyen
   del tiempo activo antes de calcular ciclo y productividad.
2. Cada componente se normaliza 0-100 respecto al grupo equivalente
   (misma estación + mismo producto) usando el estándar de la estación como
   referencia de 100, para no comparar operadores en contextos distintos.
3. Si el número de unidades muestreadas es menor que `min_units` (config,
   por defecto 20), NO se calcula un puntaje publicable: la clasificación es
   "Datos insuficientes" y se explica por qué.
4. Valores atípicos (eventos fuera de 3 desviaciones estándar del grupo) se
   amortiguan con un "winsorize" suave antes de promediar, para que un solo
   evento extremo (ej. una orden pequeña o un cambio de producto) no distorsione
   el resultado.
5. El resultado final se limita estrictamente al rango [0, 100].
6. Se devuelve siempre el desglose (`breakdown`) con cada componente, su peso
   y su valor crudo, para que el resultado sea trazable y explicable.
7. El nivel de confianza de los datos (`data_confidence`) se calcula a partir
   del número de muestras y de cuántos días distintos las componen, y se
   muestra junto al puntaje — nunca se oculta.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field


CLASSIFICATION_BANDS = [
    (90.0, 100.0, "Excelente"),
    (80.0, 89.999, "Bueno"),
    (65.0, 79.999, "En observación"),
    (0.0, 64.999, "Requiere apoyo"),
]

INSUFFICIENT_DATA_LABEL = "Datos insuficientes"

DISCLAIMER = (
    "Este indicador es una herramienta de apoyo para mejora continua. "
    "Debe revisarse junto con el contexto operativo antes de tomar decisiones."
)


@dataclass
class ScoringWeights:
    quality: float = 0.35
    cycle: float = 0.25
    productivity: float = 0.20
    consistency: float = 0.10
    rework: float = 0.10
    min_units: int = 20

    def normalized(self) -> "ScoringWeights":
        total = self.quality + self.cycle + self.productivity + self.consistency + self.rework
        if total <= 0:
            return ScoringWeights(min_units=self.min_units)
        return ScoringWeights(
            quality=self.quality / total,
            cycle=self.cycle / total,
            productivity=self.productivity / total,
            consistency=self.consistency / total,
            rework=self.rework / total,
            min_units=self.min_units,
        )


@dataclass
class ScoreBreakdownItem:
    key: str
    label: str
    raw_value: float
    normalized_value: float
    weight: float
    contribution: float


@dataclass
class ScoreResult:
    score: float | None
    classification: str
    data_confidence: str
    sample_size: int
    distinct_days: int
    breakdown: list[ScoreBreakdownItem] = field(default_factory=list)
    explanation: str = ""
    disclaimer: str = DISCLAIMER


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _winsorize(values: list[float], z: float = 3.0) -> list[float]:
    """Amortigua valores fuera de z desviaciones estándar (no los elimina)."""
    if len(values) < 3:
        return values
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) or 1e-9
    lo, hi = mean - z * stdev, mean + z * stdev
    return [min(max(v, lo), hi) for v in values]


def classify(score: float | None) -> str:
    if score is None:
        return INSUFFICIENT_DATA_LABEL
    for lo, hi, label in CLASSIFICATION_BANDS:
        if lo <= score <= hi:
            return label
    return INSUFFICIENT_DATA_LABEL


def data_confidence_label(sample_size: int, distinct_days: int, min_units: int) -> str:
    if sample_size < max(5, min_units // 4):
        return "Baja"
    if sample_size < min_units:
        return "Media-baja"
    if sample_size < min_units * 3 and distinct_days < 10:
        return "Media"
    if sample_size >= min_units * 3 and distinct_days >= 10:
        return "Alta"
    return "Media-alta"


@dataclass
class GroupSample:
    """Un evento agregable de producción, ya con tiempos muertos autorizados excluidos."""

    units_processed: int
    units_conforming: int
    units_rejected: int
    units_reworked: int
    cycle_time_seconds: float
    standard_cycle_seconds: float
    event_date: str


def compute_score(
    samples: list[GroupSample],
    weights: ScoringWeights | None = None,
) -> ScoreResult:
    weights = (weights or ScoringWeights()).normalized()

    sample_size = sum(s.units_processed for s in samples)
    distinct_days = len({s.event_date for s in samples})

    confidence = data_confidence_label(sample_size, distinct_days, weights.min_units)

    if sample_size < weights.min_units or not samples:
        return ScoreResult(
            score=None,
            classification=INSUFFICIENT_DATA_LABEL,
            data_confidence=confidence,
            sample_size=sample_size,
            distinct_days=distinct_days,
            breakdown=[],
            explanation=(
                f"Se registraron {sample_size} unidades, por debajo del mínimo configurado "
                f"({weights.min_units}) para publicar una clasificación confiable. "
                "Todavía no hay suficientes unidades para calcular una tendencia confiable."
            ),
        )

    total_processed = sum(s.units_processed for s in samples)
    total_conforming = sum(s.units_conforming for s in samples)
    total_rejected = sum(s.units_rejected for s in samples)
    total_reworked = sum(s.units_reworked for s in samples)

    # 1) Calidad (FPY normalizado): unidades conformes a la primera / procesadas.
    fpy = 100.0 * total_conforming / total_processed if total_processed else 0.0
    quality_norm = _clamp(fpy)

    # 2) Cumplimiento de ciclo: estándar / real, por evento, amortiguado y promediado.
    cycle_ratios = [
        _clamp(100.0 * (s.standard_cycle_seconds / s.cycle_time_seconds) if s.cycle_time_seconds > 0 else 0.0)
        for s in samples
    ]
    cycle_ratios = _winsorize(cycle_ratios)
    cycle_norm = statistics.fmean(cycle_ratios) if cycle_ratios else 0.0

    # 3) Productividad normalizada: unidades/segundo real vs. estándar del grupo.
    total_active_seconds = sum(s.cycle_time_seconds for s in samples if s.cycle_time_seconds > 0)
    real_rate = (total_processed / total_active_seconds) if total_active_seconds > 0 else 0.0
    standard_rate_values = [s.standard_cycle_seconds for s in samples if s.standard_cycle_seconds > 0]
    standard_rate = 1.0 / (statistics.fmean(standard_rate_values)) if standard_rate_values else 0.0
    productivity_norm = _clamp(100.0 * (real_rate / standard_rate)) if standard_rate else 0.0

    # 4) Consistencia: 1 - coeficiente de variación del tiempo de ciclo.
    cycle_times = _winsorize([s.cycle_time_seconds for s in samples if s.cycle_time_seconds > 0])
    if len(cycle_times) >= 2:
        mean_ct = statistics.fmean(cycle_times)
        stdev_ct = statistics.pstdev(cycle_times)
        cv = (stdev_ct / mean_ct) if mean_ct else 1.0
        consistency_norm = _clamp(100.0 * (1.0 - min(cv, 1.0)))
    else:
        consistency_norm = 60.0  # neutral, poca evidencia para evaluar consistencia

    # 5) Retrabajo: 100 - tasa de retrabajo (piso en 0).
    rework_rate = 100.0 * total_reworked / total_processed if total_processed else 0.0
    rework_norm = _clamp(100.0 - rework_rate)

    breakdown = [
        ScoreBreakdownItem("quality", "Calidad / FPY", fpy, quality_norm, weights.quality, quality_norm * weights.quality),
        ScoreBreakdownItem("cycle", "Cumplimiento de ciclo", statistics.fmean(cycle_ratios) if cycle_ratios else 0.0, cycle_norm, weights.cycle, cycle_norm * weights.cycle),
        ScoreBreakdownItem("productivity", "Productividad normalizada", real_rate, productivity_norm, weights.productivity, productivity_norm * weights.productivity),
        ScoreBreakdownItem("consistency", "Consistencia", consistency_norm, consistency_norm, weights.consistency, consistency_norm * weights.consistency),
        ScoreBreakdownItem("rework", "Retrabajo (invertido)", rework_rate, rework_norm, weights.rework, rework_norm * weights.rework),
    ]

    raw_score = sum(item.contribution for item in breakdown)
    final_score = round(_clamp(raw_score), 1)

    explanation = (
        f"Calculado con {sample_size} unidades en {distinct_days} día(s). "
        f"Calidad {quality_norm:.1f} × {weights.quality:.2f} + Ciclo {cycle_norm:.1f} × {weights.cycle:.2f} + "
        f"Productividad {productivity_norm:.1f} × {weights.productivity:.2f} + Consistencia {consistency_norm:.1f} × "
        f"{weights.consistency:.2f} + Retrabajo(inv) {rework_norm:.1f} × {weights.rework:.2f} = {final_score}."
    )

    return ScoreResult(
        score=final_score,
        classification=classify(final_score),
        data_confidence=confidence,
        sample_size=sample_size,
        distinct_days=distinct_days,
        breakdown=breakdown,
        explanation=explanation,
    )
