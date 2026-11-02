/* Visual organizer for PDF pages, PPTX slides and DOCX blocks: select, drag to reorder, duplicate, delete, rotate. */
(function () {
  "use strict";
  document.querySelectorAll("[data-organizer]").forEach((root) => {
    const cfg = JSON.parse(document.getElementById(root.dataset.organizer).textContent);
    // items: [{src, page, label, thumb?}]
    let items = cfg.items.map((it, i) => Object.assign({ uid: i, rotate: 0 }, it));
    const original = JSON.stringify(items);
    const grid = root.querySelector("[data-grid]");
    const form = root.querySelector("form");
    const planInput = form.querySelector("[name=plan]");
    let selected = new Set(), dragUid = null, uidSeq = items.length;
    const history = [];
    const push = () => { history.push(JSON.stringify(items)); if (history.length > 50) history.shift(); };

    function render() {
      grid.innerHTML = items.map((it, pos) =>
        '<div class="thumb' + (selected.has(it.uid) ? " sel" : "") + '" draggable="true" data-uid="' + it.uid + '" tabindex="0" role="option" aria-selected="' + selected.has(it.uid) + '">' +
        (it.thumb ? '<img loading="lazy" alt="' + GPV.esc(it.label) + '" src="' + GPV.esc(it.thumb) + '" style="transform:rotate(' + it.rotate + 'deg)">' :
          '<div style="height:90px;overflow:hidden;font-size:.8rem;text-align:left">' + GPV.esc(it.text || "") + "</div>") +
        '<div class="tlabel">' + (pos + 1) + " · " + GPV.esc(it.label) + (it.rotate ? " ↻" + it.rotate + "°" : "") + (it.dup ? " (copia)" : "") + "</div>" +
        '<div class="tools">' + (cfg.rotate ? '<button type="button" class="btn btn-sm" data-rot="' + it.uid + '" title="Rotar 90°">↻</button>' : "") +
        '<button type="button" class="btn btn-sm" data-dup="' + it.uid + '" title="Duplicar">⧉</button>' +
        '<button type="button" class="btn btn-sm" data-del="' + it.uid + '" title="Eliminar">✕</button></div></div>').join("") ||
        '<p class="muted">Sin elementos: el resultado estaría vacío.</p>';
      root.querySelector("[data-count]").textContent = items.length + " elemento(s) · " + selected.size + " seleccionado(s)";
    }
    const idx = (uid) => items.findIndex((x) => x.uid === uid);
    grid.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (b) {
        push();
        if (b.dataset.rot) { const it = items[idx(+b.dataset.rot)]; it.rotate = (it.rotate + 90) % 360; }
        if (b.dataset.dup) { const i = idx(+b.dataset.dup); items.splice(i + 1, 0, Object.assign({}, items[i], { uid: uidSeq++, dup: true })); }
        if (b.dataset.del) { items.splice(idx(+b.dataset.del), 1); }
        GPV.dirty = true;
        return render();
      }
      const t = e.target.closest(".thumb");
      if (!t) return;
      const uid = +t.dataset.uid;
      if (!(e.ctrlKey || e.metaKey || e.shiftKey)) selected = new Set([uid]);
      else if (selected.has(uid)) selected.delete(uid); else selected.add(uid);
      render();
    });
    grid.addEventListener("dragstart", (e) => { const t = e.target.closest(".thumb"); if (t) { dragUid = +t.dataset.uid; t.classList.add("dragging"); } });
    grid.addEventListener("dragover", (e) => e.preventDefault());
    grid.addEventListener("drop", (e) => {
      e.preventDefault();
      const t = e.target.closest(".thumb");
      if (!t || dragUid == null) return;
      push();
      const from = idx(dragUid), to = idx(+t.dataset.uid);
      const [moved] = items.splice(from, 1);
      items.splice(to, 0, moved);
      dragUid = null;
      GPV.dirty = true;
      render();
    });
    grid.addEventListener("keydown", (e) => {
      const t = e.target.closest(".thumb"); if (!t) return;
      const i = idx(+t.dataset.uid);
      if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && e.altKey) {
        e.preventDefault(); push();
        const j = e.key === "ArrowLeft" ? Math.max(0, i - 1) : Math.min(items.length - 1, i + 1);
        const [m] = items.splice(i, 1); items.splice(j, 0, m); render();
        grid.querySelector('[data-uid="' + m.uid + '"]').focus();
      }
      if (e.key === " ") { e.preventDefault(); t.click(); }
    });
    const act = (name, fn) => { const b = root.querySelector('[data-org="' + name + '"]'); if (b) b.addEventListener("click", () => { fn(); render(); }); };
    act("keep", () => { if (!selected.size) return GPV.toast("Seleccione elementos (Ctrl+clic para varios)."); push(); items = items.filter((x) => selected.has(x.uid)); });
    act("remove", () => { if (!selected.size) return GPV.toast("Seleccione elementos."); push(); items = items.filter((x) => !selected.has(x.uid)); selected.clear(); });
    act("dupsel", () => { push(); const out = []; items.forEach((x) => { out.push(x); if (selected.has(x.uid)) out.push(Object.assign({}, x, { uid: uidSeq++, dup: true })); }); items = out; });
    act("rotsel", () => { push(); items.forEach((x) => { if (selected.has(x.uid)) x.rotate = (x.rotate + 90) % 360; }); });
    act("all", () => { selected = new Set(items.map((x) => x.uid)); });
    act("undo", () => { if (history.length) items = JSON.parse(history.pop()); else GPV.toast("Nada que deshacer."); });
    act("reset", () => { push(); items = JSON.parse(original); selected.clear(); });
    form.addEventListener("submit", () => {
      planInput.value = JSON.stringify(cfg.kind === "pdf" ? items.map((x) => ({ src: x.src || 0, page: x.page, rotate: x.rotate })) : items.map((x) => x.page));
    }, true);
    // lazy thumbnails for office files (preview rendered on demand)
    const pv = root.querySelector("[data-preview]");
    if (pv) pv.addEventListener("click", async () => {
      GPV.setLoading(pv, true);
      try {
        const r = await GPV.api(pv.dataset.preview, { method: "POST", body: new FormData() });
        items.forEach((x) => { x.thumb = cfg.thumb.replace("PAGE", x.page); });
        if (r.data.pages && r.data.pages !== items.length) GPV.toast("La vista previa tiene " + r.data.pages + " páginas renderizadas.");
        pv.hidden = true;
        render();
      } catch (e) { GPV.toast(e.message, "error"); } finally { GPV.setLoading(pv, false); }
    });
    render();
  });
})();
