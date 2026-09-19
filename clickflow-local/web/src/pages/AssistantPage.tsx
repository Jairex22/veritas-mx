import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { publicApi } from "../lib/api";
import { getSessionId } from "../lib/session";
import { applyBusinessTheme } from "../lib/theme";
import type { CatalogItemPublic, ChatProposal, PublicBusiness, ServiceRequest } from "../lib/types";
import MessageBubble from "../components/chat/MessageBubble";
import QuickActions from "../components/chat/QuickActions";
import ProductCard from "../components/chat/ProductCard";
import { OrderFlow, AppointmentFlow, ContactFlow } from "../components/chat/RequestFlows";
import AiProposalCard from "../components/chat/AiProposalCard";
import RequestResultCard from "../components/chat/RequestResultCard";

type UIMessage =
  | { id: string; kind: "text"; role: "user" | "assistant"; content: string }
  | { id: string; kind: "catalog"; items: CatalogItemPublic[] }
  | { id: string; kind: "order-flow"; item: CatalogItemPublic }
  | { id: string; kind: "appointment-flow"; item?: CatalogItemPublic }
  | { id: string; kind: "contact-flow" }
  | { id: string; kind: "ai-proposal"; proposal: ChatProposal }
  | { id: string; kind: "result"; request: ServiceRequest; extraNote?: string };

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export default function AssistantPage() {
  const { businessSlug = "" } = useParams();
  const [searchParams] = useSearchParams();
  const isEmbed = searchParams.get("embed") === "1";

  const [business, setBusiness] = useState<PublicBusiness | null>(null);
  const [catalog, setCatalog] = useState<CatalogItemPublic[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const biz = (await publicApi(businessSlug).getBusiness()) as PublicBusiness;
        if (cancelled) return;
        setBusiness(biz);
        applyBusinessTheme(biz.colors);
        const cat = (await publicApi(businessSlug).getCatalog()) as { items: CatalogItemPublic[] };
        if (cancelled) return;
        setCatalog(cat.items);
        setMessages([
          {
            id: uid(),
            kind: "text",
            role: "assistant",
            content: `¡Hola! Soy el asistente virtual de ${biz.name}. Puedo ayudarte a ver precios, encontrar algo, pedir una cita o dejarte en contacto con el negocio. ¿En qué te ayudo?`,
          },
        ]);
      } catch (e: any) {
        if (!cancelled) setLoadError(e.message || "No pudimos cargar este negocio.");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [businessSlug]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function push(msg: UIMessage) {
    setMessages((prev) => [...prev, msg]);
  }

  function replace(id: string, msg: UIMessage) {
    setMessages((prev) => prev.map((m) => (m.id === id ? msg : m)));
  }

  function remove(id: string) {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  }

  if (loadError) {
    return (
      <CenteredMessage>
        No pudimos cargar este asistente. Verifica el enlace o intenta de nuevo en un momento.
      </CenteredMessage>
    );
  }
  if (!business) {
    return <CenteredMessage>Cargando asistente…</CenteredMessage>;
  }

  const sessionId = getSessionId(business.slug);

  async function handleSend(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setInput("");
    push({ id: uid(), kind: "text", role: "user", content: trimmed });
    setSending(true);
    try {
      const result = await publicApi(business!.slug).chat(sessionId, trimmed) as {
        reply: string;
        proposal: ChatProposal | null;
      };
      push({ id: uid(), kind: "text", role: "assistant", content: result.reply });
      if (result.proposal) {
        push({ id: uid(), kind: "ai-proposal", proposal: result.proposal });
      }
    } catch (e: any) {
      push({
        id: uid(),
        kind: "text",
        role: "assistant",
        content: "No pudimos procesar tu mensaje en este momento. Intenta de nuevo en un momento.",
      });
    } finally {
      setSending(false);
    }
  }

  async function handleQuickAction(key: string) {
    if (key === "catalog") {
      push({ id: uid(), kind: "text", role: "assistant", content: "Este es nuestro catálogo:" });
      push({ id: uid(), kind: "catalog", items: catalog });
    } else if (key === "find") {
      handleSend("Ayúdame a encontrar el servicio o producto que necesito.");
    } else if (key === "appointment") {
      push({ id: uid(), kind: "appointment-flow" });
    } else if (key === "contact") {
      push({ id: uid(), kind: "contact-flow" });
    }
  }

  function handleProductAction(item: CatalogItemPublic) {
    if (item.durationMinutes != null) {
      push({ id: uid(), kind: "appointment-flow", item });
    } else {
      push({ id: uid(), kind: "order-flow", item });
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: isEmbed ? "100vh" : "100vh",
        maxWidth: isEmbed ? "100%" : 480,
        margin: isEmbed ? 0 : "0 auto",
        background: "var(--cf-bg)",
        fontFamily: "var(--cf-font)",
      }}
    >
      <header
        style={{
          padding: "14px 16px",
          background: "var(--cf-primary)",
          color: "var(--cf-primary-text)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        {business.logoUrl && (
          <img src={business.logoUrl} alt="" style={{ width: 32, height: 32, borderRadius: 8 }} />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Asistente virtual de {business.name}</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>
            {business.openNow ? "Abierto ahora" : "Cerrado ahora"} · {business.openStatusText}
          </div>
        </div>
        {business.isDemo && (
          <span style={{ fontSize: 10, fontWeight: 700, background: "var(--cf-accent)", color: "var(--cf-accent-text)", padding: "3px 8px", borderRadius: 999 }}>
            DEMO
          </span>
        )}
      </header>

      {business.aiPaused && (
        <Banner>El negocio pausó temporalmente las respuestas automáticas.</Banner>
      )}
      {!business.aiConfigured && (
        <Banner tone="muted">La conversación libre con IA está pendiente de configurar; el resto funciona con datos reales del negocio.</Banner>
      )}

      <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {messages.map((m) => (
          <MessageRenderer
            key={m.id}
            msg={m}
            business={business}
            catalog={catalog}
            sessionId={sessionId}
            onProductAction={handleProductAction}
            onCancelFlow={() => remove(m.id)}
            onFlowDone={(request, extraNote) => replace(m.id, { id: m.id, kind: "result", request, extraNote })}
          />
        ))}
        {sending && <MessageBubble role="assistant" content="Escribiendo…" />}
      </div>

      <div style={{ padding: "0 16px" }}>
        <QuickActions onSelect={handleQuickAction} disabled={sending} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend(input);
        }}
        style={{ display: "flex", gap: 8, padding: 16, borderTop: "1px solid var(--cf-border)", background: "var(--cf-surface)" }}
      >
        <label htmlFor="cf-chat-input" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden" }}>
          Escribe tu mensaje
        </label>
        <input
          id="cf-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu pregunta…"
          style={{
            flex: 1,
            border: "1px solid var(--cf-border)",
            borderRadius: 999,
            padding: "12px 16px",
            fontSize: 14,
            minHeight: 44,
          }}
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          style={{
            border: "none",
            borderRadius: 999,
            padding: "0 20px",
            background: "var(--cf-primary)",
            color: "var(--cf-primary-text)",
            fontWeight: 700,
            cursor: "pointer",
            minHeight: 44,
          }}
        >
          Enviar
        </button>
      </form>
    </div>
  );
}

