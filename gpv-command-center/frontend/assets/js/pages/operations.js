import { get, post } from "../api.js";
import { card, checksList, chip, errorAlert, h, icon, loading, modal, mount, pageHead, statusChip, toast, uuid } from "../ui.js";

const INTEGRATION_LABELS = [["official_method", "Método oficial"], ["endpoint", "Endpoint / servicio"], ["license", "Licencia"],
  ["authentication", "Autenticación"], ["privileges", "Privilegios requeridos"], ["consequences", "Consecuencias"], ["reversibility", "Reversión"]];

export async function render(root, { query, state }) {
  const left = h("div", { class: "stack" }, loading(4));
  const right = h("div", { class: "stack" });
  mount(root, pageHead("Centro de Operaciones Controladas",
    "Toda acción exige rol autorizado, verificación del estado previo, confirmación explícita, auditoría y comprobación posterior."),
    h("div", { class: "grid g-3" }, left, h("div", { class: "span-2" }, right)));

  let catalog;
  try { catalog = await get("/api/operations/catalog"); } catch (e) { mount(left, errorAlert(e)); return; }
  const role = state.user.role;
  const modeAlert = catalog.mode === "DEMO"
    ? h("div", { class: "alert demo" }, icon("cpu"), h("div", null, h("b", null, "Modo DEMO"), "Las acciones se ejecutan en un simulador en memoria con datos sintéticos. No existe conexión de escritura a FactoryLogix."))
    : h("div", { class: "alert warn" }, icon("lock"), h("div", null, h("b", null, "SOLO LECTURA"), "Ninguna transacción de FactoryLogix ha sido verificada para esta instalación. Las acciones se muestran como NO DISPONIBLE con sus requisitos faltantes."));

  const groups = {};
  catalog.actions.forEach((a) => (groups[a.category] = groups[a.category] || []).push(a));
  const buttons = new Map();
  const select = (a, prefill = {}) => {
    buttons.forEach((b, id) => b.style.borderColor = id === a.id ? "var(--accent)" : "");
    renderAction(right, a, role, catalog.mode, prefill);
  };
  mount(left, modeAlert, ...Object.entries(groups).map(([g, acts]) => card(g, h("div", { class: "stack", style: { gap: "8px" } }, acts.map((a) => {
    const allowed = a.roles.includes(role);
    const b = h("button", { class: "role-card", style: { padding: "10px 12px" }, onclick: () => select(a) },
      h("div", { style: { flex: 1 } }, h("b", { style: { fontSize: "13px" } }, a.name), h("div", { class: "row", style: { marginTop: "4px", gap: "6px" } },
        statusChip(a.availability), allowed ? null : chip("ROL NO AUTORIZADO", "neutral"), a.destructive ? chip("DESTRUCTIVA", "err") : null)),
      icon("chevronRight"));
    buttons.set(a.id, b);
    return b;
  })))));

  const initial = catalog.actions.find((a) => a.id === query.action) || catalog.actions.find((a) => a.availability !== "NO_DISPONIBLE" && a.roles.includes(role)) || catalog.actions[0];
  select(initial, query.serial ? { serial: query.serial } : {});
}

