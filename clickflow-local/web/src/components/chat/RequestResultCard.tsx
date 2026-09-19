import StatusBadge from "./StatusBadge";
import type { ServiceRequest } from "../../lib/types";

const LABELS: Record<ServiceRequest["type"], string> = {
  order: "Pedido",
  appointment: "Cita",
  contact: "Contacto",
};

export default function RequestResultCard({ request, extraNote }: { request: ServiceRequest; extraNote?: string }) {
  return (
    <div
      style={{
        border: "1px solid var(--cf-border)",
        borderRadius: "var(--cf-radius-md)",
        background: "var(--cf-surface)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{LABELS[request.type]} registrado</strong>
        <StatusBadge status={request.status} />
      </div>
      <div style={{ fontSize: 14 }}>
        Folio: <strong>{request.folio}</strong>
      </div>
      {request.totalCents != null && (
        <div style={{ fontSize: 14 }}>
          Total: {(request.totalCents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" })}
        </div>
      )}
      {extraNote && <p style={{ fontSize: 12, color: "var(--cf-text-muted)", margin: 0 }}>{extraNote}</p>}
      <p style={{ fontSize: 12, color: "var(--cf-text-muted)", margin: 0 }}>
        Guarda tu folio. El negocio revisará tu solicitud y actualizará su estado.
      </p>
    </div>
  );
}
