import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, button, buttonSecondary } from "./adminUi";

interface Metrics {
  conversations: number;
  requestsTotal: number;
  contactsRequested: number;
  requestsByStatus: Record<string, number>;
}

export default function AdminDashboardPage() {
  const api = adminApi(getAdminToken());
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [me, setMe] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setMetrics((await api.metrics()) as Metrics);
      setMe(await api.me());
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function togglePause() {
    if (!me) return;
    setBusy(true);
    try {
      await api.pauseAi(!me.business.aiPaused);
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p style={{ color: "var(--cf-danger)" }}>{error}</p>;
  if (!metrics || !me) return <p>Cargando…</p>;

  return (
    <div>
      <h1>Panel de {me.business.name}</h1>
      <p style={{ color: "var(--cf-text-muted)" }}>
        Estas son métricas verificables (conteos reales de la base de datos), no cifras de "ventas" ni ingresos.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 16, marginBottom: 20 }}>
        <MetricCard label="Conversaciones" value={metrics.conversations} />
        <MetricCard label="Solicitudes registradas" value={metrics.requestsTotal} />
        <MetricCard label="Contactos solicitados" value={metrics.contactsRequested} />
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Solicitudes por estado</h3>
        <ul>
          {Object.entries(metrics.requestsByStatus).map(([status, count]) => (
            <li key={status}>
              {status}: {count}
            </li>
          ))}
          {Object.keys(metrics.requestsByStatus).length === 0 && <li>Sin solicitudes todavía.</li>}
        </ul>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Estado de la IA</h3>
        <p>
          Modelo configurado: <strong>{me.business.aiModel}</strong>
        </p>
        <p>
          Estado actual: <strong>{me.business.aiPaused ? "Pausado" : "Activo"}</strong>
        </p>
        <button style={me.business.aiPaused ? button : buttonSecondary} onClick={togglePause} disabled={busy}>
          {me.business.aiPaused ? "Reactivar asistente" : "Pausar asistente"}
        </button>
        <p style={{ fontSize: 12, color: "var(--cf-text-muted)", marginTop: 10 }}>
          Al pausar, el chat deja de responder automáticamente en todas las conversaciones hasta que lo reactives.
        </p>
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 12, color: "var(--cf-text-muted)", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 800, color: "var(--cf-petrol)" }}>{value}</div>
    </div>
  );
}
