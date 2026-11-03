/* Lightweight native SVG charts. No libraries, no animations.
 * Every chart shows its real unit and an explicit empty state.
 */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const EMPTY = "No hay información verificable para este periodo.";

  function s(tag, attrs, text) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
    if (text !== undefined) el.textContent = String(text);
    return el;
  }

  function empty(container, message) {
    Pulse.clear(container).appendChild(Pulse.h("div", { class: "empty", text: message || EMPTY }));
  }

  function niceMax(value) {
    if (!value || value <= 0) return 1;
    const exp = Math.pow(10, Math.floor(Math.log10(value)));
    const f = value / exp;
    const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return nice * exp;
  }

  function shortNum(v) {
    if (Math.abs(v) >= 1e6) return (v / 1e6).toLocaleString("es-MX", { maximumFractionDigits: 1 }) + " M";
    if (Math.abs(v) >= 1e4) return (v / 1e3).toLocaleString("es-MX", { maximumFractionDigits: 1 }) + " k";
    return v.toLocaleString("es-MX", { maximumFractionDigits: 1 });
  }

  function frame(width, height, maxValue, unit, m) {
    const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", preserveAspectRatio: "xMidYMid meet" });
    const plotH = height - m.top - m.bottom;
    const axis = s("g", { class: "chart-axis" });
    for (let i = 0; i <= 4; i++) {
      const value = (maxValue / 4) * i;
      const y = m.top + plotH - (plotH * i) / 4;
      axis.appendChild(s("line", { x1: m.left, x2: width - m.right, y1: y, y2: y, class: "chart-grid" }));
      axis.appendChild(s("text", { x: m.left - 6, y: y + 4, "text-anchor": "end" }, shortNum(value)));
    }
    svg.appendChild(axis);
    svg.appendChild(s("text", { x: 4, y: 12, class: "chart-unit" }, unit || ""));
    return { svg, plotH };
  }

  /** Vertical bars. items: [{label, value|null, cls, title}] */
  function bar(container, opts) {
    const items = (opts.items || []).filter((i) => i.value !== null && i.value !== undefined);
    if (!items.length) return empty(container, opts.emptyText);
    const width = 680, height = 280;
    const m = { top: 22, right: 10, bottom: 58, left: 56 };
    const max = niceMax(Math.max(...items.map((i) => i.value)));
    const { svg, plotH } = frame(width, height, max, opts.unit, m);
    const plotW = width - m.left - m.right;
    const slot = plotW / items.length;
    const bw = Math.max(2, Math.min(48, slot * 0.72));
    const every = Math.ceil(items.length / 16);
    items.forEach((item, idx) => {
      const x = m.left + idx * slot + (slot - bw) / 2;
      const bh = (item.value / max) * plotH;
      const rect = s("rect", { x, y: m.top + plotH - bh, width: bw, height: Math.max(0, bh), class: "chart-bar " + (item.cls || "") });
      rect.appendChild(s("title", {}, `${item.label}: ${Pulse.fmtNumber(item.value)} ${opts.unit || ""}${item.title ? " · " + item.title : ""}`));
      svg.appendChild(rect);
      if (items.length <= 12) svg.appendChild(s("text", { x: x + bw / 2, y: m.top + plotH - bh - 4, "text-anchor": "middle", class: "chart-value" }, shortNum(item.value)));
      if (idx % every === 0) {
        const lx = x + bw / 2, ly = m.top + plotH + 12;
        svg.appendChild(s("text", { x: lx, y: ly, "text-anchor": "end", class: "chart-label", transform: `rotate(-35 ${lx} ${ly})` }, item.label));
      }
    });
    Pulse.clear(container).appendChild(svg);
  }

  /** Line chart. points: [{label, value}] */
  function line(container, opts) {
    const pts = (opts.points || []).filter((p) => p.value !== null && p.value !== undefined);
    if (!pts.length) return empty(container, opts.emptyText);
    const width = 680, height = 280;
    const m = { top: 22, right: 14, bottom: 58, left: 56 };
    const max = niceMax(Math.max(...pts.map((p) => p.value)));
    const { svg, plotH } = frame(width, height, max, opts.unit, m);
    const plotW = width - m.left - m.right;
    const step = pts.length > 1 ? plotW / (pts.length - 1) : 0;
    const coords = pts.map((p, i) => [m.left + (pts.length > 1 ? i * step : plotW / 2), m.top + plotH - (p.value / max) * plotH]);
    svg.appendChild(s("polyline", { points: coords.map((c) => c.join(",")).join(" "), class: "chart-line" }));
    const every = Math.ceil(pts.length / 12);
    pts.forEach((p, i) => {
      const [x, y] = coords[i];
      const dot = s("circle", { cx: x, cy: y, r: pts.length > 60 ? 1.5 : 3, class: "chart-dot" });
      dot.appendChild(s("title", {}, `${p.label}: ${Pulse.fmtNumber(p.value)} ${opts.unit || ""}`));
      svg.appendChild(dot);
      if (i % every === 0 || (i === pts.length - 1 && i % every >= every / 2)) {
        const ly = m.top + plotH + 12;
        svg.appendChild(s("text", { x, y: ly, "text-anchor": "end", class: "chart-label", transform: `rotate(-35 ${x} ${ly})` }, p.label));
      }
    });
    Pulse.clear(container).appendChild(svg);
  }

  /** Horizontal bars. items: [{label, value, cls}] */
  function hbar(container, opts) {
    const items = (opts.items || []).filter((i) => i.value !== null && i.value !== undefined);
    if (!items.length) return empty(container, opts.emptyText);
    const rowH = 30, width = 680;
    const m = { top: 24, right: 70, bottom: 8, left: 150 };
    const height = m.top + m.bottom + items.length * rowH;
    const max = niceMax(Math.max(...items.map((i) => i.value)));
    const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
    svg.appendChild(s("text", { x: 4, y: 14, class: "chart-unit" }, opts.unit || ""));
    const plotW = width - m.left - m.right;
    items.forEach((item, idx) => {
      const y = m.top + idx * rowH;
      const w = (item.value / max) * plotW;
      const label = item.label.length > 22 ? item.label.slice(0, 21) + "…" : item.label;
      svg.appendChild(s("text", { x: m.left - 8, y: y + rowH / 2 + 4, "text-anchor": "end", class: "chart-label" }, label));
      const rect = s("rect", { x: m.left, y: y + 5, width: Math.max(1, w), height: rowH - 10, class: "chart-bar " + (item.cls || "") });
      rect.appendChild(s("title", {}, `${item.label}: ${Pulse.fmtNumber(item.value)} ${opts.unit || ""}`));
      svg.appendChild(rect);
      svg.appendChild(s("text", { x: m.left + w + 6, y: y + rowH / 2 + 4, class: "chart-value" }, Pulse.fmtNumber(item.value)));
    });
    Pulse.clear(container).appendChild(svg);
  }

  /** Grouped bars: labels[], series [{name, values[], cls}] */
  function grouped(container, opts) {
    const labels = opts.labels || [];
    const all = (opts.series || []).flatMap((sr) => sr.values).filter((v) => v !== null && v !== undefined);
    if (!labels.length || !all.length) return empty(container, opts.emptyText);
    const width = 680, height = 280;
    const m = { top: 22, right: 10, bottom: 58, left: 56 };
    const max = niceMax(Math.max(...all));
    const { svg, plotH } = frame(width, height, max, opts.unit, m);
    const plotW = width - m.left - m.right;
    const slot = plotW / labels.length;
    const n = opts.series.length;
    const bw = Math.max(3, Math.min(36, (slot * 0.78) / n));
    labels.forEach((label, idx) => {
      const groupX = m.left + idx * slot + (slot - bw * n) / 2;
      opts.series.forEach((sr, si) => {
        const v = sr.values[idx];
        if (v === null || v === undefined) return;
        const bh = (v / max) * plotH;
        const rect = s("rect", { x: groupX + si * bw, y: m.top + plotH - bh, width: bw - 1, height: bh, class: "chart-bar " + (sr.cls || "") });
        rect.appendChild(s("title", {}, `${label} · ${sr.name}: ${Pulse.fmtNumber(v)} ${opts.unit || ""}`));
        svg.appendChild(rect);
      });
      const lx = m.left + idx * slot + slot / 2, ly = m.top + plotH + 12;
      svg.appendChild(s("text", { x: lx, y: ly, "text-anchor": "end", class: "chart-label", transform: `rotate(-35 ${lx} ${ly})` }, label));
    });
    Pulse.clear(container).appendChild(svg);
  }

  window.PulseCharts = { bar, line, hbar, grouped, empty, EMPTY };
})();
