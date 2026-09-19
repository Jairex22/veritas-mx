import { useMemo, useState } from "react";
import { publicApi } from "../../lib/api";
import { newIdempotencyKey } from "../../lib/session";
import type { CatalogItemPublic, PublicBusiness, QuoteResult, ServiceRequest } from "../../lib/types";

const cardStyle: React.CSSProperties = {
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-md)",
  background: "var(--cf-surface)",
  padding: 16,
  display: "flex",
  flexDirection: "column",
  gap: 12,
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

const inputStyle: React.CSSProperties = {
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-sm)",
  padding: "10px 12px",
  fontSize: 14,
  minHeight: 44,
  width: "100%",
};

function ErrorText({ children }: { children: React.ReactNode }) {
  return <p style={{ color: "var(--cf-danger)", fontSize: 13, margin: 0 }}>{children}</p>;
}

// ---------------- Pedido ----------------

export function OrderFlow({
  business,
  item,
  sessionId,
  onCancel,
  onDone,
}: {
  business: PublicBusiness;
  item: CatalogItemPublic;
  sessionId: string;
  onCancel: () => void;
  onDone: (request: ServiceRequest) => void;
}) {
  const api = useMemo(() => publicApi(business.slug), [business.slug]);
  const idempotencyKey = useState(() => newIdempotencyKey())[0];
  const [step, setStep] = useState<"form" | "summary" | "submitting">("form");
  const [quantity, setQuantity] = useState(1);
  const [variantName, setVariantName] = useState<string>(item.variants[0]?.name ?? "");
  const [note, setNote] = useState("");
  const [deliveryPreference, setDeliveryPreference] = useState("");
  const [quote, setQuote] = useState<QuoteResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function goToSummary() {
    setError(null);
    try {
      const lines = [{ itemId: item.id, quantity, variantName: variantName || undefined }];
      const result = await api.quote(lines) as QuoteResult;
      if (!result.ok) {
        setError(result.errors[0] || "No se pudo calcular el total.");
        return;
      }
      setQuote(result);
      setStep("summary");
    } catch (e: any) {
      setError(e.message || "No se pudo calcular el total.");
    }
  }

  async function confirm() {
    if (!quote) return;
    setStep("submitting");
    setError(null);
    try {
      const res = await api.createOrder({
        sessionId,
        idempotencyKey,
        lines: [{ itemId: item.id, quantity, variantName: variantName || undefined }],
        deliveryPreference: deliveryPreference || undefined,
        customerNote: note || undefined,
      }) as { request: ServiceRequest };
      onDone(res.request);
    } catch (e: any) {
      setError(e.message || "No se pudo registrar el pedido.");
      setStep("summary");
    }
  }

  if (step === "form") {
    return (
      <div style={cardStyle}>
        <strong>Pedido: {item.name}</strong>
        <label style={{ fontSize: 13 }}>
          Cantidad
          <input
            style={inputStyle}
            type="number"
            min={1}
            max={50}
            value={quantity}
            onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        {item.variants.length > 0 && (
          <label style={{ fontSize: 13 }}>
            Variante
            <select style={inputStyle} value={variantName} onChange={(e) => setVariantName(e.target.value)}>
              {item.variants.map((v) => (
                <option key={v.name} value={v.name}>
                  {v.name} — {(v.priceCents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" })}
                </option>
              ))}
            </select>
          </label>
        )}
        <label style={{ fontSize: 13 }}>
          Preferencia de entrega (opcional)
          <input
            style={inputStyle}
            placeholder="Ej. recoger en tienda"
            value={deliveryPreference}
            onChange={(e) => setDeliveryPreference(e.target.value)}
          />
        </label>
        <label style={{ fontSize: 13 }}>
          Nota para el negocio (opcional)
          <textarea style={{ ...inputStyle, minHeight: 60 }} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {error && <ErrorText>{error}</ErrorText>}
        <div style={{ display: "flex", gap: 8 }}>
          <button style={primaryBtn} onClick={goToSummary} type="button">
            Continuar
          </button>
          <button style={secondaryBtn} onClick={onCancel} type="button">
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <strong>Resumen de tu pedido (revisa antes de confirmar)</strong>
      {quote?.lines.map((l) => (
        <div key={l.itemId} style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
          <span>
            {l.quantity} × {l.name}
            {l.variantName ? ` (${l.variantName})` : ""}
          </span>
          <span>{(l.lineTotalCents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" })}</span>
        </div>
      ))}
      <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, borderTop: "1px solid var(--cf-border)", paddingTop: 8 }}>
        <span>Total</span>
        <span>{quote?.totalFormatted}</span>
      </div>
      {deliveryPreference && <div style={{ fontSize: 13 }}>Entrega: {deliveryPreference}</div>}
      {note && <div style={{ fontSize: 13 }}>Nota: {note}</div>}
      {error && <ErrorText>{error}</ErrorText>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={primaryBtn} onClick={confirm} type="button" disabled={step === "submitting"}>
          {step === "submitting" ? "Enviando..." : "Confirmar pedido"}
        </button>
        <button style={secondaryBtn} onClick={() => setStep("form")} type="button" disabled={step === "submitting"}>
          Editar
        </button>
      </div>
    </div>
  );
}

// ---------------- Cita ----------------

export function AppointmentFlow({
  business,
  items,
  preselectedItem,
  sessionId,
  onCancel,
  onDone,
}: {
  business: PublicBusiness;
  items: CatalogItemPublic[];
  preselectedItem?: CatalogItemPublic;
  sessionId: string;
  onCancel: () => void;
  onDone: (request: ServiceRequest, warnings: string[]) => void;
}) {
  const api = useMemo(() => publicApi(business.slug), [business.slug]);
  const idempotencyKey = useState(() => newIdempotencyKey())[0];
  const services = items.filter((i) => i.durationMinutes != null);
  const [step, setStep] = useState<"form" | "summary" | "submitting">("form");
  const [itemId, setItemId] = useState(preselectedItem?.id ?? services[0]?.id ?? "");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const selected = items.find((i) => i.id === itemId) ?? preselectedItem;

  function goToSummary() {
    setError(null);
    if (!selected) return setError("Elige un servicio.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return setError("Elige una fecha válida.");
    if (!/^\d{2}:\d{2}$/.test(time)) return setError("Elige una hora válida.");
    setStep("summary");
  }

  async function confirm() {
    setStep("submitting");
    setError(null);
    try {
      const res = await api.createAppointment({
        sessionId,
        idempotencyKey,
        itemId,
        preferredDate: date,
        preferredTime: time,
        customerNote: note || undefined,
      }) as { request: ServiceRequest; warnings: string[] };
      onDone(res.request, res.warnings || []);
    } catch (e: any) {
      setError(e.message || "No se pudo registrar la cita.");
      setStep("summary");
    }
  }

  if (step === "form") {
    return (
      <div style={cardStyle}>
        <strong>Solicitar cita</strong>
        <label style={{ fontSize: 13 }}>
          Servicio
          <select style={inputStyle} value={itemId} onChange={(e) => setItemId(e.target.value)}>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} — {s.priceFormatted}
              </option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: 13 }}>
          Fecha
          <input style={inputStyle} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label style={{ fontSize: 13 }}>
          Hora
          <input style={inputStyle} type="time" value={time} onChange={(e) => setTime(e.target.value)} />
        </label>
        <label style={{ fontSize: 13 }}>
          Nota (opcional)
          <textarea style={{ ...inputStyle, minHeight: 60 }} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {error && <ErrorText>{error}</ErrorText>}
        <div style={{ display: "flex", gap: 8 }}>
          <button style={primaryBtn} onClick={goToSummary} type="button">
            Continuar
          </button>
          <button style={secondaryBtn} onClick={onCancel} type="button">
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <strong>Resumen de tu cita (revisa antes de confirmar)</strong>
      <div style={{ fontSize: 14 }}>Servicio: {selected?.name}</div>
      <div style={{ fontSize: 14 }}>Fecha y hora preferidas: {date} {time}</div>
      <div style={{ fontSize: 14 }}>Precio del servicio: {selected?.priceFormatted}</div>
      {note && <div style={{ fontSize: 13 }}>Nota: {note}</div>}
      <p style={{ fontSize: 12, color: "var(--cf-text-muted)", margin: 0 }}>
        Esto es una solicitud, no una reserva confirmada. {business.name} revisará disponibilidad real y te
        confirmará.
      </p>
      {error && <ErrorText>{error}</ErrorText>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={primaryBtn} onClick={confirm} type="button" disabled={step === "submitting"}>
          {step === "submitting" ? "Enviando..." : "Confirmar solicitud"}
        </button>
        <button style={secondaryBtn} onClick={() => setStep("form")} type="button" disabled={step === "submitting"}>
          Editar
        </button>
      </div>
    </div>
  );
}

// ---------------- Contacto humano ----------------

export function ContactFlow({
  business,
  sessionId,
  onCancel,
  onDone,
}: {
  business: PublicBusiness;
  sessionId: string;
  onCancel: () => void;
  onDone: (request: ServiceRequest) => void;
}) {
  const api = useMemo(() => publicApi(business.slug), [business.slug]);
  const idempotencyKey = useState(() => newIdempotencyKey())[0];
  const [step, setStep] = useState<"form" | "summary" | "submitting">("form");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [whatsappOpened, setWhatsappOpened] = useState(false);

  function goToSummary() {
    if (!reason.trim()) return setError("Cuéntanos brevemente el motivo.");
    setError(null);
    setStep("summary");
  }

  async function confirm() {
    setStep("submitting");
    setError(null);
    try {
      const res = await api.createContact({ sessionId, idempotencyKey, reason }) as { request: ServiceRequest };
      onDone(res.request);
    } catch (e: any) {
      setError(e.message || "No se pudo registrar la solicitud.");
      setStep("summary");
    }
  }

  const whatsappHref = business.whatsappAvailable
    ? `https://wa.me/?text=${encodeURIComponent(
        `Hola ${business.name}, escribo desde su asistente virtual. ${reason || "Quisiera más información."}`
      )}`
    : null;

  if (step === "form") {
    return (
      <div style={cardStyle}>
        <strong>Hablar con {business.name}</strong>
        <p style={{ fontSize: 13, margin: 0, color: "var(--cf-text-muted)" }}>{business.openStatusText}</p>
        <label style={{ fontSize: 13 }}>
          ¿En qué te ayudamos?
          <textarea style={{ ...inputStyle, minHeight: 70 }} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        {error && <ErrorText>{error}</ErrorText>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button style={primaryBtn} onClick={goToSummary} type="button">
            Continuar
          </button>
          <button style={secondaryBtn} onClick={onCancel} type="button">
            Cancelar
          </button>
        </div>
        {whatsappHref && (
          <div style={{ borderTop: "1px solid var(--cf-border)", paddingTop: 10 }}>
            <a
              href={whatsappHref}
              target="_blank"
              rel="noreferrer"
              onClick={() => setWhatsappOpened(true)}
              style={{ color: "var(--cf-primary)", fontWeight: 700, fontSize: 13 }}
            >
              O abrir WhatsApp directamente →
            </a>
            <p style={{ fontSize: 11, color: "var(--cf-text-muted)", margin: "4px 0 0" }}>
              Se abrirá WhatsApp con un mensaje preparado; debes enviarlo tú desde ahí. Abrir el enlace no
              significa que el negocio ya lo recibió.
              {whatsappOpened ? " (Ya abriste WhatsApp; recuerda enviar el mensaje.)" : ""}
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <strong>Confirma tu solicitud de contacto</strong>
      <div style={{ fontSize: 14 }}>{reason}</div>
      {error && <ErrorText>{error}</ErrorText>}
      <div style={{ display: "flex", gap: 8 }}>
        <button style={primaryBtn} onClick={confirm} type="button" disabled={step === "submitting"}>
          {step === "submitting" ? "Enviando..." : "Confirmar y avisar al negocio"}
        </button>
        <button style={secondaryBtn} onClick={() => setStep("form")} type="button" disabled={step === "submitting"}>
          Editar
        </button>
      </div>
    </div>
  );
}
