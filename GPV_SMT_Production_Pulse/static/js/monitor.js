/* Live monitor: polls the LOCAL API (/api/monitor, SQLite only) and updates the DOM in place.
 * The browser never triggers OData requests; the background collector is the only reader of
 * FactoryLogix. No full page reloads.
 */
(function () {
  "use strict";
  const { h, clear, $, api, fmtNumber, fmtDateTime, fmtAge, setChip, alertBox } = Pulse;
  const Charts = window.PulseCharts;
  const STATUS = {
    starting: ["loading", "Iniciando"], querying: ["loading", "Consultando"], ok: ["ok", "Actualizado"],
    backoff: ["error", "Error: reintento programado"], waiting: ["warn", "En espera"],
    blocked: ["error", "Recolección bloqueada"], stopped: ["error", "Detenido"],
  };
  const DIM_ORDER = ["project", "work_order", "product"];
  let data = null;
  let timer = null;
  let inFlight = false;

  const fmtTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso) :
      d.toLocaleString("es-MX", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  const fmtSeconds = (s) => {
    if (s === null || s === undefined) return "—";
    if (s < 90) return Math.round(s) + " s";
    if (s < 5400) return Math.round(s / 60) + " min";
    return (s / 3600).toFixed(1) + " h";
  };

  function card(title, status, value, unit, note) {
    return h("div", { class: "card status-" + status }, [
      h("div", { class: "card-title" }, [title + " ", Pulse.badge(status)]),
      h("div", { class: "card-value" + (String(value).length > 12 ? " small-value" : ""), text: value }),
      h("div", { class: "card-unit", text: unit || "" }),
      h("div", { class: "card-note", text: note || "" }),
    ]);
  }

  function tile(label, value, sub) {
    return h("div", { class: "tile" }, [h("div", { class: "tile-label", text: label }),
      h("div", { class: "tile-value", text: value }), h("div", { class: "tile-sub", text: sub || "" })]);
  }

  function renderStatus(d) {
    const c = d.collector || {};
    const m = d.metrics;
    let [kind, label] = STATUS[c.status] || ["idle", c.status || "Sin estado"];
    if (!d.collector_mode) { kind = "error"; label = "Recolector inactivo"; }
    else if (c.status === "ok" && m.activity === "syncing") { kind = "loading"; label = "Sincronizando historial"; }
    else if (c.status === "ok" && !m.has_recent_activity) { kind = "warn"; label = "Sin datos recientes"; }
    setChip($("#mon-chip"), kind, label);
    $("#mon-msg").textContent = (c.message || "") + (d.data_mode === "demo" ? " (MODO DEMO: datos simulados)" : "");
    updateCountdown();
    const warn = clear($("#mon-warnings"));
    d.warnings.forEach((w) => warn.appendChild(alertBox(w.kind === "error" ? "error" : w.kind === "info" ? "info" : "warn", w.text)));
  }

  function updateCountdown() {
    if (!data) return;
    const c = data.collector || {};
    const parts = ["Última lectura correcta: " + (c.last_success_at ? fmtTime(c.last_success_at) + " (" + fmtAge(c.last_success_at) + ")" : "ninguna")];
    if (c.next_run_at && data.collector_mode) {
      const s = Math.max(0, Math.round((new Date(c.next_run_at).getTime() - Date.now()) / 1000));
      parts.push("Próxima consulta en " + Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"));
    }
    $("#mon-when").textContent = parts.join(" · ");
  }

  function renderCards(d) {
    const m = d.metrics;
    const wrap = clear($("#mon-cards"));
    const unit = m.unit ? "unidades (" + m.unit + ")" : "";
    const u = m.units_today;
    wrap.appendChild(card("Unidades registradas hoy", u.status, u.value === null ? "—" : fmtNumber(u.value), unit,
      u.value === null ? (m.quantity_field ? "Sin registros hoy o semántica sin confirmar." : "No hay campo de cantidad identificado.")
        : `${u.records} registro(s) por hora de producción${u.unknown ? ` · ${u.unknown} sin lectura base` : ""}.`));
    const inc = m.increment;
    wrap.appendChild(card("Incremento entre lecturas", inc.status, inc.value === undefined ? "—" : (inc.value > 0 ? "+" : "") + fmtNumber(inc.value), unit,
      inc.value === undefined ? inc.note : `${fmtTime(inc.from)} → ${fmtTime(inc.to)} (${fmtSeconds(inc.seconds)}). ${inc.note}`));
    const t = m.trend;
    const arrow = t.direction === "up" ? "▲ " : t.direction === "down" ? "▼ " : "";
    wrap.appendChild(card("Tendencia por hora", t.status, t.percent === undefined ? "—" : arrow + fmtNumber(t.percent, 1) + " %", "",
      t.percent === undefined ? t.note : `${t.note} ${fmtNumber(t.last_value)} vs ${fmtNumber(t.previous_value)}.`));
    wrap.appendChild(card("Hora del último registro", m.latest_production_ts ? "verified" : "unavailable",
      m.latest_production_ts ? fmtTime(m.latest_production_ts) : "Sin registros", "hora de producción (FactoryLogix)",
      m.latest_production_ts ? "Antigüedad: " + fmtSeconds(m.latest_production_age_seconds) +
        (m.source_lag_seconds !== null ? ` · diferencia con la última consulta: ${fmtSeconds(m.source_lag_seconds)}` : "") : ""));
    const act = { active: ["verified", "Con actividad", "Hay producción registrada en la ventana reciente."],
      syncing: ["partial", "Sincronizando", "Recuperando historial; registros confirmados hasta " + fmtTime(m.complete_until) + "."],
      no_recent_data: ["unavailable", "Sin datos recientes", "No se ha confirmado actividad en la ventana reciente."] }[m.activity];
    wrap.appendChild(card("Actividad reciente", act[0], act[1], `últimos ${m.recent_minutes} min (hora de producción)`, act[2]));
  }

  function renderSeries(d) {
    const m = d.metrics;
    $("#mon-series-unit").textContent = m.unit ? "Unidad: " + m.unit : "";
    Charts.bar($("#mon-chart"), {
      unit: m.unit,
      items: m.series.map((s) => ({ label: s.label, value: s.value, cls: s.in_progress ? "progress" : s.partial ? "drop" : "",
        title: s.records + " registro(s)" + (s.in_progress ? " · hora en curso o aún sin sincronizar" : "") })),
    });
  }

  function renderLines(d) {
    const m = d.metrics;
    $("#mon-recent-head").textContent = "Últimos " + m.recent_minutes + " min";
    const body = clear($("#mon-lines").tBodies[0]);
    const empty = $("#mon-lines-empty");
    if (!d.mapping.line) {
      empty.textContent = "La entidad no tiene un campo de línea identificado: no se pueden mostrar líneas SMT.";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.toggle("hidden", m.lines.length > 0);
    if (!m.lines.length) empty.textContent = "Sin registros guardados de líneas en las últimas 24 h.";
    $("#mon-lines-note").textContent = "Campo: " + d.mapping.line;
    m.lines.forEach((l) => {
      body.appendChild(h("tr", null, [
        h("td", { text: l.line }),
        h("td", { class: "num", text: fmtNumber(l.units_today) + (l.partial ? " *" : "") }),
        h("td", { class: "num", text: fmtNumber(l.recent_units) }),
        h("td", { text: fmtTime(l.last_production_ts) }),
        h("td", null, [l.status === "active" ? Pulse.badge("verified", "Activa") : l.status === "syncing" ? Pulse.badge("partial", "Sincronizando")
          : Pulse.badge("unavailable", "Sin datos recientes")]),
      ]));
    });
  }

  function renderDims(d) {
    const wrap = clear($("#mon-dims"));
    const m = d.metrics;
    DIM_ORDER.forEach((dim) => {
      const items = m.dimensions[dim];
      if (!items) return;  // field not identified in ProductivityOverTime: section not shown
      const top = items.slice().sort((a, b) => b.units - a.units).slice(0, 12);
      wrap.appendChild(h("section", { class: "panel" }, [
        h("div", { class: "panel-head" }, [h("h2", { text: m.dimension_labels[dim] + " (hoy)" }), h("span", { class: "muted small", text: "Campo: " + d.mapping[dim] })]),
        top.length ? h("div", { class: "table-wrap" }, [h("table", null, [
          h("thead", null, [h("tr", null, [h("th", { text: m.dimension_labels[dim] }), h("th", { class: "num", text: "Unidades" }), h("th", { text: "Último registro" })])]),
          h("tbody", null, top.map((g) => h("tr", null, [h("td", { text: g.name }), h("td", { class: "num", text: fmtNumber(g.units) + (g.unknown ? " *" : "") }), h("td", { text: fmtTime(g.last_ts) })]))),
        ])]) : h("p", { class: "note", text: "Sin registros hoy." }),
      ]));
    });
  }

  function renderTimes(d) {
    const c = d.collector || {};
    const m = d.metrics;
    const tiles = clear($("#mon-times"));
    tiles.appendChild(tile("Última consulta exitosa", fmtTime(c.last_success_at), "Hora de CONSULTA a FactoryLogix"));
    tiles.appendChild(tile("Último intento", fmtTime(c.last_attempt_at), c.last_error ? "Error: " + (c.last_error.http_status || c.last_error.status) : "Sin error"));
    tiles.appendChild(tile("Registro más reciente", fmtTime(m.latest_production_ts), "Hora de PRODUCCIÓN del registro"));
    tiles.appendChild(tile("Registros guardados", fmtNumber(d.records.records), `${fmtNumber(d.records.revisions)} lecturas en historial`));
    tiles.appendChild(tile("Frecuencia", fmtSeconds(c.interval_seconds), "1 consulta OData por ciclo · autenticación: " + (c.auth || "—")));
    tiles.appendChild(tile("Cobertura local desde", fmtTime(c.coverage_start), c.catching_up ? "Sincronizando historial" : "Al día"));
    const sem = m.semantics;
    $("#mon-semantics").textContent = "Semántica de la cantidad: " + sem.label + " — " + (sem.source === "config" ? "definida en config.json" :
      sem.source === "auto" ? "detectada automáticamente (confirmar con MES)" : "sin campo de cantidad") + ". " + sem.reason;
    const body = clear($("#mon-runs").tBodies[0]);
    (d.runs || []).forEach((r) => {
      body.appendChild(h("tr", null, [h("td", { text: fmtTime(r.started_at) }), h("td", { text: r.kind }), h("td", { text: r.status }),
        h("td", { class: "num", text: r.http_status || "" }), h("td", { class: "num", text: r.elapsed_ms ? Math.round(r.elapsed_ms) : "" }),
        h("td", { class: "num", text: r.records_received ?? "" }), h("td", { class: "num", text: r.inserted ?? "" }),
        h("td", { class: "num", text: r.updated ?? "" }), h("td", { class: "num", text: r.unchanged ?? "" }),
        h("td", { class: "mono", text: r.window_start ? r.window_start.slice(11, 16) + "–" + (r.window_end || "").slice(11, 16) : "" }),
        h("td", { text: (r.message || "").slice(0, 120) })]));
    });
  }

  async function refresh() {
    if (inFlight) return;
    inFlight = true;
    try {
      const d = await api("/api/monitor");
      if (!d || d.ok === false) {
        setChip($("#mon-chip"), "error", "Aplicación no disponible");
        $("#mon-msg").textContent = (d && d.message) || "No se pudo leer el estado local. Los últimos valores mostrados pueden estar desactualizados.";
        return;
      }
      data = d;
      renderStatus(d);
      renderCards(d);
      renderSeries(d);
      renderLines(d);
      renderDims(d);
      renderTimes(d);
    } finally {
      inFlight = false;
      schedule(data ? data.poll_seconds : 30);  // keep polling even after a failed local read
    }
  }

  function schedule(seconds) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(refresh, Math.max(10, seconds || 30) * 1000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    Pulse.loadStatus();
    refresh();
    setInterval(updateCountdown, 1000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(); });
  });
})();
