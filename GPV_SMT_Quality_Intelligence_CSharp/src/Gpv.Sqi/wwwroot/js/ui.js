/* Utilidades de interfaz. Todo el contenido dinámico se inserta con textContent (protección XSS). */
"use strict";
const UI = (() => {
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function mount(node, ...children) { clear(node); children.flat().forEach(c => c && node.appendChild(c)); }

  async function api(path, body, opts = {}) {
    const init = { method: body === undefined ? "GET" : "POST",
                   headers: { "X-CSRF-Token": CSRF, "Accept": "application/json" } };
    if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    let resp;
    try { resp = await fetch(path, init); }
    catch (e) { throw new Error("No hay comunicación con el servidor local de la aplicación."); }
    if (opts.blob) {
      if (!resp.ok) { const j = await resp.json().catch(() => ({})); throw new Error(j.error || `HTTP ${resp.status}`); }
      const cd = resp.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      return { blob: await resp.blob(), filename: m ? m[1] : "reporte" };
    }
    const data = await resp.json().catch(() => ({ error: "Respuesta inválida del servidor local" }));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  const STATUS_CLASS = { OK: "ok", EMPTY: "ok", NOT_REQUESTED: "nv" };
  const STATUS_TEXT = {
    OK: "Correcto", EMPTY: "Sin registros", AUTH_ERROR: "HTTP 401", FORBIDDEN: "HTTP 403",
    NOT_FOUND: "HTTP 404", BAD_REQUEST: "HTTP 400", RATE_LIMITED: "HTTP 429", SERVER_ERROR: "Error servidor",
    HTTP_ERROR: "Error HTTP", TIMEOUT: "Timeout", CONNECTION_ERROR: "Sin conexión",
    INVALID_RESPONSE: "Respuesta inválida", BLOCKED_BY_POLICY: "Bloqueado por política",
    NOT_CONFIGURED: "No configurado", VALIDATION_ERROR: "Entrada inválida", BUSY: "Ocupado",
    NOT_REQUESTED: "No requerida",
  };
  function statusChip(s) {
    if (!s) return el("span", { class: "chip nv", text: "Sin datos" });
    let cls = STATUS_CLASS[s.status] || "err";
    let text = STATUS_TEXT[s.status] || s.status;
    if (s.stale) { cls = "warn"; text += " · caché"; }
    return el("span", { class: `chip ${cls}`, text, title: s.label || s.status });
  }

  function fmtTime(v) {
    if (!v) return "—";
    const m = String(v).match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/);
    if (!m) return String(v);
    return `${m[1]} ${m[2]}${m[3] ? m[3].slice(0, 4) : ""}${m[4] ? " (" + (m[4] === "Z" ? "UTC" : m[4]) + ")" : ""}`;
  }
  function fmtMs(ms) {
    if (ms === null || ms === undefined) return "—";
    return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
  }

  function stateBox(kind, text) { return el("div", { class: `state ${kind}`, text }); }

  function tile(label, value, sub, small) {
    return el("div", { class: "tile" }, el("div", { class: "label", text: label }),
      el("div", { class: "value" + (small ? " small" : ""), text: value === null || value === undefined ? "—" : String(value) }),
      sub ? el("div", { class: "sub", text: sub }) : null);
  }

  function kv(k, v) {
    const empty = v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length);
    return el("div", { class: "kv" }, el("div", { class: "k", text: k }),
      el("div", { class: "v" + (empty ? " nv" : ""), text: empty ? "No verificable" : (Array.isArray(v) ? v.join(", ") : String(v)) }));
  }

  /* Tabla con búsqueda, filtro y ordenamiento. columns: [{key, label, fmt?, mono?}] */
  function dataTable(columns, rows, opts = {}) {
    let sortKey = opts.sortKey || null, sortDir = opts.sortDir || 1, query = "";
    const tbody = el("tbody");
    const count = el("span", { class: "count" });
    const headers = columns.map(c => {
      const th = el("th", { text: c.label, scope: "col", tabindex: "0" });
      const toggle = () => { sortDir = sortKey === c.key ? -sortDir : 1; sortKey = c.key; render(); };
      th.addEventListener("click", toggle);
      th.addEventListener("keydown", e => { if (e.key === "Enter") toggle(); });
      c._th = th; return th;
    });
    function cellText(r, c) { const v = r[c.key]; return c.fmt ? c.fmt(v, r) : (v === null || v === undefined ? "" : String(v)); }
    function render() {
      let data = rows.slice();
      if (query) { const q = query.toLowerCase(); data = data.filter(r => columns.some(c => cellText(r, c).toLowerCase().includes(q))); }
      if (sortKey) {
        data.sort((a, b) => {
          const x = a[sortKey], y = b[sortKey];
          if (typeof x === "number" && typeof y === "number") return (x - y) * sortDir;
          return String(x ?? "").localeCompare(String(y ?? ""), "es", { numeric: true }) * sortDir;
        });
      }
      columns.forEach(c => c._th.setAttribute("aria-sort", c.key === sortKey ? (sortDir > 0 ? "ascending" : "descending") : "none"));
      clear(tbody);
      for (const r of data.slice(0, opts.limit || 1000)) {
        const tr = el("tr", opts.onRow ? { class: "clickable", tabindex: "0" } : null,
          columns.map(c => el("td", { class: c.mono ? "mono" : null, text: cellText(r, c) })));
        if (opts.onRow) {
          tr.addEventListener("click", () => { tbody.querySelectorAll("tr.selected").forEach(t => t.classList.remove("selected")); tr.classList.add("selected"); opts.onRow(r); });
          tr.addEventListener("keydown", e => { if (e.key === "Enter") tr.click(); });
        }
        tbody.appendChild(tr);
      }
      count.textContent = `${data.length} de ${rows.length} registros`;
    }
    const filter = el("input", { class: "table-filter", type: "search", placeholder: "Buscar en la tabla…", "aria-label": "Buscar en la tabla" });
    filter.addEventListener("input", () => { query = filter.value.trim(); render(); });
    render();
    if (!rows.length) return stateBox("", opts.empty || "Sin registros.");
    return el("div", null, el("div", { class: "table-tools" }, filter, count),
      el("div", { class: "table-wrap" }, el("table", { class: "data" }, el("thead", null, el("tr", null, headers)), tbody)));
  }

  /* Barras horizontales de una sola serie (magnitud). Los valores siempre visibles como texto. */
  function bars(items, opts = {}) {
    if (!items || !items.length) return stateBox("", "Sin datos.");
    const max = Math.max(...items.map(i => i.count), 1);
    const list = items.slice(0, opts.limit || 10);
    const rest = items.slice(opts.limit || 10);
    if (rest.length) list.push({ key: `Otros (${rest.length})`, count: rest.reduce((a, b) => a + b.count, 0) });
    return el("div", { class: "bars", role: "list" }, list.map(i => {
      const fill = el("div", { class: "bar-fill" });
      fill.style.width = `${Math.max(1, (i.count / max) * 100)}%`;
      return el("div", { class: "bar-row", role: "listitem", title: `${i.key}: ${i.count}` },
        el("span", { class: "lbl", text: i.key }), el("div", { class: "bar-track" }, fill),
        el("span", { class: "num", text: String(i.count) }));
    }));
  }

  let toastTimer;
  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
  }

  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function toIsoFromLocal(v) { if (!v) return null; const d = new Date(v); return isNaN(d) ? null : d.toISOString(); }

  return { el, clear, mount, api, statusChip, fmtTime, fmtMs, stateBox, tile, kv, dataTable, bars, toast, download, toIsoFromLocal, STATUS_TEXT };
})();
