import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer, Legend } from "recharts";
import { CheckCircle2, Clock, ArrowLeft } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { OperatorDetail as OperatorDetailType, ScoreResult } from "../lib/types";
import Badge from "../components/Badge";
import ConfidenceTag from "../components/ConfidenceTag";
import DisclaimerBanner from "../components/DisclaimerBanner";
import Breadcrumbs from "../components/Breadcrumbs";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import { formatDate, formatDateTime, formatNumber, formatPercent } from "../lib/format";
import DataTable, { type ColumnDef } from "../components/DataTable";
import styles from "./OperatorDetail.module.css";

const CAN_WRITE_ROLES = new Set(["Administrador", "Ingeniero MES", "Supervisor", "Líder de línea"]);

export default function OperatorDetail() {
  const { operatorId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [data, setData] = useState<OperatorDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTrend, setActiveTrend] = useState<"d7" | "d30" | "d90">("d30");
  const [noteText, setNoteText] = useState("");
  const [actionText, setActionText] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [savingAction, setSavingAction] = useState(false);

  const load = useCallback(async () => {
    if (!operatorId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<OperatorDetailType>(`/api/operators/${operatorId}`);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar el detalle del operador.");
    } finally {
      setLoading(false);
    }
  }, [operatorId]);

  useEffect(() => {
    load();
  }, [load]);

  async function submitNote() {
    if (!noteText.trim() || !operatorId) return;
    setSavingNote(true);
    try {
      await api.post("/api/operators/supervisor-notes", { operator_id: Number(operatorId), note: noteText.trim() });
      setNoteText("");
      await load();
    } finally {
      setSavingNote(false);
    }
  }

  async function submitAction() {
    if (!actionText.trim() || !operatorId) return;
    setSavingAction(true);
    try {
      await api.post("/api/operators/training-actions", {
        operator_id: Number(operatorId),
        action_type: "Reforzamiento sugerido",
        description: actionText.trim(),
      });
      setActionText("");
      await load();
    } finally {
      setSavingAction(false);
    }
  }

  if (loading) return <LoadingSkeleton rows={10} height={40} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const { operator } = data;
  const trend: ScoreResult = data.trends[activeTrend];
  const canWrite = user ? CAN_WRITE_ROLES.has(user.role) : false;

  const stationColumns: ColumnDef<(typeof data.station_history)[number]>[] = [
    { key: "station", label: "Estación", render: (r) => r.station },
    { key: "units_processed", label: "Unidades", align: "right", render: (r) => formatNumber(r.units_processed) },
    { key: "fpy", label: "FPY", align: "right", render: (r) => formatPercent(r.fpy) },
    { key: "avg_cycle_time_seconds", label: "Ciclo real (s)", align: "right", render: (r) => formatNumber(r.avg_cycle_time_seconds, 1) },
    { key: "standard_cycle_seconds", label: "Ciclo estándar (s)", align: "right", render: (r) => formatNumber(r.standard_cycle_seconds, 1) },
    { key: "compliance_pct", label: "Cumplimiento", align: "right", render: (r) => formatPercent(r.compliance_pct) },
  ];

  const productColumns: ColumnDef<(typeof data.products_worked)[number]>[] = [
    { key: "product", label: "Producto", render: (r) => r.product },
    { key: "work_order", label: "Work Order", render: (r) => r.work_order },
    { key: "units", label: "Unidades", align: "right", render: (r) => formatNumber(r.units) },
  ];

  const certColumns: ColumnDef<(typeof data.certifications)[number]>[] = [
    { key: "station", label: "Estación", render: (r) => r.station },
    { key: "level", label: "Nivel", render: (r) => r.level },
    { key: "certified_at", label: "Certificado", render: (r) => formatDate(r.certified_at) },
    { key: "expires_at", label: "Vence", render: (r) => formatDate(r.expires_at) },
    { key: "plan_status", label: "Plan", render: (r) => r.plan_status },
  ];

  return (
    <>
      <Breadcrumbs items={[{ label: "Rendimiento", to: "/rendimiento" }, { label: operator.full_name }]} />

      <button className="btn btn-ghost btn-sm" style={{ width: "fit-content" }} onClick={() => navigate(-1)}>
        <ArrowLeft size={14} /> Volver
      </button>

      <section className={`panel ${styles.headerPanel}`}>
        <div className={styles.avatar}>
          {operator.full_name
            .split(" ")
            .slice(0, 2)
            .map((n) => n[0])
            .join("")
            .toUpperCase()}
        </div>
        <div className={styles.headerMeta}>
          <span className={styles.headerName}>{operator.full_name}</span>
          <span className={styles.headerSub}>
            <span>N.º {operator.employee_number}</span>
            <span>{operator.shift}</span>
            <span>{operator.area}</span>
            <span>
              <Clock size={12} style={{ verticalAlign: -1 }} /> Ingreso: {formatDate(operator.hire_date)}
            </span>
            <span>Última actividad: {formatDate(operator.last_activity)}</span>
          </span>
        </div>
        <div className={styles.headerTags}>
          {operator.is_new_hire && <span className="badge badge--warning">Ingreso reciente</span>}
          <Badge classification={trend.classification} />
          <ConfidenceTag level={trend.data_confidence} sampleSize={trend.sample_size} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Rendimiento actual</h2>
            <p className="panel-subtitle">Selecciona la ventana de tiempo para ver el puntaje y su desglose.</p>
          </div>
          <div className={styles.tabRow}>
            {(["d7", "d30", "d90"] as const).map((key) => (
              <button
                key={key}
                className={`${styles.tabBtn} ${activeTrend === key ? styles.tabBtnActive : ""}`}
                onClick={() => setActiveTrend(key)}
              >
                {key === "d7" ? "7 días" : key === "d30" ? "30 días" : "90 días"}
              </button>
            ))}
          </div>
        </div>
        <div className="panel-body">
          {trend.score === null ? (
            <ErrorState message={trend.explanation} />
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-4)", marginBottom: "var(--space-4)" }}>
                <span style={{ fontSize: "var(--font-size-xxl)", fontWeight: 700 }}>{formatNumber(trend.score, 1)}</span>
                <Badge classification={trend.classification} />
              </div>
              <div className={styles.breakdownGrid}>
                {trend.breakdown.map((b) => (
                  <div key={b.key} className={styles.breakdownRow}>
                    <span>{b.label}</span>
                    <div className="linear-meter">
                      <span
                        style={{
                          width: `${Math.min(100, b.normalized_value)}%`,
                          background: "var(--color-steel-blue)",
                        }}
                      />
                    </div>
                    <span style={{ textAlign: "right" }}>{formatNumber(b.normalized_value, 1)}</span>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)", marginTop: "var(--space-3)" }}>
                {trend.explanation}
              </p>
            </>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Producción por día (90 días)</h2>
            <p className="panel-subtitle">Unidades procesadas y FPY diario.</p>
          </div>
        </div>
        <div className="panel-body">
          {data.daily_series.length === 0 ? (
            <ErrorState message="Todavía no hay suficientes unidades para calcular una tendencia confiable." />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data.daily_series} margin={{ left: -12, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval={6} stroke="var(--text-muted)" />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={36} domain={[0, 100]} />
                <RTooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="processed" name="Unidades" fill="var(--color-steel-blue)" radius={[3, 3, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="fpy" name="FPY %" stroke="var(--color-op-green)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <div className="two-col-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Historial por estación</h2>
          </div>
          <div className="panel-body panel-body--tight">
            <DataTable columns={stationColumns} rows={data.station_history} rowKey={(r) => r.station} compact />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Comparación contra el grupo equivalente</h2>
          </div>
          <div className="panel-body">
            <div className={styles.comparisonRow}>
              <div className={styles.comparisonStat}>
                <span className={styles.comparisonValue}>
                  {data.group_comparison.operator_score_90d !== null ? formatNumber(data.group_comparison.operator_score_90d, 1) : "—"}
                </span>
                <span className={styles.comparisonLabel}>Puntaje del operador (90 días)</span>
              </div>
              <div className={styles.comparisonStat}>
                <span className={styles.comparisonValue}>
                  {data.group_comparison.group_average_90d !== null ? formatNumber(data.group_comparison.group_average_90d, 1) : "—"}
                </span>
                <span className={styles.comparisonLabel}>Promedio del grupo (mismo turno y área)</span>
              </div>
            </div>
            <p style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)", marginTop: "var(--space-3)" }}>
              El grupo equivalente considera operadores del mismo turno y área. Este resultado cambió si el operador
              trabajó en una estación diferente durante el periodo.
            </p>
          </div>
        </section>
      </div>

      <div className="two-col-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Productos y Work Orders trabajados</h2>
          </div>
          <div className="panel-body panel-body--tight">
            <DataTable columns={productColumns} rows={data.products_worked} rowKey={(r) => `${r.product}-${r.work_order}`} compact />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Certificaciones y estaciones autorizadas</h2>
          </div>
          <div className="panel-body panel-body--tight">
            <DataTable columns={certColumns} rows={data.certifications} rowKey={(r) => r.station} compact />
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Contexto del resultado</h2>
            <p className="panel-subtitle">
              Factores detectados que pueden explicar el resultado y que no necesariamente son responsabilidad del operador.
            </p>
          </div>
        </div>
        <div className="panel-body panel-body--tight">
          <ul className={styles.contextList}>
            {data.context_factors.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      </section>

      <div className="two-col-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Recomendaciones de capacitación</h2>
          </div>
          <div className="panel-body panel-body--tight" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <ul className={styles.recommendList}>
              {data.recommendations.map((r, i) => (
                <li key={i}>
                  <CheckCircle2 size={13} style={{ verticalAlign: -2, marginRight: 6, color: "var(--color-steel-blue)" }} />
                  {r}
                </li>
              ))}
            </ul>
            {canWrite && (
              <div className={styles.formRow}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label className="field-label">Nueva acción de capacitación</label>
                  <input className="input" value={actionText} onChange={(e) => setActionText(e.target.value)} />
                </div>
                <button className="btn btn-primary btn-sm" disabled={savingAction} onClick={submitAction}>
                  {savingAction ? "Guardando…" : "Registrar acción"}
                </button>
              </div>
            )}
            <ul className={styles.trainingList}>
              {data.training_actions.map((t, i) => (
                <li key={i} className={styles.trainingItem}>
                  <div className={styles.noteMeta}>
                    {t.action_type} · {t.status} · {formatDate(t.created_at)} · {t.created_by}
                  </div>
                  {t.description}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Observaciones del supervisor</h2>
          </div>
          <div className="panel-body panel-body--tight" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            {canWrite && (
              <div className={styles.formRow}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label className="field-label">Nueva observación</label>
                  <input className="input" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
                </div>
                <button className="btn btn-primary btn-sm" disabled={savingNote} onClick={submitNote}>
                  {savingNote ? "Guardando…" : "Agregar"}
                </button>
              </div>
            )}
            <ul className={styles.noteList}>
              {data.supervisor_notes.length === 0 && (
                <li style={{ color: "var(--text-muted)", fontSize: "var(--font-size-sm)" }}>Sin observaciones registradas.</li>
              )}
              {data.supervisor_notes.map((n, i) => (
                <li key={i} className={styles.noteItem}>
                  <div className={styles.noteMeta}>
                    {n.author} · {formatDateTime(n.created_at)}
                  </div>
                  {n.note}
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>

      <DisclaimerBanner />
    </>
  );
}
