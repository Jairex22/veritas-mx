/* Reports list page and print-ready report view (browser "Save as PDF"). */
(function () {
  "use strict";
  const { h, clear, $, api, fmtNumber, fmtDateTime, fmtDate, alertBox } = Pulse;
  const SOURCE = { odata: "Consulta directa", cache: "Caché vigente", stored: "Información guardada" };

  // ------------------------------------------------------------------ list
  async function loadList() {
    const res = await api("/api/reports");
    const body = clear($("#reports-table").tBodies[0]);
    const items = res.ok ? res.items : [];
    $("#reports-empty").textContent = items.length ? "" : "Aún no hay reportes. Genera uno desde la pantalla de Producción.";
    items.forEach((r) => {
      const id = encodeURIComponent(r.report_id);
      body.appendChild(h("tr", null, [
        h("td", { text: fmtDateTime(r.generated_at) }),
        h("td", { text: fmtDate(r.period_start) + " – " + fmtDate(r.period_end) }),
        h("td", { text: Pulse.filtersText(r.filters) }),
        h("td", { text: fmtDateTime(r.data_fetched_at) }),
        h("td", null, [document.createTextNode((SOURCE[r.data_source] || r.data_source) + " "), r.data_mode === "demo" ? Pulse.badge("partial", "DEMO") : null]),
        h("td", null, [
          h("a", { class: "btn btn-sm", href: "/reports/print?id=" + id, target: "_blank", rel: "noopener", text: "PDF" }), " ",
          h("a", { class: "btn btn-sm", href: "/api/reports/" + id + "/xlsx", text: "Excel" }), " ",
          h("a", { class: "btn btn-sm", href: "/api/reports/" + id + "/csv", text: "CSV" }), " ",
          h("button", { type: "button", class: "btn btn-sm btn-danger", text: "Eliminar", onclick: () => remove(r.report_id) }),
        ]),
      ]));
    });
  }

  async function remove(id) {
    if (!window.confirm("¿Eliminar este reporte guardado? Esta acción no se puede deshacer.")) return;
    const res = await api("/api/reports/" + encodeURIComponent(id) + "/delete", { method: "POST" });
    clear($("#reports-msg")).appendChild(alertBox(res.ok ? "info" : "warn", res.message));
    loadList();
  }

  // ------------------------------------------------------------------ print view
  async function loadPrint() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id") || "";
    if (!/^[a-f0-9]{32}$/.test(id)) {
      clear($("#report-error")).appendChild(alertBox("error", "Identificador de reporte no válido."));
      return;
    }
    const res = await api("/api/reports/" + id);
    if (!res.ok) {
      clear($("#report-error")).appendChild(alertBox("error", res.message));
      return;
    }
    const snap = res.report.snapshot;
    document.body.dataset.mode = snap.data_mode;
    document.title = "Reporte " + snap.period.start + " a " + snap.period.end + " | SMT Production Pulse";
    $("#r-generated").textContent = "Generado: " + fmtDateTime(snap.generated_at);
    const info = clear($("#r-info"));
    const add = (k, v) => { info.appendChild(h("dt", { text: k })); info.appendChild(h("dd", { text: v })); };
    add("Aplicación", snap.app + " v" + snap.version);
    add("Modo de datos", snap.data_mode === "demo" ? "MODO DEMOSTRACIÓN — datos simulados" : "FactoryLogix (ProductivityOverTime)");
    add("Periodo solicitado", fmtDate(snap.period.start) + " – " + fmtDate(snap.period.end));
    add("Filtros", Pulse.filtersText(snap.filters));
    add("Intervalo", snap.interval_label);
    add("Extracción OData", fmtDateTime(snap.source.fetched_at));
    add("Información desde caché", snap.source.from_cache ? "Sí" : "No (consulta directa)");
    add("Calidad del resultado", Pulse.STATUS_LABELS[snap.analytics.quality] || snap.analytics.quality);
    add("Registros utilizados", String(snap.analytics.records_used) + (snap.analytics.truncated ? " (resultado parcial)" : ""));

    const cards = clear($("#r-cards"));
    snap.analytics.cards.forEach((c) => {
      const value = c.id === "updated" ? fmtDateTime(c.value) : c.display;
      cards.appendChild(h("div", { class: "card status-" + c.status }, [
        h("div", { class: "card-title" }, [c.title + " ", Pulse.badge(c.status)]),
        h("div", { class: "card-value" + (String(value).length > 12 ? " small-value" : ""), text: value }),
        h("div", { class: "card-unit", text: c.unit || "" }), h("div", { class: "card-note", text: c.note || "" }),
      ]));
    });
    if (snap.trend && snap.trend.status !== "unavailable" && snap.trend.percent !== null && snap.trend.percent !== undefined) {
      cards.appendChild(h("div", { class: "card status-" + snap.trend.status }, [
        h("div", { class: "card-title" }, ["Tendencia vs periodo anterior ", Pulse.badge(snap.trend.status)]),
        h("div", { class: "card-value", text: fmtNumber(snap.trend.percent, 1) + " %" }),
        h("div", { class: "card-note", text: snap.trend.note }),
      ]));
    }
    const unit = snap.analytics.unit;
    const drops = new Set(snap.analytics.drops.map((d) => d.label));
    window.PulseCharts.bar($("#r-chart-series"), { unit, items: snap.analytics.series.map((s) => ({ label: s.label, value: s.value, cls: s.in_progress ? "progress" : drops.has(s.label) ? "drop" : "" })) });
    window.PulseCharts.hbar($("#r-chart-lines"), { unit, items: snap.analytics.by_line.filter((g) => g.with_quantity).map((g) => ({ label: g.name, value: g.value })) });
    $("#r-drop-rule").textContent = snap.analytics.drop_rule;
    const dl = clear($("#r-drops"));
    if (!snap.analytics.drops.length) dl.appendChild(h("li", { class: "muted", text: "Sin disminuciones detectadas con la regla configurada." }));
    snap.analytics.drops.forEach((d) => dl.appendChild(h("li", { text: `${d.label}: ${fmtNumber(d.value)} (${fmtNumber(d.percent, 1)} % vs mediana ${fmtNumber(d.reference)})` })));

    const table = $("#r-table");
    clear(table.tHead).appendChild(h("tr", null, snap.columns.map((c) => h("th", { class: c.key === "quantity" ? "num" : null, text: c.label }))));
    const body = clear(table.tBodies[0]);
    snap.rows.forEach((row) => body.appendChild(h("tr", null, snap.columns.map((c) => h("td", {
      class: c.key === "quantity" ? "num" : null, text: c.key === "quantity" ? fmtNumber(row[c.key]) : (row[c.key] ?? "—") })))));
    const lim = clear($("#r-limits"));
    snap.analytics.limitations.forEach((t) => lim.appendChild(h("li", { text: t })));
    $("#report").classList.remove("hidden");
    if (params.get("print") === "1") setTimeout(() => window.print(), 400);
  }

  document.addEventListener("DOMContentLoaded", () => {
    Pulse.loadStatus();
    if (document.body.dataset.page === "print") {
      $("#btn-print").addEventListener("click", () => window.print());
      loadPrint();
    } else {
      loadList();
    }
  });
})();
