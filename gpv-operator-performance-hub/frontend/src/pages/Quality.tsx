import { useCallback, useEffect, useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  BarChart,
  LineChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  Legend,
} from "recharts";
import { api, ApiError } from "../lib/api";
import { useFilters } from "../lib/filters";
import type { QualityOverview } from "../lib/types";
import { LoadingSkeleton, ErrorState, EmptyState } from "../components/StateBlocks";
import { formatNumber, formatPercent } from "../lib/format";
import styles from "./Quality.module.css";

function fpyTone(fpy: number | null) {
  if (fpy === null) return "var(--color-tech-gray)";
  if (fpy >= 97) return "var(--color-op-green)";
  if (fpy >= 90) return "var(--color-attention-amber)";
  return "var(--color-intervention-red)";
}

export default function Quality() {
  const { periodDays } = useFilters();
  const [data, setData] = useState<QualityOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<QualityOverview>(`/api/quality?period_days=${periodDays}`);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar la información de calidad.");
    } finally {
      setLoading(false);
    }
  }, [periodDays]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <div className="page-header">
        <h1>Calidad</h1>
        <p className="page-subtitle">
          Los defectos se clasifican por causa (proceso, material, equipo, programa, diseño, método, posible error
          operativo o causa sin confirmar). No se atribuyen automáticamente al operador.
        </p>
      </div>

      {loading && <LoadingSkeleton rows={6} height={80} />}
      {!loading && error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && data && (
        <>
          <div className={styles.summaryRow}>
            <div className="panel panel-body" style={{ flex: 1, minWidth: 200 }}>
              <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                Unidades bloqueadas
              </span>
              <div style={{ fontSize: "var(--font-size-xl)", fontWeight: 700 }}>{formatNumber(data.blocked_units)}</div>
            </div>
            <div className="panel panel-body" style={{ flex: 1, minWidth: 200 }}>
              <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                Validaciones fallidas
              </span>
              <div style={{ fontSize: "var(--font-size-xl)", fontWeight: 700 }}>{formatNumber(data.validation_failures)}</div>
            </div>
          </div>

          <div className="two-col-grid">
            <section className="panel">
              <div className="panel-header">
                <h2>Pareto de defectos</h2>
              </div>
              <div className="panel-body">
                {data.pareto.length === 0 ? (
                  <EmptyState title="Sin defectos" description="No se registraron defectos en el periodo seleccionado." />
                ) : (
                  <ResponsiveContainer width="100%" height={280}>
                    <ComposedChart data={data.pareto.slice(0, 10)} margin={{ left: -18, right: 12 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                      <XAxis dataKey="defect_code" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={60} stroke="var(--text-muted)" />
                      <YAxis yAxisId="left" tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} domain={[0, 100]} stroke="var(--text-muted)" width={36} />
                      <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar yAxisId="left" dataKey="quantity" name="Cantidad" fill="var(--color-intervention-red)" radius={[3, 3, 0, 0]} />
                      <Line yAxisId="right" dataKey="cumulative_pct" name="% acumulado" stroke="var(--color-steel-blue)" strokeWidth={2} dot={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>Retrabajos por causa</h2>
              </div>
              <div className="panel-body">
                {data.rework_by_cause.length === 0 ? (
                  <EmptyState title="Sin retrabajos" description="No se registraron retrabajos en el periodo." />
                ) : (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={data.rework_by_cause} layout="vertical" margin={{ left: 8, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
                      <YAxis type="category" dataKey="cause" tick={{ fontSize: 10 }} width={150} stroke="var(--text-muted)" />
                      <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                      <Bar dataKey="quantity" name="Cantidad" fill="var(--color-attention-amber)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>
          </div>

          <div className="two-col-grid">
            <section className="panel">
              <div className="panel-header">
                <h2>Defectos por estación y por producto</h2>
              </div>
              <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.defects_by_station} margin={{ left: -18, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                    <XAxis dataKey="station" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={60} stroke="var(--text-muted)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} />
                    <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                    <Bar dataKey="quantity" name="Defectos por estación" fill="var(--color-reference-blue)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.defects_by_product} margin={{ left: -18, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                    <XAxis dataKey="product" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={60} stroke="var(--text-muted)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} />
                    <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                    <Bar dataKey="quantity" name="Defectos por producto" fill="var(--color-steel-blue)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>FPY por turno y tendencia semanal</h2>
              </div>
              <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={data.fpy_by_shift} margin={{ left: -18, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                    <XAxis dataKey="shift" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} />
                    <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                    <Bar dataKey="fpy" name="FPY %" fill="var(--color-op-green)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data.weekly_trend} margin={{ left: -18, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                    <XAxis dataKey="week" tick={{ fontSize: 10 }} stroke="var(--text-muted)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} domain={[0, 100]} />
                    <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                    <Line dataKey="fpy" name="FPY semanal %" stroke="var(--color-reference-blue)" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>

          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Matriz estación-producto</h2>
                <p className="panel-subtitle">{data.note}</p>
              </div>
            </div>
            <div className="panel-body">
              {data.station_product_matrix.length === 0 ? (
                <EmptyState title="Sin datos" description="No hay combinaciones estación-producto en el periodo." />
              ) : (
                <div className={styles.matrixGrid}>
                  {data.station_product_matrix.map((cell, i) => (
                    <div key={i} className={styles.matrixCell} style={{ borderLeft: `3px solid ${fpyTone(cell.fpy)}` }}>
                      <strong>{formatPercent(cell.fpy)}</strong>
                      {cell.station} · {cell.product}
                      <div style={{ color: "var(--text-muted)" }}>{formatNumber(cell.units_processed)} unidades</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}
