import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Eye } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { OperatorListItem } from "../lib/types";
import DataTable, { type ColumnDef } from "../components/DataTable";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import { formatDate } from "../lib/format";

export default function Operators() {
  const navigate = useNavigate();
  const [items, setItems] = useState<OperatorListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      const result = await api.get<{ items: OperatorListItem[] }>(`/api/operators?${params.toString()}`);
      setItems(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar el directorio de operadores.");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const columns: ColumnDef<OperatorListItem>[] = [
    { key: "employee_number", label: "N.º empleado", render: (r) => r.employee_number },
    { key: "full_name", label: "Nombre", render: (r) => r.full_name },
    { key: "shift", label: "Turno", render: (r) => r.shift },
    { key: "area", label: "Área", render: (r) => r.area },
    { key: "hire_date", label: "Antigüedad", render: (r) => formatDate(r.hire_date) },
    {
      key: "is_new_hire",
      label: "Estado",
      render: (r) => (r.is_new_hire ? <span className="badge badge--warning">Ingreso reciente</span> : <span className="badge badge--neutral">Activo</span>),
    },
    { key: "authorized_station_count", label: "Estaciones autorizadas", align: "right", render: (r) => r.authorized_station_count },
    { key: "last_activity", label: "Última actividad", render: (r) => formatDate(r.last_activity) },
    {
      key: "actions",
      label: "",
      align: "right",
      render: (r) => (
        <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`/operadores/${r.id}`); }}>
          <Eye size={14} /> Ver detalles
        </button>
      ),
    },
  ];

  return (
    <>
      <div className="page-header">
        <h1>Operadores</h1>
        <p className="page-subtitle">Directorio del personal operativo activo, con acceso directo al detalle de cada persona.</p>
      </div>

      <div className="panel" style={{ padding: "var(--space-3) var(--space-4)" }}>
        <div style={{ position: "relative", maxWidth: 320 }}>
          <Search size={15} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            className="input"
            style={{ paddingLeft: 32 }}
            placeholder="Buscar por nombre o número de empleado"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <section className="panel">
        <div className="panel-body panel-body--tight">
          {loading && <LoadingSkeleton rows={8} height={32} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && (
            <DataTable
              columns={columns}
              rows={items}
              rowKey={(r) => r.id}
              onRowClick={(r) => navigate(`/operadores/${r.id}`)}
              emptyTitle="Sin operadores"
              emptyDescription="No se encontraron operadores para la búsqueda."
            />
          )}
        </div>
      </section>
    </>
  );
}
