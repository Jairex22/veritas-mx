import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, AlertOctagon, Info } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useFilters } from "../lib/filters";
import type { AlertItem } from "../lib/types";
import { LoadingSkeleton, ErrorState, EmptyState } from "../components/StateBlocks";

const SEVERITY_ICON = { bad: AlertOctagon, warning: AlertTriangle, neutral: Info };
const SEVERITY_COLOR: Record<string, string> = {
  bad: "var(--color-intervention-red)",
  warning: "var(--color-attention-amber)",
  neutral: "var(--text-muted)",
};

export default function Alerts() {
  const { periodDays } = useFilters();
  const [items, setItems] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<{ items: AlertItem[] }>(`/api/alerts?period_days=${periodDays}`);
      setItems(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar las alertas.");
    } finally {
      setLoading(false);
    }
  }, [periodDays]);

  useEffect(() => {
    load();
  }, [load]);

  const categories = Array.from(new Set(items.map((i) => i.category)));
  const filtered = category ? items.filter((i) => i.category === category) : items;

  return (
    <>
      <div className="page-header">
        <h1>Alertas</h1>
        <p className="page-subtitle">
          Estaciones con riesgo de proceso, operadores que requieren apoyo, certificaciones por vencer y cobertura de
          datos. Revisa el contexto antes de actuar.
        </p>
      </div>

      <div className="panel" style={{ padding: "var(--space-3) var(--space-4)" }}>
        <select className="select" style={{ maxWidth: 260 }} value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Todas las categorías</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <section className="panel">
        <div className="panel-body panel-body--tight">
          {loading && <LoadingSkeleton rows={6} height={50} />}
          {!loading && error && <ErrorState message={error} onRetry={load} />}
          {!loading && !error && filtered.length === 0 && (
            <EmptyState title="Sin alertas" description="No se identificaron elementos que requieran atención en este periodo." />
          )}
          {!loading && !error && filtered.length > 0 && (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column" }}>
              {filtered.map((a, i) => {
                const Icon = SEVERITY_ICON[a.severity as keyof typeof SEVERITY_ICON] ?? Info;
                return (
                  <li
                    key={i}
                    style={{
                      display: "flex",
                      gap: "var(--space-3)",
                      padding: "var(--space-3) var(--space-2)",
                      borderBottom: "1px solid var(--border-subtle)",
                    }}
                  >
                    <Icon size={18} color={SEVERITY_COLOR[a.severity] ?? "var(--text-muted)"} style={{ flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <div style={{ fontSize: "var(--font-size-sm)", fontWeight: 600 }}>
                        {a.title} <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>· {a.category}</span>
                      </div>
                      <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-secondary)", marginTop: 2 }}>{a.detail}</div>
                      {a.context && (
                        <div style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)", marginTop: 2, fontStyle: "italic" }}>
                          {a.context}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
    </>
  );
}
