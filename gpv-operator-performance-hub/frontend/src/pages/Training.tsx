import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { TrainingMatrixItem } from "../lib/types";
import DataTable, { type ColumnDef } from "../components/DataTable";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import { formatDate } from "../lib/format";

const LEVEL_TONE: Record<string, string> = {
  "No capacitado": "badge--bad",
  "En entrenamiento": "badge--warning",
  Supervisado: "badge--warning",
  Certificado: "badge--good",
  Instructor: "badge--excellent",
};

export default function Training() {
  const [items, setItems] = useState<TrainingMatrixItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState("");
  const [reinforcementOnly, setReinforcementOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<{ items: TrainingMatrixItem[] }>("/api/training/matrix");
      setItems(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar la matriz de capacitación.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = items.filter((i) => {
    if (levelFilter && i.level !== levelFilter) return false;
    if (reinforcementOnly && !i.reinforcement_needed) return false;
    return true;
  });

  const columns: ColumnDef<TrainingMatrixItem>[] = [
    { key: "employee_number", label: "N.º empleado", render: (r) => r.employee_number },
    { key: "operator_name", label: "Operador", render: (r) => r.operator_name },
    { key: "station", label: "Estación", render: (r) => r.station },
    { key: "level", label: "Nivel actual", render: (r) => <span className={`badge ${LEVEL_TONE[r.level] ?? "badge--neutral"}`}>{r.level}</span> },
    { key: "certified_at", label: "Certificación", render: (r) => formatDate(r.certified_at) },
    { key: "expires_at", label: "Vence", render: (r) => formatDate(r.expires_at) },
    {
      key: "reinforcement_needed",
      label: "Necesidad de refuerzo",
      render: (r) => (r.reinforcement_needed ? <span className="badge badge--warning">Sí</span> : <span className="badge badge--neutral">No</span>),
    },
    { key: "recommended_course", label: "Curso recomendado", render: (r) => r.recommended_course || "—" },
    { key: "plan_status", label: "Estado del plan", render: (r) => r.plan_status },
  ];

  return (
    <>
      <div className="page-header">
        <h1>Capacitación</h1>
        <p className="page-subtitle">Matriz de habilidades por operador y estación: nivel, certificación y necesidad de refuerzo.</p>
      </div>

      <div className="panel" style={{ padding: "var(--space-3) var(--space-4)", display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <select className="select" style={{ maxWidth: 220 }} value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}>
          <option value="">Todos los niveles</option>
          <option value="No capacitado">No capacitado</option>
          <option value="En entrenamiento">En entrenamiento</option>
          <option value="Supervisado">Supervisado</option>
          <option value="Certificado">Certificado</option>
          <option value="Instructor">Instructor</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-size-sm)" }}>
          <input type="checkbox" checked={reinforcementOnly} onChange={(e) => setReinforcementOnly(e.target.checked)} />
          Sólo con necesidad de refuerzo
        </label>
      </div>

      <section className="panel">
        <div className="panel-body panel-body--tight">
          {loading && <LoadingSkeleton rows={8} height={32} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && (
            <DataTable
              columns={columns}
              rows={filtered}
              rowKey={(r) => `${r.operator_id}-${r.station}`}
              emptyTitle="Sin registros"
              emptyDescription="No hay certificaciones para los filtros seleccionados."
            />
          )}
        </div>
      </section>
    </>
  );
}
