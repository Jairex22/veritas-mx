import { useCallback, useEffect, useState } from "react";
import { Save } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { ScoringConfig, SystemStatus } from "../lib/types";
import { LoadingSkeleton, ErrorState } from "../components/StateBlocks";
import DisclaimerBanner from "../components/DisclaimerBanner";
import { formatDateTime } from "../lib/format";

const CAN_EDIT_ROLES = new Set(["Administrador", "Ingeniero MES"]);

const WEIGHT_FIELDS: { key: keyof ScoringConfig; label: string }[] = [
  { key: "weight_quality", label: "Calidad / FPY" },
  { key: "weight_cycle", label: "Cumplimiento de tiempo de ciclo" },
  { key: "weight_productivity", label: "Productividad normalizada" },
  { key: "weight_consistency", label: "Consistencia" },
  { key: "weight_rework", label: "Retrabajo (invertido)" },
];

export default function Settings() {
  const { user } = useAuth();
  const canEdit = user ? CAN_EDIT_ROLES.has(user.role) : false;

  const [config, setConfig] = useState<ScoringConfig | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, number>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfg, st] = await Promise.all([
        api.get<ScoringConfig>("/api/config/scoring"),
        api.get<SystemStatus>("/api/system/status"),
      ]);
      setConfig(cfg);
      setStatus(st);
      setForm({
        weight_quality: cfg.weight_quality,
        weight_cycle: cfg.weight_cycle,
        weight_productivity: cfg.weight_productivity,
        weight_consistency: cfg.weight_consistency,
        weight_rework: cfg.weight_rework,
        min_units_for_classification: cfg.min_units_for_classification,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error al cargar la configuración.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const totalWeight = WEIGHT_FIELDS.reduce((sum, f) => sum + (form[f.key as string] ?? 0), 0);

  async function handleSave() {
    setSaving(true);
    setSaveMessage(null);
    try {
      const updated = await api.put<ScoringConfig>("/api/config/scoring", {
        weight_quality: form.weight_quality,
        weight_cycle: form.weight_cycle,
        weight_productivity: form.weight_productivity,
        weight_consistency: form.weight_consistency,
        weight_rework: form.weight_rework,
        min_units_for_classification: form.min_units_for_classification,
      });
      setConfig(updated);
      setSaveMessage("Configuración actualizada correctamente.");
    } catch (err) {
      setSaveMessage(err instanceof ApiError ? err.message : "No fue posible guardar la configuración.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Configuración</h1>
        <p className="page-subtitle">Ajusta los pesos del motor de puntaje y revisa el estado de la integración con FactoryLogix.</p>
      </div>

      {loading && <LoadingSkeleton rows={6} height={40} />}
      {!loading && error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && config && (
        <>
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Motor de puntaje</h2>
                <p className="panel-subtitle">
                  puntaje = calidad×{form.weight_quality?.toFixed(2)} + ciclo×{form.weight_cycle?.toFixed(2)} +
                  productividad×{form.weight_productivity?.toFixed(2)} + consistencia×{form.weight_consistency?.toFixed(2)} +
                  retrabajo(inv)×{form.weight_rework?.toFixed(2)}
                </p>
              </div>
            </div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              {WEIGHT_FIELDS.map((f) => (
                <div key={f.key as string}>
                  <label className="field-label">
                    {f.label} — {((form[f.key as string] ?? 0) * 100).toFixed(0)}%
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    disabled={!canEdit}
                    value={form[f.key as string] ?? 0}
                    onChange={(e) => setForm((prev) => ({ ...prev, [f.key as string]: Number(e.target.value) }))}
                    style={{ width: "100%" }}
                  />
                </div>
              ))}
              <div>
                <label className="field-label">Mínimo de unidades para clasificar</label>
                <input
                  type="number"
                  className="input"
                  style={{ maxWidth: 160 }}
                  disabled={!canEdit}
                  value={form.min_units_for_classification ?? 20}
                  onChange={(e) => setForm((prev) => ({ ...prev, min_units_for_classification: Number(e.target.value) }))}
                />
              </div>

              <p style={{ fontSize: "var(--font-size-xs)", color: Math.abs(totalWeight - 1) > 0.01 ? "var(--color-attention-amber)" : "var(--text-muted)" }}>
                Suma de pesos actual: {(totalWeight * 100).toFixed(0)}%. Si no suma 100%, el sistema normaliza
                automáticamente antes de calcular el puntaje.
              </p>

              {canEdit ? (
                <div>
                  <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                    <Save size={15} /> {saving ? "Guardando…" : "Guardar cambios"}
                  </button>
                  {saveMessage && <p style={{ fontSize: "var(--font-size-sm)", marginTop: "var(--space-2)" }}>{saveMessage}</p>}
                </div>
              ) : (
                <p style={{ fontSize: "var(--font-size-sm)", color: "var(--text-muted)" }}>
                  Tu rol ({user?.role}) puede consultar esta configuración pero no modificarla.
                </p>
              )}

              <p style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>
                Última actualización: {formatDateTime(config.updated_at)} por {config.updated_by}
              </p>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Conexión con FactoryLogix Analytics</h2>
            </div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", fontSize: "var(--font-size-sm)" }}>
              <span>Planta: {status?.plant_name}</span>
              <span>Ambiente: {status?.environment}</span>
              <span>FactoryLogix habilitado: {status?.factorylogix_enabled ? "Sí" : "No (usando datos simulados)"}</span>
              <span>Estado: {status?.message}</span>
              <p style={{ color: "var(--text-muted)", fontSize: "var(--font-size-xs)" }}>
                La URL, entidad, usuario y contraseña de FactoryLogix se configuran en el archivo{" "}
                <code>backend/.env</code>. Ver <code>MANUAL_FACTORYLOGIX.md</code> para más detalle. Las credenciales
                nunca se guardan ni se muestran en el frontend.
              </p>
            </div>
          </section>

          <DisclaimerBanner />
        </>
      )}
    </>
  );
}
