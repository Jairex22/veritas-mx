import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Download, Columns3, Rows3 } from "lucide-react";
import { api, ApiError, API_BASE_URL, getToken } from "../lib/api";
import { useFilters } from "../lib/filters";
import type { PaginatedPerformance, PerformanceRow } from "../lib/types";
import DataTable, { type ColumnDef } from "../components/DataTable";
import Pagination from "../components/Pagination";
import Badge from "../components/Badge";
import ConfidenceTag from "../components/ConfidenceTag";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import DisclaimerBanner from "../components/DisclaimerBanner";
import { formatDate, formatNumber, formatPercent } from "../lib/format";
import styles from "./Performance.module.css";

const ALL_COLUMNS: ColumnDef<PerformanceRow>[] = [
  { key: "employee_number", label: "N.º empleado", sortable: false, render: (r) => r.employee_number },
  { key: "full_name", label: "Nombre", sortable: true, render: (r) => r.full_name },
  { key: "shift", label: "Turno", sortable: true, render: (r) => r.shift },
  { key: "area", label: "Área", sortable: true, render: (r) => r.area },
  { key: "line", label: "Línea", sortable: false, render: (r) => r.line },
  { key: "main_station", label: "Estación principal", sortable: false, render: (r) => r.main_station },
  { key: "product", label: "Producto", sortable: false, render: (r) => r.product },
  { key: "work_order", label: "Work Order", sortable: false, render: (r) => r.work_order },
  { key: "units_processed", label: "Unid. procesadas", sortable: true, align: "right", render: (r) => formatNumber(r.units_processed) },
  { key: "units_conforming", label: "Unid. conformes", sortable: false, align: "right", render: (r) => formatNumber(r.units_conforming) },
  { key: "units_rejected", label: "Rechazos", sortable: false, align: "right", render: (r) => formatNumber(r.units_rejected) },
  { key: "units_reworked", label: "Retrabajos", sortable: false, align: "right", render: (r) => formatNumber(r.units_reworked) },
  { key: "fpy", label: "FPY", sortable: true, align: "right", render: (r) => formatPercent(r.fpy) },
  { key: "avg_cycle_time_seconds", label: "Ciclo prom. (s)", sortable: true, align: "right", render: (r) => formatNumber(r.avg_cycle_time_seconds, 1) },
  { key: "cycle_compliance_pct", label: "Cumpl. estándar", sortable: true, align: "right", render: (r) => formatPercent(r.cycle_compliance_pct) },
  { key: "consistency_index", label: "Consistencia", sortable: true, align: "right", render: (r) => formatPercent(r.consistency_index) },
  { key: "data_confidence", label: "Confianza de datos", sortable: false, render: (r) => <ConfidenceTag level={r.data_confidence} /> },
  { key: "score", label: "Puntaje", sortable: true, align: "right", render: (r) => (r.score !== null ? formatNumber(r.score, 1) : "—") },
  { key: "classification", label: "Clasificación", sortable: false, render: (r) => <Badge classification={r.classification} /> },
  { key: "trend", label: "Tendencia", sortable: false, render: (r) => r.trend },
  { key: "last_activity", label: "Última actividad", sortable: true, render: (r) => formatDate(r.last_activity) },
];

const DEFAULT_VISIBLE = new Set(ALL_COLUMNS.map((c) => c.key));

