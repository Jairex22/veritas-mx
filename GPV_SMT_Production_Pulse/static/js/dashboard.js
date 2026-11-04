/* Trends page: compares two stored queries. Never contacts FactoryLogix. */
(function () {
  "use strict";
  const { h, clear, $, api, fmtNumber, fmtDateTime, fmtDate, alertBox } = Pulse;
  const Charts = window.PulseCharts;
  let items = [];
  let localMode = false;

  function optionLabel(item) {
    return `${fmtDate(item.start)} – ${fmtDate(item.end)} · ${Pulse.filtersText(item.filters)} · extraído ${fmtDateTime(item.fetched_at)}`;
  }

  async function loadList() {
    const res = await api("/api/stored-list");
    items = res.ok ? res.items : [];
    const a = clear($("#cmp-a"));
    const b = clear($("#cmp-b"));
    items.forEach((item) => {
      a.appendChild(h("option", { value: item.cache_id, text: optionLabel(item) }));
      b.appendChild(h("option", { value: item.cache_id, text: optionLabel(item) }));
    });
    if (items.length > 1) b.selectedIndex = 1;
    $("#btn-compare").disabled = items.length < 2;
    $("#cmp-msg").textContent = items.length < 2
      ? "Se necesitan al menos dos consultas guardadas. Realiza consultas en la pantalla de Producción."
      : "";
    $("#stored-count").textContent = items.length + " consulta(s) guardada(s) dentro de la política de retención";
    const body = clear($("#stored-table").tBodies[0]);
    items.forEach((item) => {
      body.appendChild(h("tr", null, [
        h("td", { text: fmtDate(item.start) + " – " + fmtDate(item.end) }),
        h("td", { text: Pulse.filtersText(item.filters) }),
        h("td", { text: fmtDateTime(item.fetched_at) + " (hace " + item.age + ")" }),
        h("td", { class: "num", text: item.records }),
        h("td", null, [item.is_fresh ? Pulse.badge("verified", "Vigente") : Pulse.badge("unavailable", "Guardada"),
          item.partial ? Pulse.badge("partial", "Parcial") : null]),
      ]));
    });
  }

  function tile(label, value, sub) {
    return h("div", { class: "tile" }, [h("div", { class: "tile-label", text: label }), h("div", { class: "tile-value", text: value }), h("div", { class: "tile-sub", text: sub || "" })]);
  }

  async function setupLocal(status) {
    localMode = true;
    $("#local-form").classList.remove("hidden");
    $("#stored-form").classList.add("hidden");
    $("#stored-panel").classList.add("hidden");
    const today = new Date(status.today + "T00:00:00");
    const iso = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
    $("#la-start").value = $("#la-end").value = iso(today);
    $("#lb-start").value = $("#lb-end").value = iso(yesterday);
    (status.known_values.line || []).forEach((v) => $("#dl-lline").appendChild(h("option", { value: v })));
    $("#btn-compare").disabled = false;
    $("#btn-reload").classList.add("hidden");
    $("#cmp-msg").textContent = "Compara dos periodos con la información guardada por el recolector automático (no consulta FactoryLogix).";
  }

  async function compare() {
    let res;
    $("#btn-compare").disabled = true;
    if (localMode) {
      const body = { a: { start: $("#la-start").value, end: $("#la-end").value }, b: { start: $("#lb-start").value, end: $("#lb-end").value },
        interval: $("#cmp-interval").value };
      if ($("#l-line").value.trim()) body.line = $("#l-line").value.trim();
      res = await api("/api/compare-local", { method: "POST", body });
    } else {
      const aId = $("#cmp-a").value, bId = $("#cmp-b").value;
      if (!aId || !bId || aId === bId) {
        $("#btn-compare").disabled = false;
        $("#cmp-msg").textContent = "Selecciona dos consultas distintas.";
        return;
      }
      res = await api("/api/compare", { method: "POST", body: { a: Number(aId), b: Number(bId), interval: $("#cmp-interval").value } });
    }
    $("#btn-compare").disabled = false;
    if (!res.ok) {
      $("#cmp-results").classList.add("hidden");
      clear($("#cmp-msg")).appendChild(alertBox("error", res.message));
      return;
    }
    $("#cmp-msg").textContent = "";
    const A = res.a.analytics, B = res.b.analytics, C = res.comparison;
    const unit = A.unit || B.unit || "";
    const tiles = clear($("#cmp-tiles"));
    tiles.appendChild(tile("Periodo A", fmtNumber(A.total), `${fmtDate(res.a.query.period.start)} – ${fmtDate(res.a.query.period.end)} · ${unit}`));
    tiles.appendChild(tile("Periodo B (referencia)", fmtNumber(B.total), `${fmtDate(res.b.query.period.start)} – ${fmtDate(res.b.query.period.end)} · ${unit}`));
    tiles.appendChild(tile("Variación A vs B", C.percent_a_vs_b === null ? "—" : fmtNumber(C.percent_a_vs_b, 1) + " %",
      C.status === "verified" ? "Ambos periodos completos" : "Al menos un periodo es parcial"));
    tiles.appendChild(tile("Calidad", Pulse.STATUS_LABELS[C.status], localMode ? "Datos locales del recolector" : "Extraídos: " + fmtDateTime(res.a.fetched_at) + " / " + fmtDateTime(res.b.fetched_at)));

    $("#a-unit").textContent = unit;
    $("#b-unit").textContent = unit;
    Charts.bar($("#chart-a"), { unit, items: A.series.map((s) => ({ label: s.label, value: s.value, cls: s.in_progress ? "progress" : "" })) });
    Charts.bar($("#chart-b"), { unit, items: B.series.map((s) => ({ label: s.label, value: s.value, cls: s.in_progress ? "progress alt" : "alt" })) });
    $("#cmp-unit").textContent = unit;
    Charts.grouped($("#chart-cmp-lines"), {
      unit, labels: C.by_line.map((r) => r.name),
      series: [{ name: "Periodo A", values: C.by_line.map((r) => r.a ?? null) }, { name: "Periodo B", values: C.by_line.map((r) => r.b ?? null), cls: "alt" }],
    });
    const body = clear($("#cmp-table").tBodies[0]);
    C.by_line.forEach((r) => {
      const pct = r.a !== null && r.a !== undefined && r.b ? fmtNumber(((r.a - r.b) / r.b) * 100, 1) + " %" : "—";
      body.appendChild(h("tr", null, [h("td", { text: r.name }), h("td", { class: "num", text: fmtNumber(r.a) }),
        h("td", { class: "num", text: fmtNumber(r.b) }), h("td", { class: "num", text: pct })]));
    });
    const lim = clear($("#cmp-limits"));
    [...new Set([...A.limitations, ...B.limitations])].forEach((t) => lim.appendChild(h("li", { text: t })));
    [...new Set([...(res.a.warnings || []), ...(res.b.warnings || [])])].forEach((t) => lim.appendChild(h("li", { text: t })));
    lim.appendChild(h("li", { text: "Comparación basada exclusivamente en información guardada localmente; no se consultó FactoryLogix." }));
    $("#cmp-results").classList.remove("hidden");
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const status = await Pulse.loadStatus();
    if (status && status.collector_mode) setupLocal(status);
    else loadList();
    $("#btn-compare").addEventListener("click", compare);
    $("#btn-reload").addEventListener("click", loadList);
  });
})();
