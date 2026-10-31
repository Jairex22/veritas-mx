// Arranque de la SPA: sesión, shell, navegación y estado de conexión.
import { api, get, onUnauthorized, post, setCsrf } from "./api.js";
import { brandMark, h, icon, mount, toast } from "./ui.js";
import * as Login from "./pages/login.js";
import * as Dashboard from "./pages/dashboard.js";
import * as Trace from "./pages/trace.js";
import * as Explorer from "./pages/explorer.js";
import * as Rework from "./pages/rework.js";
import * as Operations from "./pages/operations.js";
import * as Packing from "./pages/packing.js";
import * as Labels from "./pages/labels.js";
import * as Intelligence from "./pages/intelligence.js";
import * as Connectors from "./pages/connectors.js";
import * as Audit from "./pages/audit.js";

const NAV = [
  { group: "OPERACIÓN" },
  { id: "dashboard", label: "Dashboard", icon: "dashboard", page: Dashboard },
  { id: "trace", label: "Trazabilidad", icon: "trace", page: Trace },
  { id: "explorer", label: "Consulta directa OData", icon: "database", page: Explorer, perm: "odata.explore" },
  { id: "rework", label: "Rework inteligente", icon: "rework", page: Rework, badge: true },
  { id: "operations", label: "Operaciones", icon: "ops", page: Operations },
  { id: "packing", label: "Packing", icon: "box", page: Packing, perm: "packing.use" },
  { id: "labels", label: "Label Control", icon: "printer", page: Labels, perm: "labels.print" },
  { group: "ANÁLISIS" },
  { id: "intelligence", label: "Production Intelligence", icon: "chart", page: Intelligence },
  { group: "SISTEMA" },
  { id: "connectors", label: "Conectores", icon: "plug", page: Connectors, perm: "connectors.read" },
  { id: "audit", label: "Auditoría", icon: "shield", page: Audit, perm: "audit.read" },
];

export const state = { status: null, user: null, cleanup: null, reworkCount: null };
const root = document.getElementById("app");

export const can = (perm) => !perm || (state.user && state.user.permissions.includes(perm));

export function navigate(path) {
  if (location.hash !== "#" + path) location.hash = path;
  else route();
}

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/dashboard";
  const [path, qs] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  return { id: parts[0] || "dashboard", params: parts.slice(1).map(decodeURIComponent), query: Object.fromEntries(new URLSearchParams(qs || "")) };
}

async function refreshStatus() {
  try {
    state.status = await get("/api/system/status");
  } catch (e) {
    state.status = { mode: "?", badges: [], connection: { state: "ERROR", label: "Servidor no responde", tone: "error" }, error: e.message };
  }
  renderTopStatus();
  return state.status;
}

function applyRibbon() {
  const demo = state.status && state.status.mode === "DEMO";
  document.body.classList.toggle("has-ribbon", !!demo);
  let rib = document.querySelector(".demo-ribbon");
  if (demo && !rib) {
    rib = h("div", { class: "demo-ribbon", role: "note" }, "MODO DEMO · TRAZABILIDAD Y KPI CON DATOS SINTÉTICOS · OPERACIONES SIMULADAS · LA CONSULTA DIRECTA ODATA SÍ LEE EL SERVIDOR REAL");
    document.body.prepend(rib);
  } else if (!demo && rib) rib.remove();
}

function renderTopStatus() {
  applyRibbon();
  const slot = document.getElementById("env-slot");
  if (!slot || !state.status) return;
  const st = state.status;
  mount(slot,
    st.badges.map((b) => h("span", { class: `badge-env ${b.tone}`, title: b.description }, b.label)),
    h("span", { class: "conn", title: st.source_note || st.data_source?.label || "" },
      h("span", { class: `dot ${st.connection.tone}` }), h("span", { class: "lbl" }, st.connection.label)));
}

function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("gpv.theme", next); } catch { /* sin almacenamiento */ }
  const btn = document.getElementById("theme-btn");
  if (btn) mount(btn, icon(next === "dark" ? "sun" : "moon"));
}

function toggleSidebar() {
  if (window.matchMedia("(max-width: 900px)").matches) { document.body.classList.toggle("nav-open"); return; }
  const c = document.body.classList.toggle("collapsed");
  try { localStorage.setItem("gpv.sidebar", c ? "collapsed" : "open"); } catch { /* */ }
}

async function logout() {
  try { await post("/api/auth/logout"); } catch { /* la sesión puede haber expirado */ }
  state.user = null; setCsrf(null);
  toast("Sesión cerrada.", "info");
  renderLogin();
}

