import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
      <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }}>
        Mostrando {from}–{to} de {total}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft size={14} /> Anterior
        </button>
        <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-secondary)" }}>
          Página {page} de {totalPages}
        </span>
        <button className="btn btn-ghost btn-sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          Siguiente <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
