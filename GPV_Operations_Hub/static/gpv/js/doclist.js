/* Batch selection in the document list (selection order is preserved for merges). */
document.addEventListener("DOMContentLoaded", () => {
  const order = [];
  const boxes = document.querySelectorAll("[data-doc]");
  boxes.forEach((b) => b.addEventListener("change", () => {
    const i = order.indexOf(b.value);
    if (b.checked && i < 0) order.push(b.value);
    if (!b.checked && i >= 0) order.splice(i, 1);
  }));
  const all = document.querySelector("[data-checkall]");
  if (all) all.addEventListener("change", () => boxes.forEach((b) => { if (b.checked !== all.checked) { b.checked = all.checked; b.dispatchEvent(new Event("change")); } }));
  const form = document.querySelector("[data-batch-form]");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    form.querySelectorAll("input[name=docs]").forEach((x) => x.remove());
    if (!order.length) { e.preventDefault(); e.stopImmediatePropagation(); GPV.toast("Seleccione documentos en la tabla.", "error"); return; }
    order.forEach((id) => { const h = document.createElement("input"); h.type = "hidden"; h.name = "docs"; h.value = id; form.appendChild(h); });
  }, true);
  const zip = form.querySelector("[data-zip]");
  zip.addEventListener("click", () => {
    if (!order.length) return GPV.toast("Seleccione documentos.", "error");
    location.href = "/documentos/zip/?" + order.map((id) => "id=" + id).join("&");
  });
});
