export default function MessageBubble({ role, content }: { role: "user" | "assistant"; content: string }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div
        style={{
          maxWidth: "85%",
          padding: "10px 14px",
          borderRadius: isUser ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
          background: isUser ? "var(--cf-primary)" : "var(--cf-surface)",
          color: isUser ? "var(--cf-primary-text)" : "var(--cf-text)",
          border: isUser ? "none" : "1px solid var(--cf-border)",
          whiteSpace: "pre-wrap",
          fontSize: 14,
          lineHeight: 1.45,
        }}
      >
        {content}
      </div>
    </div>
  );
}
