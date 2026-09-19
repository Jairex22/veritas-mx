import { useEffect, useState } from "react";
import { adminApi } from "../../lib/api";
import { getAdminToken } from "../../lib/adminAuth";
import { card, table, th, td, buttonSecondary } from "./adminUi";

const STATUSES = ["borrador", "solicitud_recibida", "pendiente_confirmacion", "confirmada", "cancelada"] as const;
const STATUS_LABELS: Record<string, string> = {
  borrador: "Borrador",
  solicitud_recibida: "Solicitud recibida",
  pendiente_confirmacion: "Pendiente de confirmación",
  confirmada: "Confirmada",
  cancelada: "Cancelada",
};
const TYPE_LABELS: Record<string, string> = { order: "Pedido", appointment: "Cita", contact: "Contacto" };

export default function AdminRequestsPage() {
  const api = adminApi(getAdminToken());
  const [requests, setRequests] = useState<any[]>([]);
  const [filterStatus, setFilterStatus] = useState("");
  const [filterType, setFilterType] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const res = await api.listRequests({
      status: filterStatus || undefined,
      type: filterType || undefined,
    } as any);
    setRequests(res.requests);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStatus, filterType]);

  async function changeStatus(id: string, status: string) {
    setError(null);
    try {
      await api.setRequestStatus(id, status);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function money(cents: number | null) {
    if (cents == null) return "—";
    return (cents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" });
  }

  return (
    <div>
      <h1>Solicitudes</h1>
      {error && <p style={{ color: "var(--cf-danger)" }}>{error}</p>}
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)} style={{ minHeight: 40 }}>
          <option value="">Todos los tipos</option>
          <option value="order">Pedido</option>
          <option value="appointment">Cita</option>
          <option value="contact">Contacto</option>
        </select>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} style={{ minHeight: 40 }}>
          <option value="">Todos los estados</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </div>

      <div style={card}>
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Folio</th>
              <th style={th}>Tipo</th>
              <th style={th}>Total</th>
              <th style={th}>Estado</th>
              <th style={th}>Creado</th>
              <th style={th}>Cambiar estado</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((r) => (
              <tr key={r.id}>
                <td style={td}>{r.folio}</td>
                <td style={td}>{TYPE_LABELS[r.type]}</td>
                <td style={td}>{money(r.totalCents)}</td>
                <td style={td}>{STATUS_LABELS[r.status]}</td>
                <td style={td}>{new Date(r.createdAt).toLocaleString("es-MX")}</td>
                <td style={td}>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {r.status === "solicitud_recibida" && (
                      <button style={buttonSecondary} onClick={() => changeStatus(r.id, "pendiente_confirmacion")}>
                        Marcar pendiente
                      </button>
                    )}
                    {r.status !== "confirmada" && r.status !== "cancelada" && (
                      <button style={buttonSecondary} onClick={() => changeStatus(r.id, "confirmada")}>
                        Confirmar
                      </button>
                    )}
                    {r.status !== "cancelada" && (
                      <button style={buttonSecondary} onClick={() => changeStatus(r.id, "cancelada")}>
                        Cancelar
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {requests.length === 0 && (
              <tr>
                <td style={td} colSpan={6}>
                  No hay solicitudes con este filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