function renderShell() {
  const u = state.user;
  const initials = u.display_name.split(/\s+/).map((x) => x[0]).slice(0, 2).join("").toUpperCase();
  const nav = h("nav", { class: "nav", "aria-label": "Navegación principal" },
    NAV.filter((n) => n.group || can(n.perm)).map((n) => n.group ? h("div", { class: "nav-group" }, n.group)
      : h("a", { href: `#/${n.id}`, dataset: { nav: n.id }, title: n.label, onclick: () => document.body.classList.remove("nav-open") },
        icon(n.icon), h("span", null, n.label), n.badge ? h("span", { class: "count hidden", id: "rework-count" }) : null)));
  const search = h("input", { type: "search", placeholder: "Buscar serial, orden, panel, ensamble…", "aria-label": "Búsqueda global", maxlength: 64 });
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && search.value.trim()) { navigate(`/trace?q=${encodeURIComponent(search.value.trim())}`); search.blur(); }
  });
  search.id = "global-search";
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  mount(root, h("div", { class: "shell" },
    h("aside", { class: "sidebar" },
      h("div", { class: "brand" }, brandMark(), h("div", { class: "brand-text" }, h("b", null, "GPV COMMAND CENTER"), h("span", null, "FactoryLogix · v" + (state.status?.version || "1.0")))),
      nav,
      h("div", { class: "sidebar-foot" }, h("button", { class: "btn ghost collapse-btn", onclick: toggleSidebar, "aria-label": "Colapsar menú" }, icon("chevronLeft"), h("span", null, "Colapsar")))),
    h("header", { class: "topbar" },
      h("button", { class: "btn ghost icon-only mobile-only", onclick: toggleSidebar, "aria-label": "Menú" }, icon("menu")),
      h("div", { class: "global-search" }, icon("search", "sm"), search, h("kbd", null, "/")),
      h("div", { class: "topbar-right" },
        h("div", { class: "row", id: "env-slot" }),
        h("button", { class: "btn ghost icon-only", id: "theme-btn", onclick: toggleTheme, "aria-label": "Cambiar tema", title: "Tema claro/oscuro" }, icon(dark ? "sun" : "moon")),
        h("div", { class: "user-chip", title: `${u.display_name} · ${u.role_label}` },
          h("span", { class: "avatar" }, initials),
          h("span", { class: "who" }, u.display_name, h("small", null, u.role_label)),
          h("button", { class: "btn ghost icon-only", onclick: logout, "aria-label": "Cerrar sesión", title: "Cerrar sesión" }, icon("logout"))))),
    h("main", { class: "main", id: "page" })));
  try { if (localStorage.getItem("gpv.sidebar") === "collapsed") document.body.classList.add("collapsed"); } catch { /* */ }
  renderTopStatus();
  updateReworkBadge();
}

export async function updateReworkBadge() {
  try {
    const d = await get("/api/diagnostics");
    const n = d.summary.CRITICAL + d.summary.HIGH;
    const el = document.getElementById("rework-count");
    if (el) { el.textContent = n; el.classList.toggle("hidden", !n); el.title = `${n} hallazgos críticos/altos`; }
  } catch { /* sin fuente: no se muestra conteo */ }
}

async function route() {
  if (!state.user) return;
  const { id, params, query } = parseHash();
  const item = NAV.find((n) => n.id === id && n.page) || NAV[1];
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === item.id));
  if (typeof state.cleanup === "function") { try { state.cleanup(); } catch { /* */ } }
  state.cleanup = null;
  const page = document.getElementById("page");
  if (!can(item.perm)) {
    mount(page, h("div", { class: "alert err" }, icon("lock"), h("div", null, h("b", null, "Acceso denegado"), "Su rol no tiene permiso para este módulo.")));
    return;
  }
  const container = h("div", { class: "page" });
  mount(page, container);
  document.title = `${item.label} · GPV Command Center`;
  window.scrollTo(0, 0);
  state.cleanup = await item.page.render(container, { state, params, query, navigate, can, refreshStatus });
}

function renderLogin() {
  document.body.classList.remove("collapsed");
  Login.render(root, {
    state,
    onLogin: async (data) => {
      state.user = data.user; setCsrf(data.csrf_token);
      renderShell();
      if (!location.hash || location.hash === "#/") location.hash = "/dashboard";
      route();
      toast(`Bienvenido, ${data.user.display_name}.`, "ok", state.status?.mode === "DEMO" ? "Sesión DEMO: datos sintéticos." : undefined);
    },
  });
}

onUnauthorized(() => {
  if (!state.user) return;
  state.user = null;
  toast("La sesión expiró. Inicie sesión nuevamente.", "warn");
  renderLogin();
});

window.addEventListener("hashchange", route);
document.addEventListener("keydown", (e) => {
  const search = document.getElementById("global-search");
  if (search && e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { e.preventDefault(); search.focus(); }
});
setInterval(() => { if (state.user) refreshStatus(); }, 60000);

(async function boot() {
  await refreshStatus();
  try {
    const me = await api("/api/auth/me");
    state.user = me.user; setCsrf(me.csrf_token);
    renderShell();
    route();
  } catch {
    renderLogin();
  }
})();
