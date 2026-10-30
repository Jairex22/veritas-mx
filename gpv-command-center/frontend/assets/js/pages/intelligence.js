import { get } from "../api.js";
import { areaChart, donut, hBars } from "../charts.js";
import { card, dataTable, h, icon, loading, mount, pageHead, pct, sourceTag } from "../ui.js";
import { STATUS_COLORS, STATUS_LABEL, hourLabel, kpiCard, unavailableBlock } from "./common.js";

const WINDOWS = [[8, "8 h"], [24, "24 h"], [72, "72 h"], [168, "7 días"]];
const METRIC_NAMES = { units_processed: "Unidades procesadas", units_packed: "Unidades empacadas", fpy: "First Pass Yield", rty: "Rolled Throughput Yield",
  failure_rate: "Tasa de fallas", rework_rate: "Tasa de retrabajos", wip: "WIP", station_time: "Tiempo por estación", top_defects: "Defectos principales",
  active_orders: "Órdenes activas", trend: "Tendencia de producción" };

export async function render(root, { query, navigate }) {
  const win = Number(query.window) || 24;
  const body = h("div", null, loading(4));
  const sel = h("div", { class: "row" }, WINDOWS.map(([v, l]) => h("button", { class: "btn sm" + (v === win ? " primary" : ""), onclick: () => navigate(`/intelligence?window=${v}`) }, l)));
  mount(root, pageHead("Production Intelligence", "Indicadores con definición formal de cálculo y fuente de datos. Sin conexión no se muestran valores.", [sel]), body);
  let m;
  try { m = await get("/api/metrics", { window_hours: win }); } catch (e) { mount(body, unavailableBlock(e)); return; }
  const k = m.kpis, d = m.definitions;
  mount(body, h("div", { class: "stack" },
    h("div", { class: "grid g-kpi" },
      kpiCard({ label: "Unidades procesadas", value: k.units_processed.value, definition: d.units_processed }),
      kpiCard({ label: "Empacadas", value: k.units_packed.value, definition: d.units_packed, color: "var(--ok)" }),
      kpiCard({ label: "RTY", value: k.rty.value, format: "pct", definition: d.rty, color: "var(--ok)" }),
      kpiCard({ label: "Tasa de fallas", value: k.failure_rate.value, format: "pct", definition: d.failure_rate, color: "var(--err)", sub: `${k.failure_rate.numerator}/${k.failure_rate.denominator}` }),
      kpiCard({ label: "Tasa de retrabajos", value: k.rework_rate.value, format: "pct", definition: d.rework_rate, color: "var(--warn)", sub: `${k.rework_rate.numerator}/${k.rework_rate.denominator}` }),
      kpiCard({ label: "WIP", value: k.wip.value, definition: d.wip, color: "var(--info)" })),
    card(`Unidades empacadas por hora · ${win} h`, areaChart(m.trend.map((t) => ({ x: t.hour, y: t.units })), { xLabel: hourLabel }), { iconName: "chart", foot: [d.trend] }),
    h("div", { class: "grid g-3" },
      card("First Pass Yield por estación", hBars(Object.entries(m.fpy).map(([st, v]) => ({ label: st, value: v.value, hint: `${v.first_pass}/${v.tested}` })),
        { valueFormat: (v) => pct(v), max: 1, colorFor: (it) => it.value >= 0.95 ? "var(--ok)" : it.value >= 0.9 ? "var(--warn)" : "var(--err)" }), { iconName: "checkCircle", foot: [d.fpy] }),
      card("Tiempo por estación (mediana, min)", hBars(Object.entries(m.station_time_min).map(([st, v]) => ({ label: st, value: v.median, hint: `${v.samples} muestras` })),
        { valueFormat: (v) => `${v} min` }), { iconName: "clock", foot: [d.station_time] }),
      card("Distribución de estados", donut(Object.entries(m.status_counts).map(([st, v]) => ({ label: STATUS_LABEL[st] || st, value: v, color: STATUS_COLORS[st] || "var(--text-3)" }))), { iconName: "layers" })),
    h("div", { class: "grid g-2" },
      card("Defectos principales", hBars(m.top_defects.map((x) => ({ label: x.code, value: x.count, hint: x.description })), { colorFor: () => "var(--err)" }), { iconName: "alert", foot: [d.top_defects] }),
      card("WIP por estación", hBars(Object.entries(m.wip_by_station).map(([st, v]) => ({ label: st, value: v })), { colorFor: () => "var(--info)" }), { iconName: "layers", foot: [d.wip] })),
    card("Definiciones formales de cálculo", dataTable([
      { key: "name", label: "Métrica", render: (r) => h("b", null, r.name) }, { key: "def", label: "Definición", sortable: false },
      { key: "src", label: "Fuente", sortable: false, render: () => sourceTag(m.source) }],
      Object.entries(d).map(([key, def]) => ({ name: METRIC_NAMES[key] || key, def }))), { iconName: "info" }),
    h("div", { class: "row" }, sourceTag(m.source), h("span", { class: "faint", style: { fontSize: "12px" } }, `Ventana: ${win} h · Generado ${new Date(m.generated_at).toLocaleString("es-MX")}`)),
    h("span", { class: "sr-only" }, icon("chart"))));
}
