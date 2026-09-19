import { useState } from "react";
import { publicApi } from "../../lib/api";
import { newIdempotencyKey } from "../../lib/session";
import type { ChatProposal, PublicBusiness, ServiceRequest } from "../../lib/types";

const cardStyle: React.CSSProperties = {
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-md)",
  background: "var(--cf-surface)",
  padding: 16,
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const primaryBtn: React.CSSProperties = {
  border: "none",
  borderRadius: "var(--cf-radius-sm)",
  padding: "10px 16px",
  background: "var(--cf-primary)",
  color: "var(--cf-primary-text)",
  fontWeight: 700,
  cursor: "pointer",
  minHeight: 44,
};

const secondaryBtn: React.CSSProperties = {
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-sm)",
  padding: "10px 16px",
  background: "transparent",
  color: "var(--cf-text)",
  fontWeight: 600,
  cursor: "pointer",
  minHeight: 44,
};

// Renderiza el resumen editable de una propuesta que armó el asistente de
// IA (o el motor de respaldo) usando sus herramientas. Nada de esto se
// guardó todavía: al confirmar, se llama al mismo endpoint que valida y
// persiste en el servidor, igual que los flujos iniciados por botones.
export default function AiProposalCard({
  business,
  sessionId,
  proposal,
  onCancel,
  onDone,
}: {
  business: PublicBusiness;
  sessionId: string;
  proposal: ChatProposal;
  onCancel: () => void;
  onDone: (request: ServiceRequest) => void;
}) {
  const api = publicApi(business.slug);
  const [idempotencyKey] = useState(() => newIdempotencyKey());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!proposal.ok) {
    return (
      <div style={cardStyle}>
        <strong>No se pudo preparar tu solicitud</strong>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          {proposal.errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
        <button style={secondaryBtn} onClick={onCancel} type="button">
          Entendido
        </button>
      </div>
    );
  }

  async function confirm() {
    setSubmitting(true);
    setError(null);
    try {
      let res: { request: ServiceRequest };
      if (proposal.proposalType === "order") {
        res = (await api.createOrder({
          sessionId,
          idempotencyKey,
          lines: proposal.lines,
          deliveryPreference: proposal.deliveryPreference ?? undefined,
          customerNote: proposal.customerNote ?? undefined,
        })) as any;
      } else if (proposal.proposalType === "appointment") {
        res = (await api.createAppointment({
          sessionId,
          idempotencyKey,
          itemId: proposal.itemId,
          preferredDate: proposal.preferredDate,
          preferredTime: proposal.preferredTime,
          customerNote: proposal.customerNote ?? undefined,
        })) as any;
      } else {
        res = (await api.createContact({
          sessionId,
          idempotencyKey,
          reason: proposal.reason,
        })) as any;
      }
      onDone(res.request);
    } catch (e: any) {
      setError(e.message || "No se pudo registrar tu solicitud.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={cardStyle}>
      <strong>Revisa antes de confirmar</strong>
      {proposal.proposalType === "order" && (
        <>
          {(proposal.lines as any[]).map((l, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
              <span>
                {l.quantity} × {l.name}
                {l.variantName ? ` (${l.variantName})` : ""}
              </span>
              <span>{(l.lineTotalCents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" })}</span>
            </div>
          ))}
          <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, borderTop: "1px solid var(--cf-border)", paddingTop: 8 }}>
            <span>Total</span>
            <span>{proposal.totalFormatted as string}</span>
          </div>
        </>
      )}
      {proposal.proposalType === "appointment" && (
        <>
          <div style={{ fontSize: 14 }}>Servicio: {proposal.itemName as string}</div>
          <div style={{ fontSize: 14 }}>
            Fecha y hora preferidas: {proposal.preferredDate as string} {proposal.preferredTime as string}
          </div>
          <div style={{ fontSize: 14 }}>Precio: {proposal.priceFormatted as string}</div>
          <p style={{ fontSize: 12, color: "var(--cf-text-muted)", margin: 0 }}>
            Esto es una solicitud, no una reserva confirmada.
          </p>
        </>
      )}
      {proposal.proposalType === "contact" && <div style={{ fontSize: 14 }}>Motivo: {proposal.reason as string}</div>}
      {error && <p style={{ color: "var(--cf-danger)", fontSize: 13, margin: 0 }}>{error}</p>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={primaryBtn} onClick={confirm} type="button" disabled={submitting}>
          {submitting ? "Enviando..." : "Confirmar"}
        </button>
        <button style={secondaryBtn} onClick={onCancel} type="button" disabled={submitting}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
