/* GPV SMT Quality Intelligence — controlador de vistas. */
"use strict";
(() => {
  const { el, mount, api, statusChip, fmtTime, fmtMs, stateBox, tile, kv, dataTable, bars, toast, download, toIsoFromLocal } = UI;
  const $ = id => document.getElementById(id);
  const TITLES = { dashboard: "Dashboard", trace: "Trazabilidad de Unidad", pulse: "SMT Production Pulse",
    quality: "Quality Intelligence", rework: "Rework & Loop Detector", history: "Historial", reports: "Reportes",
    config: "Configuración", diagnostics: "Diagnóstico OData" };
  const CLASS_TEXT = { ACTIVE: "Defecto activo", CLOSED: "Cerrado (no implica PASS)", HISTORY_INCOMPLETE: "Historial incompleto", UNKNOWN_STATUS: "Estado no reconocido" };
  const CLASS_CHIP = { ACTIVE: "err", CLOSED: "ok", HISTORY_INCOMPLETE: "warn", UNKNOWN_STATUS: "nv" };
  let STATUS = null, pulseTimer = null;
  const busy = new Set();

  /* ---------------------------------------------------------- tema y navegación */
  function applyTheme(t) { document.documentElement.dataset.theme = t; try { localStorage.setItem("gpv-theme", t); } catch (e) { /* opcional */ } }
  try { applyTheme(localStorage.getItem("gpv-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")); } catch (e) { applyTheme("light"); }
  $("theme-btn").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  $("menu-btn").addEventListener("click", () => $("sidebar").classList.toggle("open"));

  function route() {
    const view = (location.hash || "#dashboard").slice(1).split("?")[0];
    const name = TITLES[view] ? view : "dashboard";
    document.querySelectorAll(".view").forEach(v => { v.hidden = v.id !== `view-${name}`; });
    document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("active", a.dataset.view === name));
    $("view-title").textContent = TITLES[name];
    $("sidebar").classList.remove("open");
    if (name !== "pulse") stopPulseTimer();
    const loaders = { dashboard: loadDashboard, history: loadHistory, reports: loadReportsRecent, config: loadConfig,
                      diagnostics: loadDiagnostics, pulse: () => { if (!$("pulse-out").childNodes.length) runPulse(); },
                      quality: () => { if (!$("quality-out").childNodes.length) runQuality(); } };
    if (loaders[name]) loaders[name]();
    const focusId = { dashboard: "dash-input", trace: "trace-input" }[name];
    if (focusId) setTimeout(() => $(focusId).focus(), 30);
  }
  window.addEventListener("hashchange", route);

  /* ---------------------------------------------------------- estado general */
  async function refreshStatus() {
    try {
      STATUS = await api("/api/status");
      $("version").textContent = `v${STATUS.version}`;
      $("site-name").textContent = STATUS.site;
      $("demo-banner").hidden = !STATUS.is_demo;
      const mc = $("mode-chip");
      mc.textContent = STATUS.is_demo ? "DEMO" : "CONEXIÓN REAL";
      mc.className = "chip plain " + (STATUS.is_demo ? "demo" : "ok");
      $("policy-banner").hidden = !STATUS.policy_block;
      $("policy-banner").textContent = STATUS.policy_block ? `Conexión real bloqueada: ${STATUS.policy_block}` : "";
      const entities = STATUS.health.filter(h => h.entity !== "$metadata");
      const cc = $("conn-chip");
      if (!entities.length) { cc.className = "chip nv"; cc.textContent = "OData: sin consultas"; }
      else {
        const bad = entities.filter(h => !["OK", "EMPTY"].includes(h.last_status));
        cc.className = "chip " + (bad.length ? (bad.length === entities.length ? "err" : "warn") : "ok");
        cc.textContent = bad.length ? `OData: ${bad.length} fuente(s) con error` : "OData: correcto";
      }
      $("pulse-auto-wrap").hidden = !STATUS.pulse_auto_refresh;
    } catch (e) {
      const cc = $("conn-chip"); cc.className = "chip err"; cc.textContent = "Servidor local no disponible";
    }
  }

  function healthTable(health) {
    if (!health.length) return stateBox("", "Aún no se han realizado consultas en este modo.");
    return dataTable([
      { key: "entity", label: "Fuente" },
      { key: "last_status", label: "Estado", fmt: v => UI.STATUS_TEXT[v] || v },
      { key: "last_http", label: "HTTP" },
      { key: "last_elapsed_ms", label: "Tiempo", fmt: v => fmtMs(v) },
      { key: "last_success_at", label: "Último OK", fmt: fmtTime },
      { key: "last_error", label: "Último error" },
    ], health);
  }

  async function withBusy(key, button, fn) {
    if (busy.has(key)) return;
    busy.add(key); if (button) button.disabled = true;
    try { return await fn(); } finally { busy.delete(key); if (button) button.disabled = false; refreshStatus(); }
  }

  /* ---------------------------------------------------------- dashboard */
  async function loadDashboard() {
    await refreshStatus();
    if (STATUS) mount($("dash-health"), healthTable(STATUS.health));
    try {
      const h = await api("/api/history");
      const recent = h.searches.filter(s => s.module === "trace").slice(0, 8);
      mount($("dash-recent"), recent.length ? dataTable([
        { key: "ts", label: "Fecha (UTC)", fmt: fmtTime }, { key: "term", label: "Identifier", mono: true },
        { key: "summary", label: "Resultado" }], recent, { onRow: r => goTrace(r.term) })
        : stateBox("", "Sin consultas todavía."));
    } catch (e) { mount($("dash-recent"), stateBox("error", e.message)); }
  }
  $("dash-form").addEventListener("submit", e => { e.preventDefault(); const v = $("dash-input").value.trim(); if (v) goTrace(v); });

  /* ---------------------------------------------------------- trazabilidad */
  function goTrace(identifier) { $("trace-input").value = identifier; location.hash = "#trace"; runTrace(identifier); }
  $("trace-form").addEventListener("submit", e => { e.preventDefault(); runTrace($("trace-input").value.trim()); });

  async function runTrace(identifier) {
    if (!identifier) { mount($("trace-out"), stateBox("error", "Escanea o escribe un número de serie.")); return; }
    const btn = $("trace-form").querySelector("button");
    await withBusy("trace", btn, async () => {
      mount($("trace-out"), stateBox("loading", `Consultando SMT, Quality y QualityHistory para ${identifier}…`));
      try { renderTrace(await api("/api/trace", { identifier })); }
      catch (e) { mount($("trace-out"), stateBox("error", e.message)); }
      finally { $("trace-input").select(); $("trace-input").focus(); }
    });
  }

  function sourcesBlock(sources) {
    return el("div", { class: "sources" }, Object.values(sources).map(s => el("div", { class: "source" },
      el("div", { class: "name" }, el("span", { text: s.entity }), statusChip(s)),
      el("div", { class: "meta", text: `${s.rows} registro(s) · ${fmtMs(s.elapsed_ms)}${s.http_status ? " · HTTP " + s.http_status : ""}${s.attempts > 1 ? " · " + s.attempts + " intentos" : ""}` }),
      s.stale ? el("div", { class: "meta", text: `Mostrando última lectura válida (${fmtTime(s.cached_at)}); puede estar desactualizada.` }) : null,
      s.error ? el("div", { class: "meta", text: s.error }) : null,
      s.truncated ? el("div", { class: "meta", text: "Resultado truncado: puede haber más registros." }) : null)));
  }

  function renderTrace(t) {
    const out = [];
    const h = t.header;
    if (t.state === "ERROR") {
      out.push(el("div", { class: "card" }, el("h2", { text: `Unidad ${t.identifier}` }),
        stateBox("error", "No se pudo consultar FactoryLogix. El estado de la unidad es desconocido (no equivale a 'sin registros')."),
        sourcesBlock(t.sources)));
      mount($("trace-out"), out); return;
    }
    if (t.state === "NOT_FOUND") {
      out.push(el("div", { class: "card" }, el("h2", { text: `Unidad ${t.identifier}` }),
        stateBox("", "Las fuentes respondieron sin registros para este Identifier. Verifique el número escaneado. Ausencia de registros no equivale a PASS."),
        sourcesBlock(t.sources)));
      mount($("trace-out"), out); return;
    }
    out.push(el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h2", { text: `Unidad ${t.identifier}` }),
        el("div", { class: "row-actions" }, ["xlsx", "csv", "html"].map(f =>
          el("button", { class: "btn" + (f === "xlsx" ? " primary" : ""), text: { xlsx: "Exportar Excel", csv: "CSV", html: "HTML imprimible" }[f],
            onclick: ev => exportReport(t.identifier, f, ev.currentTarget) })))),
      t.is_demo ? el("div", { class: "disclaimer", text: "Datos de demostración. El caso W07632100028 es un fixture histórico confirmado, no producción actual." }) : null,
      el("div", { class: "unit-head" }, kv("Cliente", h.customer), kv("Assembly", h.assembly), kv("Revisión", h.assembly_revision),
        kv("Batch", h.batch), kv("Lot", h.lot), kv("Work Order", h.work_order),
        kv("Línea registrada en defectos", h.lines_registered_in_defects)),
      el("p", { class: "hint", text: h.line_note }),
      el("div", { class: "verdict" }, el("strong", { text: "Resultado final: NO VERIFICABLE" }),
        el("span", { text: "No existe evidencia de aprobación final en SMT, Quality ni QualityHistory." })),
      t.defects.length ? el("div", { class: "disclaimer", text: t.disclaimer }) : null,
      sourcesBlock(t.sources)));

    const s = t.summary;
    out.push(el("div", { class: "tiles" },
      tile("Eventos de proceso", s.smt_events, "Registros en entidad SMT"),
      tile("Operaciones distintas", s.operations.length),
      tile("Operaciones repetidas", s.repeated_operations.length, s.repeated_operations.join(", ") || "Ninguna"),
      tile("Defectos únicos", s.unique_defects, "Contados por DefectID"),
      tile("Entradas de historial", s.history_entries, "No son defectos adicionales"),
      tile("Alertas de reglas", t.alerts.length)));

    out.push(el("div", { class: "card" }, el("h2", { text: "Evidencia" }), el("div", { class: "evidence" },
      evCol("c", "Evidencia confirmada", t.evidence.confirmed),
      evCol("i", "Inferencias / hipótesis", t.evidence.inferred),
      evCol("u", "No verificable / pendiente", t.evidence.unverifiable))));

    out.push(el("div", { class: "grid-2" },
      el("div", { class: "card" }, el("h2", { text: "Línea de tiempo" }), timeline(t.timeline)),
      el("div", { class: "card" }, el("h2", { text: "Alertas de reproceso" }),
        t.alerts.length ? alertList(t.alerts, a => toast(`${a.rule}: ${a.definition}`)) : stateBox("", "Sin alertas."),
        el("p", { class: "hint" }, "Detalle completo en ", el("a", { href: "#rework", text: "Rework Detector" }), "."))));

    out.push(el("div", { class: "card" }, el("h2", { text: "Defectos (únicos por DefectID)" }),
      t.defects.length ? t.defects.map(defectBlock) : stateBox("", "Quality no registra defectos para esta unidad (no equivale a PASS).")));

    out.push(el("div", { class: "card" }, el("h2", { text: "Eventos SMT" }), dataTable([
      { key: "EventDate", label: "Fecha", fmt: fmtTime, mono: true }, { key: "OperationName", label: "Operación" },
      { key: "Batch", label: "Batch" }, { key: "Assembly", label: "Assembly" }, { key: "WorkOrder", label: "Work Order" }],
      t.smt_events, { sortKey: "EventDate" })));
    mount($("trace-out"), out);
  }

  function evCol(cls, title, items) {
    return el("div", { class: `col ${cls}` }, el("strong", { text: title }),
      items.length ? el("ul", null, items.map(i => el("li", { text: i }))) : el("p", { class: "muted", text: "—" }));
  }

  function timeline(items) {
    if (!items.length) return stateBox("", "Sin eventos.");
    return el("ul", { class: "timeline" }, items.map(it => el("li", { class: `k-${it.kind}` + (/REPAIR/i.test(it.title) ? " repair" : "") },
      el("div", { class: "t", text: fmtTime(it.time) + (it.time_verified ? "" : " · hora no verificable") }),
      el("div", { class: "title", text: it.title }),
      el("div", { class: "src", text: `${it.source} · ${it.ref}` }),
      Object.keys(it.details).length ? el("div", { class: "det", text: Object.entries(it.details).map(([k, v]) => `${k}: ${v}`).join(" · ") }) : null)));
  }

  function defectBlock(d) {
    return el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h2", { text: `${d.description || "Defecto"} — ${d.comment || ""}` }),
        el("span", { class: `chip ${CLASS_CHIP[d.classification] || "nv"}`, text: CLASS_TEXT[d.classification] || d.classification })),
      el("div", { class: "unit-head" }, kv("DefectID", d.defect_id), kv("Estado actual", d.status), kv("Referencia", d.reference),
        kv("Operación origen", d.source_operation), kv("Estación inspección", d.inspection_workstation),
        kv("Línea registrada", d.line_registered), kv("Creado", fmtTime(d.date_created)),
        kv("Cierre histórico", d.closed_at ? fmtTime(d.closed_at) : null), kv("Operación de cierre", d.closed_operation),
        kv("Estación de cierre", d.closed_workstation), kv("Operador de cierre", d.closed_operator),
        kv("Minutos a cierre", d.time_to_close_min)),
      d.notes.length ? el("ul", { class: "notes" }, d.notes.map(n => el("li", { text: n }))) : null,
      el("h3", { text: `Historial (${d.history_entries} entradas, un solo defecto)` }),
      dataTable([{ key: "DefectHistoryTime", label: "Hora", fmt: fmtTime, mono: true },
        { key: "DefectHistoryStatus", label: "Estado histórico" }, { key: "DefectHistoryOperation", label: "Operación" },
        { key: "DefectHistoryWorkstation", label: "Estación" }, { key: "DefectHistoryOperator", label: "Operador" },
        { key: "DefectHistoryComment", label: "Comentario" }], d.history || [], { empty: "Sin historial disponible." }));
  }

  function alertList(alerts, onSelect) {
    return el("div", null, alerts.map(a => {
      const item = el("div", { class: `alert-item cat-${a.category}`, tabindex: "0" },
        el("div", { class: "h" }, el("span", { text: `${a.rule} · ${a.title}` }), el("span", { class: "chip plain nv", text: `confianza ${a.confidence}` })),
        el("div", { class: "x", text: a.explanation }));
      const pick = () => { item.parentNode.querySelectorAll(".selected").forEach(n => n.classList.remove("selected")); item.classList.add("selected"); onSelect(a); };
      item.addEventListener("click", pick);
      item.addEventListener("keydown", e => { if (e.key === "Enter") pick(); });
      return item;
    }));
  }

  async function exportReport(identifier, format, button) {
    await withBusy("report", button, async () => {
      try { const r = await api("/api/report", { identifier, format }, { blob: true }); download(r.blob, r.filename); toast(`Reporte generado: ${r.filename}`); }
      catch (e) { toast(`Error: ${e.message}`); }
    });
  }

  /* ---------------------------------------------------------- formularios con ventana */
  function bindWindowToggle(form) {
    const sel = form.querySelector('select[name="window"]');
    const sync = () => form.querySelectorAll(".custom-only").forEach(l => { l.hidden = sel.value !== "custom"; });
    sel.addEventListener("change", sync); sync();
  }
  function formParams(form) {
    const p = {};
    new FormData(form).forEach((v, k) => { if (typeof v === "string" && v.trim()) p[k] = v.trim(); });
    if (p.window === "custom") { p.from = toIsoFromLocal(p.from); p.to = toIsoFromLocal(p.to); }
    return p;
  }

  /* ---------------------------------------------------------- pulse */
  bindWindowToggle($("pulse-form"));
  $("pulse-form").addEventListener("submit", e => { e.preventDefault(); runPulse(); });
  $("pulse-auto").addEventListener("change", e => { if (e.target.checked) startPulseTimer(); else stopPulseTimer(); });
  function startPulseTimer() { stopPulseTimer(); pulseTimer = setInterval(runPulse, Math.max(300, STATUS?.pulse_interval || 300) * 1000); }
  function stopPulseTimer() { if (pulseTimer) clearInterval(pulseTimer); pulseTimer = null; }

  async function runPulse() {
    const btn = $("pulse-form").querySelector('button[type="submit"]');
    await withBusy("pulse", btn, async () => {
      mount($("pulse-out"), stateBox("loading", "Consultando eventos SMT de la ventana seleccionada…"));
      try { renderPulse(await api("/api/pulse", formParams($("pulse-form")))); }
      catch (e) { mount($("pulse-out"), stateBox("error", e.message)); }
    });
  }

  function renderPulse(p) {
    const k = p.kpis, s = p.source;
    const failed = !s.ok && !s.stale;
    const head = el("div", { class: "card" }, el("div", { class: "card-head" },
      el("h2", { text: `Ventana: ${p.window.label} · ${fmtTime(p.window.start)} → ${fmtTime(p.window.end)}` }),
      el("div", { class: "row-actions" }, statusChip(s), el("span", { class: "chip plain", text: `OData ${fmtMs(s.elapsed_ms)}` }))),
      s.stale ? el("div", { class: "disclaimer", text: `FactoryLogix no respondió (${s.error}). Se muestra la última lectura válida en caché (${fmtTime(s.cached_at)}); puede estar desactualizada.` }) : null,
      failed ? stateBox("error", `No se pudo consultar SMT: ${s.error || s.status}. Sin datos en caché para esta ventana.`) : null,
      el("ul", { class: "notes" }, p.notes.concat([p.line_filter.reason]).map(n => el("li", { text: n }))));
    if (failed) { mount($("pulse-out"), head); return; }
    mount($("pulse-out"), head,
      el("div", { class: "tiles" }, tile("Eventos registrados", k.events), tile("Identificadores únicos", k.unique_identifiers, "Unidades observadas, no aprobadas"),
        tile("Ensambles", k.assemblies), tile("Batches", k.batches), tile("Operaciones", k.operations),
        tile("Último evento", fmtTime(k.last_event), null, true), tile("Identificadores repetidos", k.repeated_identifiers, "Misma operación >1 vez"),
        tile("Eventos de reparación", k.repair_events), tile("Respuesta OData", fmtMs(k.response_ms), null, true),
        tile("Caché", s.stale ? "Desactualizada" : "Actualizada", s.fetched_at ? fmtTime(s.fetched_at) : null, true)),
      el("div", { class: "grid-2" },
        el("div", { class: "card" }, el("h2", { text: "Eventos por cliente" }), bars(p.by_customer)),
        el("div", { class: "card" }, el("h2", { text: "Eventos por operación" }), bars(p.by_operation)),
        el("div", { class: "card" }, el("h2", { text: "Eventos por ensamble" }), bars(p.by_assembly)),
        el("div", { class: "card" }, el("h2", { text: "Eventos por batch" }), bars(p.by_batch))),
      el("div", { class: "card" }, el("h2", { text: "Eventos" }), dataTable([
        { key: "EventDate", label: "Fecha", fmt: fmtTime, mono: true }, { key: "Identifier", label: "Identifier", mono: true },
        { key: "OperationName", label: "Operación" }, { key: "Customer", label: "Cliente" }, { key: "Assembly", label: "Assembly" },
        { key: "Batch", label: "Batch" }], p.events, { onRow: r => r.Identifier && goTrace(r.Identifier), limit: 500 })),
      el("p", { class: "hint", text: "Clic en un evento para ver la trazabilidad de la unidad." }));
  }

  /* ---------------------------------------------------------- quality */
  bindWindowToggle($("quality-form"));
  $("quality-form").addEventListener("submit", e => { e.preventDefault(); runQuality(); });
  async function runQuality() {
    const btn = $("quality-form").querySelector('button[type="submit"]');
    await withBusy("quality", btn, async () => {
      mount($("quality-out"), stateBox("loading", "Consultando defectos en Quality…"));
      try { renderQuality(await api("/api/quality", formParams($("quality-form")))); }
      catch (e) { mount($("quality-out"), stateBox("error", e.message)); }
    });
  }

  function renderQuality(q) {
    const s = q.summary, src = q.source;
    const failed = !src.ok && !src.stale;
    const ttcBox = el("div");
    const head = el("div", { class: "card" }, el("div", { class: "card-head" },
      el("h2", { text: `Ventana: ${q.window.label} · ${fmtTime(q.window.start)} → ${fmtTime(q.window.end)}` }),
      el("div", { class: "row-actions" }, statusChip(src), el("span", { class: "chip plain", text: `OData ${fmtMs(src.elapsed_ms)}` }))),
      src.stale ? el("div", { class: "disclaimer", text: `Quality no respondió. Última lectura válida: ${fmtTime(src.cached_at)}.` }) : null,
      failed ? stateBox("error", `No se pudo consultar Quality: ${src.error || src.status}. Estado de defectos desconocido.`) : null,
      el("ul", { class: "notes" }, q.notes.map(n => el("li", { text: n }))));
    if (failed) { mount($("quality-out"), head); return; }
    const ttcBtn = el("button", { class: "btn", text: "Calcular tiempos de cierre (QualityHistory)" });
    ttcBtn.addEventListener("click", () => withBusy("ttc", ttcBtn, async () => {
      mount(ttcBox, stateBox("loading", "Consultando QualityHistory…"));
      try {
        const r = await api("/api/quality/close-times", { defect_ids: q.defects.map(d => d.defect_id).filter(Boolean).slice(0, 50) });
        mount(ttcBox, el("div", { class: "row-actions" }, r.source ? statusChip(r.source) : null,
          el("span", { class: "hint", text: `Limitado a ${r.limited_to} defectos por solicitud para proteger FactoryLogix.` })),
          dataTable([{ key: "defect_id", label: "DefectID", mono: true }, { key: "classification", label: "Clasificación", fmt: v => CLASS_TEXT[v] || v },
            { key: "date_created", label: "Creado", fmt: fmtTime }, { key: "closed_at", label: "Cierre", fmt: fmtTime },
            { key: "time_to_close_min", label: "Minutos a cierre" }, { key: "history_entries", label: "Entradas historial" },
            { key: "notes", label: "Notas", fmt: v => (v || []).join("; ") }], r.defects));
      } catch (e) { mount(ttcBox, stateBox("error", e.message)); }
    }));
    mount($("quality-out"), head,
      el("div", { class: "tiles" }, tile("Defectos únicos", s.unique_defects, "Por DefectID"), tile("Activos (Open)", s.active),
        tile("Cerrados", s.closed, "No implica PASS"), tile("Estado no reconocido", s.unknown_status),
        tile("Tiempo medio a cierre", s.avg_time_to_close_min === null ? "No calculado" : `${s.avg_time_to_close_min} min`, "Requiere QualityHistory", true)),
      el("div", { class: "grid-3" },
        el("div", { class: "card" }, el("h2", { text: "Por ensamble" }), bars(s.by_assembly)),
        el("div", { class: "card" }, el("h2", { text: "Por batch" }), bars(s.by_batch)),
        el("div", { class: "card" }, el("h2", { text: "Por operación origen" }), bars(s.by_operation)),
        el("div", { class: "card" }, el("h2", { text: "Por línea registrada" }), bars(s.by_line)),
        el("div", { class: "card" }, el("h2", { text: "Por referencia de componente" }), bars(s.by_reference)),
        el("div", { class: "card" }, el("h2", { text: "Por tipo de defecto" }), bars(s.by_description))),
      el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", { text: "Tiempo entre creación y cierre" }), ttcBtn), ttcBox),
      el("div", { class: "card" }, el("h2", { text: "Defectos" }), dataTable([
        { key: "date_created", label: "Creado", fmt: fmtTime, mono: true }, { key: "identifier", label: "Identifier", mono: true },
        { key: "description", label: "Defecto" }, { key: "comment", label: "Comentario" }, { key: "reference", label: "Referencia" },
        { key: "status", label: "Estado" }, { key: "assembly", label: "Assembly" }, { key: "batch", label: "Batch" },
        { key: "source_operation", label: "Operación" }, { key: "line_registered", label: "Línea registrada" }],
        q.defects, { onRow: r => r.identifier && goTrace(r.identifier) })));
  }

  /* ---------------------------------------------------------- rework */
  $("rework-form").addEventListener("submit", async e => {
    e.preventDefault();
    const p = formParams(e.target);
    if (!p.value) { mount($("rework-out"), stateBox("error", "Escriba un Identifier o Batch.")); return; }
    const btn = e.target.querySelector("button");
    await withBusy("rework", btn, async () => {
      mount($("rework-out"), stateBox("loading", "Evaluando reglas…"));
      try { renderRework(await api("/api/rework", p.by === "batch" ? { batch: p.value } : { identifier: p.value })); }
      catch (err) { mount($("rework-out"), stateBox("error", err.message)); }
    });
  });

  function renderRework(r) {
    const src = r.source || (r.sources && r.sources.SMT);
    const failed = src && !src.ok && !src.stale;
    const blocks = [el("div", { class: "card" }, el("div", { class: "card-head" },
      el("h2", { text: r.mode === "batch" ? `Batch ${r.batch}: ${r.units_observed} unidades observadas, ${r.units.length} con alertas` : `Unidad ${r.identifier}` }),
      src ? statusChip(src) : null),
      failed ? stateBox("error", `No se pudo consultar SMT: ${src.error || src.status}. No es posible evaluar reglas.`) : null,
      r.notes ? el("ul", { class: "notes" }, r.notes.map(n => el("li", { text: n }))) : null)];
    if (!failed) {
      if (!r.units.length || r.units.every(u => !u.alerts.length)) blocks.push(stateBox("", "Sin alertas para el criterio consultado."));
      for (const u of r.units) {
        if (!u.alerts.length) continue;
        blocks.push(el("div", { class: "card" }, el("h2", { text: `${u.identifier} · ${u.events} eventos` }), alertList(u.alerts, showAlertDetail)));
      }
    }
    blocks.push(el("div", { class: "card" }, el("h2", { text: "Reglas configuradas" }), dataTable([
      { key: "rule", label: "Regla" }, { key: "title", label: "Categoría" }, { key: "definition", label: "Definición" }], r.rules)));
    mount($("rework-out"), blocks);
  }

  function showAlertDetail(a) {
    mount($("rework-detail"), el("h2", { text: "¿Por qué se generó la alerta?" }),
      el("div", { class: "unit-head" }, kv("Regla", a.rule), kv("Categoría", a.title), kv("Confianza", a.confidence)),
      el("h3", { text: "Definición de la regla" }), el("p", { text: a.definition }),
      el("h3", { text: "Explicación" }), el("p", { text: a.explanation }),
      el("h3", { text: "Evidencia" }), a.evidence.length ? el("ul", { class: "notes" }, a.evidence.map(x => el("li", { text: x }))) : el("p", { class: "muted", text: "—" }),
      el("h3", { text: "No se puede concluir" }), el("ul", { class: "notes" }, a.cannot_conclude.map(x => el("li", { text: x }))));
  }

  /* ---------------------------------------------------------- historial */
  async function loadHistory() {
    try {
      const h = await api("/api/history");
      mount($("history-searches"), dataTable([
        { key: "ts", label: "Fecha (UTC)", fmt: fmtTime, mono: true }, { key: "module", label: "Módulo" },
        { key: "term", label: "Consulta", mono: true }, { key: "summary", label: "Resultado" }, { key: "data_source", label: "Fuente" }],
        h.searches, { onRow: r => r.module === "trace" && goTrace(r.term), empty: "Sin consultas registradas." }));
      mount($("history-queries"), auditTable(h.queries));
    } catch (e) { mount($("history-searches"), stateBox("error", e.message)); }
  }
  function auditTable(rows) {
    return dataTable([
      { key: "ts", label: "Fecha (UTC)", fmt: fmtTime, mono: true }, { key: "data_source", label: "Fuente" }, { key: "entity", label: "Entidad" },
      { key: "status", label: "Estado" }, { key: "http_status", label: "HTTP" }, { key: "elapsed_ms", label: "Total", fmt: fmtMs },
      { key: "wait_headers_ms", label: "Red+servidor", fmt: fmtMs }, { key: "download_ms", label: "Descarga", fmt: fmtMs },
      { key: "parse_ms", label: "Parseo", fmt: fmtMs }, { key: "attempts", label: "Intentos" }, { key: "rows", label: "Filas" },
      { key: "error", label: "Error" }, { key: "query", label: "Consulta lógica" }], rows, { empty: "Sin solicitudes registradas." });
  }
  $("history-clear").addEventListener("click", async () => {
    if (!confirm("¿Borrar el historial local de búsquedas? La auditoría OData se conserva.")) return;
    try { await api("/api/history/clear", {}); loadHistory(); toast("Historial borrado"); } catch (e) { toast(e.message); }
  });

  /* ---------------------------------------------------------- reportes */
  $("report-form").addEventListener("submit", e => {
    e.preventDefault();
    const id = e.target.identifier.value.trim();
    if (!id) { toast("Escriba un Identifier"); return; }
    exportReport(id, (e.submitter && e.submitter.dataset.format) || "xlsx", e.submitter);
  });
  async function loadReportsRecent() {
    try {
      const h = await api("/api/history");
      const seen = new Set(); const recent = [];
      h.searches.filter(s => s.module === "trace").forEach(s => { if (!seen.has(s.term)) { seen.add(s.term); recent.push(s); } });
      mount($("report-recent"), dataTable([{ key: "term", label: "Identifier", mono: true }, { key: "ts", label: "Consultado (UTC)", fmt: fmtTime },
        { key: "summary", label: "Resumen" }], recent.slice(0, 30), {
        onRow: r => { $("report-form").identifier.value = r.term; }, empty: "Consulte una unidad primero." }));
    } catch (e) { mount($("report-recent"), stateBox("error", e.message)); }
  }

  /* ---------------------------------------------------------- configuración */
  const CONFIG_FIELDS = [
    ["mode", "Modo", "select", ["demo", "live"], "live solo funciona si TI aprobó la conexión en config.json"],
    ["odata.base_url", "URL base OData", "text", null, "Ej.: http://10.62.54.10:6065/odata/"],
    ["odata.auth_method", "Autenticación", "select", ["none", "basic"], "Basic sobre HTTP requiere aprobación de TI"],
    ["odata.credential_source", "Fuente de credenciales", "select", ["env", "windows_credential_manager"], "Nunca se guardan contraseñas aquí"],
    ["odata.timeout_seconds", "Timeout (s)", "number", null, "1–60; inicial 10"],
    ["odata.max_retries", "Reintentos (429/5xx)", "number", null, "0–2; nunca ante 401/403"],
    ["odata.backoff_seconds", "Backoff (s)", "number", null, "0.5–30"],
    ["odata.max_concurrent_requests", "Solicitudes simultáneas", "number", null, "1–2; recomendado 1"],
    ["pulse.auto_refresh_enabled", "Auto-actualizar Pulse", "checkbox", null, "Activar solo con autorización de TI"],
    ["pulse.refresh_interval_seconds", "Intervalo Pulse (s)", "number", null, "Mínimo 300"],
    ["pulse.max_events", "Máx. eventos Pulse", "number", null, "10–1000"],
    ["quality.default_window_hours", "Ventana Quality (h)", "number", null, "1–168"],
    ["rework.repair_keywords", "Palabras clave de reparación", "text", null, "Separadas por coma"],
  ];
  function getPath(o, p) { return p.split(".").reduce((a, k) => (a == null ? a : a[k]), o); }
  async function loadConfig() {
    try {
      const c = await api("/api/config");
      const flat = { ...c, "rework.repair_keywords": c.rework.repair_keywords };
      mount($("config-form"), CONFIG_FIELDS.map(([key, label, type, options, help]) => {
        const val = key === "rework.repair_keywords" ? flat[key].join(", ") : getPath(c, key);
        let input;
        if (type === "select") input = el("select", { name: key }, options.map(o => el("option", { value: o, text: o, selected: o === val })));
        else if (type === "checkbox") input = el("input", { type: "checkbox", name: key, checked: !!val });
        else input = el("input", { type, name: key, value: val ?? "", step: type === "number" ? "any" : null });
        return el("label", null, label, input, el("span", { class: "help", text: help }));
      }));
      mount($("config-security"), el("div", { class: "unit-head" },
        kv("Modo real aprobado por TI", c.security.live_mode_approved ? "Sí" : "No"),
        kv("Basic sobre HTTP aprobado", c.security.allow_basic_auth_over_http ? "Sí" : "No"),
        kv("Credencial configurada", c.credential_configured === null ? "No aplica (sin autenticación)" : (c.credential_configured ? "Sí" : "No")),
        kv("Flujos de proceso autorizados", c.rework.process_flows_configured.length ? c.rework.process_flows_configured : "Ninguno (bucles no confirmables)"),
        kv("Versión", c.version)));
    } catch (e) { mount($("config-msg"), el("div", { class: "msg-err", text: e.message })); }
  }
  $("config-save").addEventListener("click", async () => {
    const form = $("config-form"), values = {};
    CONFIG_FIELDS.forEach(([key, , type]) => {
      const inp = form.elements[key]; if (!inp) return;
      if (type === "checkbox") values[key] = inp.checked;
      else if (type === "number") values[key] = Number(inp.value);
      else if (key === "rework.repair_keywords") values[key] = inp.value.split(",").map(s => s.trim()).filter(Boolean);
      else values[key] = inp.value;
    });
    try { await api("/api/config", { values }); mount($("config-msg"), el("div", { class: "msg-ok", text: "Configuración guardada." })); loadConfig(); refreshStatus(); }
    catch (e) { mount($("config-msg"), el("div", { class: "msg-err", text: e.message })); }
  });
  $("config-reset").addEventListener("click", async () => {
    if (!confirm("¿Restablecer los ajustes a los valores de config.json?")) return;
    try { await api("/api/config/reset", {}); mount($("config-msg"), el("div", { class: "msg-ok", text: "Ajustes restablecidos." })); loadConfig(); refreshStatus(); }
    catch (e) { mount($("config-msg"), el("div", { class: "msg-err", text: e.message })); }
  });

  /* ---------------------------------------------------------- diagnóstico */
  async function loadDiagnostics() {
    try {
      const d = await api("/api/diagnostics");
      mount($("diag-info"),
        d.policy_block ? el("div", { class: "disclaimer", text: `Conexión real bloqueada: ${d.policy_block}` }) : null,
        el("div", { class: "unit-head" }, kv("Modo", d.mode === "demo" ? "Demostración" : "Conexión real"), kv("URL base", d.base_url),
          kv("Servidor", d.host), kv("Puerto", d.port), kv("Esquema", d.scheme), kv("Autenticación", d.auth_method),
          kv("Credencial", d.credential_configured === null ? "No aplica" : (d.credential_configured ? "Configurada" : "No configurada")),
          kv("Timeout", `${d.timeout_seconds} s`), kv("Reintentos", d.max_retries), kv("Concurrencia", d.max_concurrent_requests),
          kv("Caché SMT / Quality / Historial", `${d.cache_counts.CachedSMTEvents} / ${d.cache_counts.CachedQualityDefects} / ${d.cache_counts.CachedQualityHistory}`),
          kv("Runtime", d.python)),
        el("h3", { text: "Salud por entidad" }), healthTable(d.health));
      mount($("diag-queries"), auditTable(d.recent_queries));
    } catch (e) { mount($("diag-info"), stateBox("error", e.message)); }
  }
  document.querySelectorAll("[data-test]").forEach(b => b.addEventListener("click", () => withBusy("diag", b, async () => {
    const entity = b.dataset.test;
    mount($("diag-test"), stateBox("loading", `Probando ${entity}…`));
    try {
      const r = await api("/api/diagnostics/test", { entity });
      const res = r.result;
      const parts = [el("div", { class: "row-actions" }, el("strong", { text: entity }), statusChip(res),
        el("span", { class: "chip plain", text: `Tiempo ${fmtMs(res.elapsed_ms)}` }), res.http_status ? el("span", { class: "chip plain", text: `HTTP ${res.http_status}` }) : null,
        el("span", { class: "chip plain", text: `Intentos ${res.attempts}` })),
        el("p", { class: "hint", text: `Red+servidor ${fmtMs(res.timings.wait_headers_ms)} · descarga ${fmtMs(res.timings.download_ms)} · parseo ${fmtMs(res.timings.parse_ms)}` })];
      if (res.error) parts.push(el("p", { class: "msg-err", text: res.error }));
      if (r.note) parts.push(el("p", { class: "hint", text: r.note }));
      if (r.comparison) {
        parts.push(el("p", { text: `OData v${r.odata_version} · EntitySets publicados: ${r.entity_sets.length}` }));
        const rows = Object.entries(r.comparison).map(([k, v]) => ({ entity: k, present: v.present ? "Sí" : "No",
          missing: v.missing.join(", ") || "—", extra: v.extra.join(", ") || "—",
          mismatches: v.type_mismatches.map(m => `${m.property}: ${m.expected}→${m.actual}`).join(", ") || "—" }));
        parts.push(dataTable([{ key: "entity", label: "Entidad" }, { key: "present", label: "Publicada" },
          { key: "missing", label: "Propiedades esperadas ausentes" }, { key: "extra", label: "Propiedades adicionales" },
          { key: "mismatches", label: "Diferencias de tipo" }], rows));
      }
      mount($("diag-test"), parts);
      loadDiagnostics();
    } catch (e) { mount($("diag-test"), stateBox("error", e.message)); }
  })));
  $("diag-copy").addEventListener("click", async () => {
    try {
      const { text } = await api("/api/diagnostics/text");
      try { await navigator.clipboard.writeText(text); toast("Diagnóstico copiado al portapapeles"); }
      catch (e) { mount($("diag-test"), el("pre", { class: "diag", text })); toast("Copie el texto mostrado manualmente"); }
    } catch (e) { toast(e.message); }
  });
  $("diag-logs").addEventListener("click", async () => {
    try { const r = await api("/api/logs/open", {}); toast(r.opened ? "Carpeta de logs abierta" : `Logs en: ${r.path}`); }
    catch (e) { toast(e.message); }
  });

  /* ---------------------------------------------------------- inicio */
  refreshStatus().then(route);
  setInterval(refreshStatus, 60000);   // solo lee estado local; no consulta FactoryLogix
})();
