import type { ReactNode } from "react";
import { Inbox, AlertCircle } from "lucide-react";

export function LoadingSkeleton({ rows = 5, height = 18 }: { rows?: number; height?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }} aria-live="polite" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height, width: `${94 - (i % 3) * 8}%` }} />
      ))}
      <span className="visually-hidden">Cargando información…</span>
    </div>
  );
}

export function EmptyState({ title, description, icon }: { title: string; description: string; icon?: ReactNode }) {
  return (
    <div className="state-block">
      {icon ?? <Inbox size={28} color="var(--text-muted)" />}
      <strong>{title}</strong>
      <p style={{ margin: 0 }}>{description}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-block">
      <AlertCircle size={28} color="var(--color-intervention-red)" />
      <strong>No fue posible cargar esta información</strong>
      <p style={{ margin: 0 }}>{message}</p>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  );
}
