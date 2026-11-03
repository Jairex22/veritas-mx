/* FactoryLogix query explorer: validated server-side queries, cancellable, results with provenance. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const form = document.querySelector("[data-flx-query]");
  if (!form) return;
  const out = document.querySelector("[data-flx-out]");
  const cancel = form.querySelector("[data-flx-cancel]");
  let ctrl = null;
  const render = (d) => {
    const cols = [...new Set(d.rows.flatMap((r) => Object.keys(r)))];
    const cell = (v) => (v === null || v === undefined ? '<span class="muted">—</span>' : GPV.esc(typeof v === "object" ? JSON.stringify(v) : v));
    out.innerHTML = '<p class="small">' + d.rows.length + " filas" + (d.count !== null && d.count !== undefined ? " de " + d.count : "") +
      (d.truncated ? " · <strong>resultado truncado</strong> (límite de filas/páginas)" : "") + " · " + d.pages + " página(s) · " + d.latency_ms + " ms</p>" +
      '<p class="small muted">Fuente: ' + GPV.esc(d.source.origin) + " · " + GPV.esc(d.source.entity_set) + " · opciones " + GPV.esc(d.source.options.join(", ")) +
      " · consultado " + GPV.esc(new Date(d.source.fetched_at).toLocaleString()) + "</p>" +
      (d.rows.length ? '<div class="table-wrap" style="max-height:60vh"><table class="data"><thead><tr>' + cols.map((c) => "<th>" + GPV.esc(c) + "</th>").join("") +
        "</tr></thead><tbody>" + d.rows.map((r) => "<tr>" + cols.map((c) => "<td>" + cell(r[c]) + "</td>").join("") + "</tr>").join("") + "</tbody></table></div>"
        : '<div class="alert alert-info">Sin datos para estos criterios.</div>');
  };
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    cancel.hidden = false;
    out.innerHTML = '<p class="muted">Consultando FactoryLogix…</p>';
    try {
      const resp = await fetch(form.getAttribute("action"), { method: "POST", body: new FormData(form), signal: ctrl.signal, credentials: "same-origin",
        headers: { "X-CSRFToken": GPV.csrf(), Accept: "application/json" } });
      const d = await resp.json();
      if (!resp.ok || !d.ok) throw new Error(d.error || "Error " + resp.status);
      render(d.data);
    } catch (err) {
      out.innerHTML = err.name === "AbortError" ? '<div class="alert alert-info">Consulta cancelada en el navegador.</div>' : '<div class="alert alert-err">' + GPV.esc(err.message) + "</div>";
    } finally {
      cancel.hidden = true;
      ctrl = null;
    }
  });
  cancel.addEventListener("click", () => ctrl && ctrl.abort());
  form.querySelector("[data-flx-csv]").addEventListener("click", () => {
    const f = document.createElement("form");
    f.method = "post"; f.action = form.getAttribute("action"); f.hidden = true;
    new FormData(form).forEach((v, k) => { const i = document.createElement("input"); i.name = k; i.value = v; f.appendChild(i); });
    const fmt = document.createElement("input"); fmt.name = "format"; fmt.value = "csv"; f.appendChild(fmt);
    document.body.appendChild(f); f.submit(); f.remove();
  });
});
