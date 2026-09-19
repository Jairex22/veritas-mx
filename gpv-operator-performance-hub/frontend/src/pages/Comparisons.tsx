import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useFilters } from "../lib/filters";
import type { ComparisonResult, StationRow } from "../lib/types";
import DataTable, { type ColumnDef } from "../components/DataTable";
import Badge from "../components/Badge";
import ConfidenceTag from "../components/ConfidenceTag";
import { LoadingSkeleton, ErrorState, EmptyState } from "../components/StateBlocks";
import { formatNumber } from "../lib/format";

export default function Comparisons() {
  const { periodDays, shift } = useFilters();
  const navigate = useNavigate();
  const [stations, setStations] = useState<StationRow[]>([]);
  const [stationId, setStationId] = useState<number | null>(null);
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ items: StationRow[] }>(`/api/stations?period_days=${periodDays}`).then((r) => {
      setStations(r.items);
      if (r.items.length > 0) setStationId(r.items[0].id);
    });
  }, [periodDays]);

  const load = useCallback(async () => {
    if (!stationId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ station_id: String(stationId), period_days: String(periodDays) });
      if (shift) params.set("shift", shift);
      const data = await api.get<ComparisonResult>(`/api/comparisons?${params.toString()}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al calcular la comparación.");
    } finally {
      setLoading(false);
    }
  }, [stationId, periodDays, shift]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnDef<ComparisonResult["items"][number]>[] = [
    { key: "employee_number", label: "N.º empleado", render: (r) => r.employee_number },
    { key: "full_name", label: "Operador", render: (r) => r.full_name },
    { key: "shift", label: "Turno", render: (r) => r.shift },
    { key: "units_processed", label: "Unidades", align: "right", render: (r) => formatNumber(r.units_processed) },
    { key: "data_confidence", label: "Confianza", render: (r) => <ConfidenceTag level={r.data_confidence} sampleSize={r.sample_size} /> },
    { key: "score", label: "Puntaje", align: "right", render: (r) => (r.score !== null ? formatNumber(r.score, 1) : "—") },
    { key: "classification", label: "Clasificación", render: (r) => <Badge classification={r.classification} /> },
  ];

  return (
    <>
      <div className="page-header">
        <h1>Comparaciones</h1>
        <p className="page-subtitle">
          Sólo se comparan operadores en el mismo contexto: misma estación, mismo turno (si se filtra) y mismo periodo.
        </p>
      </div>

      <div className="panel" style={{ padding: "var(--space-3) var(--space-4)" }}>
        <label className="field-label">Estación a comparar</label>
        <select
          className="select"
          style={{ maxWidth: 320 }}
          value={stationId ?? ""}
          onChange={(e) => setStationId(Number(e.target.value))}
        >
          {stations.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{result?.context.station ?? "Operadores equivalentes"}</h2>
            <p className="panel-subtitle">{result?.note}</p>
          </div>
        </div>
        <div className="panel-body panel-body--tight">
          {loading && <LoadingSkeleton rows={6} height={32} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && result && result.items.length === 0 && (
            <EmptyState title="Sin operadores comparables" description="No hay operadores con actividad en esta estación durante el periodo." />
          )}
          {!loading && !error && result && result.items.length > 0 && (
            <DataTable
              columns={columns}
              rows={result.items}
              rowKey={(r) => r.operator_id}
              onRowClick={(r) => navigate(`/operadores/${r.operator_id}`)}
            />
          )}
        </div>
      </section>
    </>
  );
}
