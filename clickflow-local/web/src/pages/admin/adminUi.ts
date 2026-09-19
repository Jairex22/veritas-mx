export const card: React.CSSProperties = {
  background: "var(--cf-surface)",
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-md)",
  padding: 20,
  marginBottom: 20,
};

export const input: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-sm)",
  padding: "8px 10px",
  fontSize: 14,
  minHeight: 40,
};

export const button: React.CSSProperties = {
  border: "none",
  borderRadius: "var(--cf-radius-sm)",
  padding: "10px 16px",
  background: "var(--cf-primary)",
  color: "var(--cf-primary-text)",
  fontWeight: 700,
  cursor: "pointer",
  minHeight: 40,
};

export const buttonSecondary: React.CSSProperties = {
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-sm)",
  padding: "10px 16px",
  background: "transparent",
  color: "var(--cf-text)",
  fontWeight: 600,
  cursor: "pointer",
  minHeight: 40,
};

export const buttonDanger: React.CSSProperties = {
  ...buttonSecondary,
  color: "var(--cf-danger)",
  borderColor: "var(--cf-danger)",
};

export const table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 14,
};

export const th: React.CSSProperties = {
  textAlign: "left",
  borderBottom: "2px solid var(--cf-border)",
  padding: "8px 6px",
  color: "var(--cf-text-muted)",
  fontSize: 12,
  textTransform: "uppercase",
};

export const td: React.CSSProperties = {
  borderBottom: "1px solid var(--cf-border)",
  padding: "8px 6px",
  verticalAlign: "top",
};
