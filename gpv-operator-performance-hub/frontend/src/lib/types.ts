export type Classification = "Excelente" | "Bueno" | "En observación" | "Requiere apoyo" | "Datos insuficientes";

export interface KpiValue {
  label: string;
  value: string;
  context: string;
  trend_direction: "up" | "down" | "neutral";
  tone: "good" | "warning" | "bad" | "neutral";
}

export interface PlantSummary {
  kpis: KpiValue[];
  hourly_trend: { hour: string; units: number }[];
  quality_by_station: { station: string; fpy: number | null; rework_rate: number | null }[];
  performance_distribution: { classification: string; count: number; tone: string }[];
  shift_comparison: { shift: string; units_processed: number; fpy: number }[];
  recent_anomalies: { type: string; detail: string; severity: string }[];
  attention_today: { title: string; detail: string; category: string }[];
  data_coverage_pct: number;
  last_sync: string | null;
}

export interface PerformanceRow {
  operator_id: number;
  employee_number: string;
  full_name: string;
  shift: string;
  area: string;
  line: string;
  main_station: string;
  product: string;
  work_order: string;
  units_processed: number;
  units_conforming: number;
  units_rejected: number;
  units_reworked: number;
  fpy: number;
  avg_cycle_time_seconds: number;
  cycle_compliance_pct: number;
  consistency_index: number;
  data_confidence: string;
  score: number | null;
  classification: Classification;
  trend: string;
  last_activity: string | null;
}

export interface PaginatedPerformance {
  items: PerformanceRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface ScoreBreakdownItem {
  key: string;
  label: string;
  raw_value: number;
  normalized_value: number;
  weight: number;
  contribution: number;
}

export interface ScoreResult {
  score: number | null;
  classification: Classification;
  data_confidence: string;
  sample_size: number;
  distinct_days: number;
  breakdown: ScoreBreakdownItem[];
  explanation: string;
  disclaimer: string;
}

export interface OperatorListItem {
  id: number;
  employee_number: string;
  full_name: string;
  shift: string;
  area: string;
  hire_date: string;
  is_new_hire: boolean;
  authorized_station_count: number;
  last_activity: string | null;
}

export interface OperatorDetail {
  operator: {
    id: number;
    employee_number: string;
    full_name: string;
    shift: string;
    area: string;
    hire_date: string;
    is_new_hire: boolean;
    last_activity: string | null;
    authorized_stations: string[];
  };
  trends: { d7: ScoreResult; d30: ScoreResult; d90: ScoreResult };
  daily_series: { date: string; processed: number; conforming: number; rejected: number; reworked: number; fpy: number | null }[];
  station_history: {
    station: string;
    units_processed: number;
    fpy: number | null;
    avg_cycle_time_seconds: number;
    standard_cycle_seconds: number;
    compliance_pct: number | null;
  }[];
  group_comparison: { operator_score_90d: number | null; group_average_90d: number | null };
  products_worked: { product: string; work_order: string; units: number }[];
  certifications: {
    station: string;
    level: string;
    certified_at: string | null;
    expires_at: string | null;
    reinforcement_needed: boolean;
    recommended_course: string;
    plan_status: string;
  }[];
  context_factors: string[];
  recommendations: string[];
  supervisor_notes: { author: string; note: string; created_at: string }[];
  training_actions: { action_type: string; description: string; status: string; created_at: string; created_by: string }[];
}

export interface StationRow {
  id: number;
  name: string;
  code: string;
  area: string;
  status: string;
  active_operators: number;
  units_processed: number;
  standard_cycle_seconds: number;
  avg_cycle_time_seconds: number | null;
  fpy: number | null;
  rework_rate: number | null;
  queue_estimate: number;
  alerts: string[];
  trend: string;
}

export interface QualityOverview {
  pareto: { defect_code: string; description: string; cause: string; quantity: number; cumulative_pct: number }[];
  defects_by_station: { station: string; quantity: number }[];
  defects_by_product: { product: string; quantity: number }[];
  fpy_by_shift: { shift: string; fpy: number }[];
  rework_by_cause: { cause: string; quantity: number }[];
  weekly_trend: { week: string; fpy: number }[];
  blocked_units: number;
  validation_failures: number;
  station_product_matrix: { station: string; product: string; fpy: number | null; units_processed: number }[];
  note: string;
}

export interface TrainingMatrixItem {
  operator_id: number;
  employee_number: string;
  operator_name: string;
  station: string;
  level: string;
  certified_at: string | null;
  expires_at: string | null;
  reinforcement_needed: boolean;
  recommended_course: string;
  plan_status: string;
}

export interface AlertItem {
  category: string;
  severity: string;
  title: string;
  detail: string;
  context: string;
}

export interface AuditLogItem {
  timestamp: string;
  username: string;
  role: string;
  action: string;
  entity: string;
  entity_id: string;
  details: string;
  ip_address: string;
}

export interface ScoringConfig {
  weight_quality: number;
  weight_cycle: number;
  weight_productivity: number;
  weight_consistency: number;
  weight_rework: number;
  min_units_for_classification: number;
  updated_at: string;
  updated_by: string;
}

export interface SystemStatus {
  plant_name: string;
  environment: string;
  factorylogix_enabled: boolean;
  last_sync: string;
  status: string;
  message: string;
}

export interface ComparisonResult {
  context: { station: string | null; product: string; shift: string; period_days: number };
  items: {
    operator_id: number;
    employee_number: string;
    full_name: string;
    shift: string;
    score: number | null;
    classification: Classification;
    data_confidence: string;
    sample_size: number;
    units_processed: number;
  }[];
  note: string;
}
