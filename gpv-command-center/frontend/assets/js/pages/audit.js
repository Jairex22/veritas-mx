import { get } from "../api.js";
import { card, chip, dataTable, errorAlert, fmtDate, h, icon, loading, mount, pageHead, statusChip } from "../ui.js";

const CATS = ["", "AUTH", "OPERATION", "PRINT", "CONFIG", "SYSTEM"];

export async function render(root) {
  const cat = h("select", { class: "input", style: { maxWidth: "180px" } }, CATS.map((c) => h("option", { value: c }, c || "Todas las categorías")));
  const q = h("input", { class: "input", placeholder: "Buscar acción, objetivo, usuario o correlación", maxlength: 64, style: { maxWidth: "340px" } });
  const tabs = h("div", { class: "tabs" });
  const integrity = h("div");
  const body = h("div", { class: "card-body" }, loading(5));
  let view = "events";
  const setTab = (v) => { view = v; tabs.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.v === v)); load(); };
  [["events", "Eventos auditados"], ["access", "Bitácora de accesos"]].forEach(([v, l]) => tabs.append(h("button", { class: "tab", dataset: { v }, onclick: () => setTab(v) }, l)));

  mount(root, pageHead("Auditoría", "Registro inalterable (cadena de hashes SHA-256) de autenticación, operaciones, impresiones y configuración.",
    [cat, q, h("button", { class: "btn", onclick: () => load() }, icon("refresh", "sm"), "Actualizar")]),
    h("div", { class: "stack" }, integrity, h("section", { class: "card" }, tabs, body)));
  cat.addEventListener("change", () => load());
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });

  async function load() {
    mount(body, loading(5));
    try {
      if (view === "access") {
        const r = await get("/api/audit/access", { limit: 300 });
        mount(body, dataTable([
          { key: "ts", label: "Fecha", render: (e) => fmtDate(e.ts) }, { key: "username", label: "Usuario", render: (e) => e.username || h("span", { class: "faint" }, "anónimo") },
          { key: "method", label: "Método", render: (e) => chip(e.method, "outline") }, { key: "path", label: "Ruta", render: (e) => h("span", { class: "mono" }, e.path) },
          { key: "status", label: "HTTP", render: (e) => chip(String(e.status), e.status < 400 ? "ok" : e.status < 500 ? "warn" : "err") },
          { key: "duration_ms", label: "ms", num: true }, { key: "correlation_id", label: "Correlación", render: (e) => h("span", { class: "mono faint" }, e.correlation_id.slice(0, 12)) },
        ], r.entries));
        return;
      }
      const r = await get("/api/audit", { category: cat.value, q: q.value.trim(), limit: 300 });
      mount(integrity, r.integrity.valid
        ? h("div", { class: "alert ok" }, icon("shield"), h("div", null, h("b", null, "Cadena de auditoría íntegra"), `${r.integrity.checked} registros verificados.`))
        : h("div", { class: "alert err" }, icon("alert"), h("div", null, h("b", null, "INTEGRIDAD COMPROMETIDA"), `La cadena se rompe en el registro #${r.integrity.broken_at_id}. Notifique a TI y Calidad.`)));
      mount(body, dataTable([
        { key: "id", label: "#", num: true }, { key: "ts", label: "Fecha", render: (e) => fmtDate(e.ts) },
        { key: "category", label: "Categoría", render: (e) => chip(e.category, "outline") }, { key: "action", label: "Acción", render: (e) => h("span", { class: "mono" }, e.action) },
        { key: "username", label: "Usuario", render: (e) => e.username ? [e.username, h("span", { class: "faint" }, e.role ? ` · ${e.role}` : "")] : h("span", { class: "faint" }, "sistema") },
        { key: "target", label: "Objetivo", render: (e) => h("span", { class: "mono" }, e.target || "—") },
        { key: "mode", label: "Modo", render: (e) => chip(e.mode, e.mode === "DEMO" ? "demo" : "info") },
        { key: "outcome", label: "Resultado", render: (e) => statusChip(e.outcome === "READY" ? "READY_OP" : e.outcome) },
        { key: "details", label: "Detalle", sortable: false, render: (e) => h("details", null, h("summary", { style: { cursor: "pointer" } }, "ver"),
          h("pre", { class: "code", style: { maxWidth: "460px" } }, JSON.stringify(e.details, null, 2), `\ncorrelación: ${e.correlation_id}\nhash: ${e.hash}`)) },
      ], r.entries, { empty: "Sin eventos." }));
    } catch (e) { mount(body, errorAlert(e)); }
  }
  setTab("events");
}
