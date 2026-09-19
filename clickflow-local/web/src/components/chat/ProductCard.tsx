import type { CatalogItemPublic } from "../../lib/types";

export default function ProductCard({
  item,
  onAction,
}: {
  item: CatalogItemPublic;
  onAction: (item: CatalogItemPublic) => void;
}) {
  const isService = item.durationMinutes != null;
  return (
    <div
      style={{
        border: "1px solid var(--cf-border)",
        borderRadius: "var(--cf-radius-md)",
        overflow: "hidden",
        background: "var(--cf-surface)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {item.imageUrl ? (
        <img src={item.imageUrl} alt="" style={{ width: "100%", height: 96, objectFit: "cover" }} />
      ) : (
        <div
          aria-hidden
          style={{
            width: "100%",
            height: 72,
            background: "linear-gradient(135deg, var(--cf-primary), var(--cf-accent))",
            opacity: 0.18,
          }}
        />
      )}
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--cf-text-muted)" }}>
          {item.category}
        </div>
        <div style={{ fontWeight: 700 }}>{item.name}</div>
        <div style={{ fontSize: 13, color: "var(--cf-text-muted)", flex: 1 }}>{item.description}</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontWeight: 700, color: "var(--cf-primary)" }}>{item.priceFormatted}</span>
          {item.isPromo && (
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--cf-graphite)", background: "var(--cf-accent)", padding: "2px 6px", borderRadius: 6 }}>
              Promoción vigente
            </span>
          )}
          {isService && item.durationMinutes ? (
            <span style={{ fontSize: 12, color: "var(--cf-text-muted)" }}>· {item.durationMinutes} min</span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => onAction(item)}
          style={{
            marginTop: 4,
            border: "none",
            borderRadius: "var(--cf-radius-sm)",
            padding: "8px 12px",
            background: "var(--cf-primary)",
            color: "var(--cf-primary-text)",
            fontWeight: 700,
            cursor: "pointer",
            minHeight: 40,
          }}
        >
          {isService ? "Solicitar cita" : "Solicitar pedido"}
        </button>
      </div>
    </div>
  );
}
