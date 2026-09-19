from app.scoring import GroupSample, ScoringWeights, compute_score


def _sample(units=30, conforming=29, rejected=1, reworked=0, cycle=20.0, standard=20.0, day="2026-01-01"):
    return GroupSample(
        units_processed=units,
        units_conforming=conforming,
        units_rejected=rejected,
        units_reworked=reworked,
        cycle_time_seconds=cycle,
        standard_cycle_seconds=standard,
        event_date=day,
    )


def test_insufficient_data_below_minimum():
    samples = [_sample(units=5, conforming=5, rejected=0)]
    result = compute_score(samples, ScoringWeights(min_units=20))
    assert result.score is None
    assert result.classification == "Datos insuficientes"


def test_excellent_operator_scores_high():
    samples = [_sample(units=40, conforming=40, rejected=0, cycle=20.0, standard=20.0, day=f"2026-01-{d:02d}") for d in range(1, 6)]
    result = compute_score(samples, ScoringWeights(min_units=20))
    assert result.score is not None
    assert result.score >= 90
    assert result.classification == "Excelente"


def test_score_is_clamped_between_0_and_100():
    # Ciclo real muy por encima del estándar y muchos defectos -> score bajo, nunca negativo.
    samples = [
        _sample(units=50, conforming=20, rejected=30, reworked=15, cycle=80.0, standard=20.0, day=f"2026-02-{d:02d}")
        for d in range(1, 4)
    ]
    result = compute_score(samples, ScoringWeights(min_units=20))
    assert result.score is not None
    assert 0.0 <= result.score <= 100.0
    assert result.classification in {"Requiere apoyo", "En observación"}


def test_breakdown_is_traceable():
    samples = [_sample(units=30, conforming=28, rejected=2, day=f"2026-03-{d:02d}") for d in range(1, 3)]
    result = compute_score(samples, ScoringWeights(min_units=20))
    keys = {b.key for b in result.breakdown}
    assert keys == {"quality", "cycle", "productivity", "consistency", "rework"}
    weight_sum = sum(b.weight for b in result.breakdown)
    assert abs(weight_sum - 1.0) < 1e-6


def test_zero_division_is_avoided():
    samples = [_sample(units=25, conforming=25, rejected=0, cycle=0.0, standard=20.0, day="2026-04-01")]
    result = compute_score(samples, ScoringWeights(min_units=20))
    assert result.score is not None
    assert 0.0 <= result.score <= 100.0
