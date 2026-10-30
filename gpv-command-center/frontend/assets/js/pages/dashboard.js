import { get } from "../api.js";
import { areaChart, donut, hBars } from "../charts.js";
import { card, dataTable, errorAlert, h, icon, loading, mount, pageHead, pct, sourceTag, statusChip } from "../ui.js";
import { SEV_COLORS, STATUS_COLORS, STATUS_LABEL, hourLabel, kpiCard, unavailableBlock } from "./common.js";

export async function render(root, { navigate }) {
  const refresh = h("button", { class: "btn", onclick: () => load() }, icon("refresh", "sm"), "Actualizar");
  const body = h("div", null, loading(4));
  mount(root, pageHead("Dashboard operativo", "Estado de producción en las últimas 24 horas.", [refresh]), body);

  async function load() {
    refresh.classList.add("loading");
    const [m, d] = await Promise.allSettled([get("/api/metrics", { window_hours: 24 }), get("/api/diagnostics")]);
    refresh.classList.remove("loading");
    if (m.status === "rejected") { mount(body, unavailableBlock(m.reason)); return; }
    const metrics = m.value;
    const k = metrics.kpis, def = metrics.definitions;

    const kpis = h("div", { class: "grid g-kpi" },
      kpiCard({ label: "Unidades procesadas", value: k.units_processed.value, definition: def.units_processed, sub: `${k.units_packed.value} empacadas`, color: "var(--accent)" }),
      kpiCard({ label: "Rolled Throughput Yield", value: k.rty.value, format: "pct", definition: def.rty, sub: "Producto de FPY por estación", color: "var(--ok)" }),
      kpiCard({ label: "Tasa de fallas", value: k.failure_rate.value, format: "pct", definition: def.failure_rate, sub: `${k.failure_rate.numerator} de ${k.failure_rate.denominator} pruebas`, color: "var(--err)" }),
      kpiCard({ label: "Tasa de retrabajo", value: k.rework_rate.value, format: "pct", definition: def.rework_rate, sub: `${k.rework_rate.numerator} seriales reparados`, color: "var(--warn)" }),
      kpiCard({ label: "WIP", value: k.wip.value, definition: def.wip, sub: "En proceso, reparación o HOLD", color: "var(--info)" }),
      kpiCard({ label: "Órdenes activas", value: k.active_orders.value, definition: def.active_orders, color: "var(--demo)" }));

    const trend = card("Tendencia de producción · unidades empacadas por hora", areaChart(metrics.trend.map((t) => ({ x: t.hour, y: t.units })), { xLabel: hourLabel }),
      { iconName: "chart", foot: [def.trend] });

    const statusItems = Object.entries(metrics.status_counts).map(([s, v]) => ({ label: STATUS_LABEL[s] || s, value: v, color: STATUS_COLORS[s] || "var(--text-3)" }));
    const statusCard = card("Estado de unidades", donut(statusItems), { iconName: "layers" });

    const fpy = card("First Pass Yield por estación", hBars(Object.entries(metrics.fpy).map(([st, v]) => ({ label: st, value: v.value, hint: `${v.first_pass}/${v.tested}` })),
      { valueFormat: (v) => pct(v), max: 1, colorFor: (it) => it.value >= 0.95 ? "var(--ok)" : it.value >= 0.9 ? "var(--warn)" : "var(--err)" }),
      { iconName: "checkCircle", foot: [def.fpy] });

    const wip = card("WIP por estación", hBars(Object.entries(metrics.wip_by_station).map(([st, v]) => ({ label: st, value: v })),
      { colorFor: (it) => it.label === "DEBUG" ? "var(--err)" : "var(--info)" }), { iconName: "layers" });

    let diagCard;
    if (d.status === "fulfilled") {
      const sum = d.value.summary;
      diagCard = card("Diagnóstico de rework", h("div", { class: "stack", style: { gap: "12px" } },
        h("div", { class: "row" }, ["CRITICAL", "HIGH", "MEDIUM"].map((sv) => h("div", { class: "card kpi", style: { flex: 1, minWidth: "90px", "--kpi-color": SEV_COLORS[sv], boxShadow: "none" } },
          h("div", { class: "label" }, statusChip(sv)), h("div", { class: "value" }, sum[sv])))),
        h("div", null, d.value.findings.slice(0, 5).map((f) => h("div", { class: `finding ${f.severity}`, onclick: () => navigate(`/rework?focus=${encodeURIComponent(f.id)}`) },
          h("span", { class: "stripe" }), h("div", null, h("h4", null, f.title), h("div", { class: "row faint", style: { fontSize: "12px" } }, f.serials.slice(0, 3).join(", "), f.serials.length > 3 ? ` +${f.serials.length - 3}` : "")),
          statusChip(f.severity))))),
        { iconName: "rework", actions: [h("a", { href: "#/rework", class: "btn sm" }, "Ver todos")] });
    } else diagCard = card("Diagnóstico de rework", errorAlert(d.reason));

    const defects = card("Defectos principales", dataTable([
      { key: "code", label: "Código", render: (r) => h("span", { class: "mono" }, r.code) },
      { key: "description", label: "Descripción" },
      { key: "count", label: "Cantidad", num: true },
    ], metrics.top_defects, { initialSort: { key: "count", dir: -1 } }), { iconName: "alert", foot: [def.top_defects] });

    const orders = card("Órdenes de trabajo", dataTable([
      { key: "number", label: "Orden", render: (r) => h("a", { href: `#/trace?q=${encodeURIComponent(r.number)}&field=work_order`, class: "mono" }, r.number) },
      { key: "assembly", label: "Ensamble", render: (r) => [r.assembly, h("span", { class: "faint" }, ` rev ${r.revision}`)] },
      { key: "line", label: "Línea" },
      { key: "quantity", label: "Cantidad", num: true },
      { key: "status", label: "Estado", render: (r) => statusChip(r.status === "ACTIVE" ? "IN_PROCESS" : r.status === "CLOSED" ? "COMPLETE" : r.status) },
    ], metrics.work_orders), { iconName: "file" });

    mount(body, h("div", { class: "stack" }, kpis,
      h("div", { class: "grid g-3" }, h("div", { class: "span-2" }, trend), statusCard),
      h("div", { class: "grid g-3" }, fpy, wip, diagCard),
      h("div", { class: "grid g-2" }, defects, orders),
      h("div", { class: "row" }, sourceTag(metrics.source), h("span", { class: "faint", style: { fontSize: "12px" } }, `Generado ${new Date(metrics.generated_at).toLocaleString("es-MX")}`))));
  }
  await load();
}
