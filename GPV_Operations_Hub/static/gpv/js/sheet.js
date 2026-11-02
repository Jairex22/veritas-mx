/* GPV spreadsheet grid. Virtualized rendering; formula results always come from the server engine. */
(function () {
  "use strict";
  const app = document.querySelector("[data-sheet-app]");
  if (!app) return;
  const boot = JSON.parse(document.getElementById("sheet-boot").textContent);
  const RH = 24, HH = 24, RW = 48, DEFW = 100;
  const api = (path, body) => GPV.api("/hojas/api/" + boot.id + "/" + path + "/", { method: "POST", body });
  const $ = (s) => app.querySelector(s);
  const vp = $("[data-viewport]"), canvas = $("[data-canvas]"), fx = $("[data-fx]"), addrBox = $("[data-addr]");
  const statusEl = $("[data-status]"), selInfo = $("[data-selinfo]"), verInfo = $("[data-verinfo]");
  let data = boot.data, version = boot.version, cur = 0, values = {}, dirty = false;
  let cursor = { r: 0, c: 0 }, sel = { r1: 0, c1: 0, r2: 0, c2: 0 }, anchor = null;
  const undo = [], redo = [];
  const filters = {}; // sheetName -> {col: text}
  let clip = null, editor = null, recalcTimer = null, busy = false;

  // ------------------------------------------------------------ helpers
  const colName = (i) => { let s = ""; i += 1; while (i) { const m = (i - 1) % 26; s = String.fromCharCode(65 + m) + s; i = Math.floor((i - 1) / 26); } return s; };
  const colIndex = (s) => { let n = 0; for (const ch of s) n = n * 26 + ch.charCodeAt(0) - 64; return n - 1; };
  const addr = (r, c) => colName(c) + (r + 1);
  const parseAddr = (a) => { const m = /^([A-Z]+)(\d+)$/.exec(a); return m ? { r: +m[2] - 1, c: colIndex(m[1]) } : null; };
  const sheet = () => data.sheets[cur];
  const cellOf = (r, c) => sheet().cells[addr(r, c)];
  const isFormula = (cell) => cell && typeof cell.v === "string" && cell.v.startsWith("=") && cell.fmt !== "text";
  const colW = (c) => ((sheet().cols || {})[colName(c)] || {}).w || DEFW;
  const setStatus = (t) => { statusEl.textContent = t; };
  const markDirty = () => { dirty = true; GPV.dirty = true; setStatus("Cambios sin guardar"); };
  const canEdit = boot.can_edit;
  verInfo.textContent = "Versión " + version + " · guardada por " + (boot.updated_by || "—") + " " + boot.updated;

  function coerce(cell) {
    if (!cell || cell.v == null) return null;
    const s = String(cell.v);
    if (cell.fmt === "text") return s;
    const t = s.trim();
    if (t === "") return null;
    if (/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/.test(t)) return parseFloat(t);
    if (/^[+-]?(\d+(\.\d*)?|\.\d+)%$/.test(t)) return parseFloat(t) / 100;
    if (/^(TRUE|VERDADERO)$/i.test(t)) return true;
    if (/^(FALSE|FALSO)$/i.test(t)) return false;
    return s;
  }
  function value(r, c) {
    const cell = cellOf(r, c);
    if (!cell) return null;
    if (isFormula(cell)) {
      const v = (values[sheet().name] || {})[addr(r, c)];
      if (!v) return { pending: true };
      return v.e ? { error: v.e } : v.v;
    }
    return coerce(cell);
  }
  function display(r, c) {
    const v = value(r, c), cell = cellOf(r, c) || {};
    if (v == null) return { text: "", cls: "" };
    if (typeof v === "object") return v.error ? { text: v.error, cls: "err" } : { text: "…", cls: "" };
    if (typeof v === "number") {
      let text;
      if (cell.fmt === "percent") text = (v * 100).toFixed(cell.dec != null ? cell.dec : 0) + "%";
      else if (cell.dec != null) text = v.toFixed(cell.dec);
      else text = Math.abs(v) >= 1e15 || (Math.abs(v) < 1e-6 && v !== 0) ? v.toExponential(6) : String(Math.round(v * 1e10) / 1e10);
      return { text, cls: "num", num: v };
    }
    if (typeof v === "boolean") return { text: v ? "VERDADERO" : "FALSO", cls: "" };
    return { text: String(v), cls: "" };
  }

  // ------------------------------------------------------------ visibility (filters & groups)
  let visRows = [];
  function computeVisible() {
    const sh = sheet(), f = filters[sh.name] || {}, hidden = new Set();
    (sh.groups || []).forEach((g) => { if (g.collapsed) for (let r = g.start + 1; r <= g.end; r++) hidden.add(r); });
    const header = (sh.freeze && sh.freeze.r) || 1;
    const fcols = Object.keys(f);
    visRows = [];
    for (let r = 0; r < sh.nrows; r++) {
      if (hidden.has(r)) continue;
      if (fcols.length && r >= header) {
        let ok = true;
        for (const c of fcols) { if (!display(r, +c).text.toLowerCase().includes(f[c].toLowerCase())) { ok = false; break; } }
        if (!ok) continue;
      }
      visRows.push(r);
    }
  }
  function colOffsets() {
    const sh = sheet(), off = [RW];
    for (let c = 0; c < sh.ncols; c++) off.push(off[c] + colW(c));
    return off;
  }

  // ------------------------------------------------------------ rendering
  function cfStyle(r, c, d) {
    for (const rule of sheet().cf || []) {
      const [a, b] = rule.range.split(":"), p1 = parseAddr(a), p2 = parseAddr(b || a);
      if (!p1 || !p2 || r < p1.r || r > p2.r || c < p1.c || c > p2.c) continue;
      const v = d.num != null ? d.num : d.text, x = isNaN(parseFloat(rule.value)) ? rule.value : parseFloat(rule.value);
      let hit = false;
      if (rule.op === "contiene") hit = String(d.text).toLowerCase().includes(String(rule.value).toLowerCase());
      else if (typeof v === "number" && typeof x === "number") hit = { ">": v > x, "<": v < x, "=": v === x, ">=": v >= x, "<=": v <= x }[rule.op];
      else if (rule.op === "=") hit = String(v) === String(x);
      if (hit) return "background:" + rule.color + ";";
    }
    return "";
  }
  function invalid(r, c) {
    const cell = cellOf(r, c);
    if (!cell || isFormula(cell)) return false;
    const v = coerce(cell);
    if (v == null) return false;
    for (const rule of sheet().dv || []) {
      const [a, b] = rule.range.split(":"), p1 = parseAddr(a), p2 = parseAddr(b || a);
      if (!p1 || !p2 || r < p1.r || r > p2.r || c < p1.c || c > p2.c) continue;
      if (rule.type === "list" && !rule.values.map(String).includes(String(v))) return true;
      if (rule.type === "number" && (typeof v !== "number" || (rule.min !== "" && rule.min != null && v < +rule.min) || (rule.max !== "" && rule.max != null && v > +rule.max))) return true;
    }
    return false;
  }
  function render() {
    computeVisible();
    const sh = sheet(), off = colOffsets(), fr = (sh.freeze && sh.freeze.r) || 0, fc = (sh.freeze && sh.freeze.c) || 0;
    canvas.style.width = off[sh.ncols] + "px";
    canvas.style.height = HH + visRows.length * RH + "px";
    const st = vp.scrollTop, sl = vp.scrollLeft, vh = vp.clientHeight, vw = vp.clientWidth;
    const d0 = Math.max(0, Math.floor(st / RH) - 2), d1 = Math.min(visRows.length, Math.ceil((st + vh) / RH) + 2);
    let c0 = 0; while (c0 < sh.ncols && off[c0 + 1] < sl) c0++;
    let c1 = c0; while (c1 < sh.ncols && off[c1] < sl + vw) c1++;
    const prot = new Set(sh.protected || []);
    const groupStarts = {}; (sh.groups || []).forEach((g, i) => { groupStarts[g.start] = { g, i }; });
    const html = [];
    const cellHtml = (di, r, c, top, left, extra) => {
      const d = display(r, c), cell = cellOf(r, c) || {};
      const inSel = r >= sel.r1 && r <= sel.r2 && c >= sel.c1 && c <= sel.c2;
      const cls = ["gcell", d.cls, inSel ? "insel" : "", cursor.r === r && cursor.c === c ? "cursor" : "", prot.has(colName(c)) ? "protected" : "",
        extra || "", invalid(r, c) ? "invalid" : ""].join(" ");
      html.push('<div class="' + cls + '" data-r="' + r + '" data-c="' + c + '" style="top:' + top + "px;left:" + left + "px;width:" + colW(c) + "px;" +
        (cell.b ? "font-weight:700;" : "") + cfStyle(r, c, d) + '">' + GPV.esc(d.text) + "</div>");
    };
    const frozenRows = visRows.filter((r) => r < fr);
    for (let di = d0; di < d1; di++) {
      const r = visRows[di];
      if (r < fr) continue;
      for (let c = Math.max(c0, fc); c < c1; c++) cellHtml(di, r, c, HH + di * RH, off[c]);
      for (let c = 0; c < fc; c++) cellHtml(di, r, c, HH + di * RH, sl + off[c] - off[0] + RW, "frozen");
      const gs = groupStarts[r];
      html.push('<div class="gcell hdr rowhdr" data-rowhdr="' + r + '" style="top:' + (HH + di * RH) + "px;left:" + sl + "px;width:" + RW + 'px">' +
        (gs ? '<span data-group="' + gs.i + '" title="Expandir/contraer grupo">' + (gs.g.collapsed ? "▸" : "▾") + "</span>" : "") + (r + 1) + "</div>");
    }
    frozenRows.forEach((r, i) => {
      const top = st + HH + i * RH;
      for (let c = Math.max(c0, fc); c < c1; c++) cellHtml(i, r, c, top, off[c], "frozen");
      for (let c = 0; c < fc; c++) cellHtml(i, r, c, top, sl + off[c] - off[0] + RW, "frozen corner");
      html.push('<div class="gcell hdr rowhdr corner" data-rowhdr="' + r + '" style="top:' + top + "px;left:" + sl + "px;width:" + RW + 'px">' + (r + 1) + "</div>");
    });
    for (let c = c0; c < c1; c++) {
      const left = c < fc ? sl + off[c] - off[0] + RW : off[c];
      const f = (filters[sh.name] || {})[c];
      html.push('<div class="gcell hdr ' + (c < fc ? "corner" : "") + '" data-colhdr="' + c + '" style="top:' + st + "px;left:" + left + "px;width:" + colW(c) + 'px">' +
        colName(c) + (f ? " ⏷" : "") + (prot.has(colName(c)) ? " 🔒" : "") + '</div><div class="col-resizer" data-resize="' + c + '" style="top:' + st + "px;left:" + (left + colW(c) - 3) + 'px"></div>');
    }
    html.push('<div class="gcell hdr corner" style="top:' + st + "px;left:" + sl + "px;width:" + RW + 'px"></div>');
    canvas.innerHTML = html.join("");
    if (editor) canvas.appendChild(editor);
    renderTabs();
    updateFormulaBar();
  }
  vp.addEventListener("scroll", () => { if (!editor) render(); });

  function renderTabs() {
    const tabs = $("[data-tabs]");
    tabs.innerHTML = data.sheets.map((s, i) => '<button type="button" data-tab="' + i + '" class="' + (i === cur ? "cur" : "") + '" title="Doble clic para renombrar">' + GPV.esc(s.name) + "</button>").join("") +
      (canEdit ? '<button type="button" data-sheetop="add" title="Nueva hoja">+</button><button type="button" data-sheetop="dup">Duplicar hoja</button>' +
        '<button type="button" data-sheetop="left">◀</button><button type="button" data-sheetop="right">▶</button><button type="button" data-sheetop="del">Eliminar hoja</button>' : "");
  }
  function updateFormulaBar() {
    addrBox.value = addr(cursor.r, cursor.c);
    const cell = cellOf(cursor.r, cursor.c);
    if (document.activeElement !== fx) fx.value = cell ? String(cell.v == null ? "" : cell.v) : "";
    let sum = 0, cnt = 0, num = 0;
    if (sel.r2 - sel.r1 + sel.c2 - sel.c1 > 0) {
      for (let r = sel.r1; r <= Math.min(sel.r2, sel.r1 + 5000); r++) for (let c = sel.c1; c <= sel.c2; c++) {
        const d = display(r, c); if (d.text !== "") cnt++; if (d.num != null) { sum += d.num; num++; }
      }
      selInfo.textContent = "Selección: cuenta " + cnt + (num ? " · suma " + Math.round(sum * 1e6) / 1e6 + " · promedio " + Math.round((sum / num) * 1e6) / 1e6 : "");
    } else selInfo.textContent = "";
    fx.disabled = !canEdit;
  }

  // ------------------------------------------------------------ editing
  function protectedCol(c) { return (sheet().protected || []).includes(colName(c)) && !boot.is_owner; }
  function validateEntry(r, c, raw) {
    if (raw === "" || raw.startsWith("=")) return null;
    const v = coerce({ v: raw, fmt: (cellOf(r, c) || {}).fmt });
    for (const rule of sheet().dv || []) {
      const [a, b] = rule.range.split(":"), p1 = parseAddr(a), p2 = parseAddr(b || a);
      if (!p1 || !p2 || r < p1.r || r > p2.r || c < p1.c || c > p2.c) continue;
      if (rule.type === "list" && !rule.values.map(String).includes(String(v))) return "Valor no permitido. Opciones: " + rule.values.join(", ");
      if (rule.type === "number") {
        if (typeof v !== "number") return "Se requiere un número.";
        if (rule.min !== "" && rule.min != null && v < +rule.min) return "Mínimo permitido: " + rule.min;
        if (rule.max !== "" && rule.max != null && v > +rule.max) return "Máximo permitido: " + rule.max;
      }
    }
    return null;
  }
  function setCells(changes, label) {
    // changes: [[r, c, newCellOrNull]]
    const sh = sheet(), rec = [];
    for (const [r, c, nc] of changes) {
      const a = addr(r, c), before = sh.cells[a] ? JSON.parse(JSON.stringify(sh.cells[a])) : null;
      if (nc == null || (nc.v === "" && !nc.fmt && !nc.b && nc.dec == null)) delete sh.cells[a]; else sh.cells[a] = nc;
      rec.push([a, before, nc ? JSON.parse(JSON.stringify(nc)) : null]);
      if (r >= sh.nrows - 1) sh.nrows = r + 20;
      if (c >= sh.ncols - 1) sh.ncols = c + 5;
    }
    undo.push({ type: "cells", sheet: cur, changes: rec, label });
    redo.length = 0;
    markDirty();
    scheduleRecalc();
    render();
  }
  function commitRaw(r, c, raw) {
    if (!canEdit) return GPV.toast("Solo lectura: no tiene permiso para editar.", "error");
    if (protectedCol(c)) return GPV.toast("La columna " + colName(c) + " está protegida.", "error");
    const err = validateEntry(r, c, raw);
    if (err) return GPV.toast(err, "error");
    const old = cellOf(r, c) || {};
    const nc = Object.assign({}, old, { v: raw });
    setCells([[r, c, nc]], "Editar " + addr(r, c));
  }
  function startEdit(initial) {
    if (!canEdit) return GPV.toast("Solo lectura.", "error");
    if (protectedCol(cursor.c)) return GPV.toast("La columna está protegida.", "error");
    const off = colOffsets(), di = visRows.indexOf(cursor.r);
    if (di < 0) return;
    editor = document.createElement("input");
    editor.className = "cell-editor";
    editor.style.top = HH + di * RH + "px";
    editor.style.left = off[cursor.c] + "px";
    editor.style.width = Math.max(colW(cursor.c), 160) + "px";
    const cell = cellOf(cursor.r, cursor.c);
    editor.value = initial != null ? initial : cell ? String(cell.v == null ? "" : cell.v) : "";
    canvas.appendChild(editor);
    editor.focus();
    const r = cursor.r, c = cursor.c;
    editor.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const v = editor.value; stopEdit(); commitRaw(r, c, v); move(e.key === "Tab" ? 0 : 1, e.key === "Tab" ? 1 : 0);
      } else if (e.key === "Escape") { stopEdit(); render(); }
      e.stopPropagation();
    });
    editor.addEventListener("blur", () => { if (editor) { const v = editor.value; stopEdit(); commitRaw(r, c, v); } });
  }
  function stopEdit() { const e = editor; editor = null; if (e) e.remove(); vp.focus(); }

  fx.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitRaw(cursor.r, cursor.c, fx.value); vp.focus(); }
    if (e.key === "Escape") { updateFormulaBar(); vp.focus(); }
  });

  function move(dr, dc, extend) {
    const di = visRows.indexOf(cursor.r);
    let ndi = Math.max(0, Math.min(visRows.length - 1, di + dr));
    const nr = visRows[ndi] != null ? visRows[ndi] : cursor.r, nc = Math.max(0, Math.min(sheet().ncols - 1, cursor.c + dc));
    if (extend) { if (!anchor) anchor = { ...cursor }; cursor = { r: nr, c: nc }; sel = norm(anchor, cursor); }
    else { cursor = { r: nr, c: nc }; anchor = null; sel = { r1: nr, c1: nc, r2: nr, c2: nc }; }
    const off = colOffsets(), top = HH + visRows.indexOf(cursor.r) * RH;
    if (top < vp.scrollTop + HH) vp.scrollTop = top - HH; else if (top + RH > vp.scrollTop + vp.clientHeight) vp.scrollTop = top + RH - vp.clientHeight;
    if (off[nc] < vp.scrollLeft + RW) vp.scrollLeft = off[nc] - RW; else if (off[nc + 1] > vp.scrollLeft + vp.clientWidth) vp.scrollLeft = off[nc + 1] - vp.clientWidth;
    render();
  }
  const norm = (a, b) => ({ r1: Math.min(a.r, b.r), c1: Math.min(a.c, b.c), r2: Math.max(a.r, b.r), c2: Math.max(a.c, b.c) });

  vp.addEventListener("keydown", (e) => {
    if (editor) return;
    const k = e.key, mod = e.ctrlKey || e.metaKey;
    if (mod && k.toLowerCase() === "s") { e.preventDefault(); save(); return; }
    if (mod && k.toLowerCase() === "z") { e.preventDefault(); doUndo(); return; }
    if (mod && k.toLowerCase() === "y") { e.preventDefault(); doRedo(); return; }
    if (mod) return;
    const arrows = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    if (arrows[k]) { e.preventDefault(); move(arrows[k][0], arrows[k][1], e.shiftKey); return; }
    if (k === "Enter" || k === "F2") { e.preventDefault(); startEdit(); return; }
    if (k === "Tab") { e.preventDefault(); move(0, e.shiftKey ? -1 : 1); return; }
    if (k === "Delete" || k === "Backspace") { e.preventDefault(); clearSelection(); return; }
    if (k.length === 1 && !e.altKey) { e.preventDefault(); startEdit(k); }
  });
  function clearSelection() {
    if (!canEdit) return;
    const ch = [];
    for (let r = sel.r1; r <= sel.r2; r++) for (let c = sel.c1; c <= sel.c2; c++) {
      if (protectedCol(c)) return GPV.toast("La selección incluye columnas protegidas.", "error");
      const cell = cellOf(r, c); if (cell) ch.push([r, c, cell.fmt || cell.b ? Object.assign({}, cell, { v: "" }) : null]);
    }
    if (ch.length) setCells(ch, "Borrar");
  }

  // mouse
  let dragging = false, resizing = null;
  canvas.addEventListener("mousedown", (e) => {
    const rz = e.target.closest("[data-resize]");
    if (rz) { resizing = { c: +rz.dataset.resize, x: e.clientX, w: colW(+rz.dataset.resize) }; e.preventDefault(); return; }
    const grp = e.target.closest("[data-group]");
    if (grp) { const g = sheet().groups[+grp.dataset.group]; g.collapsed = !g.collapsed; markDirty(); render(); return; }
    const ch = e.target.closest("[data-colhdr]");
    if (ch) { const c = +ch.dataset.colhdr; cursor = { r: cursor.r, c }; sel = { r1: 0, c1: c, r2: sheet().nrows - 1, c2: c }; render(); vp.focus(); return; }
    const rh = e.target.closest("[data-rowhdr]");
    if (rh) { const r = +rh.dataset.rowhdr; cursor = { r, c: 0 }; sel = { r1: r, c1: 0, r2: r, c2: sheet().ncols - 1 }; render(); vp.focus(); return; }
    const cell = e.target.closest(".gcell[data-r]");
    if (!cell) return;
    const p = { r: +cell.dataset.r, c: +cell.dataset.c };
    if (e.shiftKey) { anchor = anchor || { ...cursor }; cursor = p; sel = norm(anchor, p); }
    else { cursor = p; anchor = { ...p }; sel = norm(p, p); dragging = true; }
    render();
    vp.focus();
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const cell = e.target.closest(".gcell[data-r]");
    if (cell) { cursor = { r: +cell.dataset.r, c: +cell.dataset.c }; sel = norm(anchor, cursor); render(); }
  });
  document.addEventListener("mousemove", (e) => {
    if (!resizing) return;
    const w = Math.max(30, resizing.w + e.clientX - resizing.x);
    sheet().cols = sheet().cols || {};
    sheet().cols[colName(resizing.c)] = Object.assign({}, sheet().cols[colName(resizing.c)], { w });
    render();
  });
  document.addEventListener("mouseup", () => { if (resizing) markDirty(); dragging = false; resizing = null; });
  canvas.addEventListener("dblclick", (e) => { if (e.target.closest(".gcell[data-r]")) startEdit(); });

  // clipboard
  function doCopy(e) {
    if (editor) return;
    const rows = [], raws = [];
    for (let r = sel.r1; r <= sel.r2; r++) {
      const line = [], rawLine = [];
      for (let c = sel.c1; c <= sel.c2; c++) { line.push(display(r, c).text); const cell = cellOf(r, c); rawLine.push(cell ? JSON.parse(JSON.stringify(cell)) : null); }
      rows.push(line.join("\t")); raws.push(rawLine);
    }
    const text = rows.join("\n");
    clip = { text, raws, r: sel.r1, c: sel.c1, sheet: cur };
    e.clipboardData.setData("text/plain", text);
    e.preventDefault();
    setStatus("Copiado " + raws.length + "×" + (raws[0] || []).length);
  }
  vp.addEventListener("copy", doCopy);
  vp.addEventListener("cut", (e) => { doCopy(e); if (clip) clip.cut = true; clearSelection(); });
  vp.addEventListener("paste", async (e) => {
    if (editor || !canEdit) return;
    e.preventDefault();
    const text = e.clipboardData.getData("text/plain");
    let grid;
    if (clip && clip.text === text && clip.cut) {
      grid = clip.raws; // moved cells keep their formulas unchanged (as in Excel)
      clip = null;
    } else if (clip && clip.text === text) {
      const flat = [].concat(...clip.raws.map((row) => row.map((c) => (c ? c.v : null))));
      try {
        const r = await api("operacion", { data, op: { type: "paste", items: flat, drow: cursor.r - clip.r, dcol: cursor.c - clip.c } });
        let i = 0;
        grid = clip.raws.map((row) => row.map((c) => { const v = r.data.items[i++]; return c ? Object.assign({}, c, { v }) : null; }));
      } catch (err) { return GPV.toast(err.message, "error"); }
    } else {
      grid = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map((line) => line.split("\t").map((v) => (v === "" ? null : { v })));
    }
    const ch = [];
    for (let i = 0; i < grid.length; i++) for (let j = 0; j < grid[i].length; j++) {
      const r = cursor.r + i, c = cursor.c + j;
      if (protectedCol(c)) return GPV.toast("El pegado afecta columnas protegidas.", "error");
      ch.push([r, c, grid[i][j]]);
    }
    setCells(ch, "Pegar");
    sel = { r1: cursor.r, c1: cursor.c, r2: cursor.r + grid.length - 1, c2: cursor.c + grid[0].length - 1 };
    render();
  });

  // ------------------------------------------------------------ undo / redo
  function applyCells(rec, dir) {
    const sh = data.sheets[rec.sheet];
    for (const [a, before, after] of rec.changes) {
      const v = dir === "undo" ? before : after;
      if (v == null) delete sh.cells[a]; else sh.cells[a] = JSON.parse(JSON.stringify(v));
    }
  }
  function doUndo() {
    const rec = undo.pop(); if (!rec) return GPV.toast("Nada que deshacer.");
    if (rec.type === "cells") applyCells(rec, "undo"); else { data = JSON.parse(rec.before); cur = Math.min(cur, data.sheets.length - 1); }
    redo.push(rec); markDirty(); scheduleRecalc(); render();
  }
  function doRedo() {
    const rec = redo.pop(); if (!rec) return GPV.toast("Nada que rehacer.");
    if (rec.type === "cells") applyCells(rec, "redo"); else { data = JSON.parse(rec.after); cur = Math.min(cur, data.sheets.length - 1); }
    undo.push(rec); markDirty(); scheduleRecalc(); render();
  }
  function snapshot(fn, label) {
    const before = JSON.stringify(data);
    return Promise.resolve(fn()).then(() => { undo.push({ type: "snap", before, after: JSON.stringify(data), label }); redo.length = 0; markDirty(); scheduleRecalc(); render(); });
  }
  async function serverOp(op, label) {
    if (!canEdit) return GPV.toast("Solo lectura.", "error");
    if (busy) return;
    busy = true; setStatus("Procesando…");
    try {
      const r = await api("operacion", { data, op: Object.assign({ sheet: sheet().name }, op) });
      await snapshot(() => { data = r.data.data; }, label);
      setStatus(label + " aplicado");
    } catch (e) { GPV.toast(e.message, "error"); setStatus("Error"); } finally { busy = false; }
  }

  // ------------------------------------------------------------ recalc & save
  function scheduleRecalc() { clearTimeout(recalcTimer); recalcTimer = setTimeout(recalc, 250); }
  async function recalc() {
    try {
      const r = await api("recalcular", { data });
      values = r.data.values;
      if (r.data.warnings && r.data.warnings.length) setStatus(r.data.warnings.join(" · "));
      render();
    } catch (e) { GPV.toast("No se pudo recalcular: " + e.message, "error"); }
  }
  async function save() {
    if (!canEdit) return GPV.toast("Solo lectura.", "error");
    const btn = app.querySelector('[data-act="save"]');
    if (btn.disabled) return;
    GPV.setLoading(btn, true);
    try {
      const r = await api("guardar", { data, base_version: version, summary: undo.slice(-5).map((u) => u.label).join(", ") });
      version = r.data.version; dirty = false; GPV.dirty = false;
      setStatus("Guardado (" + r.data.changed + " celdas cambiadas)");
      verInfo.textContent = "Versión " + version + " · guardada por usted " + r.data.updated;
      if (r.data.warnings && r.data.warnings.length) GPV.toast("Validación: " + r.data.warnings.slice(0, 3).join(" · "), "error");
      else GPV.toast("Hoja guardada (versión " + version + ")", "ok");
    } catch (e) {
      if (e.status === 409) {
        if (confirm(e.message + "\n\n¿Guardar SU trabajo como una copia nueva? (Aceptar = guardar copia; Cancelar = otras opciones)")) {
          try { const c = await api("copia", { data }); GPV.dirty = false; location.href = c.data.url; } catch (e2) { GPV.toast(e2.message, "error"); }
        } else if (confirm("¿Recargar la versión actual del servidor? Se perderán sus cambios no guardados.")) { GPV.dirty = false; location.reload(); }
      } else GPV.toast(e.message, "error");
    } finally { GPV.setLoading(btn, false); }
  }

  // ------------------------------------------------------------ toolbar actions
  function eachSel(fn) {
    const ch = [];
    for (let r = sel.r1; r <= Math.min(sel.r2, sheet().nrows - 1); r++) for (let c = sel.c1; c <= sel.c2; c++) {
      const cell = cellOf(r, c) ? JSON.parse(JSON.stringify(cellOf(r, c))) : { v: "" };
      const nc = fn(cell); if (nc) ch.push([r, c, nc]);
    }
    if (ch.length) setCells(ch, "Formato");
  }
  const selRange = () => addr(sel.r1, sel.c1) + ":" + addr(sel.r2, sel.c2);
  const actions = {
    save, undo: doUndo, redo: doRedo,
    insrow: () => serverOp({ type: "insert_rows", index: cursor.r, count: sel.r2 - sel.r1 + 1 }, "Insertar fila"),
    delrow: () => confirm("¿Eliminar " + (sel.r2 - sel.r1 + 1) + " fila(s)? Las referencias a ellas mostrarán #REF!.") && serverOp({ type: "delete_rows", index: sel.r1, count: sel.r2 - sel.r1 + 1 }, "Eliminar fila"),
    duprow: () => serverOp({ type: "duplicate_rows", index: sel.r1, count: sel.r2 - sel.r1 + 1 }, "Duplicar fila"),
    inscol: () => serverOp({ type: "insert_cols", index: cursor.c, count: sel.c2 - sel.c1 + 1 }, "Insertar columna"),
    delcol: () => confirm("¿Eliminar columna(s)?") && serverOp({ type: "delete_cols", index: sel.c1, count: sel.c2 - sel.c1 + 1 }, "Eliminar columna"),
    sortasc: () => serverOp({ type: "sort", col: cursor.c, asc: true, header: (sheet().freeze && sheet().freeze.r) || 1 }, "Ordenar"),
    sortdesc: () => serverOp({ type: "sort", col: cursor.c, asc: false, header: (sheet().freeze && sheet().freeze.r) || 1 }, "Ordenar"),
    filter: () => {
      const f = (filters[sheet().name] = filters[sheet().name] || {});
      const t = prompt("Mostrar filas cuya columna " + colName(cursor.c) + " contenga (vacío = quitar filtro):", f[cursor.c] || "");
      if (t === null) return;
      if (t) f[cursor.c] = t; else delete f[cursor.c];
      render();
    },
    find: () => {
      const q = prompt("Buscar:"); if (!q) return;
      const rep = prompt("Reemplazar por (Cancelar = solo buscar):");
      const sh = sheet(), hits = Object.keys(sh.cells).filter((a) => String(sh.cells[a].v).toLowerCase().includes(q.toLowerCase()));
      if (!hits.length) return GPV.toast("Sin coincidencias.");
      if (rep === null) { const p = parseAddr(hits[0]); cursor = p; sel = norm(p, p); render(); return GPV.toast(hits.length + " coincidencias; se muestra la primera (" + hits[0] + ")."); }
      const rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), ch = [];
      for (const a of hits) { const p = parseAddr(a); if (protectedCol(p.c)) continue; ch.push([p.r, p.c, Object.assign({}, sh.cells[a], { v: String(sh.cells[a].v).replace(rx, rep) })]); }
      setCells(ch, "Reemplazar"); GPV.toast(ch.length + " celdas reemplazadas.");
    },
    bold: () => eachSel((c) => Object.assign(c, { b: !c.b })),
    decplus: () => eachSel((c) => Object.assign(c, { dec: Math.min(10, (c.dec == null ? 0 : c.dec) + 1) })),
    decminus: () => eachSel((c) => Object.assign(c, { dec: Math.max(0, (c.dec == null ? 2 : c.dec) - 1) })),
    cf: () => {
      const op = prompt("Formato condicional para " + selRange() + "\nOperador: >, <, =, >=, <= o contiene", ">"); if (!op) return;
      if (![">", "<", "=", ">=", "<=", "contiene"].includes(op)) return GPV.toast("Operador no soportado.", "error");
      const v = prompt("Valor:"); if (v === null) return;
      const color = prompt("Color de fondo (ej. #fde2e1 rojo claro, #e4f3ea verde claro):", "#fde2e1") || "#fde2e1";
      if (!/^#[0-9a-fA-F]{6}$/.test(color)) return GPV.toast("Color inválido.", "error");
      snapshot(() => { (sheet().cf = sheet().cf || []).push({ range: selRange(), op, value: v, color }); }, "Formato condicional");
    },
    dv: () => {
      const t = prompt("Validación para " + selRange() + "\nEscriba «lista», «numero» o «quitar»:", "lista"); if (!t) return;
      if (t === "quitar") return snapshot(() => { sheet().dv = (sheet().dv || []).filter((x) => x.range !== selRange()); }, "Quitar validación");
      if (t === "lista") { const vals = prompt("Valores permitidos separados por coma:"); if (!vals) return; snapshot(() => { (sheet().dv = sheet().dv || []).push({ range: selRange(), type: "list", values: vals.split(",").map((s) => s.trim()) }); }, "Validación"); }
      else { const min = prompt("Mínimo (vacío = sin mínimo):", ""), max = prompt("Máximo (vacío = sin máximo):", ""); snapshot(() => { (sheet().dv = sheet().dv || []).push({ range: selRange(), type: "number", min, max }); }, "Validación"); }
    },
    protect: () => {
      if (!boot.is_owner) return GPV.toast("Solo el propietario puede proteger columnas.", "error");
      const col = colName(cursor.c);
      snapshot(() => { const p = (sheet().protected = sheet().protected || []); const i = p.indexOf(col); if (i >= 0) p.splice(i, 1); else p.push(col); }, "Proteger columna");
    },
    group: () => {
      const g = sheet().groups = sheet().groups || [];
      const exact = g.findIndex((x) => x.start === sel.r1 && x.end === sel.r2);
      if (exact >= 0) return snapshot(() => g.splice(exact, 1), "Desagrupar");
      const inside = g.find((x) => cursor.r >= x.start && cursor.r <= x.end);
      if (inside && sel.r1 === sel.r2) { inside.collapsed = !inside.collapsed; markDirty(); return render(); }
      if (sel.r2 <= sel.r1) return GPV.toast("Seleccione al menos dos filas para agrupar.");
      snapshot(() => g.push({ start: sel.r1, end: sel.r2, collapsed: false }), "Agrupar filas");
      GPV.toast("Grupo creado: use ▾/▸ en el número de fila para contraer/expandir.");
    },
    freeze: () => snapshot(() => { const f = sheet().freeze || {}; sheet().freeze = f.r === cursor.r && f.c === cursor.c ? { r: 0, c: 0 } : { r: cursor.r, c: cursor.c }; }, "Congelar"),
    pivot: async () => {
      const header = (sheet().freeze && sheet().freeze.r) || 1;
      const heads = []; for (let c = 0; c < sheet().ncols; c++) { const d = display(header - 1, c).text; if (d) heads.push(d); }
      const rows = prompt("Tabla dinámica — columna para FILAS:\n" + heads.join(", ")); if (!rows) return;
      const cols = prompt("Columna para COLUMNAS (vacío = ninguna):", "");
      const val = prompt("Columna de VALORES:"); if (!val) return;
      const agg = prompt("Agregación: sum, count o avg", "sum"); if (!agg) return;
      try {
        const r = await api("operacion", { data, op: { type: "pivot", sheet: sheet().name, rows, cols, value: val, agg, header } });
        await snapshot(() => {
          let name = "Dinámica", n = 1; while (data.sheets.some((s) => s.name.toLowerCase() === name.toLowerCase())) name = "Dinámica " + ++n;
          const cells = {};
          r.data.table.forEach((row, i) => row.forEach((v, j) => { if (v != null) cells[addr(i, j)] = { v: String(v), b: i === 0 || j === 0, fmt: typeof v === "number" ? "number" : "text", dec: typeof v === "number" ? 2 : undefined }; }));
          data.sheets.push({ name, nrows: r.data.table.length + 20, ncols: r.data.table[0].length + 3, cells, cols: {}, freeze: { r: 1, c: 1 }, cf: [], dv: [], protected: [], groups: [] });
          cur = data.sheets.length - 1;
        }, "Tabla dinámica");
      } catch (e) { GPV.toast(e.message, "error"); }
    },
    xlsx: () => exportAs("xlsx"), csv: () => exportAs("csv"),
  };
  async function exportAs(fmt) {
    const box = $("[data-sheet-result]");
    try {
      const r = await api("exportar", { data, fmt, sheet: sheet().name });
      box.hidden = false; box.innerHTML = ""; GPV.renderResult(box, r.data);
    } catch (e) { GPV.toast(e.message, "error"); }
  }
  app.querySelectorAll("[data-act]").forEach((b) => {
    if (b.tagName === "SELECT") {
      b.addEventListener("change", () => {
        const v = b.value; b.value = ""; if (!v) return;
        eachSel((c) => { if (v === "general") delete c.fmt; else c.fmt = v; return c; });
      });
    } else b.addEventListener("click", () => { const f = actions[b.dataset.act]; if (f) f(); vp.focus(); });
  });

  // tabs
  $("[data-tabs]").addEventListener("click", async (e) => {
    const t = e.target.closest("[data-tab]");
    if (t) { cur = +t.dataset.tab; cursor = { r: 0, c: 0 }; sel = { r1: 0, c1: 0, r2: 0, c2: 0 }; vp.scrollTop = vp.scrollLeft = 0; render(); return; }
    const op = e.target.closest("[data-sheetop]");
    if (!op) return;
    const kind = op.dataset.sheetop;
    if (kind === "add") snapshot(() => { let n = data.sheets.length + 1, name = "Hoja" + n; while (data.sheets.some((s) => s.name.toLowerCase() === name.toLowerCase())) name = "Hoja" + ++n; data.sheets.push({ name, nrows: 100, ncols: 26, cells: {}, cols: {}, freeze: { r: 1, c: 0 }, cf: [], dv: [], protected: [], groups: [] }); cur = data.sheets.length - 1; }, "Nueva hoja");
    if (kind === "dup") serverOp({ type: "duplicate_sheet" }, "Duplicar hoja");
    if (kind === "left" && cur > 0) snapshot(() => { const s = data.sheets.splice(cur, 1)[0]; data.sheets.splice(--cur, 0, s); }, "Mover hoja");
    if (kind === "right" && cur < data.sheets.length - 1) snapshot(() => { const s = data.sheets.splice(cur, 1)[0]; data.sheets.splice(++cur, 0, s); }, "Mover hoja");
    if (kind === "del") {
      if (data.sheets.length === 1) return GPV.toast("El libro debe tener al menos una hoja.", "error");
      try {
        const r = await api("operacion", { data, op: { type: "delete_sheet_check", sheet: sheet().name } });
        const broken = r.data.broken;
        if (!confirm(broken.length ? "Otras hojas usan esta hoja (" + broken.slice(0, 8).join(", ") + "). Esas fórmulas mostrarán #REF!. ¿Eliminar de todos modos?" : "¿Eliminar la hoja «" + sheet().name + "»?")) return;
        snapshot(() => { data.sheets.splice(cur, 1); cur = Math.max(0, cur - 1); }, "Eliminar hoja");
      } catch (err) { GPV.toast(err.message, "error"); }
    }
  });
  $("[data-tabs]").addEventListener("dblclick", (e) => {
    const t = e.target.closest("[data-tab]"); if (!t || !canEdit) return;
    const name = prompt("Nuevo nombre de la hoja (las fórmulas que la referencian se actualizan):", data.sheets[+t.dataset.tab].name);
    if (name && name.trim()) { cur = +t.dataset.tab; serverOp({ type: "rename_sheet", new: name.trim() }, "Renombrar hoja"); }
  });

  window.addEventListener("resize", render);
  render();
  recalc();
  vp.focus();
})();
