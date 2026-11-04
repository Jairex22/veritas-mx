/* Production page: operator flow (period -> line -> Consultar -> results -> export). */
(function () {
  "use strict";
  const { h, clear, $, api, fmtNumber, fmtDateTime, fmtAge, fmtDate, setChip, alertBox } = Pulse;
  const Charts = window.PulseCharts;
  const STORAGE_KEY = "pulse.filters.v1";
  const INTERVAL_LABELS = { hour: "Hora", day: "Día", shift: "Turno" };
  const FILTER_ROLES = ["line", "station", "shift"];

  let status = null;
  let current = null;          // last rendered result
  let lastBody = null;         // last query body sent
  let controller = null;       // AbortController of the active request
  let sequence = 0;            // logical cancellation of stale responses
  let busy = false;
  const reportIds = {};        // cache_id|interval -> report_id

  function storageGet() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); } catch (e) { return null; }
  }
  function storageSet(value) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); } catch (e) { /* optional convenience */ }
  }
  function storageClear() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
  }

  function formBody() {
    const body = { start: $("#f-start").value, end: $("#f-end").value, interval: $("#f-interval").value };
    FILTER_ROLES.forEach((role) => {
      const field = document.querySelector(`[data-filter="${role}"]`);
      if (field && !field.classList.contains("hidden")) {
        const value = $("#f-" + role).value.trim();
        if (value) body[role] = value;
      }
    });
    return body;
  }

  function setBusy(value) {
    busy = value;
    $("#btn-query").disabled = value;
    $("#btn-query").textContent = value ? "Consultando…" : "Consultar producción";
  }

  function setExportEnabled(enabled) {
    ["#btn-xlsx", "#btn-pdf", "#btn-csv"].forEach((id) => { $(id).disabled = !enabled; });
  }

  // ------------------------------------------------------------------ init
  async function init() {
    status = await Pulse.loadStatus();
    if (!status || status.ok === false) {
      setChip($("#state-chip"), "error", "Aplicación no disponible");
      $("#state-msg").textContent = (status && status.message) || "No se pudo cargar el estado.";
      return;
    }
    $("#tz-note").textContent = "Horario: " + status.timezone;
    const today = status.today;
    const saved = storageGet();
    $("#f-start").value = (saved && saved.start) || today;
    $("#f-end").value = (saved && saved.end) || today;
    $("#f-start").max = today;
    $("#f-end").max = today;

    const sel = clear($("#f-interval"));
    status.available.intervals.forEach((iv) => sel.appendChild(h("option", { value: iv, text: INTERVAL_LABELS[iv] })));
    if (saved && status.available.intervals.includes(saved.interval)) sel.value = saved.interval;

    const missing = [];
    FILTER_ROLES.forEach((role) => {
      const field = document.querySelector(`[data-filter="${role}"]`);
      const available = status.available.filters[role];
      field.classList.toggle("hidden", !available);
      if (!available) missing.push({ line: "línea", station: "estación", shift: "turno" }[role]);
      const dl = clear($("#dl-" + role));
      (status.known_values[role] || []).forEach((v) => dl.appendChild(h("option", { value: v })));
      if (available && saved && saved[role]) $("#f-" + role).value = saved[role];
    });
    $("#filters-note").textContent = missing.length
      ? "Filtros no mostrados (campo inexistente o filtro no comprobado en FactoryLogix): " + missing.join(", ") + "."
      : "";

    const readiness = $("#readiness");
    if (status.collector_mode) {
      // All data comes from the local store filled by the background collector.
      $("#f-force").closest("label").classList.add("hidden");
      $("#btn-last").classList.add("hidden");
      clear(readiness).classList.remove("hidden");
      readiness.className = "alert alert-info";
      readiness.appendChild(document.createTextNode("Consulta sobre la información local guardada por el recolector automático. " +
        "Esta pantalla no envía consultas a FactoryLogix; los filtros se aplican sobre los registros guardados."));
    } else if (!status.ready) {
      clear(readiness).classList.remove("hidden");
      readiness.appendChild(h("strong", { text: "Las consultas a FactoryLogix están bloqueadas hasta completar la validación:" }));
      readiness.appendChild(h("ul", null, status.readiness_reasons.map((r) => h("li", { text: r }))));
      readiness.appendChild(h("a", { href: "/diagnostics", text: "Ir a Estado de conexión" }));
      readiness.appendChild(document.createTextNode(" · Puedes consultar información guardada con “Ver última consulta”."));
    }
    if (status.limits.AUTO_REFRESH_ENABLED) setupAutoRefresh();

    $("#btn-query").addEventListener("click", () => runQuery(formBody()));
    $("#btn-last").addEventListener("click", loadLast);
    $("#btn-clear").addEventListener("click", clearFilters);
    $("#btn-xlsx").addEventListener("click", () => exportReport("xlsx"));
    $("#btn-csv").addEventListener("click", () => exportReport("csv"));
    $("#btn-pdf").addEventListener("click", () => exportReport("pdf"));
    $("#query-form").addEventListener("submit", (e) => { e.preventDefault(); runQuery(formBody()); });
  }

  function clearFilters() {
    storageClear();
    $("#f-start").value = status.today;
    $("#f-end").value = status.today;
    FILTER_ROLES.forEach((role) => { $("#f-" + role).value = ""; });
    $("#f-interval").value = "hour";
    $("#f-force").checked = false;
  }

  // ------------------------------------------------------------------ queries
  async function post(body) {
    if (controller) controller.abort();       // logical cancellation of obsolete requests
    controller = new AbortController();
    const mySeq = ++sequence;
    try {
      const result = await api("/api/query", { method: "POST", body, signal: controller.signal });
      return mySeq === sequence ? result : null;
    } catch (err) {
      return null;  // aborted
    }
  }

  async function runQuery(body, options) {
    if (busy) return;                           // repeated-click protection
    const opts = options || {};
    if (!opts.silent) body.force_refresh = $("#f-force").checked;
    storageSet({ start: body.start, end: body.end, interval: body.interval, line: body.line, station: body.station, shift: body.shift });
    lastBody = Object.assign({}, body);
    setBusy(true);
    setChip($("#state-chip"), "loading", "Consultando");
    $("#state-msg").textContent = "Consultando… (la información vigente en caché se reutiliza automáticamente)";
    $("#state-when").textContent = "";
    clear($("#state-extra"));
    const result = await post(body);
    setBusy(false);
    $("#f-force").checked = false;
    if (!result) return;
    if (result.ok) render(result);
    else renderError(result);
    Pulse.loadStatus();
  }

  async function loadLast() {
    if (busy) return;
    setChip($("#state-chip"), "loading", "Cargando");
    const result = await api("/api/last-query");
    if (result.ok) render(result);
    else renderError(result);
  }

  async function loadStored(cacheId, interval) {
    const qs = "?id=" + encodeURIComponent(cacheId) + (interval ? "&interval=" + encodeURIComponent(interval) : "");
    const result = await api("/api/stored" + qs);
    if (result.ok) render(result);
    else renderError(result);
  }

  // ------------------------------------------------------------------ rendering
  const ERROR_CHIPS = {
    busy: ["warn", "Consulta en curso"], rate_limited: ["warn", "Espera"], session_limit: ["warn", "Límite alcanzado"],
    global_limit: ["warn", "Límite alcanzado"], invalid_input: ["warn", "Revisa los filtros"],
    blocked_unverified: ["warn", "Datos no verificables"], auto_refresh_disabled: ["warn", "Deshabilitado"],
    no_stored_data: ["idle", "Sin datos guardados"], bad_request: ["warn", "Consulta incompatible"],
    metadata_incompatible: ["warn", "Datos no verificables"], invalid_json: ["warn", "Datos no verificables"],
    incomplete_data: ["warn", "Datos no verificables"], unsupported_format: ["warn", "Datos no verificables"],
  };

  function renderError(result) {
    const [kind, label] = ERROR_CHIPS[result.status] || ["error", "Servidor no disponible"];
    setChip($("#state-chip"), kind, label);
    $("#state-msg").textContent = result.message || "No se pudo completar la consulta.";
    $("#state-when").textContent = "";
    $("#results").classList.add("hidden");   // never leave old data looking current
    current = null;
    setExportEnabled(false);
    const extra = clear($("#state-extra"));
    if (result.reasons && result.reasons.length) extra.appendChild(alertBox("warn", "Motivo:", result.reasons));
    if (result.stored_available) {
      const box = h("div", { class: "alert alert-info" }, [
        document.createTextNode("Hay información guardada extraída el " + fmtDateTime(result.stored_fetched_at) + " (" + fmtAge(result.stored_fetched_at) + "). "),
        h("button", { type: "button", class: "btn btn-sm", text: "Ver información guardada", onclick: () => loadStored(result.stored_cache_id) }),
      ]);
      extra.appendChild(box);
    }
  }

  function render(result) {
    current = result;
    const a = result.analytics;
    const empty = a.records_used === 0;
    if (empty) setChip($("#state-chip"), "idle", "Sin registros");
    else if (result.source === "odata") setChip($("#state-chip"), "ok", "Datos disponibles");
    else if (result.source === "cache") setChip($("#state-chip"), "cache", "Información desde caché");
    else if (result.source === "local") setChip($("#state-chip"), result.is_fresh ? "ok" : "warn", result.is_fresh ? "Datos locales" : "Datos locales no recientes");
    else setChip($("#state-chip"), "warn", "Información guardada");
    const demo = result.data_mode === "demo" ? " (DATOS SIMULADOS)" : "";
    $("#state-msg").textContent = result.message + demo + " · Periodo " + fmtDate(result.query.period.start) + " – " +
      fmtDate(result.query.period.end) + " · " + Pulse.filtersText(result.query.filters);
    $("#state-when").textContent = result.fetched_at
      ? (result.source === "local" ? "Última lectura del recolector: " : "Extraído: ") + fmtDateTime(result.fetched_at) + " (" + fmtAge(result.fetched_at) + ")"
      : "Sin lecturas del recolector";
    const extra = clear($("#state-extra"));
    if (result.notice) extra.appendChild(alertBox("info", result.notice));
    if (result.warnings && result.warnings.length) extra.appendChild(alertBox("warn", "Atención:", result.warnings));

    $("#results").classList.remove("hidden");
    setExportEnabled(true);
    renderCards(result);
    renderCharts(result);
    renderTable(result);
    const lim = clear($("#limitations"));
    a.limitations.forEach((t) => lim.appendChild(h("li", { text: t })));
    let decoded = result.relative_url;
    try { decoded = decodeURIComponent(result.relative_url); } catch (e) { /* keep raw */ }
    $("#query-url").textContent = decoded ? "Consulta OData utilizada: " + decoded : "Fuente: almacenamiento local SQLite (recolector automático).";
  }

  function card(title, status, value, unit, note, extraNode) {
    const isText = typeof value === "string" && value.length > 12;
    return h("div", { class: "card status-" + status }, [
      h("div", { class: "card-title" }, [title + " ", Pulse.badge(status)]),
      h("div", { class: "card-value" + (isText ? " small-value" : ""), text: value }),
      h("div", { class: "card-unit", text: unit || "" }),
      h("div", { class: "card-note", text: note || "" }),
      extraNode || null,
    ]);
  }

  function renderCards(result) {
    const wrap = clear($("#cards"));
    const byId = {};
    result.analytics.cards.forEach((c) => { byId[c.id] = c; });
    const add = (c) => { if (c) wrap.appendChild(card(c.title, c.status, c.id === "updated" ? fmtDateTime(c.value) : c.display, c.unit, c.note)); };
    add(byId.production);
    add(byId.per_period);
    wrap.appendChild(trendCard(result));
    add(byId.lines);
    add(byId.updated);
  }

  function trendCard(result) {
    const t = result.trend || { status: "unavailable" };
    const prev = t.previous_period;
    const prevText = prev ? "Periodo anterior: " + fmtDate(prev.start) + " – " + fmtDate(prev.end) : "";
    if (t.status === "unavailable") {
      let action = null;
      if (prev && status && status.ready && !status.collector_mode && result.analytics.total !== null && result.analytics.total !== undefined) {
        action = h("button", { type: "button", class: "btn btn-sm", text: "Consultar periodo anterior", onclick: () => fetchPrevious(result) });
      }
      return card("Tendencia vs periodo anterior", "unavailable", "—", "", (t.note || "") + " " + prevText, action);
    }
    const arrow = t.direction === "up" ? "▲ " : t.direction === "down" ? "▼ " : "";
    const value = t.percent === null || t.percent === undefined ? "—" : arrow + fmtNumber(t.percent, 1) + " %";
    const note = prevText + " · anterior: " + fmtNumber(t.previous_total) + " (extraído " + fmtDateTime(t.previous_fetched_at) + ")";
    return card("Tendencia vs periodo anterior", t.status, value, "variación de la producción registrada", note);
  }

  async function fetchPrevious(result) {
    const prev = result.trend.previous_period;
    const body = Object.assign({}, result.query.filters, { start: prev.start, end: prev.end, interval: result.query.interval });
    Object.keys(body).forEach((k) => { if (body[k] === null) delete body[k]; });
    const currentBody = Object.assign({}, body, { start: result.query.period.start, end: result.query.period.end });
    if (busy) return;
    setBusy(true);
    setChip($("#state-chip"), "loading", "Consultando");
    $("#state-msg").textContent = "Consultando el periodo anterior para calcular la tendencia…";
    let prevResult = await post(body);
    if (prevResult && prevResult.status === "rate_limited" && prevResult.wait_seconds <= 10) {
      // Respect the server-imposed spacing, then try exactly once more (no loops).
      const wait = (prevResult.wait_seconds || 1) + 1;
      $("#state-msg").textContent = "Respetando el intervalo mínimo entre consultas: se consultará el periodo anterior en " + wait + " s…";
      await new Promise((resolve) => setTimeout(resolve, wait * 1000));
      prevResult = await post(body);
    }
    setBusy(false);
    if (!prevResult) return;
    if (!prevResult.ok) { renderError(prevResult); return; }
    await runQuery(currentBody, { silent: true });  // served from cache: no additional OData request
  }

  function renderCharts(result) {
    const a = result.analytics;
    const unit = a.unit || "";
    const dropLabels = new Set(a.drops.map((d) => d.label));
    $("#series-unit").textContent = unit ? "Unidad: " + unit : "";
    Charts.bar($("#chart-series"), {
      unit,
      items: a.series.map((s) => ({ label: s.label, value: s.value, title: s.records + " registro(s)" + (s.in_progress ? " · en curso" : ""),
        cls: s.in_progress ? "progress" : dropLabels.has(s.label) ? "drop" : "" })),
    });
    let acc = 0;
    Charts.line($("#chart-trend"), {
      unit: unit ? unit + " (acumulado)" : "",
      points: a.series.filter((s) => s.value !== null).map((s) => { acc += s.value; return { label: s.label, value: acc }; }),
    });
    const hasLine = Boolean(result.mapping && result.mapping.line);
    $("#panel-lines").classList.toggle("hidden", !hasLine);
    if (hasLine) {
      $("#lines-unit").textContent = unit;
      Charts.hbar($("#chart-lines"), { unit, items: a.by_line.filter((g) => g.with_quantity).map((g) => ({ label: g.name, value: g.value })) });
    }
    const hasShift = Boolean(result.mapping && result.mapping.shift);
    $("#panel-shifts").classList.toggle("hidden", !hasShift);
    if (hasShift) {
      $("#shifts-unit").textContent = unit;
      Charts.hbar($("#chart-shifts"), { unit, items: a.by_shift.filter((g) => g.with_quantity).map((g) => ({ label: g.name, value: g.value, cls: "alt" })) });
    }
    const dist = a.by_station.length > 1 ? a.by_station : a.by_line.length ? a.by_line : a.by_station;
    Charts.hbar($("#chart-dist"), { unit: "registros", items: dist.map((g) => ({ label: g.name, value: g.records, cls: "alt" })) });

    $("#drop-rule").textContent = a.drop_rule;
    const list = clear($("#drops"));
    if (!a.drops.length) list.appendChild(h("li", { class: "muted", text: a.records_used ? "No se detectaron intervalos completos con disminuciones relevantes (o no hay suficientes intervalos)." : Charts.EMPTY }));
    a.drops.forEach((d) => list.appendChild(h("li", { text: `${d.label}: ${fmtNumber(d.value)} ${unit} (${fmtNumber(d.percent, 1)} % vs mediana ${fmtNumber(d.reference)})` })));
  }

  function renderTable(result) {
    const m = result.mapping || {};
    const cols = [["timestamp", "Fecha/hora"]];
    if (m.line) cols.push(["line", "Línea"]);
    if (m.station) cols.push(["station", "Estación"]);
    if (m.shift) cols.push(["shift", "Turno"]);
    if (m.quantity) cols.push(["quantity", "Cantidad (" + (m.quantity) + ")"]);
    const table = $("#rows-table");
    clear(table.tHead).appendChild(h("tr", null, cols.map(([k, label]) => h("th", { class: k === "quantity" ? "num" : null, text: label }))));
    const body = clear(table.tBodies[0]);
    result.rows.forEach((row) => {
      body.appendChild(h("tr", null, cols.map(([k]) => h("td", { class: k === "quantity" ? "num" : null,
        text: k === "quantity" ? fmtNumber(row[k]) : (row[k] === null || row[k] === undefined ? "—" : row[k]) }))));
    });
    $("#rows-count").textContent = result.rows.length + " registro(s)" + (result.more_available ? " · resultado parcial" : "");
  }

  // ------------------------------------------------------------------ exports
  async function exportReport(format) {
    if (!current) return;
    const local = current.source === "local";
    const key = local ? "local|" + JSON.stringify(current.query) : current.cache_id + "|" + current.query.interval;
    const popup = format === "pdf" ? window.open("about:blank", "_blank") : null;
    let id = reportIds[key];
    if (!id) {
      const body = local
        ? { local_query: Object.assign({ start: current.query.period.start, end: current.query.period.end, interval: current.query.interval },
          ...Object.entries(current.query.filters).filter(([, v]) => v).map(([k, v]) => ({ [k]: v }))) }
        : { cache_id: current.cache_id, interval: current.query.interval, viewed_source: current.source };
      const res = await api("/api/reports", { method: "POST", body });
      if (!res.ok) {
        if (popup) popup.close();
        clear($("#state-extra")).appendChild(alertBox("error", res.message || "No se pudo generar el reporte."));
        return;
      }
      id = reportIds[key] = res.report_id;
    }
    if (format === "pdf") {
      const url = "/reports/print?id=" + encodeURIComponent(id) + "&print=1";
      if (popup) popup.location.href = url; else window.location.href = url;
    } else {
      Pulse.download("/api/reports/" + encodeURIComponent(id) + "/" + format);
    }
  }

  // ------------------------------------------------------------------ optional auto refresh
  function setupAutoRefresh() {
    const seconds = Math.max(status.limits.AUTO_REFRESH_INTERVAL_SECONDS, status.limits.MIN_REFRESH_INTERVAL_SECONDS);
    $("#filters-note").textContent += " Actualización automática activa cada " + seconds + " s (solo con la pestaña visible; usa la caché).";
    setInterval(() => {
      if (document.visibilityState !== "visible" || !lastBody || busy) return;
      runQuery(Object.assign({}, lastBody, { auto: true, force_refresh: false }), { silent: true });
    }, seconds * 1000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
