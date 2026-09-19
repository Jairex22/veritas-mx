export interface QuickAction {
  key: string;
  label: string;
}

const ACTIONS: QuickAction[] = [
  { key: "catalog", label: "Ver precios" },
  { key: "find", label: "Encontrar un servicio" },
  { key: "appointment", label: "Solicitar cita" },
  { key: "contact", label: "Hablar con el negocio" },
];

export default function QuickActions({
  onSelect,
  disabled,
}: {
  onSelect: (key: string) => void;
  disabled?: boolean;
}) {
  return (
    <div
      role="group"
      aria-label="Acciones rápidas"
      style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "8px 0" }}
    >
      {ACTIONS.map((a) => (
        <button
          key={a.key}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(a.key)}
          style={{
            border: "1px solid var(--cf-primary)",
            background: "transparent",
            color: "var(--cf-primary)",
            borderRadius: 999,
            padding: "8px 14px",
            fontSize: 13,
            fontWeight: 700,
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.5 : 1,
            minHeight: 40,
          }}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}
