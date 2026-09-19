"""Esquemas Pydantic de entrada/salida de la API."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    display_name: str
    role: str
    username: str


class ScoreBreakdownOut(BaseModel):
    key: str
    label: str
    raw_value: float
    normalized_value: float
    weight: float
    contribution: float


class ScoreOut(BaseModel):
    score: float | None
    classification: str
    data_confidence: str
    sample_size: int
    distinct_days: int
    breakdown: list[ScoreBreakdownOut]
    explanation: str
    disclaimer: str


class PerformanceRow(BaseModel):
    operator_id: int
    employee_number: str
    full_name: str
    shift: str
    area: str
    line: str
    main_station: str
    product: str
    work_order: str
    units_processed: int
    units_conforming: int
    units_rejected: int
    units_reworked: int
    fpy: float
    avg_cycle_time_seconds: float
    cycle_compliance_pct: float
    consistency_index: float
    data_confidence: str
    score: float | None
    classification: str
    trend: str
    last_activity: date | None


class PaginatedPerformance(BaseModel):
    items: list[PerformanceRow]
    total: int
    page: int
    page_size: int


class KpiValue(BaseModel):
    label: str
    value: str
    context: str
    trend_direction: str = "neutral"  # up | down | neutral
    tone: str = "neutral"  # good | warning | bad | neutral


class PlantSummaryOut(BaseModel):
    kpis: list[KpiValue]
    hourly_trend: list[dict]
    quality_by_station: list[dict]
    performance_distribution: list[dict]
    shift_comparison: list[dict]
    recent_anomalies: list[dict]
    attention_today: list[dict]
    data_coverage_pct: float
    last_sync: datetime | None


class ScoringConfigOut(BaseModel):
    weight_quality: float
    weight_cycle: float
    weight_productivity: float
    weight_consistency: float
    weight_rework: float
    min_units_for_classification: int
    updated_at: datetime
    updated_by: str


class ScoringConfigUpdate(BaseModel):
    weight_quality: float = Field(ge=0, le=1)
    weight_cycle: float = Field(ge=0, le=1)
    weight_productivity: float = Field(ge=0, le=1)
    weight_consistency: float = Field(ge=0, le=1)
    weight_rework: float = Field(ge=0, le=1)
    min_units_for_classification: int = Field(ge=1, le=1000)


class TrainingActionCreate(BaseModel):
    operator_id: int
    station_id: int | None = None
    action_type: str
    description: str


class SupervisorNoteCreate(BaseModel):
    operator_id: int
    note: str
