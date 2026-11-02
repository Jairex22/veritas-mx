/* Label designer: millimetre canvas, rulers, grid snap, zoom, multi-select, align/distribute, layers,
   lock, undo/redo and duplication. The visual is rendered by the server (same engine as PDF/ZPL). */
(function () {
  "use strict";
  const root = document.querySelector("[data-designer]");
  if (!root) return;
  const boot = JSON.parse(document.getElementById("designer-boot").textContent);
  let t = boot.draft, revision = boot.revision;
  t.elements = t.elements || [];
  t.prompts = t.prompts || [];
  const paper = root.querySelector("[data-paper]"), stage = root.querySelector("[data-stage]");
  const props = root.querySelector("[data-props]"), layers = root.querySelector("[data-layers]");
  const warnBox = root.querySelector("[data-warnings]"), status = root.querySelector("[data-dstatus]");
  const zoomIn = root.querySelector("[data-zoom]"), snapIn = root.querySelector("[data-snap]");
  let zoom = 5, sel = new Set(), overflow = new Set(), undo = [], redo = [], timer = null, seq = Date.now() % 100000;
  const snap = (v) => (snapIn.checked ? Math.round(v * 2) / 2 : Math.round(v * 10) / 10);
  const byId = (id) => t.elements.find((e) => e.id === id);
  const selected = () => t.elements.filter((e) => sel.has(e.id));
  const push = () => { undo.push(JSON.stringify(t)); if (undo.length > 80) undo.shift(); redo = []; GPV.dirty = true; status.textContent = "Cambios sin guardar"; };
  const boxWH = (e) => (e.rot === 90 || e.rot === 270 ? [e.h, e.w] : [e.w, e.h]);

  const DEFAULTS = {
    text: { w: 40, h: 6, content: "Texto", font_size: 10, align: "left" },
    field: { type: "text", w: 45, h: 6, content: "Orden: {work_order}", font_size: 10, bold: true, autofit: true },
    code128: { w: 60, h: 14, content: "{work_order}", module_mm: 0.33, show_text: true },
    qr: { w: 18, h: 18, content: "{part_number};{lot};{serial}", ec: "M" },
    line: { w: 40, h: 0, stroke_mm: 0.3 },
    rect: { w: 30, h: 15, stroke_mm: 0.3, fill: false },
  };

  function add(kind, extra) {
    push();
    const d = Object.assign({}, DEFAULTS[kind] || {}, extra || {});
    const e = Object.assign({ id: "e" + seq++, type: d.type || kind, name: (d.type || kind) + " " + (t.elements.length + 1), x: 3, y: 3, rot: 0, z: t.elements.length }, d);
    delete e.type_;
    t.elements.push(e);
    sel = new Set([e.id]);
    refresh();
  }

  function drawRulers() {
    const rh = root.querySelector("[data-ruler-h]"), rv = root.querySelector("[data-ruler-v]");
    rh.style.width = t.width_mm * zoom + "px";
    rv.style.height = t.height_mm * zoom + "px";
    let h = "", v = "";
    const step = zoom >= 6 ? 5 : 10;
    for (let mm = 0; mm <= t.width_mm; mm += step) h += '<span style="position:absolute;left:' + mm * zoom + 'px;top:2px">' + mm + "</span>";
    for (let mm = 0; mm <= t.height_mm; mm += step) v += '<span style="position:absolute;top:' + mm * zoom + 'px;left:2px">' + mm + "</span>";
    rh.innerHTML = h; rv.innerHTML = v;
  }

  function overlay() {
    paper.style.width = t.width_mm * zoom + "px";
    paper.style.height = t.height_mm * zoom + "px";
    paper.querySelectorAll(".lel,.label-grid").forEach((n) => n.remove());
    if (snapIn.checked && zoom >= 4) {
      const g = document.createElement("div");
      g.className = "label-grid";
      g.style.backgroundImage = "linear-gradient(to right, rgba(0,0,0,.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(0,0,0,.05) 1px, transparent 1px)";
      g.style.backgroundSize = zoom + "px " + zoom + "px";
      paper.appendChild(g);
    }
    const m = (t.margin_mm || 0) * zoom;
    if (m) { const mg = document.createElement("div"); mg.className = "label-grid"; mg.style.cssText += ";inset:" + m + "px;border:1px dashed rgba(31,95,139,.35)"; paper.appendChild(mg); }
    t.elements.slice().sort((a, b) => (a.z || 0) - (b.z || 0)).forEach((e) => {
      if (e.hidden) return;
      const [w, h] = boxWH(e);
      const d = document.createElement("div");
      d.className = "lel" + (sel.has(e.id) ? " sel" : "") + (e.locked ? " locked" : "") + (overflow.has(e.id) ? " overflow" : "");
      d.dataset.id = e.id;
      d.title = e.name + (e.locked ? " (bloqueado)" : "");
      Object.assign(d.style, { left: e.x * zoom + "px", top: e.y * zoom + "px", width: Math.max(4, w * zoom) + "px", height: Math.max(4, h * zoom) + "px" });
      if (sel.has(e.id) && !e.locked && sel.size === 1) { const hd = document.createElement("div"); hd.className = "handle"; hd.dataset.handle = "1"; d.appendChild(hd); }
      paper.appendChild(d);
    });
  }

  function renderLayers() {
    layers.innerHTML = t.elements.slice().sort((a, b) => (b.z || 0) - (a.z || 0)).map((e) =>
      '<li data-layer="' + e.id + '" class="' + (sel.has(e.id) ? "sel" : "") + '"><span>' + GPV.esc(e.name) + "</span><span>" + (e.locked ? "🔒" : "") +
      '<button type="button" class="link-btn" data-vis="' + e.id + '" title="Mostrar/ocultar">' + (e.hidden ? "◌" : "●") + "</button></span></li>").join("") || '<li class="muted">Sin elementos</li>';
  }

  const field = (label, key, e, type, opts) => {
    const v = e[key] == null ? "" : e[key];
    if (type === "select") return '<label>' + label + '<select data-p="' + key + '">' + opts.map((o) => '<option value="' + o[0] + '"' + (String(v) === String(o[0]) ? " selected" : "") + ">" + o[1] + "</option>").join("") + "</select></label>";
    if (type === "check") return '<label class="check"><input type="checkbox" data-p="' + key + '"' + (v ? " checked" : "") + "> " + label + "</label>";
    if (type === "area") return "<label>" + label + '<textarea rows="2" data-p="' + key + '">' + GPV.esc(v) + "</textarea></label>";
    return "<label>" + label + '<input data-p="' + key + '" ' + (type === "number" ? 'type="number" step="0.1"' : "") + ' value="' + GPV.esc(v) + '"></label>';
  };
  function renderProps() {
    const s = selected();
    if (s.length !== 1) { props.innerHTML = s.length ? "<p>" + s.length + " elementos seleccionados (use alinear/distribuir).</p>" : '<p class="muted">Seleccione un elemento.</p>'; return; }
    const e = s[0];
    let html = field("Nombre", "name", e) + '<div class="form-grid">' + field("X mm", "x", e, "number") + field("Y mm", "y", e, "number") +
      field("Ancho mm", "w", e, "number") + field("Alto mm", "h", e, "number") + "</div>" +
      field("Rotación", "rot", e, "select", [[0, "0°"], [90, "90°"], [180, "180°"], [270, "270°"]]);
    if (e.type === "text") html += field("Contenido (fijo o {campo})", "content", e, "area") + '<div class="form-grid">' + field("Tamaño pt", "font_size", e, "number") +
      field("Alineación", "align", e, "select", [["left", "Izquierda"], ["center", "Centro"], ["right", "Derecha"]]) + "</div>" +
      field("Negrita", "bold", e, "check") + field("Ajuste automático (reduce tamaño)", "autofit", e, "check") + field("Varias líneas", "wrap", e, "check");
    if (e.type === "code128") html += field("Contenido", "content", e) + field("Módulo X (mm)", "module_mm", e, "number") + field("Mostrar texto", "show_text", e, "check");
    if (e.type === "qr") html += field("Contenido", "content", e, "area") + field("Corrección de error", "ec", e, "select", [["L", "L 7%"], ["M", "M 15%"], ["Q", "Q 25%"], ["H", "H 30%"]]);
    if (e.type === "line" || e.type === "rect") html += field("Grosor mm", "stroke_mm", e, "number") + (e.type === "rect" ? field("Relleno", "fill", e, "check") : "");
    html += field("Bloqueado", "locked", e, "check");
    props.innerHTML = html;
    props.querySelectorAll("[data-p]").forEach((inp) => inp.addEventListener("change", () => {
      push();
      const k = inp.dataset.p;
      let v = inp.type === "checkbox" ? inp.checked : inp.value;
      if (["x", "y", "w", "h", "font_size", "module_mm", "stroke_mm"].includes(k)) v = parseFloat(v) || 0;
      if (k === "rot") v = parseInt(v, 10);
      e[k] = v;
      refresh();
    }));
  }

  function bindTemplateInputs() {
    root.querySelectorAll("[data-t]").forEach((inp) => {
      const k = inp.dataset.t;
      inp.value = t[k] == null ? "" : t[k];
      inp.addEventListener("change", () => {
        push();
        t[k] = ["width_mm", "height_mm", "margin_mm"].includes(k) ? parseFloat(inp.value) || 0 : k === "dpi" ? parseInt(inp.value, 10) : inp.value;
        refresh();
      });
    });
    const pr = root.querySelector("[data-prompts]");
    pr.value = (t.prompts || []).map((p) => p.name + ":" + (p.label || "")).join("\n");
    pr.addEventListener("change", () => {
      push();
      t.prompts = pr.value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [n, ...rest] = l.split(":"); return { name: n.trim(), label: rest.join(":").trim() || n.trim() }; });
      refresh();
    });
  }

  function refresh() { overlay(); renderLayers(); renderProps(); drawRulers(); schedulePreview(); }

  function sampleData() {
    try { return JSON.parse(root.querySelector("[data-sample]").value || "{}"); } catch (e) { return {}; }
  }
  function schedulePreview() { clearTimeout(timer); timer = setTimeout(preview, 300); }
  async function preview() {
    try {
      const prompts = {};
      (t.prompts || []).forEach((p) => { prompts[p.name] = "[" + (p.label || p.name) + "]"; });
      const r = await GPV.api("/etiquetas/api/" + boot.id + "/vista-previa/", { method: "POST", body: { draft: t, record: sampleData(), prompts } });
      let svg = paper.querySelector("svg.render");
      const holder = document.createElement("div");
      holder.innerHTML = r.data.svg;
      const ns = holder.firstElementChild;
      ns.classList.add("render");
      if (svg) svg.replaceWith(ns); else paper.prepend(ns);
      overflow = new Set(r.data.overflow);
      warnBox.innerHTML = r.data.warnings.length ? '<div class="alert alert-warn small">' + r.data.warnings.map(GPV.esc).join("<br>") + "</div>" : "";
      overlay();
    } catch (e) { warnBox.innerHTML = '<div class="alert alert-err">' + GPV.esc(e.message) + "</div>"; }
  }

  // ---- interaction
  let drag = null;
  paper.addEventListener("mousedown", (ev) => {
    const el = ev.target.closest(".lel");
    if (!el) { sel.clear(); refresh(); return; }
    const id = el.dataset.id;
    if (ev.shiftKey) { if (sel.has(id)) sel.delete(id); else sel.add(id); } else if (!sel.has(id)) sel = new Set([id]);
    const items = selected().filter((e) => !e.locked);
    if (!items.length) { refresh(); return; }
    push();
    drag = { x: ev.clientX, y: ev.clientY, resize: !!ev.target.dataset.handle, start: items.map((e) => ({ e, x: e.x, y: e.y, w: e.w, h: e.h })) };
    ev.preventDefault();
    overlay(); renderLayers(); renderProps();
  });
  document.addEventListener("mousemove", (ev) => {
    if (!drag) return;
    const dx = (ev.clientX - drag.x) / zoom, dy = (ev.clientY - drag.y) / zoom;
    drag.start.forEach((s) => {
      if (drag.resize) {
        const rotated = s.e.rot === 90 || s.e.rot === 270;
        if (rotated) { s.e.h = Math.max(1, snap(s.h + dx)); s.e.w = Math.max(1, snap(s.w + dy)); }
        else { s.e.w = Math.max(1, snap(s.w + dx)); s.e.h = Math.max(s.e.type === "line" ? 0 : 1, snap(s.h + dy)); }
      } else { s.e.x = snap(s.x + dx); s.e.y = snap(s.y + dy); }
    });
    overlay();
  });
  document.addEventListener("mouseup", () => { if (drag) { drag = null; refresh(); } });
  document.addEventListener("keydown", (ev) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    const s = selected().filter((e) => !e.locked);
    const step = ev.shiftKey ? 5 : 0.5;
    const mv = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[ev.key];
    if (mv && s.length) { ev.preventDefault(); push(); s.forEach((e) => { e.x = Math.round((e.x + mv[0]) * 10) / 10; e.y = Math.round((e.y + mv[1]) * 10) / 10; }); refresh(); }
    if ((ev.key === "Delete" || ev.key === "Backspace") && s.length) { ev.preventDefault(); act.del(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); act.undo(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "y") { ev.preventDefault(); act.redo(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "d") { ev.preventDefault(); act.dup(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); act.save(); }
  });
  layers.addEventListener("click", (ev) => {
    const vis = ev.target.closest("[data-vis]");
    if (vis) { push(); const e = byId(vis.dataset.vis); e.hidden = !e.hidden; refresh(); return; }
    const li = ev.target.closest("[data-layer]");
    if (li) { sel = ev.shiftKey ? new Set([...sel, li.dataset.layer]) : new Set([li.dataset.layer]); refresh(); }
  });
  zoomIn.addEventListener("input", () => { zoom = parseFloat(zoomIn.value); overlay(); drawRulers(); });
  snapIn.addEventListener("change", overlay);
  root.querySelector("[data-sample]").addEventListener("change", schedulePreview);

  const act = {
    undo() { if (!undo.length) return GPV.toast("Nada que deshacer."); redo.push(JSON.stringify(t)); t = JSON.parse(undo.pop()); bindTemplateInputs(); refresh(); },
    redo() { if (!redo.length) return GPV.toast("Nada que rehacer."); undo.push(JSON.stringify(t)); t = JSON.parse(redo.pop()); bindTemplateInputs(); refresh(); },
    dup() { const s = selected(); if (!s.length) return; push(); sel = new Set(); s.forEach((e) => { const c = JSON.parse(JSON.stringify(e)); c.id = "e" + seq++; c.name = e.name + " copia"; c.x += 2; c.y += 2; c.locked = false; c.z = t.elements.length; t.elements.push(c); sel.add(c.id); }); refresh(); },
    del() { const s = selected().filter((e) => !e.locked); if (!s.length) return GPV.toast("Nada seleccionado o elementos bloqueados."); push(); t.elements = t.elements.filter((e) => !s.includes(e)); sel.clear(); refresh(); },
    lock() { const s = selected(); if (!s.length) return; push(); const v = !s.every((e) => e.locked); s.forEach((e) => { e.locked = v; }); refresh(); },
    up() { const s = selected(); if (!s.length) return; push(); s.forEach((e) => { e.z = (e.z || 0) + 1.5; }); normZ(); refresh(); },
    down() { const s = selected(); if (!s.length) return; push(); s.forEach((e) => { e.z = (e.z || 0) - 1.5; }); normZ(); refresh(); },
    async save() {
      const btn = root.parentElement.querySelector('[data-d="save"]');
      if (btn.disabled) return;
      GPV.setLoading(btn, true);
      try {
        const r = await GPV.api("/etiquetas/api/" + boot.id + "/borrador/", { method: "POST", body: { draft: t, revision } });
        revision = r.data.revision; GPV.dirty = false; status.textContent = "Borrador guardado (rev. " + revision + ")";
        GPV.toast("Borrador guardado", "ok");
      } catch (e) { GPV.toast(e.message, "error"); } finally { GPV.setLoading(btn, false); }
    },
  };
  function normZ() { t.elements.sort((a, b) => (a.z || 0) - (b.z || 0)).forEach((e, i) => { e.z = i; }); }
  root.parentElement.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => act[b.dataset.d] && act[b.dataset.d]()));
  root.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => add(b.dataset.add)));
  root.querySelector("[data-add-image]").addEventListener("change", (ev) => {
    const f = ev.target.files[0]; if (!f) return;
    if (f.size > 290000) return GPV.toast("La imagen debe pesar menos de ~290 KB.", "error");
    const rd = new FileReader();
    rd.onload = () => add("image", { type: "image", w: 20, h: 20, src: rd.result, name: "Imagen " + f.name });
    rd.readAsDataURL(f);
  });
  root.parentElement.querySelectorAll("[data-align]").forEach((b) => b.addEventListener("click", () => {
    const s = selected().filter((e) => !e.locked);
    if (!s.length) return GPV.toast("Seleccione elementos.");
    push();
    const W = t.width_mm, H = t.height_mm, k = b.dataset.align;
    const ref = s.length > 1 ? { x0: Math.min(...s.map((e) => e.x)), y0: Math.min(...s.map((e) => e.y)), x1: Math.max(...s.map((e) => e.x + boxWH(e)[0])), y1: Math.max(...s.map((e) => e.y + boxWH(e)[1])) } : { x0: 0, y0: 0, x1: W, y1: H };
    if (k.startsWith("dist")) {
      if (s.length < 3) { GPV.toast("Distribuir requiere 3 o más elementos."); return; }
      const hz = k === "dist-h", sorted = s.slice().sort((a, b2) => (hz ? a.x - b2.x : a.y - b2.y));
      const total = sorted.reduce((acc, e) => acc + boxWH(e)[hz ? 0 : 1], 0);
      const gap = ((hz ? ref.x1 - ref.x0 : ref.y1 - ref.y0) - total) / (sorted.length - 1);
      let pos = hz ? ref.x0 : ref.y0;
      sorted.forEach((e) => { if (hz) e.x = Math.round(pos * 10) / 10; else e.y = Math.round(pos * 10) / 10; pos += boxWH(e)[hz ? 0 : 1] + gap; });
    } else s.forEach((e) => {
      const [w, h] = boxWH(e);
      if (k === "left") e.x = ref.x0; if (k === "right") e.x = ref.x1 - w; if (k === "hcenter") e.x = Math.round(((ref.x0 + ref.x1) / 2 - w / 2) * 10) / 10;
      if (k === "top") e.y = ref.y0; if (k === "bottom") e.y = ref.y1 - h; if (k === "vcenter") e.y = Math.round(((ref.y0 + ref.y1) / 2 - h / 2) * 10) / 10;
    });
    refresh();
  }));
  const exp = root.parentElement.querySelector("[data-d-export]");
  if (exp) exp.addEventListener("click", (ev) => { if (GPV.dirty) { ev.preventDefault(); GPV.toast("Guarde el borrador para ver el PDF con los últimos cambios.", "error"); } });
  zoom = Math.max(2, Math.min(12, Math.floor((stage.clientWidth - 80) / Math.max(10, t.width_mm))));
  zoomIn.value = zoom;
  bindTemplateInputs();
  refresh();
})();