function renderAction(root, a, role, mode, prefill) {
  const allowed = a.roles.includes(role);
  const integ = a.integration;
  const info = card(a.name, h("div", { class: "stack", style: { gap: "12px" } },
    h("p", { style: { margin: 0 } }, a.description),
    h("div", { class: "row" }, statusChip(a.availability), chip(`Roles: ${a.roles.join(", ")}`, "outline"), chip(`Verificación: ${integ.verification_status}`, integ.verification_status === "VERIFICADO" ? "ok" : "warn")),
    a.availability_reason ? h("p", { class: "muted", style: { margin: 0, fontSize: "13px" } }, a.availability_reason) : null,
    h("details", null, h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Requisitos de integración con FactoryLogix"),
      h("dl", { class: "kv", style: { marginTop: "10px" } }, INTEGRATION_LABELS.map(([k, l]) => [h("dt", null, l), h("dd", { class: integ[k] === "NO VERIFICADO" ? "" : "" }, integ[k] === "NO VERIFICADO" ? chip("NO VERIFICADO", "warn") : integ[k])])),
      integ.missing_requirements.length ? h("div", { class: "alert warn", style: { marginTop: "10px" } }, icon("alert"), h("div", null, h("b", null, "Requisitos faltantes para habilitar en producción"),
        h("ul", null, integ.missing_requirements.map((m) => h("li", null, m))))) : null)), { iconName: "ops" });

  if (a.availability === "NO_DISPONIBLE") {
    mount(root, info, h("div", { class: "alert warn" }, icon("lock"), h("div", null, h("b", null, "NO DISPONIBLE"), a.availability_reason)));
    return;
  }
  if (!allowed) {
    mount(root, info, h("div", { class: "alert err" }, icon("lock"), h("div", null, h("b", null, "Rol no autorizado"), `Su rol (${role}) no puede ejecutar esta acción. Roles permitidos: ${a.roles.join(", ")}.`)));
    return;
  }

  const inputs = {};
  const datalist = h("datalist", { id: "defect-options" });
  const fields = a.params.map((p) => {
    let el;
    if (p.kind === "enum") el = h("select", { class: "input" }, h("option", { value: "" }, "Seleccione…"), p.options.map((o) => h("option", { value: o, selected: prefill[p.name] === o }, o)));
    else if (p.kind === "list") el = h("textarea", { class: "input mono", rows: 4, placeholder: "Un serial por línea" });
    else if (p.max_len > 120) el = h("textarea", { class: "input", rows: 2, maxlength: p.max_len });
    else el = h("input", { class: "input" + (p.name === "serial" || p.name.endsWith("_id") ? " mono" : ""), maxlength: p.max_len, value: prefill[p.name] || "", list: p.name === "defect_id" ? "defect-options" : null });
    inputs[p.name] = el;
    return h("label", { class: "field" }, `${p.label}${p.required ? " *" : ""}`, el, h("span", { class: "err", dataset: { err: p.name } }));
  });
  if (inputs.serial && inputs.defect_id) {
    const loadDefects = async () => {
      const s = inputs.serial.value.trim();
      if (!s) return;
      try {
        const d = await get(`/api/units/${encodeURIComponent(s)}`);
        mount(datalist, d.unit.defects.filter((x) => x.status === "OPEN").map((x) => h("option", { value: x.id }, `${x.code} · ${x.description}`)));
        const open = d.unit.defects.filter((x) => x.status === "OPEN");
        if (open.length === 1 && !inputs.defect_id.value) inputs.defect_id.value = open[0].id;
      } catch { mount(datalist); }
    };
    inputs.serial.addEventListener("change", loadDefects);
    if (inputs.serial.value) loadDefects();
  }
  const values = () => Object.fromEntries(a.params.map((p) => [p.name, p.kind === "list" ? inputs[p.name].value.split(/\s+/).map((x) => x.trim()).filter(Boolean) : inputs[p.name].value.trim()]));
  const result = h("div", { class: "stack" });
  const prepareBtn = h("button", { class: "btn primary", type: "submit" }, icon("checkCircle", "sm"), "Validar estado y preparar");

  const form = h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    root.querySelectorAll("[data-err]").forEach((x) => (x.textContent = ""));
    Object.values(inputs).forEach((x) => x.classList.remove("invalid"));
    prepareBtn.classList.add("loading");
    const params = values();
    try {
      const prep = await post(`/api/operations/${a.id}/prepare`, { params });
      renderPrepared(result, a, prep, params, mode);
    } catch (err) {
      const f = (err.details && err.details.fields) || {};
      Object.entries(f).forEach(([k, msg]) => { const sp = root.querySelector(`[data-err="${k}"]`); if (sp) sp.textContent = msg; inputs[k] && inputs[k].classList.add("invalid"); });
      mount(result, errorAlert(err));
    } finally { prepareBtn.classList.remove("loading"); }
  } }, h("div", { class: "form-grid" }, fields), datalist, h("div", { class: "row" }, prepareBtn, h("span", { class: "faint", style: { fontSize: "12px" } }, "Paso 1 de 2 · No se modifica nada en este paso.")));
  mount(root, info, card("Parámetros", form, { iconName: "file" }), result);
}

