// Asistente de mapeo OData: descubre entidades y propiedades REALES del $metadata
// de la instalación, permite mapear campos con selectores, probar y activar.
import { get, post } from "../api.js";
import { card, checksList, dataTable, errorAlert, fmtDate, h, icon, modal, mount, statusChip, toast } from "../ui.js";

const STEPS = ["Descubrir", "Mapear", "Probar", "Activar"];

export function odataWizard(root, { can, refreshStatus, onActivated }) {
  const state = { meta: null, mapping: null, schema: null, draft: null, samples: {}, report: null, step: 0 };
  const body = h("div", { class: "stack" });
  const stepsBar = h("div", { class: "tabs" });
  mount(root, card("Asistente de mapeo OData", h("div", { class: "stack" },
    h("p", { class: "muted", style: { margin: 0 } }, "Lee el $metadata real de su FactoryLogix, muestra las propiedades disponibles y genera el mapeo verificado. Todas las consultas son de sólo lectura (GET con $top)."),
    stepsBar, body), { iconName: "database" }));

  const renderSteps = () => mount(stepsBar, STEPS.map((s, i) => h("button", { class: "tab" + (i === state.step ? " active" : ""), disabled: i > state.step && !(i === 1 && state.meta) && !(i === 2 && state.draft) , onclick: () => go(i) }, `${i + 1}. ${s}`)));

  async function init() {
    renderSteps();
    mount(body, h("div", { class: "skeleton", style: { height: "80px" } }));
    try { state.mapping = await get("/api/connectors/odata/mapping"); } catch (e) { mount(body, errorAlert(e)); return; }
    state.schema = state.mapping.schema;
    state.draft = state.mapping.mapping ? structuredClone(state.mapping.mapping) : emptyDraft();
    go(0);
  }

  function emptyDraft() {
    const d = { odata_version: "4", max_rows: 2000, window_hours: 72 };
    for (const sec of Object.keys(state.schema)) d[sec] = sec === "events" ? { entity_set: "", fields: {}, value_maps: {} } : null;
    return d;
  }

  function go(i) { state.step = i; renderSteps(); [stepDiscover, stepMap, stepTest, stepActivate][i](); }

  // ---------------- Paso 1: descubrir ----------------
  async function stepDiscover() {
    const m = state.mapping;
    const current = m.mapping
      ? h("div", { class: `alert ${m.errors.length ? "warn" : "ok"}` }, icon(m.errors.length ? "alert" : "checkCircle"), h("div", null,
          h("b", null, m.active ? "Mapeo activo" : "Mapeo guardado (no activo)"), h("span", { class: "mono" }, m.path),
          m.mapping.verified_by ? h("div", { class: "faint", style: { fontSize: "12px" } }, `Verificado por ${m.mapping.verified_by} · ${fmtDate(m.mapping.verified_on)}`) : null,
          m.errors.length ? h("ul", null, m.errors.map((e) => h("li", null, e))) : null))
      : h("div", { class: "alert info" }, icon("info"), h("div", null, h("b", null, "Sin mapeo"), "Aún no existe un mapeo OData para esta instalación."));
    const btn = h("button", { class: "btn primary", onclick: async () => {
      btn.classList.add("loading");
      try {
        state.meta = await get("/api/connectors/odata/metadata", { refresh: true });
        toast(`${state.meta.entity_sets.length} EntitySets descubiertos (OData ${state.meta.version || "?"}).`, "ok");
        refreshStatus(); go(1);
      } catch (e) { mount(out, errorAlert(e)); toast(e.message, "err"); } finally { btn.classList.remove("loading"); }
    } }, icon("search", "sm"), "Leer $metadata de FactoryLogix");
    const out = h("div");
    mount(body, current, h("div", { class: "row" }, btn, h("span", { class: "faint", style: { fontSize: "12px" } }, "Requiere GPV_ODATA_BASE_URL y credenciales en el servidor.")), out,
      m.mapping && !state.meta ? h("button", { class: "btn", onclick: () => { state.meta = null; go(1); } }, "Editar mapeo guardado sin volver a descubrir") : null);
  }

  // ---------------- Paso 2: mapear ----------------
  function stepMap() {
    const sets = state.meta ? state.meta.entity_sets : [];
    const sections = Object.entries(state.schema).map(([sec, sch]) => sectionEditor(sec, sch, sets));
    const general = h("div", { class: "form-grid" },
      field("Versión OData", select(["4", "2"], state.draft.odata_version, (v) => (state.draft.odata_version = v), (v) => v === "4" ? "v4 (JSON, fechas ISO)" : "v2 (/Date(ms)/, $format=json)")),
      field("Ventana de lectura (horas, 0 = sin límite)", input(state.draft.window_hours, (v) => (state.draft.window_hours = Number(v) || 0), "number")),
      field("Máximo de filas por consulta", input(state.draft.max_rows, (v) => (state.draft.max_rows = Number(v) || 2000), "number")));
    const next = h("button", { class: "btn primary", onclick: () => { if (!state.draft.events?.entity_set) { toast("Seleccione el EntitySet de historial.", "warn"); return; } go(2); } }, icon("chevronRight", "sm"), "Probar mapeo");
    mount(body, state.meta ? h("div", { class: "faint", style: { fontSize: "12px" } }, `OData ${state.meta.version || "?"} · ${sets.length} EntitySets · ${state.meta.base_url}`)
      : h("div", { class: "alert warn" }, icon("alert"), h("div", null, "Sin $metadata cargado: los nombres se escriben manualmente. Vuelva al paso 1 para seleccionarlos de la lista real.")),
      general, ...sections, h("div", { class: "row" }, next));
  }

  function sectionEditor(sec, sch, sets) {
    const enabled = !!state.draft[sec];
    const content = h("div", { class: "stack", style: { gap: "12px" } });
    const draw = () => {
      const d = state.draft[sec];
      if (!d) { mount(content, h("p", { class: "muted", style: { margin: 0 } }, "Sección desactivada.")); return; }
      const es = sets.find((x) => x.name === d.entity_set);
      const props = es ? es.properties.map((p) => p.name) : [];
      const esSel = sets.length
        ? select(["", ...sets.map((s) => s.name)], d.entity_set, (v) => { d.entity_set = v; d.fields = {}; draw(); }, (v) => v || "Seleccione EntitySet…")
        : input(d.entity_set, (v) => (d.entity_set = v));
      const sampleBtn = h("button", { class: "btn sm", disabled: !d.entity_set, onclick: () => showSample(sec, d.entity_set) }, icon("search", "sm"), "Ver datos de muestra");
      const grid = h("div", { class: "form-grid" }, sch.fields.map((f) => field(f.label + (f.required ? " *" : ""),
        props.length ? select(["", ...props], d.fields[f.name] || "", (v) => { if (v) d.fields[f.name] = v; else delete d.fields[f.name]; }, (v) => v ? `${v}  (${(es.properties.find((p) => p.name === v) || {}).type || ""})` : "— sin mapear —")
          : input(d.fields[f.name] || "", (v) => { if (v) d.fields[f.name] = v; else delete d.fields[f.name]; }))));
      mount(content, h("div", { class: "row" }, h("div", { style: { flex: 1, minWidth: "260px" } }, esSel), sampleBtn), grid, valueMaps(sec, sch, d));
    };
    const toggle = sch.required ? null : h("label", { class: "row", style: { fontSize: "12px" } }, h("input", { type: "checkbox", checked: enabled, onchange: (e) => { state.draft[sec] = e.target.checked ? { entity_set: "", fields: {}, value_maps: {} } : null; draw(); } }), "Habilitar");
    draw();
    return card(sch.label, content, { iconName: "layers", actions: toggle ? [toggle] : null });
  }

  function valueMaps(sec, sch, d) {
    const keys = Object.keys(sch.value_maps).filter((k) => d.fields[k]);
    if (!keys.length) return null;
    const sample = state.samples[d.entity_set] || [];
    return h("div", null, h("h5", { class: "section-title" }, "MAPA DE VALORES (valor en FactoryLogix → valor del Command Center)"),
      keys.map((k) => {
        d.value_maps[k] = d.value_maps[k] || {};
        const fromReport = ((state.report || {}).sections || {})[sec]?.unmapped_values?.[k]?.seen || [];
        const seen = [...new Set([...sample.map((r) => r[d.fields[k]]).filter((v) => v !== null && v !== undefined).map(String), ...fromReport])];
        const known = new Set([...seen, ...Object.keys(d.value_maps[k])]);
        const rows = h("div", { class: "stack", style: { gap: "6px" } });
        const addRow = (src) => rows.append(h("div", { class: "row" }, h("span", { class: "mono", style: { minWidth: "160px" } }, src),
          icon("chevronRight", "sm"), select(["", ...sch.value_maps[k]], d.value_maps[k][src] || "", (v) => { if (v) d.value_maps[k][src] = v; else delete d.value_maps[k][src]; }, (v) => v || "— sin asignar (se usa tal cual) —")));
        [...known].forEach(addRow);
        const newVal = h("input", { class: "input mono", placeholder: "Valor de origen", style: { maxWidth: "200px" } });
        return h("div", { style: { marginBottom: "10px" } }, h("div", { class: "muted", style: { fontSize: "12px", marginBottom: "4px" } }, `${k} · valores permitidos: ${sch.value_maps[k].join(", ")}`,
          seen.length ? "" : " · pulse “Ver datos de muestra” para cargar los valores reales"), rows,
          h("div", { class: "row", style: { marginTop: "6px" } }, newVal, h("button", { class: "btn sm", onclick: () => { if (newVal.value.trim()) { addRow(newVal.value.trim()); newVal.value = ""; } } }, "Agregar valor")));
      }));
  }

  async function showSample(sec, entitySet) {
    let r;
    try { r = await post("/api/connectors/odata/sample", { entity_set: entitySet, top: 10 }); } catch (e) { toast(e.message, "err", e.correlationId); return; }
    state.samples[entitySet] = r.rows;
    await modal({ title: `Muestra de ${entitySet} (${r.count} filas, sólo lectura)`, confirmText: "Cerrar", cancelText: "", iconName: "database",
      body: r.rows.length ? h("div", { class: "table-wrap", style: { maxHeight: "50vh" } }, h("table", { class: "table" },
        h("thead", null, h("tr", null, r.columns.map((c) => h("th", null, c)))),
        h("tbody", null, r.rows.map((row) => h("tr", null, r.columns.map((c) => h("td", { class: "mono", style: { fontSize: "11px" } }, row[c] === null || row[c] === undefined ? "—" : String(row[c]).slice(0, 60))))))))
        : h("p", null, "El EntitySet no devolvió filas.") });
    stepMap();
  }

  // ---------------- Paso 3: probar ----------------
  async function stepTest() {
    mount(body, h("div", { class: "skeleton", style: { height: "120px" } }));
    let r;
    try { r = await post("/api/connectors/odata/mapping/test", { mapping: state.draft, top: 100 }); }
    catch (e) { mount(body, errorAlert(e), h("button", { class: "btn", onclick: () => go(1) }, icon("arrowLeft", "sm"), "Corregir mapeo")); return; }
    state.report = r.report; state.draft = r.mapping;
    const rep = r.report;
    const checks = [];
    for (const [sec, info] of Object.entries(rep.sections)) {
      checks.push({ check: `${sec}: filas leídas`, ok: info.rows > 0, message: `${info.rows} filas de muestra.` });
      if (info.unparsable_timestamps !== undefined) checks.push({ check: `${sec}: fechas interpretables`, ok: info.unparsable_timestamps === 0, message: `${info.unparsable_timestamps} no interpretables.` });
      for (const [k, v] of Object.entries(info.unmapped_values)) checks.push({ check: `${sec}.${k}: valores reconocidos`, ok: v.unknown.length === 0, message: v.unknown.length ? `Sin asignar: ${v.unknown.join(", ")}` : `Valores: ${v.seen.join(", ") || "—"}` });
    }
    checks.push({ check: "Unidades construidas", ok: rep.units_built > 0, message: `${rep.units_built} unidades a partir de la muestra.` });
    mount(body, h("div", { class: `alert ${rep.ok ? "ok" : "warn"}` }, icon(rep.ok ? "checkCircle" : "alert"), h("div", null, h("b", null, rep.ok ? "El mapeo produce datos coherentes" : "El mapeo tiene advertencias"),
        rep.warnings.length ? h("ul", null, rep.warnings.map((w) => h("li", null, w))) : "Revise la vista previa y continúe para guardar.")),
      checksList(checks),
      rep.units_preview.length ? card("Vista previa de unidades (datos reales de la muestra)", dataTable([
        { key: "serial", label: "Serial", render: (u) => h("span", { class: "mono" }, u.serial) }, { key: "work_order", label: "Orden" },
        { key: "status", label: "Estado", render: (u) => statusChip(u.status) }, { key: "current_station", label: "Estación" },
        { key: "last_result", label: "Último resultado", render: (u) => statusChip(u.last_result) }, { key: "last_activity", label: "Actividad", render: (u) => fmtDate(u.last_activity) },
      ], rep.units_preview)) : null,
      h("div", { class: "row" }, h("button", { class: "btn", onclick: () => go(1) }, icon("arrowLeft", "sm"), "Ajustar mapeo"),
        h("button", { class: "btn primary", onclick: () => go(3) }, icon("chevronRight", "sm"), "Guardar y activar")));
  }

  // ---------------- Paso 4: activar ----------------
  function stepActivate() {
    const m = state.mapping;
    const admin = can("connectors.configure");
    const activate = h("input", { type: "checkbox", checked: m.mode === "REAL", disabled: m.mode !== "REAL" });
    const confirm = h("input", { type: "checkbox" });
    const saveBtn = h("button", { class: "btn primary", disabled: !admin, onclick: async () => {
      if (!confirm.checked) { toast("Confirme la verificación del mapeo.", "warn"); return; }
      saveBtn.classList.add("loading");
      try {
        const r = await post("/api/connectors/odata/mapping/save", { mapping: state.draft, activate: activate.checked, confirm_verified: true });
        toast(r.activated ? "Mapeo guardado y fuente OData activada." : "Mapeo guardado.", "ok", r.saved);
        if (r.note) toast(r.note, "info");
        await refreshStatus();
        if (onActivated) onActivated(r);
        state.mapping = await get("/api/connectors/odata/mapping"); go(0);
      } catch (e) { toast(e.message, "err", e.correlationId); body.append(errorAlert(e)); }
      finally { saveBtn.classList.remove("loading"); }
    } }, icon("checkCircle", "sm"), "Guardar mapeo verificado");
    mount(body,
      h("pre", { class: "code" }, JSON.stringify(state.draft, null, 2)),
      m.mode !== "REAL" ? h("div", { class: "alert demo" }, icon("cpu"), h("div", null, h("b", null, "Modo DEMO"), "El mapeo se guardará en el archivo, pero la activación requiere GPV_MODE=REAL en el servidor.")) : null,
      h("label", { class: "row", style: { fontSize: "13px" } }, activate, "Activar como fuente de datos ahora (sin reiniciar)"),
      h("label", { class: "row", style: { fontSize: "13px", alignItems: "flex-start" } }, confirm, h("span", null, "Confirmo que revisé las propiedades contra la instalación de FactoryLogix y la vista previa muestra datos correctos. El mapeo quedará firmado con mi usuario en la auditoría.")),
      admin ? null : h("div", { class: "alert warn" }, icon("lock"), h("div", null, "Guardar requiere rol Administrador. Puede exportar el JSON mostrado y entregarlo al administrador.")),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: () => go(2) }, icon("arrowLeft", "sm"), "Volver"), saveBtn));
  }

  // ---------------- helpers ----------------
  function field(label, el) { return h("label", { class: "field" }, label, el); }
  function input(value, onChange, type = "text") { return h("input", { class: "input mono", type, value: value ?? "", oninput: (e) => onChange(e.target.value) }); }
  function select(options, value, onChange, labelFor = (v) => v) {
    return h("select", { class: "input", onchange: (e) => onChange(e.target.value) }, options.map((o) => h("option", { value: o, selected: o === String(value ?? "") }, labelFor(o))));
  }
  init();
}
