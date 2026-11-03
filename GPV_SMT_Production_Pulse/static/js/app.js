/* GPV SMT Production Pulse - shared frontend core.
 * All DOM content is created with textContent / createElement (never HTML string injection),
 * so values coming from FactoryLogix are always escaped.
 */
(function () {
  "use strict";

  const STATUS_LABELS = { verified: "Verificado", partial: "Parcial", unavailable: "No disponible" };

  /** Create an element: h("div", {class: "x", text: "hello"}, [children]). */
  function h(tag, attrs, children) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [key, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === "text") el.textContent = String(value);
        else if (key === "class") el.className = value;
        else if (key === "dataset") Object.assign(el.dataset, value);
        else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
        else el.setAttribute(key, value === true ? "" : String(value));
      }
    }
    for (const child of [].concat(children || [])) {
      if (child === null || child === undefined || child === false) continue;
      el.appendChild(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
    }
    return el;
  }

  function clear(el) {
    while (el && el.firstChild) el.removeChild(el.firstChild);
    return el;
  }

  const $ = (sel) => document.querySelector(sel);

  /** JSON API call. POST adds the anti-CSRF header required by the server. */
  async function api(path, options) {
    const opts = options || {};
    const init = { method: opts.method || "GET", credentials: "same-origin", headers: { Accept: "application/json" } };
    if (opts.signal) init.signal = opts.signal;
    if (init.method === "POST") {
      init.headers["Content-Type"] = "application/json";
      init.headers["X-Pulse-Request"] = "1";
      init.body = JSON.stringify(opts.body || {});
    }
    let response;
    try {
      response = await fetch(path, init);
    } catch (err) {
      if (err && err.name === "AbortError") throw err;
      return { ok: false, status: "app_unreachable", message: "No se pudo comunicar con la aplicación local. ¿Sigue en ejecución?" };
    }
    try {
      return await response.json();
    } catch (err) {
      return { ok: false, status: "invalid_response", message: "Respuesta no válida de la aplicación local." };
    }
  }

  function fmtNumber(value, decimals) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    const d = decimals === undefined ? (Number.isInteger(value) ? 0 : 2) : decimals;
    return Number(value).toLocaleString("es-MX", { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function fmtDateTime(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleString("es-MX", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function fmtAge(iso) {
    if (!iso) return "";
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 60) return "hace " + Math.round(seconds) + " s";
    if (seconds < 3600) return "hace " + Math.round(seconds / 60) + " min";
    if (seconds < 172800) return "hace " + Math.floor(seconds / 3600) + " h " + Math.round((seconds % 3600) / 60) + " min";
    return "hace " + Math.round(seconds / 86400) + " días";
  }

  function fmtDate(isoDate) {
    if (!isoDate) return "—";
    const [y, m, d] = String(isoDate).split("-");
    return d + "/" + m + "/" + y;
  }

  function setChip(el, kind, label) {
    if (!el) return;
    el.className = "chip chip-" + kind;
    el.textContent = label;
  }

  function alertBox(kind, title, items) {
    const box = h("div", { class: "alert alert-" + kind }, [title ? h("strong", { text: title }) : null]);
    if (items && items.length) box.appendChild(h("ul", null, items.map((t) => h("li", { text: t }))));
    return box;
  }

  function badge(status, label) {
    return h("span", { class: "badge badge-" + status, text: label || STATUS_LABELS[status] || status });
  }

  function filtersText(filters) {
    const parts = [];
    if (filters && filters.line) parts.push("Línea: " + filters.line);
    if (filters && filters.station) parts.push("Estación: " + filters.station);
    if (filters && filters.shift) parts.push("Turno: " + filters.shift);
    return parts.length ? parts.join(" · ") : "Sin filtros adicionales";
  }

  /** Header chip shows global health without contacting FactoryLogix. */
  async function loadStatus() {
    const status = await api("/api/status");
    const chip = $("#header-chip");
    if (!status || status.ok === false) {
      setChip(chip, "error", "App no disponible");
      return status;
    }
    if (status.data_mode === "demo") setChip(chip, "warn", "Modo DEMO");
    else if (status.breaker && status.breaker.state === "open") setChip(chip, "error", "Consultas en pausa");
    else if (status.ready) setChip(chip, "ok", "Listo para consultar");
    else setChip(chip, "warn", "Pendiente de validación");
    return status;
  }

  function markNav() {
    const page = document.body.dataset.page;
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === page) a.classList.add("active");
    });
  }

  function download(url) {
    const a = h("a", { href: url, download: "" });
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  window.Pulse = { h, clear, $, api, fmtNumber, fmtDateTime, fmtAge, fmtDate, setChip, alertBox, badge,
    filtersText, loadStatus, download, STATUS_LABELS };

  document.addEventListener("DOMContentLoaded", markNav);
})();
