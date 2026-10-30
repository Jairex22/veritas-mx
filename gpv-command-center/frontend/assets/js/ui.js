// Utilidades de UI. Todo el contenido dinámico se inserta como texto (sin innerHTML) para evitar XSS.

const SVG_NS = "http://www.w3.org/2000/svg";

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  applyAttrs(el, attrs);
  append(el, children);
  return el;
}

export function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v);
  append(el, children);
  return el;
}

function applyAttrs(el, attrs) {
  if (!attrs) return;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
export function mount(el, ...children) { clear(el); append(el, children); return el; }

// ---------------- Iconos (trazos propios, 24x24) ----------------
const ICONS = {
  dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
  search: "M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14zM20 20l-4.2-4.2",
  trace: "M6 3v12M6 21a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM18 9a3 3 0 1 0 0-6a3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9",
  rework: "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z",
  ops: "M13 2L4 14h8l-1 8 9-12h-8z",
  box: "M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8",
  printer: "M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6z",
  chart: "M3 3v18h18M8 16v-5M13 16V8M18 16v-9",
  plug: "M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4",
  shield: "M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6zM9 12l2 2 4-4",
  sun: "M12 7a5 5 0 1 0 0 10a5 5 0 1 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  menu: "M3 6h18M3 12h18M3 18h18",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  alert: "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  check: "M20 6L9 17l-5-5",
  checkCircle: "M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4L12 14l-3-3",
  x: "M18 6L6 18M6 6l12 12",
  xCircle: "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20zM15 9l-6 6M9 9l6 6",
  info: "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20zM12 16v-4M12 8h.01",
  refresh: "M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15",
  chevronLeft: "M15 18l-6-6 6-6",
  chevronRight: "M9 18l6-6-6-6",
  arrowLeft: "M19 12H5M12 19l-7-7 7-7",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8a4 4 0 1 0 0-8z",
  cpu: "M6 6h12v12H6zM9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3",
  scan: "M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 8v8M10 8v8M14 8v8M17 8v8",
  play: "M5 3l14 9-14 9z",
  layers: "M12 2L2 7l10 5 10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  clock: "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20zM12 6v6l4 2",
  database: "M12 2c5 0 9 1.3 9 3s-4 3-9 3-9-1.3-9-3 4-3 9-3zM21 12c0 1.7-4 3-9 3s-9-1.3-9-3M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
  wrench: "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z",
  link: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
};

export function icon(name, cls = "") {
  const svg = s("svg", { class: `icon ${cls}`.trim(), viewBox: "0 0 24 24", "aria-hidden": "true" });
  svg.append(s("path", { d: ICONS[name] || ICONS.info }));
  return svg;
}

export function brandMark() {
  return s("svg", { class: "brand-mark", viewBox: "0 0 64 64", "aria-hidden": "true" },
    s("rect", { width: 64, height: 64, rx: 14, fill: "#0f1a24", stroke: "#31435a" }),
    s("path", { d: "M14 40 L26 22 L36 34 L50 16", stroke: "#2fb8d6", "stroke-width": 6, fill: "none", "stroke-linecap": "round", "stroke-linejoin": "round" }),
    s("circle", { cx: 50, cy: 16, r: 5, fill: "#36c690" }),
    s("rect", { x: 12, y: 46, width: 40, height: 5, rx: 2.5, fill: "#31435a" }));
}

// ---------------- Formato ----------------
const dtf = new Intl.DateTimeFormat("es-MX", { dateStyle: "short", timeStyle: "medium" });
export function fmtDate(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : dtf.format(d); }
export function fmtRel(iso) {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "hace segundos";
  if (diff < 3600) return `hace ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `hace ${(diff / 3600).toFixed(1)} h`;
  return `hace ${(diff / 86400).toFixed(1)} d`;
}
export function pct(v, digits = 1) { return v === null || v === undefined ? "—" : (v * 100).toFixed(digits) + "%"; }
export function num(v) { return v === null || v === undefined ? "—" : new Intl.NumberFormat("es-MX").format(v); }

// ---------------- Chips de estado ----------------
const STATUS = {
  IN_PROCESS: ["En proceso", "info"], IN_REPAIR: ["En reparación", "err"], HOLD: ["HOLD", "warn"],
  COMPLETE: ["Completo", "ok"], PACKED: ["Empacado", "ok"], SCRAPPED: ["Scrap", "neutral"],
  PASS: ["PASS", "ok"], FAIL: ["FAIL", "err"], INFO: ["INFO", "neutral"],
  OPEN: ["Abierto", "err"], REPAIRED: ["Reparado · sin re-prueba", "warn"], VERIFIED: ["Verificado", "ok"],
  CRITICAL: ["CRÍTICO", "crit"], HIGH: ["ALTO", "err"], MEDIUM: ["MEDIO", "warn"], LOW: ["BAJO", "info"],
  OK: ["OK", "ok"], SIMULATED: ["SIMULADO", "demo"], NOT_CONFIGURED: ["NO CONFIGURADO", "neutral"], UNKNOWN: ["NO COMPROBADO", "neutral"],
  AUTH_DENIED: ["ACCESO DENEGADO (401)", "err"], FORBIDDEN: ["PROHIBIDO (403)", "err"], NOT_FOUND: ["NO ENCONTRADO (404)", "err"],
  SERVER_ERROR: ["ERROR SERVIDOR (5xx)", "err"], UNREACHABLE: ["INACCESIBLE", "err"], TIMEOUT: ["TIEMPO AGOTADO", "err"],
  TLS_ERROR: ["ERROR TLS", "err"], UNEXPECTED: ["RESPUESTA INESPERADA", "warn"], DISABLED: ["DESHABILITADO", "neutral"],
  SIMULADA_DEMO: ["SIMULADA · DEMO", "demo"], NO_DISPONIBLE: ["NO DISPONIBLE", "neutral"], DISPONIBLE: ["DISPONIBLE", "ok"],
  READY: ["LISTA (simulado)", "ok"], OFFLINE: ["SIN COMUNICACIÓN", "err"], REACHABLE: ["PUERTO ACCESIBLE", "ok"],
  SIMULATED_SUCCESS: ["ÉXITO SIMULADO", "demo"], SIMULATED_FAILED: ["FALLO SIMULADO", "err"], DENIED: ["DENEGADO", "err"],
  SUCCESS: ["ÉXITO", "ok"], READY_OP: ["LISTA", "ok"], BLOCKED: ["BLOQUEADA", "warn"],
};
export function statusChip(code, extraCls = "") {
  if (!code) return h("span", { class: "faint" }, "—");
  const [label, tone] = STATUS[code] || [code, code.startsWith("FAILED") ? "err" : "neutral"];
  return h("span", { class: `chip ${tone} ${extraCls}`.trim() }, label);
}
export function chip(text, tone = "neutral") { return h("span", { class: `chip ${tone}` }, text); }

export function infoTip(text) {
  return h("span", { class: "info-tip", tabindex: "0", "aria-label": text }, icon("info", "sm"), h("span", { class: "tip", role: "tooltip" }, text));
}

// ---------------- Estados de carga / error ----------------
export function loading(rows = 3) {
  return h("div", { class: "stack", "aria-busy": "true" },
    Array.from({ length: rows }, () => h("div", { class: "skeleton", style: { height: "54px" } })));
}

export function emptyState(title, text, iconName = "search") {
  return h("div", { class: "empty" }, icon(iconName), h("h4", null, title), text ? h("p", { class: "muted" }, text) : null);
}

export function errorAlert(err, title) {
  const diag = (err.details && err.details.diagnosis) || [];
  const missing = (err.details && err.details.missing_requirements) || [];
  const fields = (err.details && err.details.fields) || null;
  const tone = err.status === 501 ? "warn" : "err";
  const heading = title || (err.status === 501 ? "NO DISPONIBLE" : err.status === 503 ? "Fuente de datos no disponible" :
    err.status === 403 ? "Acceso denegado" : err.status === 0 ? "Sin comunicación" : "Error");
  return h("div", { class: `alert ${tone}`, role: "alert" }, icon(tone === "warn" ? "lock" : "alert"),
    h("div", null, h("b", null, heading), err.message,
      fields ? h("ul", null, Object.entries(fields).map(([k, v]) => h("li", null, h("span", { class: "mono" }, k), ": ", v))) : null,
      diag.length ? h("ul", null, diag.map((d) => h("li", null, d))) : null,
      missing.length ? h("div", { style: { marginTop: "6px" } }, h("b", null, "Requisitos faltantes:"), h("ul", null, missing.map((d) => h("li", null, d)))) : null,
      err.correlationId ? h("div", { class: "faint mono", style: { marginTop: "6px", fontSize: "11px" } }, `ID de correlación: ${err.correlationId}`) : null));
}

export function sourceTag(source) {
  if (!source) return null;
  return h("span", { class: "source-tag" }, icon(source.synthetic ? "cpu" : "database", "sm"),
    "Fuente: ", h("b", null, source.label), source.synthetic ? chip("SINTÉTICO", "demo") : null);
}

// ---------------- Toasts ----------------
export function toast(message, tone = "info", detail) {
  const host = document.getElementById("toasts");
  const ic = { ok: "checkCircle", err: "xCircle", warn: "alert", info: "info" }[tone] || "info";
  const el = h("div", { class: `toast ${tone}`, role: tone === "err" ? "alert" : "status" }, icon(ic),
    h("div", null, message, detail ? h("small", null, detail) : null));
  host.append(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; setTimeout(() => el.remove(), 320); }, tone === "err" ? 7000 : 4200);
}

// ---------------- Modal de confirmación ----------------
export function modal({ title, body, confirmText = "Confirmar", cancelText = "Cancelar", tone = "primary", requireCheck, iconName = "alert" }) {
  return new Promise((resolve) => {
    let checked = !requireCheck;
    const confirmBtn = h("button", { class: `btn ${tone}`, disabled: !checked }, confirmText);
    const close = (v) => { backdrop.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") close(false); };
    const check = requireCheck ? h("label", { class: "row", style: { marginTop: "14px", fontSize: "13px", alignItems: "flex-start" } },
      h("input", { type: "checkbox", onchange: (e) => { checked = e.target.checked; confirmBtn.disabled = !checked; } }),
      h("span", null, requireCheck)) : null;
    confirmBtn.addEventListener("click", () => close(true));
    const backdrop = h("div", { class: "modal-backdrop", onclick: (e) => { if (e.target === backdrop) close(false); } },
      h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title },
        h("div", { class: "modal-head" }, h("span", { style: { color: tone === "danger" ? "var(--err)" : "var(--accent)" } }, icon(iconName, "lg")), h("h3", null, title)),
        h("div", { class: "modal-body" }, body, check),
        h("div", { class: "modal-foot" }, h("button", { class: "btn ghost", onclick: () => close(false) }, cancelText), confirmBtn)));
    document.body.append(backdrop);
    document.addEventListener("keydown", onKey);
    (requireCheck ? backdrop.querySelector("input") : confirmBtn).focus();
  });
}

// ---------------- Drawer ----------------
export function drawer(titleNodes, bodyNodes) {
  const close = () => { bd.remove(); dr.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const bd = h("div", { class: "drawer-backdrop", onclick: close });
  const dr = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true" },
    h("div", { class: "drawer-head" }, h("div", { style: { flex: "1" } }, titleNodes),
      h("button", { class: "btn ghost icon-only", "aria-label": "Cerrar", onclick: close }, icon("x"))),
    h("div", { class: "drawer-body" }, bodyNodes));
  document.body.append(bd, dr);
  document.addEventListener("keydown", onKey);
  return close;
}

// ---------------- Tabla con orden ----------------
export function dataTable(columns, rows, { onRowClick, empty = "Sin registros.", initialSort } = {}) {
  let sortKey = initialSort ? initialSort.key : null;
  let dir = initialSort ? initialSort.dir : 1;
  const tbody = h("tbody");
  const render = () => {
    const data = [...rows];
    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      const val = col.sortValue || ((r) => r[col.key]);
      data.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * dir; });
    }
    mount(tbody, data.length ? data.map((r) => h("tr", { class: onRowClick ? "clickable" : "", onclick: onRowClick ? () => onRowClick(r) : null },
      columns.map((c) => h("td", { class: c.num ? "num" : "" }, c.render ? c.render(r) : (r[c.key] ?? "—")))))
      : h("tr", null, h("td", { colspan: columns.length }, h("div", { class: "empty" }, empty))));
  };
  const head = h("tr", null, columns.map((c) => {
    const th = h("th", { class: c.sortable === false ? "" : "sortable", style: c.num ? { textAlign: "right" } : null }, c.label);
    if (c.sortable !== false) th.addEventListener("click", () => { dir = sortKey === c.key ? -dir : 1; sortKey = c.key; render(); });
    return th;
  }));
  render();
  return h("div", { class: "table-wrap" }, h("table", { class: "table" }, h("thead", null, head), tbody));
}

export function card(title, body, { actions, foot, iconName, cls = "" } = {}) {
  return h("section", { class: `card ${cls}`.trim() },
    title ? h("div", { class: "card-head" }, h("h3", null, iconName ? icon(iconName, "sm") : null, title), actions ? h("div", { class: "row" }, actions) : null) : null,
    h("div", { class: "card-body" }, body),
    foot ? h("div", { class: "card-foot" }, foot) : null);
}

export function pageHead(title, subtitle, actions) {
  return h("div", { class: "page-head" }, h("div", null, h("h1", null, title), subtitle ? h("p", null, subtitle) : null),
    actions ? h("div", { class: "page-actions" }, actions) : null);
}

export function checksList(checks) {
  return h("ul", { class: "checks" }, checks.map((c) => h("li", { class: c.ok ? "ok" : "bad" },
    icon(c.ok ? "checkCircle" : "xCircle"), h("div", null, h("b", null, c.check), h("div", { class: "muted" }, c.message)))));
}

export function uuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
  const a = new Uint8Array(16); crypto.getRandomValues(a); return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function beep(ok = true) {
  try {
    const ctx = beep.ctx || (beep.ctx = new (window.AudioContext || window.webkitAudioContext)());
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = ok ? 1150 : 220; o.type = ok ? "sine" : "square";
    g.gain.value = 0.05; o.connect(g); g.connect(ctx.destination); o.start(); o.stop(ctx.currentTime + (ok ? 0.08 : 0.25));
  } catch { /* audio no disponible */ }
}
