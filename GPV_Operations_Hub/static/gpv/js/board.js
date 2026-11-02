/* Basic dashboard builder: dataset (production records) x dimension x measure x aggregation x chart. */
(function () {
  "use strict";
  const root = document.querySelector("[data-board]");
  if (!root) return;
  const J = (id) => JSON.parse(document.getElementById(id).textContent);
  const config = J("board-config") || { widgets: [] };
  const DIMS = J("board-dims"), MEAS = J("board-measures"), AGGS = J("board-aggs");
  const canEdit = root.dataset.canEdit === "1";
  const wrap = root.querySelector("[data-widgets]");
  let version = parseInt(root.dataset.version, 10);
  const filters = Object.fromEntries(new URLSearchParams(location.search));
  config.widgets = config.widgets || [];

  const opt = (obj, cur) => Object.keys(obj).map((k) => '<option value="' + k + '"' + (k === cur ? " selected" : "") + ">" + GPV.esc(obj[k]) + "</option>").join("");

  function editor(w, i) {
    return '<details><summary class="small">Configurar</summary><div class="form-grid">' +
      '<label>Título<input data-k="title" value="' + GPV.esc(w.title || "") + '"></label>' +
      '<label>Dimensión<select data-k="dimension">' + opt(DIMS, w.dimension) + "</select></label>" +
      '<label>Medida<select data-k="measure">' + opt(MEAS, w.measure) + "</select></label>" +
      '<label>Agregación<select data-k="agg">' + opt(AGGS, w.agg) + "</select></label>" +
      '<label>Gráfico<select data-k="chart">' + opt({ bar: "Barras", line: "Tendencia", table: "Tabla" }, w.chart) + "</select></label>" +
      '<label>Orden<select data-k="order">' + opt({ key: "Por categoría", value_desc: "Mayor a menor" }, w.order) + "</select></label>" +
      '<label>Límite<input type="number" min="1" max="200" data-k="limit" value="' + (w.limit || 30) + '"></label>' +
      '<label>Ancho<select data-k="width">' + opt({ 1: "Media", 2: "Completa" }, String(w.width || 1)) + "</select></label>" +
      '<label class="full">Campo calculado (opcional; operaciones + − × ÷ sobre ' + Object.keys(MEAS).join(", ") + ')<input data-k="calc" placeholder="qty_scrap / (qty_good + qty_scrap) * 100" value="' + GPV.esc(w.calc || "") + '"></label>' +
      '<label class="check"><input type="checkbox" data-k="join_plan"' + (w.join_plan ? " checked" : "") + "> Unir con meta del plan (por orden; se valida cardinalidad)</label>" +
      '</div><p class="actions"><button type="button" class="btn btn-sm" data-apply="' + i + '">Aplicar</button>' +
      '<button type="button" class="btn btn-sm" data-dup="' + i + '">Duplicar</button><button type="button" class="btn btn-sm" data-up="' + i + '">↑</button>' +
      '<button type="button" class="btn btn-sm" data-down="' + i + '">↓</button><button type="button" class="btn btn-sm btn-danger" data-del="' + i + '">Eliminar</button></p></details>';
  }

  function render() {
    wrap.innerHTML = config.widgets.map((w, i) => '<section class="card" style="' + (String(w.width) === "2" ? "grid-column:1/-1" : "") + '" data-w="' + i + '"><h2>' +
      GPV.esc(w.title || "Widget") + '</h2><div class="chart" data-c></div><p class="muted small" data-info></p>' + (canEdit ? editor(w, i) : "") + "</section>").join("") ||
      '<p class="muted">Sin widgets. ' + (canEdit ? "Use «Agregar widget»." : "") + "</p>";
    config.widgets.forEach((w, i) => draw(i));
    if (!canEdit) return;
    const read = (i) => {
      const sec = wrap.querySelector('[data-w="' + i + '"]');
      sec.querySelectorAll("[data-k]").forEach((inp) => {
        const k = inp.dataset.k;
        config.widgets[i][k] = inp.type === "checkbox" ? inp.checked : inp.value;
      });
      GPV.dirty = true;
    };
    wrap.querySelectorAll("[data-apply]").forEach((b) => b.addEventListener("click", () => { read(+b.dataset.apply); render(); }));
    wrap.querySelectorAll("[data-dup]").forEach((b) => b.addEventListener("click", () => { read(+b.dataset.dup); config.widgets.splice(+b.dataset.dup + 1, 0, JSON.parse(JSON.stringify(config.widgets[+b.dataset.dup]))); GPV.dirty = true; render(); }));
    wrap.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => { if (confirm("¿Eliminar widget?")) { config.widgets.splice(+b.dataset.del, 1); GPV.dirty = true; render(); } }));
    wrap.querySelectorAll("[data-up]").forEach((b) => b.addEventListener("click", () => { const i = +b.dataset.up; if (i > 0) { [config.widgets[i - 1], config.widgets[i]] = [config.widgets[i], config.widgets[i - 1]]; GPV.dirty = true; render(); } }));
    wrap.querySelectorAll("[data-down]").forEach((b) => b.addEventListener("click", () => { const i = +b.dataset.down; if (i < config.widgets.length - 1) { [config.widgets[i + 1], config.widgets[i]] = [config.widgets[i], config.widgets[i + 1]]; GPV.dirty = true; render(); } }));
  }

  async function draw(i) {
    const w = config.widgets[i];
    const sec = wrap.querySelector('[data-w="' + i + '"]');
    const c = sec.querySelector("[data-c]"), info = sec.querySelector("[data-info]");
    c.innerHTML = '<p class="muted">Cargando…</p>';
    try {
      const r = await GPV.api("/analitica/api/widget/", { method: "POST", body: { widget: w, filters } });
      const d = r.data;
      info.textContent = d.agg + " de " + d.measure + " por " + d.dimension + (d.calc ? " · calculado: " + d.calc : "") + (d.join ? " · " + d.join.message : "");
      if (w.chart === "table") {
        c.innerHTML = '<div class="table-wrap"><table class="data"><thead><tr><th>' + GPV.esc(d.dimension) + '</th><th class="num">Valor</th>' + (w.join_plan ? '<th class="num">Meta plan</th>' : "") + "</tr></thead><tbody>" +
          d.points.map((p) => "<tr><td>" + GPV.esc(p.key) + '</td><td class="num">' + (p.value == null ? "—" : p.value.toLocaleString("es-MX")) + "</td>" + (w.join_plan ? '<td class="num">' + (p.planned == null ? "—" : p.planned) + "</td>" : "") + "</tr>").join("") + "</tbody></table></div>";
      } else if (w.join_plan && d.join && d.join.ok && w.dimension === "work_order") {
        GPVChart(c, { type: "grouped", series: ["Meta", d.measure], data: d.points.map((p) => ({ key: p.key, value: p.value, value2: p.planned })) });
      } else GPVChart(c, { type: w.chart === "line" ? "line" : "bar", data: d.points });
    } catch (e) { c.innerHTML = '<div class="alert alert-err">' + GPV.esc(e.message) + "</div>"; }
  }

  root.querySelector("[data-refresh]").addEventListener("click", render);
  if (canEdit) {
    root.querySelector("[data-add]").addEventListener("click", () => {
      config.widgets.push({ title: "Nuevo widget", dimension: "line", measure: "qty_good", agg: "sum", chart: "bar", limit: 30, width: 1 });
      GPV.dirty = true;
      render();
    });
    const save = root.querySelector("[data-save]");
    save.addEventListener("click", async () => {
      GPV.setLoading(save, true);
      try {
        const body = { version, widgets: config.widgets, name: root.querySelector("[data-f-name]").value,
          shared_all: root.querySelector("[data-f-all]").checked,
          shared_roles: [...root.querySelectorAll("[data-f-role]:checked")].map((x) => x.value),
          shared_areas: [...root.querySelectorAll("[data-f-area]:checked")].map((x) => x.value) };
        const r = await GPV.api("/analitica/api/tableros/" + root.dataset.id + "/guardar/", { method: "POST", body });
        version = r.data.version;
        GPV.dirty = false;
        root.querySelector("[data-board-name]").textContent = body.name;
        GPV.toast("Dashboard guardado (versión " + version + ")", "ok");
      } catch (e) { GPV.toast(e.message, "error"); } finally { GPV.setLoading(save, false); }
    });
  }
  render();
})();
