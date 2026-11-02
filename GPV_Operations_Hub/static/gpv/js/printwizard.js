/* Print wizard: preview with real data, confirmation of total labels, double-submit protection. */
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-print-form]");
  if (!form) return;
  const out = form.querySelector("[data-print-preview-out]");
  const box = form.querySelector("[data-print-box]");
  const all = form.querySelector("[data-checkall]");
  if (all) all.addEventListener("change", () => form.querySelectorAll("[name=rec]").forEach((c) => { c.checked = all.checked; }));
  let busy = false;
  const preview = async () => {
    const r = await GPV.api(GPV.ds(form).previewUrl, { method: "POST", body: new FormData(form) });
    const d = r.data;
    out.innerHTML = '<div class="card"><p><strong>Total: ' + d.total + " etiquetas</strong> (" + d.records + " registros × " + d.copies + " copias) · destino: " + GPV.esc(d.printer) +
      "</p>" + (d.warnings.length ? '<div class="alert alert-warn">' + d.warnings.map(GPV.esc).join("<br>") + "</div>" : "") +
      '<div style="max-width:420px;border:1px solid var(--border)">' + d.svg + '</div><p class="muted small">Primera etiqueta con datos reales (las líneas rojas indican contenido desbordado).</p></div>';
    return d;
  };
  form.querySelector("[data-print-preview]").addEventListener("click", () => preview().catch((e) => GPV.toast(e.message, "error")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const btn = form.querySelector("[type=submit]");
    busy = true;
    GPV.setLoading(btn, true);
    try {
      const d = await preview();
      if (d.warnings.length && !confirm("Hay advertencias en la etiqueta:\n- " + d.warnings.join("\n- ") + "\n\n¿Continuar de todos modos?")) return;
      if (!confirm("Se generarán " + d.total + " etiquetas (" + d.records + " registros × " + d.copies + " copias) hacia: " + d.printer + ".\n¿Confirmar impresión?")) return;
      form.querySelector("[name=confirm_total]").value = d.total;
      const fd = new FormData(form);
      fd.append("idempotency_key", crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
      const r = await GPV.api(form.action, { method: "POST", body: fd });
      box.hidden = false;
      box.innerHTML = "";
      GPV.renderResult(box, r.data);
      GPV.toast(r.data.summary, "ok");
    } catch (err) {
      box.hidden = false;
      box.innerHTML = '<div class="alert alert-err">' + GPV.esc(err.message) + "</div>";
    } finally {
      busy = false;
      GPV.setLoading(btn, false);
    }
  });
});
