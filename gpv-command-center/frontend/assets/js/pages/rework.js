import { get } from "../api.js";
import { card, chip, drawer, emptyState, fmtDate, h, icon, loading, mount, pageHead, sourceTag, statusChip } from "../ui.js";
import { SEV_COLORS, unavailableBlock } from "./common.js";

const RISK_TONE = { ALTO: "err", MEDIO: "warn", BAJO: "ok" };

export async function render(root, { query, navigate }) {
  const body = h("div", null, loading(5));
  const refresh = h("button", { class: "btn", onclick: () => load() }, icon("refresh", "sm"), "Re-analizar");
  mount(root, pageHead("Rework inteligente", "Motor de diagnóstico: hechos confirmados con evidencia, hipótesis separadas y riesgo de intervenir.", [refresh]), body);
  let filter = { severity: null, rule: null };

  async function load() {
    refresh.classList.add("loading");
    let d;
    try { d = await get("/api/diagnostics"); } catch (e) { mount(body, unavailableBlock(e)); return; } finally { refresh.classList.remove("loading"); }
    const list = h("div");
    const renderList = () => {
      const items = d.findings.filter((f) => (!filter.severity || f.severity === filter.severity) && (!filter.rule || f.rule_id === filter.rule));
      mount(list, items.length ? items.map((f) => findingRow(f)) : emptyState("Sin hallazgos con estos filtros", null, "checkCircle"));
    };
    const findingRow = (f) => h("div", { class: `finding ${f.severity}`, onclick: () => openFinding(f, navigate), tabindex: "0", onkeydown: (e) => { if (e.key === "Enter") openFinding(f, navigate); } },
      h("span", { class: "stripe" }),
      h("div", null,
        h("div", { class: "row", style: { gap: "8px" } }, h("h4", null, f.title), f.station ? chip(f.station, "outline") : null),
        h("div", { class: "muted", style: { fontSize: "13px" } }, f.facts[0].statement),
        h("div", { class: "row faint", style: { fontSize: "12px", marginTop: "4px" } }, icon("trace", "sm"),
          f.panel_id ? h("span", { class: "mono" }, f.panel_id + " · ") : null, h("span", { class: "mono" }, f.serials.slice(0, 4).join(", ")), f.serials.length > 4 ? ` +${f.serials.length - 4}` : "",
          f.work_order ? h("span", { class: "mono" }, " · " + f.work_order) : null)),
      h("div", { style: { textAlign: "right" } }, statusChip(f.severity),
        h("div", { class: "faint", style: { fontSize: "11px", marginTop: "8px" } }, `Confianza ${f.confidence.level}`),
        h("div", { class: "meter", style: { marginLeft: "auto", marginTop: "4px" } }, h("i", { style: { width: `${f.confidence.score * 100}%` } }))));

    const sevChips = h("div", { class: "row" }, h("button", { class: "btn sm" + (!filter.severity ? " primary" : ""), onclick: () => { filter.severity = null; load2(); } }, `Todas · ${d.findings.length}`),
      Object.entries(d.summary).filter(([, n]) => n).map(([sv, n]) => h("button", { class: "btn sm" + (filter.severity === sv ? " primary" : ""), onclick: () => { filter.severity = sv; load2(); } },
        h("span", { class: "dot", style: { background: SEV_COLORS[sv] } }), `${statusChip(sv).textContent} · ${n}`)));
    const rules = h("div", { class: "stack", style: { gap: "4px" } }, Object.entries(d.rules).map(([id, label]) => h("button", {
      class: "btn ghost sm" + (filter.rule === id ? " primary" : ""), style: { justifyContent: "space-between", width: "100%" },
      onclick: () => { filter.rule = filter.rule === id ? null : id; load2(); } }, label, chip(String(d.by_rule[id] || 0), d.by_rule[id] ? "err" : "neutral"))));
    const thresholds = h("dl", { class: "kv", style: { fontSize: "12px" } },
      h("dt", null, "Atrapado en reparación"), h("dd", null, `≥ ${d.thresholds.stuck_repair_hours} h sin reparación`),
      h("dt", null, "Espera en Depanel"), h("dd", null, `≥ ${d.thresholds.depanel_wait_hours} h`),
      h("dt", null, "Bucle FCT↔Debug"), h("dd", null, `≥ ${d.thresholds.loop_min_cycles} ciclos`),
      h("dt", null, "Retorno repetido"), h("dd", null, `≥ ${d.thresholds.repeat_min_visits} ingresos`));
    function load2() { mount(body, layout()); renderList(); }
    const layout = () => h("div", { class: "grid g-4" },
      h("div", { class: "stack" }, card("Reglas", rules, { iconName: "layers" }), card("Umbrales", thresholds, { iconName: "clock" })),
      h("div", { class: "span-3 stack" }, sevChips, h("section", { class: "card" }, list), h("div", null, sourceTag(d.source), h("span", { class: "faint", style: { fontSize: "12px" } }, ` · Análisis ${fmtDate(d.generated_at)}`))));
    load2();
    if (query.focus) {
      const f = d.findings.find((x) => x.id === query.focus);
      if (f) openFinding(f, navigate);
      query.focus = null;
    }
  }
  await load();
}

