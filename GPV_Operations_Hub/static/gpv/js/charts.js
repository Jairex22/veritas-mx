/* Minimal SVG chart library for GPV Operations Hub (bar, grouped bar, line, pareto). Own code, no dependencies. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const el = (name, attrs, parent) => {
    const n = document.createElementNS(NS, name);
    for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  };
  const fmt = (v) => (v == null ? "—" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("es-MX") : (Math.round(v * 100) / 100).toLocaleString("es-MX"));

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const n = v / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }

  /**
   * opts: {type: 'bar'|'line'|'grouped'|'pareto', data: [{key, value, value2?, cumulative_pct?}],
   *        series: ['Nombre1','Nombre2'], selected: key, onClick: fn(key), height}
   */
  window.GPVChart = function (container, opts) {
    container.innerHTML = "";
    const data = opts.data || [];
    const W = Math.max(320, container.clientWidth || 600), H = opts.height || 240;
    const m = { l: 56, r: opts.type === "pareto" ? 40 : 12, t: 12, b: 48 };
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.title || "Gráfico" }, container);
    if (!data.length) {
      el("text", { x: W / 2, y: H / 2, "text-anchor": "middle", class: "empty" }, svg).textContent = "Sin datos para los filtros seleccionados";
      return;
    }
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const vals = data.map((d) => Math.max(d.value || 0, opts.type === "grouped" ? d.value2 || 0 : 0));
    const ymax = niceMax(Math.max.apply(null, vals));
    const y = (v) => m.t + ih - (ih * (v || 0)) / ymax;
    const axis = el("g", { class: "axis" }, svg);
    for (let i = 0; i <= 4; i++) {
      const v = (ymax * i) / 4, yy = y(v);
      el("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy, "stroke-dasharray": i ? "2,3" : "" }, axis);
      el("text", { x: m.l - 6, y: yy + 4, "text-anchor": "end" }, axis).textContent = fmt(v);
    }
    const slot = iw / data.length;
    const labelEvery = Math.ceil(data.length / Math.max(1, Math.floor(iw / 48)));
    data.forEach((d, i) => {
      if (i % labelEvery === 0) {
        const t = el("text", { x: m.l + slot * i + slot / 2, y: H - m.b + 14, "text-anchor": "middle" }, axis);
        t.textContent = String(d.key).length > 10 ? String(d.key).slice(0, 10) + "…" : d.key;
      }
    });
    const tip = (node, text) => { el("title", {}, node).textContent = text; };
    if (opts.type === "line") {
      const pts = data.map((d, i) => [m.l + slot * i + slot / 2, y(d.value)]);
      el("path", { d: "M" + pts.map((p) => p.join(",")).join("L"), class: "line" }, svg);
      pts.forEach((p, i) => {
        const c = el("circle", { cx: p[0], cy: p[1], r: 3.5, class: "bar", tabindex: 0 }, svg);
        tip(c, data[i].key + ": " + fmt(data[i].value));
        if (opts.onClick) c.addEventListener("click", () => opts.onClick(data[i].key));
      });
    } else {
      const groups = opts.type === "grouped" ? 2 : 1;
      const bw = (slot * 0.75) / groups;
      data.forEach((d, i) => {
        const x0 = m.l + slot * i + slot * 0.125;
        const series = groups === 2 ? [["value2", "bar2"], ["value", "bar"]] : [["value", "bar"]];
        series.forEach(([k, cls], si) => {
          const v = d[k] || 0;
          const r = el("rect", { x: x0 + bw * si, y: y(v), width: Math.max(1, bw - 2), height: Math.max(0, m.t + ih - y(v)),
            class: cls + (opts.selected === d.key ? " sel" : ""), tabindex: 0, role: "button" }, svg);
          tip(r, d.key + " · " + (opts.series ? opts.series[groups === 2 ? si : 0] : "") + ": " + fmt(v));
          if (opts.onClick) {
            r.addEventListener("click", () => opts.onClick(d.key));
            r.addEventListener("keydown", (e) => { if (e.key === "Enter") opts.onClick(d.key); });
          }
        });
      });
      if (opts.type === "pareto") {
        const y2 = (p) => m.t + ih - (ih * p) / 100;
        const pts = data.map((d, i) => [m.l + slot * i + slot / 2, y2(d.cumulative_pct || 0)]);
        el("path", { d: "M" + pts.map((p) => p.join(",")).join("L"), class: "line" }, svg);
        [0, 50, 80, 100].forEach((p) => { el("text", { x: W - m.r + 4, y: y2(p) + 4 }, axis).textContent = p + "%"; });
      }
    }
  };
})();
