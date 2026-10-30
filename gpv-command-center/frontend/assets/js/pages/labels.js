import { get, post } from "../api.js";
import { card, chip, dataTable, errorAlert, fmtDate, h, icon, loading, modal, mount, pageHead, s, statusChip, toast } from "../ui.js";

export async function render(root, { can }) {
  mount(root, pageHead("Label Control", "Impresión controlada separada de las transacciones de producción. Compatible conceptualmente con Zebra (ZPL), CAB y BarTender."), loading(3));
  let cfg;
  try { cfg = await get("/api/labels/printers"); } catch (e) { mount(root, pageHead("Label Control"), errorAlert(e)); return; }

  const printerSel = h("select", { class: "input" }, cfg.printers.map((p) => h("option", { value: p.id }, p.name)));
  const templateSel = h("select", { class: "input" }, cfg.templates.map((t) => h("option", { value: t.id }, `${t.name} · ${t.language}`)));
  const printerState = h("div");
  const formSlot = h("div");
  const previewSlot = h("div");
  const jobsSlot = h("div");
  const inputs = {};

  const checkPrinter = async () => {
    if (!printerSel.value) { mount(printerState, h("div", { class: "alert warn" }, icon("alert"), h("div", null, h("b", null, "Sin impresoras autorizadas"), "Configure config/printers.json en el servidor."))); return; }
    mount(printerState, h("span", { class: "faint" }, "Consultando estado…"));
    try {
      const st = await post(`/api/labels/printers/${encodeURIComponent(printerSel.value)}/check`);
      const p = cfg.printers.find((x) => x.id === printerSel.value);
      mount(printerState, h("div", { class: "stack", style: { gap: "6px" } }, h("div", { class: "row" }, statusChip(st.state), st.simulated ? chip("SIMULADA", "demo") : null, chip(p.vendor, "outline"), chip(p.language, "outline")),
        h("div", { class: "muted", style: { fontSize: "12px" } }, st.message)));
    } catch (e) { mount(printerState, errorAlert(e)); }
  };

  const renderForm = () => {
    const t = cfg.templates.find((x) => x.id === templateSel.value);
    Object.keys(inputs).forEach((k) => delete inputs[k]);
    if (t.unavailable_reason) { mount(formSlot, h("div", { class: "alert warn" }, icon("lock"), h("div", null, h("b", null, "NO DISPONIBLE"), t.unavailable_reason))); mount(previewSlot); return; }
    mount(formSlot, h("div", { class: "form-grid" }, t.fields.map((f) => {
      inputs[f.name] = h("input", { class: "input mono", placeholder: f.label, maxlength: 64 });
      return h("label", { class: "field" }, f.label + (f.required ? " *" : ""), inputs[f.name]);
    })), h("div", { class: "row", style: { marginTop: "12px" } }, h("button", { class: "btn", onclick: preview }, icon("search", "sm"), "Validar y previsualizar")));
    mount(previewSlot);
  };

  const data = () => Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value.trim()]));

  async function preview() {
    let p;
    try { p = await post("/api/labels/preview", { template_id: templateSel.value, data: data() }); } catch (e) { mount(previewSlot, errorAlert(e)); return; }
    const W = p.template.width_dots, H = p.template.height_dots;
    const svg = s("svg", { class: "label-canvas", viewBox: `0 0 ${W} ${H}`, width: Math.min(W, 520), role: "img", "aria-label": "Previsualización de etiqueta" });
    svg.append(s("rect", { width: W, height: H, fill: "#fff" }));
    p.layout.forEach((el) => {
      if (el.type === "text") svg.append(s("text", { x: el.x, y: el.y + el.size * 0.85, style: `font: 700 ${el.size}px Arial, sans-serif; fill:#000` }, el.value));
      if (el.type === "barcode") {
        // Representación esquemática (NO escaneable): franjas derivadas del contenido.
        let x = el.x; const bw = 2;
        for (const ch of el.value) { const code = ch.charCodeAt(0); for (let b = 0; b < 6; b++) { const w = ((code >> b) & 1 ? 2 : 1) * bw; if (b % 2 === 0) svg.append(s("rect", { x, y: el.y, width: w, height: el.height, fill: "#000" })); x += w + bw; } }
        svg.append(s("text", { x: el.x, y: el.y + el.height + 22, style: "font: 18px monospace; fill:#000" }, el.value));
      }
    });
    const reason = h("input", { class: "input", placeholder: "Justificación de reimpresión (mín. 10 caracteres)", maxlength: 240 });
    const printBtn = h("button", { class: "btn primary" }, icon("printer", "sm"), p.would_be_reprint ? "Reimprimir…" : "Imprimir…");
    const reprintBlocked = p.would_be_reprint && !can("labels.reprint");
    if (reprintBlocked) printBtn.disabled = true;
    printBtn.addEventListener("click", async () => {
      const printer = cfg.printers.find((x) => x.id === printerSel.value);
      const ok = await modal({ title: p.would_be_reprint ? "Confirmar REIMPRESIÓN" : "Confirmar impresión", iconName: "printer",
        body: h("dl", { class: "kv" }, h("dt", null, "Impresora"), h("dd", null, printer ? printer.name : printerSel.value), h("dt", null, "Plantilla"), h("dd", null, p.template.name),
          Object.entries(p.data).map(([k, v]) => [h("dt", null, k), h("dd", { class: "mono" }, v)])),
        requireCheck: printer && printer.simulated ? "Entiendo que la impresión es simulada (DEMO)." : null });
      if (!ok) return;
      printBtn.classList.add("loading");
      try {
        const r = await post("/api/labels/print", { printer_id: printerSel.value, template_id: templateSel.value, data: data(), reason: reason.value.trim() });
        toast(r.message, r.outcome.includes("SUCCESS") ? "ok" : "err", `Trabajo #${r.job_id}`);
        loadJobs(); preview();
      } catch (e) { toast(e.message, "err", e.correlationId); previewSlot.append(errorAlert(e)); }
      finally { printBtn.classList.remove("loading"); }
    });
    mount(previewSlot, card("Previsualización", h("div", { class: "stack" },
      h("div", { style: { padding: "16px", background: "var(--surface-2)", borderRadius: "8px", textAlign: "center" } }, svg),
      h("p", { class: "faint", style: { fontSize: "12px", margin: 0 } }, p.note + " El código de barras mostrado es esquemático y no es escaneable."),
      h("details", null, h("summary", { style: { cursor: "pointer" } }, `Código ${p.template.language} generado`), h("pre", { class: "code", style: { marginTop: "8px" } }, p.zpl)),
      p.would_be_reprint ? h("div", { class: "alert warn" }, icon("alert"), h("div", null, h("b", null, "Esta etiqueta ya fue impresa"),
        reprintBlocked ? "La reimpresión requiere rol de Calidad o Administrador." : "La reimpresión requiere justificación y queda auditada.")) : null,
      p.would_be_reprint && !reprintBlocked ? reason : null,
      h("div", { class: "row" }, printBtn)), { iconName: "printer" }));
  }

  async function loadJobs() {
    try {
      const j = await get("/api/labels/jobs");
      mount(jobsSlot, card("Historial de impresión", dataTable([
        { key: "id", label: "#", num: true }, { key: "ts", label: "Fecha", render: (r) => fmtDate(r.ts) }, { key: "username", label: "Usuario" },
        { key: "printer_id", label: "Impresora", render: (r) => h("span", { class: "mono" }, r.printer_id) }, { key: "template_id", label: "Plantilla" },
        { key: "serial", label: "Clave", render: (r) => h("span", { class: "mono" }, r.serial) },
        { key: "is_reprint", label: "Tipo", render: (r) => r.is_reprint ? chip("REIMPRESIÓN", "warn") : chip("ORIGINAL", "outline") },
        { key: "outcome", label: "Resultado", render: (r) => statusChip(r.outcome) }, { key: "message", label: "Mensaje" },
      ], j.jobs, { empty: "Sin trabajos registrados." }), { iconName: "clock" }));
    } catch (e) { mount(jobsSlot, errorAlert(e)); }
  }

  printerSel.addEventListener("change", checkPrinter);
  templateSel.addEventListener("change", renderForm);
  mount(root, pageHead("Label Control", "Impresión controlada separada de las transacciones de producción. Compatible conceptualmente con Zebra (ZPL), CAB y BarTender."),
    h("div", { class: "stack" },
      h("div", { class: "grid g-3" },
        card("Impresora autorizada", h("div", { class: "stack", style: { gap: "10px" } }, printerSel, printerState,
          h("button", { class: "btn sm", onclick: checkPrinter }, icon("refresh", "sm"), "Consultar estado")), { iconName: "printer" }),
        h("div", { class: "span-2" }, card("Plantilla y datos", h("div", { class: "stack", style: { gap: "12px" } }, templateSel, formSlot), { iconName: "file" }))),
      previewSlot, jobsSlot));
  checkPrinter(); renderForm(); loadJobs();
}
