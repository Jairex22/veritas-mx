/* Document detail helpers: crop preview, dedupe preview, DOCX section selection, result links. */
document.addEventListener("DOMContentLoaded", () => {
  const prev = document.querySelector("[data-crop-preview]");
  if (prev) {
    const img = prev.querySelector("img"), box = prev.querySelector("[data-crop-box]");
    const W = parseFloat(prev.dataset.w), H = parseFloat(prev.dataset.h);
    const upd = () => {
      const v = (k) => parseFloat(document.querySelector('[data-crop="' + k + '"]').value) || 0;
      const sx = img.clientWidth / W, sy = img.clientHeight / H;
      box.style.left = v("left") * sx + "px"; box.style.top = v("top") * sy + "px";
      box.style.width = Math.max(0, img.clientWidth - (v("left") + v("right")) * sx) + "px";
      box.style.height = Math.max(0, img.clientHeight - (v("top") + v("bottom")) * sy) + "px";
    };
    document.querySelectorAll("[data-crop]").forEach((i) => i.addEventListener("input", upd));
    img.addEventListener("load", upd);
    if (img.complete) upd();
  }
  const dd = document.querySelector("[data-dedupe]");
  if (dd) dd.querySelector("[data-dedupe-preview]").addEventListener("click", async () => {
    const out = dd.querySelector("[data-dedupe-out]");
    try {
      const r = await GPV.api(dd.dataset.dedupe + "?columns=" + encodeURIComponent(dd.querySelector("[data-dedupe-cols]").value));
      out.textContent = r.data.duplicates + " duplicados (filas " + r.data.rows.join(", ") + (r.data.duplicates > 50 ? "…" : "") + "); quedarían " + r.data.remaining + " registros.";
    } catch (e) { out.textContent = e.message; }
  });
  const sf = document.querySelector("[data-sections]");
  if (sf) sf.addEventListener("submit", () => {
    sf.querySelector("[name=plan]").value = JSON.stringify([...sf.querySelectorAll("[data-sec]:checked")].map((x) => +x.value));
  }, true);
  document.querySelectorAll("form[data-job-form]").forEach((f) => f.addEventListener("gpv:done", (e) => {
    const r = e.detail || {}, box = f.querySelector(".jobbox") || document.querySelector(f.dataset.jobForm);
    if (box && r.zip_url) box.insertAdjacentHTML("beforeend", '<p><a class="btn" href="' + GPV.esc(r.zip_url) + '">Descargar todos en ZIP</a></p>');
    if (box && r.files) box.insertAdjacentHTML("beforeend", "<p class=\"small\">" + r.files.map((x) => x.doc_url ? '<a href="' + GPV.esc(x.doc_url) + '">Abrir ' + GPV.esc(x.name) + " en el centro</a>" : "").join(" · ") + "</p>");
  }));
});
