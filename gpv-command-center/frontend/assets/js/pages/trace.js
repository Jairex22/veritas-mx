import { get } from "../api.js";
import { card, chip, dataTable, emptyState, errorAlert, fmtDate, fmtRel, h, icon, loading, mount, pageHead, sourceTag, statusChip } from "../ui.js";
import { unitLink } from "./common.js";

const FIELDS = [["any", "Todos los campos"], ["serial", "Serial Number"], ["work_order", "Work Order"], ["assembly", "Assembly Name"],
  ["batch", "Batch"], ["revision", "Product Revision"], ["station", "Station"], ["area", "Area"], ["line", "Line"], ["panel", "Panel"]];
const STATION_ICON = { SMT_TOP: "cpu", SMT_BOTTOM: "cpu", AOI: "search", ICT: "ops", DEPANEL: "layers", FCT: "ops", FINAL_ASSY: "wrench", FINAL_TEST: "checkCircle", PACK: "box", DEBUG: "rework" };

export async function render(root, ctx) {
  if (ctx.params[0]) return renderUnit(root, ctx, ctx.params[0]);
  return renderSearch(root, ctx);
}

function renderSearch(root, { query, navigate }) {
  const input = h("input", { class: "input", type: "search", placeholder: "Ej. DEMO-GPV-L00001, WO-DEMO-24101, PNL-DEMO-MIX-04", value: query.q || "", maxlength: 64, "aria-label": "Valor a buscar" });
  const field = h("select", { class: "input", style: { maxWidth: "220px" }, "aria-label": "Campo" }, FIELDS.map(([v, l]) => h("option", { value: v, selected: (query.field || "any") === v }, l)));
  const results = h("div", null);
  const submit = (e) => {
    e && e.preventDefault();
    const q = input.value.trim();
    if (q) navigate(`/trace?q=${encodeURIComponent(q)}&field=${field.value}`);
  };
  mount(root, pageHead("Trazabilidad", "Busque por serial, orden, ensamble, lote, revisión, estación, área, línea o panel."),
    h("form", { class: "card card-body row", onsubmit: submit, style: { marginBottom: "16px" } },
      h("div", { style: { flex: 1, minWidth: "240px" } }, input), field, h("button", { class: "btn primary", type: "submit" }, icon("search", "sm"), "Buscar")),
    results);
  input.focus();
  if (!query.q) { mount(results, card(null, emptyState("Ingrese un criterio de búsqueda", "Los resultados muestran el estado reportado y el último resultado del historial.", "trace"))); return; }
  mount(results, loading(5));
  get("/api/search", { q: query.q, field: query.field || "any", limit: 200 }).then((r) => {
    if (r.count === 1 && (query.field === "serial" || r.results[0].serial.toLowerCase() === query.q.toLowerCase())) {
      navigate(`/trace/${encodeURIComponent(r.results[0].serial)}`); return;
    }
    mount(results, card(`${r.count} resultado(s) para “${r.query}”`, dataTable([
      { key: "serial", label: "Serial", render: (u) => unitLink(u.serial) },
      { key: "work_order", label: "Orden", render: (u) => h("span", { class: "mono" }, u.work_order) },
      { key: "assembly", label: "Ensamble / Rev", render: (u) => [u.assembly, h("span", { class: "faint" }, ` · ${u.revision}`)] },
      { key: "status", label: "Estado", render: (u) => statusChip(u.status) },
      { key: "current_station", label: "Estación actual", render: (u) => u.current_station || h("span", { class: "faint" }, "—") },
      { key: "last_result", label: "Último resultado", render: (u) => statusChip(u.last_result) },
      { key: "open_defects", label: "Def. abiertos", num: true, render: (u) => u.open_defects ? chip(String(u.open_defects), "err") : "0" },
      { key: "last_activity", label: "Última actividad", render: (u) => h("span", { title: fmtDate(u.last_activity) }, fmtRel(u.last_activity)) },
    ], r.results, { onRowClick: (u) => navigate(`/trace/${encodeURIComponent(u.serial)}`), empty: "Sin coincidencias en la fuente de datos." }),
    { iconName: "search", foot: [sourceTag(r.source)] }));
  }).catch((e) => mount(results, errorAlert(e)));
}