export default function Performance() {
  const { periodDays, shift } = useFilters();
  const navigate = useNavigate();

  const [data, setData] = useState<PaginatedPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [area, setArea] = useState("");
  const [classification, setClassification] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sortBy, setSortBy] = useState("full_name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [compact, setCompact] = useState(false);
  const [columnMenuOpen, setColumnMenuOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(DEFAULT_VISIBLE);

  const buildParams = useCallback(() => {
    const params = new URLSearchParams({
      period_days: String(periodDays),
      page: String(page),
      page_size: String(pageSize),
      sort_by: sortBy,
      sort_dir: sortDir,
    });
    if (shift) params.set("shift", shift);
    if (area) params.set("area", area);
    if (classification) params.set("classification", classification);
    if (search) params.set("search", search);
    return params;
  }, [periodDays, shift, area, classification, search, page, pageSize, sortBy, sortDir]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<PaginatedPerformance>(`/api/performance?${buildParams().toString()}`);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar el rendimiento de los operadores.");
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  useEffect(() => {
    setPage(1);
  }, [search, area, classification, periodDays, shift]);

  function handleSort(key: string) {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("asc");
    }
  }

  function toggleColumn(key: string) {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const columns = useMemo(() => ALL_COLUMNS.filter((c) => visibleColumns.has(c.key)), [visibleColumns]);

  function exportCsv() {
    const params = buildParams();
    params.delete("page");
    params.delete("page_size");
    const token = getToken();
    const url = `${API_BASE_URL}/api/performance/export.csv?${params.toString()}`;
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((res) => res.blob())
      .then((blob) => {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "rendimiento_operadores.csv";
        link.click();
      });
  }

  return (
    <>
      <div className="page-header">
        <h1>Rendimiento</h1>
        <p className="page-subtitle">
          Tabla comparativa normalizada por estación, producto y turno. Los operadores en contextos distintos no se
          comparan directamente entre sí.
        </p>
      </div>

      <div className={`panel ${styles.toolbar}`} style={{ padding: "var(--space-3) var(--space-4)" }}>
        <div className={styles.searchBox}>
          <Search size={15} className={styles.searchIcon} />
          <input
            className="input"
            placeholder="Buscar por nombre o número de empleado"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className={`select ${styles.filterSelect}`} value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">Todas las áreas</option>
          <option value="SMT">SMT</option>
          <option value="Inserción">Inserción</option>
          <option value="Ensamble">Ensamble</option>
          <option value="Prueba">Prueba</option>
          <option value="Empaque">Empaque</option>
        </select>
        <select
          className={`select ${styles.filterSelect}`}
          value={classification}
          onChange={(e) => setClassification(e.target.value)}
        >
          <option value="">Todas las clasificaciones</option>
          <option value="Excelente">Excelente</option>
          <option value="Bueno">Bueno</option>
          <option value="En observación">En observación</option>
          <option value="Requiere apoyo">Requiere apoyo</option>
          <option value="Datos insuficientes">Datos insuficientes</option>
        </select>

        <div className={styles.spacer} />

        <button className="btn btn-secondary btn-sm" onClick={() => setCompact((v) => !v)}>
          <Rows3 size={14} /> {compact ? "Vista normal" : "Vista compacta"}
        </button>
        <div className={styles.columnMenu}>
          <button className="btn btn-secondary btn-sm" onClick={() => setColumnMenuOpen((v) => !v)}>
            <Columns3 size={14} /> Columnas
          </button>
          {columnMenuOpen && (
            <div className={styles.columnDropdown}>
              {ALL_COLUMNS.map((c) => (
                <label key={c.key}>
                  <input
                    type="checkbox"
                    checked={visibleColumns.has(c.key)}
                    onChange={() => toggleColumn(c.key)}
                  />
                  {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
        <button className="btn btn-primary btn-sm" onClick={exportCsv}>
          <Download size={14} /> Exportar CSV
        </button>
      </div>

      <section className="panel">
        <div className="panel-body panel-body--tight" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {loading && <LoadingSkeleton rows={8} height={32} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && data && (
            <>
              <DataTable
                columns={columns}
                rows={data.items}
                rowKey={(r) => r.operator_id}
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={handleSort}
                compact={compact}
                onRowClick={(r) => navigate(`/operadores/${r.operator_id}`)}
                emptyTitle="Sin operadores para estos filtros"
                emptyDescription="Ajusta el periodo, turno o clasificación para ver resultados."
              />
              {data.items.length > 0 && (
                <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
              )}
            </>
          )}
        </div>
      </section>

      <DisclaimerBanner />
    </>
  );
}
