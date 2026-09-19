import type { RequestStatus } from "../../lib/types";

const LABELS: Record<RequestStatus, string> = {
  borrador: "Borrador",
  solicitud_recibida: "Solicitud recibida",
  pendiente_confirmacion: "Pendiente de confirmación",
  confirmada: "Confirmada",
  cancelada: "Cancelada",
};

const COLORS: Record<RequestStatus, { bg: string; fg: string }> = {
  borrador: { bg: "#e9e5da", fg: "#5b6570" },
  solicitud_recibida: { bg: "#e4eeee", fg: "#245c57" },
  pendiente_confirmacion: { bg: "#fbeedb", fg: "#8a5a00" },
  confirmada: { bg: "#e2f2e6", fg: "#1e6b3a" },
  cancelada: { bg: "#f7e4e2", fg: "#b3261e" },
};

export default function StatusBadge({ status }: { status: RequestStatus }) {
  const c = COLORS[status];
  return (
    <span
      style={{
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 700,
        background: c.bg,
        color: c.fg,
      }}
    >
      {LABELS[status]}
    </span>
  );
}