function flowDiagram(unit) {
  const inRoute = unit.station_flow.filter((n) => n.in_route);
  const side = unit.station_flow.filter((n) => !n.in_route);
  return h("div", null,
    h("div", { class: "flow", role: "list", "aria-label": "Flujo de estaciones" }, inRoute.map((n) => h("div", { class: `flow-node ${n.state}`, role: "listitem",
      title: `${n.station}: ${n.state} · visitas ${n.visits} · fallas ${n.fails}${n.last_ts ? " · " + fmtDate(n.last_ts) : ""}` },
      n.visits > 1 ? h("span", { class: "visits" }, `×${n.visits}`) : null,
      h("div", { class: "bubble" }, icon(n.state === "FAIL" ? "xCircle" : n.state === "DONE" ? "check" : STATION_ICON[n.station] || "cpu")),
      h("div", { class: "name" }, n.station.replace("_", " ")),
      h("div", { class: "meta" }, n.fails ? `${n.fails} FAIL` : n.state === "PENDING" ? "pendiente" : n.state === "CURRENT" ? "actual" : n.last_result || "")))),
    side.length ? h("div", { class: "flow-side" }, h("span", { class: "faint" }, "Fuera de ruta:"),
      side.map((n) => h("span", { class: `side-node ${n.state}` }, icon(STATION_ICON[n.station] || "cpu", "sm"), h("b", null, n.station),
        `${n.visits} ingreso(s)`, n.state === "CURRENT" ? chip("ACTUAL", "info") : null))) : null,
    unit.route_inferred ? h("p", { class: "faint", style: { fontSize: "12px" } }, "Ruta inferida del orden de aparición en el historial (la fuente no reporta la ruta oficial).") : null);
}

function timeline(events) {
  if (!events.length) return emptyState("Sin eventos", null, "clock");
  return h("ul", { class: "timeline" }, [...events].reverse().map((e) => h("li", { class: e.result },
    h("div", { class: "t-head" }, h("b", null, e.station), chip(e.operation, "outline"), statusChip(e.result), h("span", { class: "faint mono", style: { fontSize: "11px" } }, e.id)),
    h("div", { class: "t-meta" }, fmtDate(e.ts), e.operator ? ` · ${e.operator}` : "", e.area ? ` · ${e.area}` : ""),
    e.details ? h("div", { class: "muted", style: { fontSize: "13px" } }, e.details) : null)));
}

