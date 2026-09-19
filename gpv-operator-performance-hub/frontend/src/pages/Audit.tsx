import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { AuditLogItem } from "../lib/types";
import DataTable, { type ColumnDef } from "../components/DataTable";
import Pagination from "../components/Pagination";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import { formatDateTime } from "../lib/format";

interface AuditResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export default function Audit() {
  const [data, setData] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<AuditResponse>(`/api/audit?page=${page}&page_size=30`);
      setData(result);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 403
            ? "Tu rol no tiene permiso para consultar el registro de auditoría."
            : err.message
          : "Ocurrió un error al cargar la auditoría."
      );
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnDef<AuditLogItem>[] = [
    { key: "timestamp", label: "Fecha y hora", render: (r) => formatDateTime(r.timestamp) },
    { key: "username", label: "Usuario", render: (r) => r.username },
    { key: "role", label: "Rol", render: (r) => r.role },
    { key: "action", label: "Acción", render: (r) => r.action },
    { key: "entity", label: "Entidad", render: (r) => r.entity || "—" },
    { key: "details", label: "Detalle", render: (r) => r.details || "—" },
  ];

  return (
    <>
      <div className="page-header">
        <h1>Auditoría</h1>
        <p className="page-subtitle">Registro de inicios de sesión, cambios de configuración y acciones de capacitación registradas en el sistema.</p>
      </div>

      <section className="panel">
        <div className="panel-body panel-body--tight" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {loading && <LoadingSkeleton rows={8} height={30} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && data && (
            <>
              <DataTable columns={columns} rows={data.items} rowKey={(r) => `${r.timestamp}-${r.username}-${r.action}`} compact />
              {data.items.length > 0 && (
                <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
              )}
            </>
          )}
        </div>
      </section>
    </>
  );
}
