// Gráficos SVG ligeros (sin librerías externas). Tooltips nativos mediante <title>.
import { h, s } from "./ui.js";

const fmt = (v, f) => (f ? f(v) : String(v));

export function areaChart(points, { height = 220, valueFormat, xLabel = (p) => p.x } = {}) {
  const W = 720, H = height, pad = { l: 40, r: 12, t: 12, b: 28 };
  if (!points.length) return h("div", { class: "empty" }, "Sin datos en la ventana seleccionada.");
  const max = Math.max(1, ...points.map((p) => p.y));
  const nice = Math.ceil(max / 4) * 4 || 4;
  const x = (i) => pad.l + (i * (W - pad.l - pad.r)) / Math.max(1, points.length - 1);
  const y = (v) => H - pad.b - (v / nice) * (H - pad.t - pad.b);
  const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Tendencia" });
  const grid = s("g", { class: "grid" });
  for (let i = 0; i <= 4; i++) {
    const v = (nice / 4) * i;
    grid.append(s("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }), s("text", { x: pad.l - 8, y: y(v) + 4, "text-anchor": "end" }, fmt(v, valueFormat)));
  }
  svg.append(grid);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");
  svg.append(s("path", { class: "area", d: `${d} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z` }), s("path", { class: "line", d }));
  const step = Math.ceil(points.length / 8);
  points.forEach((p, i) => {
    if (i % step === 0) svg.append(s("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, xLabel(p)));
    const g = s("g");
    g.append(s("rect", { class: "hit", x: x(i) - 8, y: pad.t, width: 16, height: H - pad.t - pad.b, fill: "transparent" }),
      s("circle", { class: "pt", cx: x(i), cy: y(p.y), r: 4 }));
    g.firstChild.append(s("title", null, `${xLabel(p)} · ${fmt(p.y, valueFormat)}`));
    svg.append(g);
  });
  return svg;
}

export function hBars(items, { valueFormat, max, colorFor } = {}) {
  if (!items.length) return h("div", { class: "empty" }, "Sin datos.");
  const top = max ?? Math.max(1, ...items.map((i) => i.value));
  return h("div", { class: "hbars", role: "list" }, items.map((it) => {
    const label = `${it.label}: ${fmt(it.value, valueFormat)}${it.hint ? " · " + it.hint : ""}`;
    return h("div", { class: "hbar-row", role: "listitem", title: label },
      h("span", { class: "hbar-label" }, it.label),
      h("span", { class: "hbar-track" }, h("i", { class: "hbar-fill", style: { width: `${Math.max(1.5, (it.value / top) * 100)}%`, background: colorFor ? colorFor(it) : null } })),
      h("span", { class: "hbar-val" }, fmt(it.value, valueFormat)));
  }));
}

export function donut(items, { size = 180, center } = {}) {
  const total = items.reduce((a, b) => a + b.value, 0);
  const r = 70, c = 2 * Math.PI * r;
  const svg = s("svg", { class: "chart", viewBox: "0 0 200 200", style: `max-width:${size}px`, role: "img" });
  svg.append(s("circle", { cx: 100, cy: 100, r, fill: "none", stroke: "var(--surface-3)", "stroke-width": 22 }));
  let off = 0;
  for (const it of items) {
    if (!it.value) continue;
    const len = (it.value / total) * c;
    svg.append(s("circle", { cx: 100, cy: 100, r, fill: "none", stroke: it.color, "stroke-width": 22, "stroke-dasharray": `${len} ${c - len}`,
      "stroke-dashoffset": -off, transform: "rotate(-90 100 100)" }, s("title", null, `${it.label}: ${it.value}`)));
    off += len;
  }
  svg.append(s("text", { x: 100, y: 98, "text-anchor": "middle", style: "font-size:28px;font-weight:700;fill:var(--text)" }, center ?? String(total)),
    s("text", { x: 100, y: 120, "text-anchor": "middle" }, "unidades"));
  const legend = h("div", { class: "legend" }, items.map((i) => h("span", null, h("i", { style: { background: i.color } }), `${i.label} · ${i.value}`)));
  return h("div", { class: "row", style: { gap: "20px", alignItems: "center" } }, svg, legend);
}