async function renderUnit(root, { navigate, can }, serial) {
  mount(root, loading(4));
  let data;
  try { data = await get(`/api/units/${encodeURIComponent(serial)}`); } catch (e) {
    mount(root, pageHead("Trazabilidad", null, [h("a", { class: "btn", href: "#/trace" }, icon("arrowLeft", "sm"), "Volver")]), errorAlert(e)); return;
  }
  const u = data.unit;
  const tabsDef = [
    ["history", "Historial", u.events.length, () => timeline(u.events)],
    ["defects", "Defectos", u.defects.length, () => dataTable([
      { key: "id", label: "ID", render: (d) => h("span", { class: "mono" }, d.id) }, { key: "ts", label: "Fecha", render: (d) => fmtDate(d.ts) },
      { key: "station", label: "Estación" }, { key: "code", label: "Código", render: (d) => h("span", { class: "mono" }, d.code) },
      { key: "description", label: "Descripción" }, { key: "symptom", label: "Síntoma" }, { key: "ref_designator", label: "Ref." },
      { key: "status", label: "Estado", render: (d) => statusChip(d.status) },
      { key: "repair_id", label: "Reparación", render: (d) => d.repair_id ? h("span", { class: "mono" }, d.repair_id) : h("span", { class: "faint" }, "sin registro") },
    ], u.defects, { empty: "Sin defectos registrados." })],
    ["repairs", "Reparaciones", u.repairs.length, () => dataTable([
      { key: "id", label: "ID", render: (r) => h("span", { class: "mono" }, r.id) }, { key: "ts", label: "Fecha", render: (r) => fmtDate(r.ts) },
      { key: "defect_id", label: "Defecto", render: (r) => h("span", { class: "mono" }, r.defect_id || "—") }, { key: "action", label: "Acción" },
      { key: "operator", label: "Técnico" }], u.repairs, { empty: "Sin reparaciones registradas." })],
    ["symptoms", "Síntomas", u.symptoms.length, () => u.symptoms.length ? h("div", { class: "row" }, u.symptoms.map((x) => chip(x, "warn"))) : emptyState("Sin síntomas registrados", null, "info")],
    ["components", "Componentes", u.components.length, () => dataTable([
      { key: "ref_designator", label: "Ref." }, { key: "part_number", label: "Número de parte", render: (c) => h("span", { class: "mono" }, c.part_number) },
      { key: "description", label: "Descripción" }, { key: "lot", label: "Lote", render: (c) => h("span", { class: "mono" }, c.lot) },
      { key: "reel_id", label: "Reel", render: (c) => h("span", { class: "mono" }, c.reel_id) }], u.components, { empty: "La fuente no reporta componentes." })],
    ["scans", "Escaneos", u.scan_history.length, () => dataTable([
      { key: "ts", label: "Fecha", render: (e) => fmtDate(e.ts) }, { key: "station", label: "Estación" }, { key: "operation", label: "Operación" },
      { key: "result", label: "Resultado", render: (e) => statusChip(e.result) }, { key: "operator", label: "Operador" }, { key: "details", label: "Detalle" }],
      u.scan_history)],
    ["panel", "Panel", data.panel.length, () => data.panel.length ? h("div", { class: "grid g-4" }, data.panel.map((p) => h("a", {
      class: "card card-body", href: `#/trace/${encodeURIComponent(p.serial)}`, style: { borderColor: p.serial === u.serial ? "var(--accent)" : null, textDecoration: "none", color: "inherit" } },
      h("div", { class: "faint", style: { fontSize: "11px", fontWeight: 700, letterSpacing: ".1em" } }, `POSICIÓN ${p.panel_position}`),
      h("div", { class: "mono", style: { margin: "4px 0 8px", fontWeight: 600 } }, p.serial),
      h("div", { class: "row" }, statusChip(p.status), statusChip(p.last_result)),
      h("div", { class: "faint", style: { fontSize: "12px", marginTop: "6px" } }, `Estación: ${p.current_station || "—"}`))))
      : emptyState("Unidad sin panel asociado", "Unidad individual o ya separada sin referencia de panel.", "layers")],
    ["diag", "Diagnóstico", data.findings.length, () => data.findings.length ? h("div", null, data.findings.map((f) => h("div", { class: `finding ${f.severity}`, onclick: () => navigate(`/rework?focus=${encodeURIComponent(f.id)}`) },
      h("span", { class: "stripe" }), h("div", null, h("h4", null, f.title), h("div", { class: "muted", style: { fontSize: "13px" } }, f.facts[0].statement)), statusChip(f.severity))))
      : emptyState("Sin hallazgos", "El motor no detectó patrones de rework para esta unidad.", "checkCircle")],
  ];
  const tabBody = h("div", { class: "card-body" });
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const select = (id) => {
    tabs.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.id === id));
    mount(tabBody, tabsDef.find((t) => t[0] === id)[3]());
  };
  tabsDef.forEach(([id, label, count]) => tabs.append(h("button", { class: "tab", role: "tab", dataset: { id }, onclick: () => select(id) }, label,
    count ? chip(String(count), id === "diag" ? "err" : "neutral") : null)));

  const facts = [["Orden", u.work_order], ["Ensamble", u.assembly], ["Revisión", u.revision], ["Lote", u.batch], ["Línea", u.line], ["Área", u.area], ["Panel", u.panel_id ? `${u.panel_id} · pos ${u.panel_position ?? "?"}` : "—"]];
  const actions = [h("a", { class: "btn", href: "#/trace" }, icon("arrowLeft", "sm"), "Búsqueda")];
  if (can("operations.read")) actions.push(h("a", { class: "btn primary", href: `#/operations?serial=${encodeURIComponent(u.serial)}` }, icon("ops", "sm"), "Operaciones"));
  mount(root,
    pageHead(h("span", { class: "row" }, h("span", { class: "mono" }, u.serial), statusChip(u.status)), null, actions),
    h("div", { class: "stack" },
      h("div", { class: "grid g-kpi" },
        [["Estación actual", u.current_station || "—"], ["Última estación completada", u.last_completed_station || "—"], ["Último resultado", statusChip(u.last_result)],
         ["Defectos abiertos", String(u.open_defects)], ["Última actividad", fmtRel(u.last_activity)]]
          .map(([l, v]) => h("div", { class: "card kpi" }, h("div", { class: "label" }, l), h("div", { class: "value", style: { fontSize: "20px" } }, v)))),
      card("Flujo de producción", flowDiagram(u), { iconName: "trace" }),
      h("div", { class: "grid g-3" },
        card("Datos de la unidad", h("dl", { class: "kv" }, facts.map(([k, v]) => [h("dt", null, k), h("dd", { class: "mono" }, v || "—")])), { iconName: "info", foot: [sourceTag(data.source)] }),
        h("section", { class: "card span-2" }, tabs, tabBody))));
  select(data.findings.length ? "diag" : "history");
}