function renderPrepared(root, a, prep, params, mode) {
  const idemKey = uuid();
  let inFlight = false;
  const execBtn = h("button", { class: "btn " + (mode === "DEMO" ? "primary" : "danger"), disabled: !prep.allowed }, icon("play", "sm"), mode === "DEMO" ? "Ejecutar simulación…" : "Ejecutar…");
  const pre = prep.pre_state.map((u) => h("div", { class: "row", style: { padding: "6px 0", borderBottom: "1px solid var(--border)" } },
    h("a", { class: "mono", href: `#/trace/${encodeURIComponent(u.serial)}` }, u.serial), statusChip(u.status), chip(`Estación: ${u.current_station || "—"}`, "outline"), statusChip(u.last_result),
    u.open_defects ? chip(`${u.open_defects} defecto(s) abierto(s)`, "err") : null));
  execBtn.addEventListener("click", async () => {
    if (inFlight) return;
    const ok = await modal({
      title: `Confirmar: ${a.name}`, tone: mode === "DEMO" ? "primary" : "danger", confirmText: mode === "DEMO" ? "Ejecutar simulación" : "Ejecutar",
      requireCheck: mode === "DEMO" ? "Entiendo que es una simulación DEMO sobre datos sintéticos y que no modifica FactoryLogix." : "Confirmo que tengo autorización para ejecutar esta transacción en FactoryLogix.",
      body: h("div", { class: "stack", style: { gap: "10px" } },
        h("dl", { class: "kv" }, h("dt", null, "Modo"), h("dd", null, chip(mode, mode === "DEMO" ? "demo" : "err")), h("dt", null, "Ejecutor"), h("dd", null, prep.executor),
          Object.entries(params).map(([k, v]) => [h("dt", null, k), h("dd", { class: "mono" }, Array.isArray(v) ? v.join(", ") : v || "—")])),
        h("div", { class: "alert warn" }, icon("alert"), h("div", null, h("b", null, "Consecuencias"), a.integration.consequences, h("br"), h("b", null, "Reversión: "), a.integration.reversibility)),
        h("p", { class: "faint", style: { fontSize: "12px", margin: 0 } }, `La confirmación expira en ${prep.expires_in} s. Si el estado cambia antes de ejecutar, la operación será rechazada.`)),
    });
    if (!ok) return;
    inFlight = true; execBtn.classList.add("loading");
    try {
      const res = await post(`/api/operations/${a.id}/execute`, { params, confirmation_token: prep.confirmation_token, idempotency_key: idemKey, confirm: true });
      execBtn.disabled = true;
      toast(res.simulated ? "Operación simulada correctamente (DEMO)." : "Operación ejecutada.", res.status.includes("SUCCESS") ? "ok" : "warn", `Auditoría #${res.audit_id} · ${res.correlation_id}`);
      root.append(card("Resultado", h("div", { class: "stack", style: { gap: "12px" } },
        h("div", { class: "row" }, statusChip(res.status), res.simulated ? chip("SIMULADO · NO ES RESPUESTA DE FACTORYLOGIX", "demo") : null, res.replayed ? chip("RESPUESTA REPETIDA (idempotencia)", "warn") : null),
        h("div", null, h("h5", { class: "section-title" }, "RESPUESTA DEL SERVIDOR"), h("pre", { class: "code" }, JSON.stringify(res.server_response, null, 2))),
        h("div", null, h("h5", { class: "section-title" }, "COMPROBACIÓN POSTERIOR DEL ESTADO"), checksList(res.post_checks)),
        h("div", null, h("h5", { class: "section-title" }, "ESTADO POSTERIOR"), res.post_state.map((u) => h("div", { class: "row" }, h("span", { class: "mono" }, u.serial), statusChip(u.status), chip(`Estación: ${u.current_station || "—"}`, "outline")))),
        h("div", { class: "faint mono", style: { fontSize: "11px" } }, `Auditoría #${res.audit_id} · Correlación ${res.correlation_id}`)), { iconName: "checkCircle" }));
    } catch (err) {
      toast(err.message, "err", err.correlationId ? `ID: ${err.correlationId}` : undefined);
      root.append(errorAlert(err));
    } finally { inFlight = false; execBtn.classList.remove("loading"); }
  });
  mount(root, card("Verificación previa", h("div", { class: "stack", style: { gap: "14px" } },
    h("div", null, h("h5", { class: "section-title" }, "ESTADO PREVIO"), pre),
    h("div", null, h("h5", { class: "section-title" }, "VALIDACIÓN DEL FLUJO DE PROCESO"), checksList(prep.validations)),
    prep.allowed ? h("div", { class: "row" }, execBtn, h("span", { class: "faint", style: { fontSize: "12px" } }, "Paso 2 de 2 · Requiere confirmación explícita."))
      : h("div", { class: "alert err" }, icon("xCircle"), h("div", null, h("b", null, "Operación bloqueada"), "El estado actual no cumple las validaciones del flujo de proceso. No se emitió token de confirmación."))),
    { iconName: "shield" }));
}
