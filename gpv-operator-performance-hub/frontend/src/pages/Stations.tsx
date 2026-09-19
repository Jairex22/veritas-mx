import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useFilters } from "../lib/filters";
import type { StationRow } from "../lib/types";
import DataTable, { type ColumnDef } from "../components/DataTable";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import Tooltip from "../components/Tooltip";
import { formatNumber, formatPercent } from "../lib/format";

const STATUS_TONE: Record<string, string> = {
  Operando: "badge--good",
  "Con alertas": "badge--warning",
  "Sin actividad": "badge--neutral",
};

export default function Stations() {
  const { periodDays } = useFilters();
  const [items, setItems] = useState<StationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<{ items: StationRow[] }>(`/api/stations?period_days=${periodDays}`);
      setItems(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar las estaciones.");
    } finally {
      setLoading(false);
    }
  }, [periodDays]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnDef<StationRow>[] = [
    { key: "name", label: "Estación", render: (r) => r.name },
    { key: "area", label: "Área", render: (r) => r.area },
    { key: "status", label: "Estado", render: (r) => <span className={`badge ${STATUS_TONE[r.status] ?? "badge--neutral"}`}>{r.status}</span> },
    { key: "active_operators", label: "Operadores activos", align: "right", render: (r) => r.active_operators },
    { key: "units_processed", label: "Unidades procesadas", align: "right", render: (r) => formatNumber(r.units_processed) },
    { key: "standard_cycle_seconds", label: "Tiempo estándar (s)", align: "right", render: (r) => formatNumber(r.standard_cycle_seconds, 1) },
    { key: "avg_cycle_time_seconds", label: "Tiempo real (s)", align: "right", render: (r) => (r.avg_cycle_time_seconds !== null ? formatNumber(r.avg_cycle_time_seconds, 1) : "—") },
    { key: "fpy", label: "FPY", align: "right", render: (r) => formatPercent(r.fpy) },
    { key: "rework_rate", label: "Retrabajo", align: "right", render: (r) => formatPercent(r.rework_rate) },
    { key: "queue_estimate", label: "Cola estimada (s)", align: "right", render: (r) => r.queue_estimate },
    { key: "trend", label: "Tendencia", render: (r) => r.trend },
    {
      key: "alerts",
      label: "Alertas",
      render: (r) =>
        r.alerts.length > 0 ? (
          <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--color-intervention-red)" }}>
            <AlertTriangle size={13} /> {r.alerts.join("; ")}
          </span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>—</span>
        ),
    },
  ];

  return (
    <>
      <div className="page-header">
        <h1>Estaciones</h1>
        <p className="page-subtitle">
          Comparación de estaciones del proceso: INITIALIZATION, THT AUTO INSERTION, HEATSINK INSERTION, AOI, POWER
          MODULE MEASUREMENT, ICT, FCT, DEPANEL, FINAL ASSEMBLY, FINAL TEST, PACKING y REWORK.
        </p>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Estado por estación</h2>
            <p className="panel-subtitle">Un tiempo real por encima del estándar puede ser causa de proceso, no del operador.</p>
          </div>
          <Tooltip text="La cola estimada aproxima el tiempo adicional por unidad respecto al estándar, no una medición directa de WIP." />
        </div>
        <div className="panel-body panel-body--tight">
          {loading && <LoadingSkeleton rows={8} height={32} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && <DataTable columns={columns} rows={items} rowKey={(r) => r.id} />}
        </div>
      </section>
    </>
  );
}
