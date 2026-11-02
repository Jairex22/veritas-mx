/* Watches a job referenced by [data-watch-job] and reloads the page on completion. */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-watch-job]").forEach((box) => {
    const id = box.dataset.watchJob;
    if (!id) { box.innerHTML = '<div class="muted">Sin trabajo asociado. Vuelva al paso anterior.</div>'; return; }
    GPV.watchJob(id, box).then(() => { if (box.dataset.reload) location.reload(); })
      .catch((e) => { box.innerHTML = '<div class="alert alert-err">' + GPV.esc(e.message) + "</div>"; });
  });
});
