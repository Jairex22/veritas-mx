// Genera folios legibles para el dueño del negocio, p.ej. "CIT-4F92K1".
const PREFIXES: Record<string, string> = {
  order: "PED",
  appointment: "CIT",
  contact: "CTC",
};

export function generateFolio(type: string): string {
  const prefix = PREFIXES[type] ?? "SOL";
  const random = Math.random().toString(36).slice(2, 8).toUpperCase();
  const stamp = Date.now().toString(36).slice(-4).toUpperCase();
  return `${prefix}-${stamp}${random.slice(0, 2)}`;
}