function openFinding(f, navigate) {
  const sec = (n, title, content) => h("section", null, h("h5", { class: "section-title" }, h("span", { class: "n" }, n), title), content);
  drawer(
    [h("div", { class: "row" }, statusChip(f.severity), chip(f.rule_id, "outline")), h("h3", { style: { margin: "8px 0 4px" } }, f.title),
     h("div", { class: "row", style: { fontSize: "12px" } }, f.serials.map((s) => h("a", { href: `#/trace/${encodeURIComponent(s)}`, class: "mono" }, s)))],
    [
      sec(1, "PROBLEMA DETECTADO", h("p", { style: { margin: 0 } }, f.title + (f.station ? ` en ${f.station}` : "") + (f.panel_id ? ` · panel ${f.panel_id}` : "") + (f.work_order ? ` · ${f.work_order}` : "") + ".")),
      sec(2, "EVIDENCIA ENCONTRADA", h("div", null, f.facts.map((x) => h("div", { class: "fact" }, h("span", { class: "tag" }, "HECHO CONFIRMADO"), x.statement,
        x.evidence.length ? h("div", { class: "evidence" }, x.evidence.slice(0, 16).map((id) => h("code", null, id)), x.evidence.length > 16 ? h("code", null, `+${x.evidence.length - 16}`) : null) : null)))),
      sec(3, "POSIBLES CAUSAS", h("div", null, f.hypotheses.map((x) => h("div", { class: "hyp" }, h("span", { class: "tag" }, "HIPÓTESIS · NO CONFIRMADA"), x.statement)))),
      sec(4, "NIVEL DE CONFIANZA", h("div", null, h("div", { class: "row" }, h("b", { style: { fontSize: "20px" } }, `${Math.round(f.confidence.score * 100)}%`), chip(f.confidence.level, f.confidence.level === "ALTA" ? "ok" : f.confidence.level === "MEDIA" ? "warn" : "neutral"),
        h("div", { class: "meter", style: { width: "200px" } }, h("i", { style: { width: `${f.confidence.score * 100}%` } }))), h("p", { class: "muted", style: { margin: "6px 0 0", fontSize: "13px" } }, f.confidence.basis))),
      sec(5, "ACCIONES RECOMENDADAS", h("ol", { style: { margin: 0, paddingLeft: "18px" } }, f.recommended_actions.map((a) => h("li", { style: { marginBottom: "4px" } }, a)))),
      sec(6, "HISTORIAL PREVIO", f.history.length ? h("ul", { class: "timeline" }, [...f.history].reverse().slice(0, 14).map((e) => h("li", { class: e.result },
        h("div", { class: "t-head" }, h("b", null, e.station), chip(e.operation, "outline"), statusChip(e.result), h("span", { class: "faint mono", style: { fontSize: "11px" } }, e.serial !== f.serials[0] ? e.serial : "")),
        h("div", { class: "t-meta" }, fmtDate(e.ts), e.details ? ` · ${e.details}` : "")))) : h("p", { class: "muted" }, "Ver historial individual de cada unidad en Trazabilidad.")),
      sec(7, "RIESGO DE INTERVENIR", h("div", { class: `alert ${RISK_TONE[f.intervention_risk.level] || "info"}` }, icon("alert"), h("div", null, h("b", null, `Riesgo ${f.intervention_risk.level}`), f.intervention_risk.description))),
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => { document.querySelector(".drawer-backdrop")?.click(); navigate(`/trace/${encodeURIComponent(f.serials[0])}`); } }, icon("trace", "sm"), "Abrir trazabilidad"),
        h("span", { class: "faint", style: { fontSize: "12px" } }, "El diagnóstico no modifica datos. Cualquier corrección debe ejecutarse por el flujo oficial.")),
    ]);
}
