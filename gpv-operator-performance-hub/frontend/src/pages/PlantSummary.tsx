import { useEffect, useState, useCallback } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  BarChart,
  Bar,
  Cell,
  LineChart,
  Line,
  Legend,
} from "recharts";
import { AlertTriangle, Gauge } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useFilters } from "../lib/filters";
import type { PlantSummary as PlantSummaryType } from "../lib/types";
import StatCard from "../components/StatCard";
import { LoadingSkeleton, ErrorState, EmptyState } from "../components/StateBlocks";
import DisclaimerBanner from "../components/DisclaimerBanner";
import { formatDateTime } from "../lib/format";
import styles from "./PlantSummary.module.css";

const CLASSIFICATION_COLOR: Record<string, string> = {
  Excelente: "var(--color-op-green)",
  Bueno: "var(--color-reference-blue)",
  "En observación": "var(--color-attention-amber)",
  "Requiere apoyo": "var(--color-intervention-red)",
  "Datos insuficientes": "var(--color-tech-gray)",
};

const KPI_TOOLTIPS: Record<string, string> = {
  "First Pass Yield": "Porcentaje de unidades conformes a la primera, sin retrabajo.",
  "Tiempo de ciclo promedio": "Promedio del tiempo real por unidad en todas las estaciones activas.",
  "Tasa de retrabajo": "Porcentaje de unidades que requirieron un segundo pase de proceso.",
  "Cumplimiento contra estándar": "Relación entre el tiempo estándar de estación y el tiempo real registrado.",
};

