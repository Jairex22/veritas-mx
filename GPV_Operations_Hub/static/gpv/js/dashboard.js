/* Main dashboard: KPIs + charts with cross filtering, drill-down and export of the current selection. */
(function () {
  "use strict";
  const root = document.querySelector("[data-dashboard]");
  if (!root) return;
  const base = new URLSearchParams(location.search);
  const cross = {}; // cross filters set by clicking charts
  const chips = root.querySelector("[data-chips]");
  const stamp = root.querySelector("[data-stamp]");

  function params() {
    const p = new URLSearchParams(base.toString());
    Object.keys(cross).forEach((k) => p.set(k, cross[k]));
    if (!p.get("period")) p.set("period", "month");
    return p;
  }

  function metricHTML(label, m) {
    if (!m) return "";
    let v, sub = "";
    if (m.status === "ok") {
      v = (Math.round(m.value * 100) / 100).toLocaleString("es-MX") + "<small>" + GPV.esc(m.unit || "") + "</small>";
      if (m.denominator != null) sub = GPV.esc(m.numerator) + " / " + GPV.esc(m.denominator);
      if (m.reason) sub += " " + GPV.esc(m.reason);
    } else {
      v = '<span class="kpi-text">' + (m.status === "insufficient" ? "Datos insuficientes" : "No calculable") + "</span>";
      sub = GPV.esc(m.reason);
    }
    return '<div class="kpi' + (m.status !== "ok" ? " kpi-na" : "") + '" title="' + GPV.esc(m.definition || "") + '"><div class="kpi-label">' + GPV.esc(label) +
      '</div><div class="kpi-value">' + v + '</div><div class="kpi-sub">' + sub + "</div></div>";
  }
  const plain = (label, v, sub) => '<div class="kpi"><div class="kpi-label">' + GPV.esc(label) + '</div><div class="kpi-value">' +
    (v == null ? "—" : (Math.round(v * 100) / 100).toLocaleString("es-MX")) + '</div><div class="kpi-sub">' + GPV.esc(sub || "") + "</div></div>";

  function setCross(key, value) {
    if (cross[key] === value) delete cross[key];
    else cross[key] = value;
    load();
  }

  function renderChips() {
    chips.innerHTML = Object.keys(cross).map((k) => '<span class="chip">' + GPV.esc(k) + ": " + GPV.esc(cross[k]) +
      ' <button type="button" aria-label="Quitar filtro" data-rm="' + GPV.esc(k) + '">×</button></span>').join(" ");
    chips.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { delete cross[b.dataset.rm]; load(); }));
    const q = params().toString();
    root.querySelectorAll("[data-link]").forEach((a) => { a.href = a.dataset.link + (a.dataset.link.includes("?") ? "&" : "?") + q; });
  }

  async function load() {
    renderChips();
    root.querySelectorAll("[data-chart]").forEach((c) => { c.innerHTML = '<p class="muted">Cargando…</p>'; });
    try {
      const r = await GPV.api(root.dataset.api + "?" + params().toString());
      const d = r.data, k = d.kpis;
      root.querySelector("[data-kpis]").innerHTML =
        metricHTML("Cumplimiento agrupado", k.compliance) + plain("Meta", k.planned_total) + plain("Buenas", k.good_total) +
        plain("Pendiente", k.pending_total, "Σ máx(meta − buenas, 0)") + plain("Atrasadas", k.late_count, "de " + k.orders + " órdenes") +
        metricHTML("Scrap", k.scrap_rate) + metricHTML("Rechazo", k.reject_rate) + metricHTML("FPY", k.fpy) + metricHTML("OEE", k.oee);
      root.querySelector("[data-warnings]").innerHTML = (k.warnings || []).map((w) => '<div class="alert alert-warn">' + GPV.esc(w) + "</div>").join("");
      stamp.textContent = "Consulta " + d.server_time + " · última importación " + (d.last_import || "—") + " · versión " + k.data_version + " · " + k.filters_text;
      const C = (name) => root.querySelector('[data-chart="' + name + '"]');
      GPVChart(C("by_line"), { type: "grouped", series: ["Meta", "Buenas"], selected: cross.line,
        data: d.by_line.map((x) => ({ key: x.key, value: x.good, value2: x.planned })), onClick: (key) => setCross("line", key) });
      GPVChart(C("by_day"), { type: "line", data: d.by_day, onClick: (key) => { cross.period = "range"; cross.date_from = key; cross.date_to = key; load(); } });
      GPVChart(C("by_shift"), { type: "bar", data: d.by_shift, selected: cross.shift, onClick: (key) => setCross("shift", key) });
      GPVChart(C("by_hour"), { type: "bar", data: d.by_hour.map((x) => ({ key: x.key + ":00", value: x.value })) });
      GPVChart(C("pareto"), { type: "pareto", data: d.pareto });
      GPVChart(C("kaizen"), { type: "bar", data: d.kaizen });
      const late = root.querySelector("[data-late]");
      late.innerHTML = d.late.length ? d.late.map((o) => '<tr><td><a href="/produccion/ordenes/' + o.id + '/">' + GPV.esc(o.number) + "</a></td><td>" +
        GPV.esc(o.line) + '</td><td class="num">' + o.pending.toLocaleString("es-MX") + "</td><td>" + GPV.esc(o.due) + "</td></tr>").join("") :
        '<tr><td colspan="4" class="muted">Sin órdenes atrasadas.</td></tr>';
    } catch (e) {
      GPV.toast(e.message, "error");
      root.querySelector("[data-warnings]").innerHTML = '<div class="alert alert-err">' + GPV.esc(e.message) + "</div>";
    }
  }
  root.querySelector("[data-refresh]").addEventListener("click", load);
  load();
  window.addEventListener("resize", () => { clearTimeout(window.__gpvR); window.__gpvR = setTimeout(load, 400); });
})();
