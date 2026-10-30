// Bloques reutilizados por varias páginas.
import { h, icon, infoTip, num, pct } from "../ui.js";

export const SEV_COLORS = { CRITICAL: "var(--crit)", HIGH: "var(--err)", MEDIUM: "var(--warn)", LOW: "var(--info)" };
export const STATUS_COLORS = { PACKED: "var(--ok)", IN_PROCESS: "var(--info)", IN_REPAIR: "var(--err)", HOLD: "var(--warn)", COMPLETE: "var(--accent)", SCRAPPED: "var(--text-3)" };
export const STATUS_LABEL = { PACKED: "Empacado", IN_PROCESS: "En proceso", IN_REPAIR: "En reparación", HOLD: "HOLD", COMPLETE: "Completo", SCRAPPED: "Scrap" };

export function kpiCard({ label, value, format = "num", sub, definition, color }) {
  const na = value === null || value === undefined;
  const text = na ? "Sin datos" : format === "pct" ? pct(value) : num(value);
  return h("div", { class: `card kpi ${na ? "na" : ""}`, style: color ? { "--kpi-color": color } : null },
    h("div", { class: "label" }, label, definition ? infoTip(definition) : null),
    h("div", { class: "value" }, text),
    sub ? h("div", { class: "sub" }, sub) : null);
}

export function hourLabel(p) {
  const d = new Date(p.x);
  return d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
}

export function unitLink(serial, navigate) {
  return h("a", { href: `#/trace/${encodeURIComponent(serial)}`, class: "mono", onclick: (e) => { e.stopPropagation(); } }, serial);
}

export function unavailableBlock(err) {
  return h("div", { class: "card" }, h("div", { class: "empty" }, icon("database"),
    h("h4", null, err.status === 503 ? "Sin fuente de datos" : "No se pudieron cargar los datos"),
    h("p", { class: "muted", style: { maxWidth: "640px", margin: "6px auto" } }, err.message),
    h("p", { class: "faint", style: { fontSize: "12px" } }, "No se muestran valores sustitutos. Revise la página de Conectores."),
    err.correlationId ? h("p", { class: "faint mono", style: { fontSize: "11px" } }, `ID de correlación: ${err.correlationId}`) : null));
}