export default function PlantSummary() {
  const { periodDays, shift } = useFilters();
  const [data, setData] = useState<PlantSummaryType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ period_days: String(periodDays) });
      if (shift) params.set("shift", shift);
      const result = await api.get<PlantSummaryType>(`/api/plant-summary?${params.toString()}`);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar el resumen de planta.");
    } finally {
      setLoading(false);
    }
  }, [periodDays, shift]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <div className="page-header">
        <h1>Resumen de planta</h1>
        <p className="page-subtitle">
          Vista general del desempeño operativo del periodo seleccionado. Los indicadores incluyen contexto para
          evitar lecturas aisladas.
        </p>
      </div>

      {loading && <LoadingSkeleton rows={6} height={90} />}
      {!loading && error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && data && (
        <>
          <div className="kpi-grid">
            {data.kpis.map((kpi) => (
              <StatCard key={kpi.label} kpi={kpi} tooltip={KPI_TOOLTIPS[kpi.label]} />
            ))}
          </div>

          <div className="two-col-grid">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Tendencia de producción por hora</h2>
                  <p className="panel-subtitle">Unidades procesadas por hora del día en el periodo filtrado.</p>
                </div>
              </div>
              <div className="panel-body">
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={data.hourly_trend} margin={{ left: -18, right: 8 }}>
                    <defs>
                      <linearGradient id="hourlyFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--color-steel-blue)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--color-steel-blue)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                    <XAxis dataKey="hour" tick={{ fontSize: 11 }} interval={2} stroke="var(--text-muted)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={40} />
                    <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                    <Area
                      type="monotone"
                      dataKey="units"
                      name="Unidades"
                      stroke="var(--color-steel-blue)"
                      fill="url(#hourlyFill)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Distribución de niveles de rendimiento</h2>
                  <p className="panel-subtitle">Cantidad de operadores por clasificación en el periodo.</p>
                </div>
              </div>
              <div className="panel-body">
                {data.performance_distribution.every((d) => d.count === 0) ? (
                  <EmptyState title="Sin clasificaciones" description="No hay operadores clasificados en este periodo." />
                ) : (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={data.performance_distribution} layout="vertical" margin={{ left: 8, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--text-muted)" allowDecimals={false} />
                      <YAxis
                        type="category"
                        dataKey="classification"
                        tick={{ fontSize: 11 }}
                        width={110}
                        stroke="var(--text-muted)"
                      />
                      <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                      <Bar dataKey="count" name="Operadores" radius={[0, 4, 4, 0]}>
                        {data.performance_distribution.map((entry) => (
                          <Cell key={entry.classification} fill={CLASSIFICATION_COLOR[entry.classification]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>
          </div>

          <div className="two-col-grid">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Calidad por estación</h2>
                  <p className="panel-subtitle">FPY y tasa de retrabajo por estación en el periodo.</p>
                </div>
              </div>
              <div className="panel-body">
                {data.quality_by_station.length === 0 ? (
                  <EmptyState title="Sin actividad" description="No hay eventos de producción en el periodo seleccionado." />
                ) : (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={data.quality_by_station} margin={{ left: -18, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                      <XAxis dataKey="station" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={70} stroke="var(--text-muted)" />
                      <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={40} />
                      <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="fpy" name="FPY %" fill="var(--color-op-green)" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="rework_rate" name="Retrabajo %" fill="var(--color-attention-amber)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Comparación entre turnos</h2>
                  <p className="panel-subtitle">Unidades procesadas y FPY por turno.</p>
                </div>
              </div>
              <div className="panel-body">
                {data.shift_comparison.length === 0 ? (
                  <EmptyState title="Sin datos" description="No hay actividad registrada para comparar turnos." />
                ) : (
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={data.shift_comparison} margin={{ left: -12, right: 12 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                      <XAxis dataKey="shift" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
                      <YAxis yAxisId="left" tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={40} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={40} />
                      <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Line yAxisId="left" type="monotone" dataKey="units_processed" name="Unidades" stroke="var(--color-steel-blue)" strokeWidth={2} />
                      <Line yAxisId="right" type="monotone" dataKey="fpy" name="FPY %" stroke="var(--color-reference-blue)" strokeWidth={2} strokeDasharray="4 3" />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>
          </div>

          <div className="two-col-grid">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Qué requiere atención hoy</h2>
                  <p className="panel-subtitle">Priorizado por severidad; incluye estaciones y operadores.</p>
                </div>
              </div>
              <div className="panel-body panel-body--tight">
                {data.attention_today.length === 0 ? (
                  <EmptyState title="Todo en orden" description="No se identificaron elementos que requieran atención inmediata." />
                ) : (
                  <ul className={styles.attentionList}>
                    {data.attention_today.map((item, i) => (
                      <li key={i} className={styles.attentionItem}>
                        <AlertTriangle size={15} color="var(--color-attention-amber)" style={{ flexShrink: 0, marginTop: 2 }} />
                        <div>
                          <div className={styles.attentionTitle}>
                            {item.title} <span className={styles.attentionCategory}>· {item.category}</span>
                          </div>
                          <div className={styles.attentionDetail}>{item.detail}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Anomalías recientes</h2>
                  <p className="panel-subtitle">Paros de estación y tasas de rechazo elevadas.</p>
                </div>
              </div>
              <div className="panel-body panel-body--tight">
                {data.recent_anomalies.length === 0 ? (
                  <EmptyState title="Sin anomalías" description="No se detectaron anomalías recientes en el periodo." />
                ) : (
                  <ul className={styles.attentionList}>
                    {data.recent_anomalies.map((item, i) => (
                      <li key={i} className={styles.attentionItem}>
                        <Gauge
                          size={15}
                          color={item.severity === "bad" ? "var(--color-intervention-red)" : "var(--color-attention-amber)"}
                          style={{ flexShrink: 0, marginTop: 2 }}
                        />
                        <div>
                          <div className={styles.attentionTitle}>{item.type}</div>
                          <div className={styles.attentionDetail}>{item.detail}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          </div>

          <div className={styles.footerRow}>
            <span className={styles.coverageNote}>
              Cobertura de datos: {data.data_coverage_pct.toFixed(1)}% de los operadores activos · Última actualización:{" "}
              {formatDateTime(data.last_sync)}
            </span>
          </div>

          <DisclaimerBanner />
        </>
      )}
    </>
  );
}
