import { get, post } from "../api.js";
import { beep, card, checksList, chip, emptyState, errorAlert, h, icon, modal, mount, pageHead, sourceTag, statusChip, toast, uuid } from "../ui.js";

export async function render(root, { state }) {
  let box = null, serials = [], validation = null, source = null;
  const scan = h("input", { class: "input scan-input", placeholder: "Escanee la caja…", autocomplete: "off", spellcheck: "false", maxlength: 64, "aria-label": "Entrada de escáner" });
  const stepLabel = h("div", { class: "nav-group", style: { margin: "0 0 8px" } }, "PASO 1 · ESCANEAR CAJA");
  const boxPanel = h("div");
  const listPanel = h("div");
  const checksPanel = h("div");
  const packBtn = h("button", { class: "btn primary", disabled: true }, icon("box", "sm"), "Empacar caja…");
  const resetBtn = h("button", { class: "btn", onclick: () => reset() }, icon("refresh", "sm"), "Nueva caja");

  mount(root, pageHead("Packing Intelligence", "Pantalla optimizada para escáner: valida duplicados, cantidades, ensamble/revisión y liberación de cada unidad.", [resetBtn, packBtn]),
    state.status?.mode === "DEMO" ? h("div", { class: "alert demo", style: { marginBottom: "16px" } }, icon("cpu"), h("div", null, h("b", null, "DEMO"), "Pruebe con la caja BOX-DEMO-24102-01 y el serial DEMO-GPV-A00005 (liberado), o seriales no conformes para ver discrepancias.")) : null,
    h("div", { class: "grid g-3" },
      h("div", { class: "span-2 stack" }, h("section", { class: "card card-body" }, stepLabel, scan), listPanel),
      h("div", { class: "stack" }, boxPanel, checksPanel)));

  const focus = () => setTimeout(() => scan.focus(), 0);
  const flash = (ok) => { scan.classList.remove("flash-ok", "flash-err"); void scan.offsetWidth; scan.classList.add(ok ? "flash-ok" : "flash-err"); beep(ok); };

  function reset() {
    box = null; serials = []; validation = null;
    scan.placeholder = "Escanee la caja…"; stepLabel.textContent = "PASO 1 · ESCANEAR CAJA";
    mount(boxPanel, card("Caja", emptyState("Sin caja", "Escanee la etiqueta de la caja para comenzar.", "box")));
    mount(listPanel); mount(checksPanel); packBtn.disabled = true; focus();
  }

  function renderBox() {
    const filled = box.serials.length + serials.length;
    const p = Math.min(100, (filled / box.capacity) * 100);
    mount(boxPanel, card("Caja", h("div", { class: "stack", style: { gap: "10px" } },
      h("div", { class: "mono", style: { fontSize: "18px", fontWeight: 700 } }, box.box_id),
      h("dl", { class: "kv" }, h("dt", null, "Orden"), h("dd", { class: "mono" }, box.work_order), h("dt", null, "Ensamble"), h("dd", null, box.assembly),
        h("dt", null, "Revisión"), h("dd", null, box.revision), h("dt", null, "Estado"), h("dd", null, chip(box.status, box.status === "OPEN" ? "ok" : "warn"))),
      h("div", null, h("div", { class: "row", style: { justifyContent: "space-between", fontSize: "12px" } }, h("span", null, "Progreso de llenado"), h("b", null, `${filled} / ${box.capacity}`)),
        h("div", { class: "progress", style: { marginTop: "6px" } }, h("i", { style: { width: p + "%" } }))),
      box.serials.length ? h("div", { class: "faint", style: { fontSize: "12px" } }, `Ya empacadas: ${box.serials.join(", ")}`) : null), { iconName: "box", foot: [sourceTag(source)] }));
  }

  function renderList() {
    const unitBy = Object.fromEntries((validation?.units || []).map((u) => [u.serial, u]));
    const checkBy = Object.fromEntries((validation?.validations || []).map((c) => [c.check.replace("Unidad ", ""), c]));
    mount(listPanel, card(`Unidades escaneadas (${serials.length})`, serials.length ? h("ul", { class: "scan-list" }, serials.map((s, i) => {
      const c = checkBy[s], u = unitBy[s];
      return h("li", null, icon(c && c.ok ? "checkCircle" : "xCircle"), h("span", { class: "mono", style: { fontWeight: 600 } }, s),
        u ? statusChip(u.status) : chip("NO ENCONTRADO", "err"), u ? chip(`${u.assembly} · ${u.revision}`, "outline") : null,
        h("span", { class: "muted", style: { fontSize: "12px", flex: 1 } }, c ? c.message : ""),
        h("button", { class: "btn ghost icon-only sm", "aria-label": "Quitar", onclick: () => { serials.splice(i, 1); validate(); } }, icon("x", "sm")));
    })) : emptyState("Sin unidades", "Escanee seriales para agregarlos a la caja.", "scan"), { iconName: "scan" }));
  }

  async function validate() {
    try {
      validation = await post("/api/packing/validate", { box_id: box.box_id, serials });
      source = validation.source;
    } catch (e) { mount(checksPanel, errorAlert(e)); return false; }
    renderBox(); renderList();
    const issues = validation.validations.filter((c) => !c.ok);
    mount(checksPanel, card("Discrepancias", issues.length ? checksList(issues) : h("div", { class: "alert ok" }, icon("checkCircle"), h("div", null, h("b", null, "Sin discrepancias"), serials.length ? "Todas las unidades están liberadas y son conformes." : "Esperando unidades.")),
      { iconName: "alert" }));
    packBtn.disabled = !validation.ready;
    return validation;
  }

  scan.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const code = scan.value.trim().toUpperCase();
    scan.value = "";
    if (!code) return;
    if (!/^[A-Z0-9._\-/]{3,64}$/.test(code)) { flash(false); toast("Lectura inválida del escáner.", "err", code); return; }
    if (!box) {
      try {
        const r = await get(`/api/packing/box/${encodeURIComponent(code)}`);
        box = r.box; source = r.source; flash(true);
        scan.placeholder = "Escanee el serial de la unidad…"; stepLabel.textContent = "PASO 2 · ESCANEAR UNIDADES";
        renderBox(); renderList(); validate();
      } catch (err) { flash(false); mount(boxPanel, errorAlert(err)); }
      return;
    }
    if (serials.includes(code)) { flash(false); toast(`Serial duplicado: ${code}`, "err"); return; }
    serials.push(code);
    const v = await validate();
    const c = v && v.validations.find((x) => x.check === `Unidad ${code}`);
    const ok = !!(c && c.ok);
    flash(ok);
    if (!ok) toast(`Discrepancia en ${code}`, "warn", c ? c.message : "Serial no encontrado");
  });

  packBtn.addEventListener("click", async () => {
    const params = { box_id: box.box_id, serials };
    let prep;
    try { prep = await post("/api/operations/pack_box/prepare", { params }); } catch (e) { toast(e.message, "err"); mount(checksPanel, errorAlert(e)); return; }
    if (!prep.allowed) { mount(checksPanel, card("Validación del servidor", checksList(prep.validations))); return; }
    const ok = await modal({ title: `Empacar ${serials.length} unidad(es) en ${box.box_id}`, requireCheck: prep.mode === "DEMO" ? "Entiendo que es una simulación DEMO y no modifica FactoryLogix." : "Confirmo la transacción de packing.",
      body: h("div", null, h("p", null, prep.executor), h("div", { class: "row" }, serials.map((s) => chip(s, "outline")))) });
    if (!ok) { focus(); return; }
    packBtn.classList.add("loading");
    try {
      const res = await post("/api/operations/pack_box/execute", { params, confirmation_token: prep.confirmation_token, idempotency_key: uuid(), confirm: true });
      toast(`Caja ${box.box_id}: ${res.server_response.body.box_count} unidad(es) registradas${res.simulated ? " (SIMULADO)" : ""}.`, "ok", `Auditoría #${res.audit_id}`);
      const id = box.box_id;
      reset();
      scan.value = id;
      scan.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    } catch (e) { toast(e.message, "err", e.correlationId); mount(checksPanel, errorAlert(e)); }
    finally { packBtn.classList.remove("loading"); }
  });

  root.addEventListener("click", (e) => { if (!e.target.closest("button, a, input, select, textarea")) focus(); });
  reset();
}