function MessageRenderer({
  msg,
  business,
  catalog,
  sessionId,
  onProductAction,
  onCancelFlow,
  onFlowDone,
}: {
  msg: UIMessage;
  business: PublicBusiness;
  catalog: CatalogItemPublic[];
  sessionId: string;
  onProductAction: (item: CatalogItemPublic) => void;
  onCancelFlow: () => void;
  onFlowDone: (request: ServiceRequest, extraNote?: string) => void;
}) {
  switch (msg.kind) {
    case "text":
      return <MessageBubble role={msg.role} content={msg.content} />;
    case "catalog":
      return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10 }}>
          {msg.items.map((item) => (
            <ProductCard key={item.id} item={item} onAction={onProductAction} />
          ))}
          {msg.items.length === 0 && (
            <p style={{ fontSize: 13, color: "var(--cf-text-muted)" }}>
              Por ahora no hay artículos activos en el catálogo.
            </p>
          )}
        </div>
      );
    case "order-flow":
      return (
        <OrderFlow
          business={business}
          item={msg.item}
          sessionId={sessionId}
          onCancel={onCancelFlow}
          onDone={(request) => onFlowDone(request)}
        />
      );
    case "appointment-flow":
      return (
        <AppointmentFlow
          business={business}
          items={catalog}
          preselectedItem={msg.item}
          sessionId={sessionId}
          onCancel={onCancelFlow}
          onDone={(request, warnings) => onFlowDone(request, warnings.join(" "))}
        />
      );
    case "contact-flow":
      return <ContactFlow business={business} sessionId={sessionId} onCancel={onCancelFlow} onDone={(r) => onFlowDone(r)} />;
    case "ai-proposal":
      return (
        <AiProposalCard
          business={business}
          sessionId={sessionId}
          proposal={msg.proposal}
          onCancel={onCancelFlow}
          onDone={(request) => onFlowDone(request)}
        />
      );
    case "result":
      return <RequestResultCard request={msg.request} extraNote={msg.extraNote} />;
    default:
      return null;
  }
}

function Banner({ children, tone = "warning" }: { children: React.ReactNode; tone?: "warning" | "muted" }) {
  return (
    <div
      style={{
        padding: "8px 16px",
        fontSize: 12,
        background: tone === "warning" ? "#fbeedb" : "#eef1ef",
        color: tone === "warning" ? "#8a5a00" : "#3f4a52",
      }}
    >
      {children}
    </div>
  );
}

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", padding: 24, textAlign: "center", fontFamily: "var(--cf-font)" }}>
      {children}
    </div>
  );
}
