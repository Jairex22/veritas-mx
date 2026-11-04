/* Diagnostics page: connection status, metadata, field mapping and capability probes. */
(function () {
  "use strict";
  const { h, clear, $, api, fmtDateTime, alertBox } = Pulse;
  const ROLES = ["timestamp", "quantity", "line", "station", "shift", "project", "work_order", "product"];
  const MAP_SOURCE = { confirmed: "Confirmado en esta pantalla", config: "Definido en config.json", demo: "Mapeo DEMO",
    auto: "Auto-detectado por nombre (pendiente de confirmar por MES)", none: "Sin mapeo" };
  const PROBE_STATUS = { ok: "Comprobado", failed: "Falló", not_tested: "No probado" };
  const BREAKER = { closed: "Normal (cerrado)", open: "Abierto: consultas en pausa", half_open: "Semiabierto: se permite 1 prueba" };
  let diag = null;

  function tile(label, value, sub, kind) {
    return h("div", { class: "tile" }, [
      h("div", { class: "tile-label", text: label }),
      h("div", { class: "tile-value" }, [kind ? Pulse.badge(kind, value) : value]),
      h("div", { class: "tile-sub", text: sub || "" }),
    ]);
  }

  function render(d) {
    diag = d;
    const summary = $("#diag-summary");
    summary.className = "alert " + (d.ready ? "alert-info" : "alert-warn");
    clear(summary).appendChild(h("strong", { text: d.summary }));
    if (!d.ready && d.readiness_reasons.length) summary.appendChild(h("ul", null, d.readiness_reasons.map((r) => h("li", { text: r }))));
    if (d.data_mode === "demo") summary.appendChild(h("div", { class: "small", text: "Modo DEMO: el servidor es un simulador local; ningún resultado de esta pantalla corresponde a FactoryLogix real." }));

    const last = d.client.last || {};
    const meta = d.metadata || {};
    const tiles = clear($("#diag-tiles"));
    const metaOk = meta.status === "ok" || meta.status === "loaded";
    tiles.appendChild(tile("FactoryLogix", d.server, "Acceso (" + d.auth_mode + "): " + d.auth));
    const col = d.collector;
    tiles.appendChild(tile("Recolector automático", col ? (col.running ? "En ejecución" : "Detenido") : "No iniciado",
      col ? `${col.message || ""} Última lectura correcta: ${col.last_success_at ? fmtDateTime(col.last_success_at) : "ninguna"}` : "Inicia con: py app.py --live",
      col && col.running && col.status !== "blocked" && col.status !== "backoff" ? "ok" : "failed"));
    tiles.appendChild(tile("Mapeo de campos", MAP_SOURCE[d.mapping_source] || d.mapping_source, `Registros guardados: ${d.records.records} · lecturas: ${d.records.revisions}`,
      d.mapping_source === "auto" ? "partial" : d.mapping_source === "none" ? "failed" : "ok"));
    tiles.appendChild(tile("Metadata", metaOk ? "Validada" : "No validada", meta.message + (meta.checked_at ? " · " + fmtDateTime(meta.checked_at) : ""), metaOk ? "ok" : "not_tested"));
    tiles.appendChild(tile("ProductivityOverTime", d.entity.compatible ? "Identificado" : "No identificado",
      d.entity.compatible ? `${d.entity.entity_type} · OData ${d.entity.odata_version}` : "Requiere metadata válida", d.entity.compatible ? "ok" : "failed"));
    const okProbes = d.probes.filter((p) => p.status === "ok").length;
    tiles.appendChild(tile("Filtros comprobados", `${okProbes} de ${d.probes.length}`, d.probes_executed_at ? "Pruebas: " + fmtDateTime(d.probes_executed_at) : "Sin pruebas vigentes"));
    tiles.appendChild(tile("Última respuesta HTTP", last.http_status ? String(last.http_status) : "—", last.message || "Sin solicitudes en esta ejecución"));
    tiles.appendChild(tile("Tiempo de consulta", last.elapsed_ms !== undefined ? Math.round(last.elapsed_ms) + " ms" : "—", last.resource ? "Recurso: " + last.resource : ""));
    tiles.appendChild(tile("Última actualización", last.at ? fmtDateTime(last.at) : "—", "Registros consultados: " + (last.records !== undefined ? last.records : "—")));
    tiles.appendChild(tile("Caché local", d.cache.cache_entries + " consultas", `${d.cache.cache_fresh_entries} vigentes · ${(d.cache.size_bytes / 1048576).toFixed(2)} MB · ${d.cache.file}`));
    const br = d.client.breaker;
    tiles.appendChild(tile("Circuit breaker", BREAKER[br.state] || br.state,
      `Fallas consecutivas: ${br.consecutive_failures}/${br.threshold}` + (br.state === "open" ? ` · reanuda en ${br.seconds_remaining} s` : ""),
      br.state === "closed" ? "ok" : "failed"));
    tiles.appendChild(tile("Uso última hora", `${d.usage.global_last_hour} / ${d.limits.MAX_ODATA_REQUESTS_PER_HOUR_GLOBAL}`, `Esta sesión: ${d.usage.session_last_hour} / ${d.limits.MAX_ODATA_REQUESTS_PER_SESSION_PER_HOUR}`));

    // properties
    const props = d.entity.properties || [];
    $("#props-empty").classList.toggle("hidden", props.length > 0);
    $("#props-meta").textContent = d.entity.compatible ? `${props.length} propiedades · hash ${d.entity.schema_hash}` : "";
    const pb = clear($("#props-table").tBodies[0]);
    props.forEach((p) => pb.appendChild(h("tr", null, [h("td", { class: "mono", text: p.name }), h("td", { text: p.edm_type }),
      h("td", { text: p.category }), h("td", { text: p.is_key ? "Sí" : "" }), h("td", { text: p.nullable ? "Sí" : "No" })])));
    const ann = clear($("#announced"));
    if (d.entity.announced) {
      const a = d.entity.announced;
      const text = a.terms.length
        ? `Capacidades ANUNCIADAS (no comprobadas): TopSupported=${a.top_supported}, Filterable=${a.filterable}, Sortable=${a.sortable}, SelectSupport=${a.select_supported}` +
          (a.non_filterable.length ? `. No filtrables: ${a.non_filterable.join(", ")}` : "")
        : "La metadata no incluye anotaciones de capacidades OData.";
      ann.appendChild(document.createTextNode(text));
    }
    if (d.entity.navigation_properties.length) ann.appendChild(h("div", { text: "Propiedades de navegación (no se consultan): " + d.entity.navigation_properties.join(", ") }));
    d.entity.warnings.forEach((w) => ann.appendChild(h("div", { text: "Advertencia: " + w })));

    renderMapping(d);
    renderProbes(d);

    const hb = clear($("#history-table").tBodies[0]);
    d.history.forEach((r) => {
      let q = r.query_text;
      try { q = decodeURIComponent(q); } catch (e) { /* raw */ }
      hb.appendChild(h("tr", null, [h("td", { text: fmtDateTime(r.created_at) }), h("td", { text: r.kind }), h("td", { text: r.result_status }),
        h("td", { text: r.cache_status }), h("td", { class: "num", text: r.http_status || "" }), h("td", { class: "num", text: r.response_ms ? Math.round(r.response_ms) : "" }),
        h("td", { class: "num", text: r.record_count ?? "" }), h("td", { class: "mono", text: q })]));
    });
  }

  function renderMapping(d) {
    const form = clear($("#mapping-form"));
    const disabled = !d.entity.compatible;
    d.roles.forEach((role) => {
      const options = d.role_options[role.role] || [];
      const select = h("select", { id: "map-" + role.role, name: role.role, disabled: disabled || null });
      select.appendChild(h("option", { value: "", text: options.length ? "(no usar)" : "NO DISPONIBLE" }));
      options.forEach((name) => {
        const prop = d.entity.properties.find((p) => p.name === name);
        select.appendChild(h("option", { value: name, text: `${name} (${prop ? prop.edm_type : ""})` }));
      });
      select.value = d.mapping[role.role] || "";
      form.appendChild(h("div", { class: "field" }, [
        h("label", { for: "map-" + role.role, text: role.label }),
        select,
        h("span", { class: "small muted" }, [Pulse.badge(role.status === "DISPONIBLE" ? "ok" : role.status === "NO DISPONIBLE" ? "failed" : "not_tested", role.status)]),
      ]));
    });
    $("#btn-mapping").disabled = disabled;
    $("#btn-suggest").disabled = disabled;
  }

  function renderProbes(d) {
    const body = clear($("#probes-table").tBodies[0]);
    d.probes.forEach((p) => {
      let q = p.query || "";
      try { q = decodeURIComponent(q); } catch (e) { /* raw */ }
      body.appendChild(h("tr", null, [h("td", { text: p.label }), h("td", null, [Pulse.badge(p.status, PROBE_STATUS[p.status])]),
        h("td", { text: p.detail }), h("td", { class: "num", text: p.http_status || "" }), h("td", { class: "mono", text: q })]));
    });
    $("#btn-probe").disabled = !d.entity.compatible;
  }

  async function withButton(button, label, fn) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    try { await fn(); } finally { button.disabled = false; button.textContent = original; }
  }

  function showMessage(target, res) {
    clear($(target)).appendChild(alertBox(res.ok ? "info" : "warn", res.message || (res.ok ? "Listo." : "No completado.")));
  }

  async function refresh() {
    const d = await api("/api/diagnostics");
    if (d && d.ok === false) { clear($("#diag-msg")).appendChild(alertBox("error", d.message)); return; }
    render(d);
    Pulse.loadStatus();
  }

  document.addEventListener("DOMContentLoaded", () => {
    refresh();
    $("#btn-refresh").addEventListener("click", refresh);
    $("#btn-check").addEventListener("click", (e) => withButton(e.target, "Verificando…", async () => {
      const res = await api("/api/diagnostics/check", { method: "POST" });
      showMessage("#diag-msg", res);
      if (res.diagnostics) render(res.diagnostics);
      Pulse.loadStatus();
    }));
    $("#btn-suggest").addEventListener("click", () => {
      if (!diag) return;
      ROLES.forEach((role) => { const el = $("#map-" + role); if (el) el.value = diag.suggested_mapping[role] || ""; });
      clear($("#mapping-msg")).appendChild(alertBox("info", "Sugerencias aplicadas en el formulario. Revísalas y presiona “Confirmar mapeo”."));
    });
    $("#btn-mapping").addEventListener("click", (e) => withButton(e.target, "Guardando…", async () => {
      const body = {};
      ROLES.forEach((role) => { const el = $("#map-" + role); body[role] = el && el.value ? el.value : null; });
      const res = await api("/api/diagnostics/mapping", { method: "POST", body });
      showMessage("#mapping-msg", res);
      if (res.diagnostics) render(res.diagnostics);
    }));
    $("#btn-probe").addEventListener("click", (e) => withButton(e.target, "Probando… (puede tardar unos segundos)", async () => {
      const res = await api("/api/diagnostics/probe", { method: "POST" });
      showMessage("#probe-msg", res);
      if (res.diagnostics) render(res.diagnostics);
      Pulse.loadStatus();
    }));
  });
})();
