/* GPV Operations Hub — shared client behaviour (no external libraries). */
(function () {
  "use strict";
  const GPV = (window.GPV = window.GPV || {});
  /* form.dataset can be shadowed by a field named "dataset": always read the real DOMStringMap. */
  const DS = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "dataset").get;
  GPV.ds = (el) => DS.call(el);
  const csrf = () => document.body.dataset.csrf || (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  GPV.csrf = csrf;

  GPV.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  };

  GPV.toast = function (msg, kind) {
    const wrap = document.querySelector("[data-toasts]");
    if (!wrap) return alert(msg);
    const el = document.createElement("div");
    el.className = "toast" + (kind ? " toast-" + kind : "");
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => el.remove(), kind === "error" ? 9000 : 4500);
  };

  /** fetch wrapper: JSON in/out, CSRF, friendly errors. */
  GPV.api = async function (url, opts) {
    opts = opts || {};
    const headers = Object.assign({ "X-CSRFToken": csrf(), Accept: "application/json" }, opts.headers || {});
    let body = opts.body;
    if (body && !(body instanceof FormData) && typeof body !== "string") {
      body = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
    let resp;
    try {
      resp = await fetch(url, { method: opts.method || (body ? "POST" : "GET"), headers, body, credentials: "same-origin" });
    } catch (e) {
      throw new Error("No hay conexión con el servidor. Verifique la red o que el servidor esté encendido.");
    }
    let data = null;
    const ctype = resp.headers.get("Content-Type") || "";
    if (ctype.includes("application/json")) data = await resp.json();
    if (!resp.ok || (data && data.ok === false)) {
      const err = new Error((data && data.error) || (resp.status === 403 ? "No tiene permiso para esta operación." : resp.status === 401 ? "Su sesión expiró; vuelva a iniciar sesión." : "Error del servidor (" + resp.status + ")."));
      err.status = resp.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  GPV.setLoading = function (btn, on) {
    if (!btn) return;
    btn.disabled = !!on;
    btn.classList.toggle("is-loading", !!on);
    btn.setAttribute("aria-busy", on ? "true" : "false");
  };

  /** Poll a background job and render progress inside box. Resolves with job payload. */
  GPV.watchJob = function (jobId, box) {
    return new Promise((resolve, reject) => {
      const render = (j) => {
        if (!box) return;
        const pct = j.progress || 0;
        box.hidden = false;
        box.innerHTML =
          '<div><strong>' + GPV.esc(j.status_label) + "</strong> " + GPV.esc(j.message || "") + "</div>" +
          '<div class="progress' + (j.status === "succeeded" ? " done" : "") + '"><span style="width:' + pct + '%"></span></div>' +
          (j.final ? "" : '<button type="button" class="btn btn-sm" data-cancel>Cancelar</button>');
        const c = box.querySelector("[data-cancel]");
        if (c) c.onclick = () => GPV.api("/api/trabajos/" + jobId + "/cancelar/", { method: "POST" }).then(() => GPV.toast("Cancelación solicitada")).catch((e) => GPV.toast(e.message, "error"));
      };
      const tick = () => {
        GPV.api("/api/trabajos/" + jobId + "/")
          .then((r) => {
            const j = r.data;
            render(j);
            if (j.final) {
              if (j.status === "succeeded") resolve(j);
              else reject(new Error(j.error || j.message || j.status_label));
            } else setTimeout(tick, 1200);
          })
          .catch(reject);
      };
      tick();
    });
  };

  GPV.renderResult = function (box, result) {
    if (!box || !result) return;
    const files = result.files || [];
    let html = '<div class="alert alert-ok"><strong>Resultado listo.</strong> ' + GPV.esc(result.summary || "") + "</div>";
    if (result.warnings && result.warnings.length) {
      html += '<div class="alert alert-warn"><strong>Advertencias:</strong><ul>' + result.warnings.map((w) => "<li>" + GPV.esc(w) + "</li>").join("") + "</ul></div>";
    }
    if (files.length) {
      html += "<ul>" + files.map((f) => '<li><a href="' + GPV.esc(f.url) + '">' + GPV.esc(f.name) + "</a> <span class=\"muted small\">" + GPV.esc(f.type || "") + " · " + GPV.esc(f.size_h || "") + "</span></li>").join("") + "</ul>";
    }
    if (result.url) html += '<p><a class="btn btn-primary" href="' + GPV.esc(result.url) + '">Abrir resultado</a></p>';
    box.insertAdjacentHTML("beforeend", html);
  };

  /** Forms with data-job-form are submitted with fetch; the server answers {job_id} or {data}. */
  function bindJobForms(root) {
    root.querySelectorAll("form[data-job-form]").forEach((form) => {
      if (GPV.ds(form).bound) return;
      GPV.ds(form).bound = "1";
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const btn = ev.submitter || form.querySelector("[type=submit]");
        if (GPV.ds(form).busy === "1") return; // double submit guard
        if (GPV.ds(form).confirm && !confirm(GPV.ds(form).confirm)) return;
        const box = (GPV.ds(form).jobForm && document.querySelector(GPV.ds(form).jobForm)) || form.querySelector(".jobbox");
        if (box) { box.hidden = false; box.innerHTML = '<div class="muted">Enviando…</div>'; }
        GPV.ds(form).busy = "1";
        GPV.setLoading(btn, true);
        try {
          const fd = new FormData(form);
          if (btn && btn.name) fd.append(btn.name, btn.value);
          if (!fd.get("idempotency_key")) fd.append("idempotency_key", (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()));
          const r = await GPV.api(form.getAttribute("action") || location.href, { method: "POST", body: fd });
          if (r.job_id) {
            const job = await GPV.watchJob(r.job_id, box);
            GPV.renderResult(box, job.result);
            form.dispatchEvent(new CustomEvent("gpv:done", { detail: job.result }));
            if (job.result && job.result.redirect) location.href = job.result.redirect;
          } else {
            if (box) { box.innerHTML = ""; GPV.renderResult(box, r.data || {}); }
            form.dispatchEvent(new CustomEvent("gpv:done", { detail: r.data }));
            if (r.data && r.data.redirect) location.href = r.data.redirect;
          }
          GPV.dirty = false;
        } catch (e) {
          if (box) box.innerHTML = '<div class="alert alert-err">' + GPV.esc(e.message) + "</div>";
          GPV.toast(e.message, "error");
        } finally {
          GPV.ds(form).busy = "0";
          GPV.setLoading(btn, false);
        }
      });
    });
  }
  GPV.bindJobForms = bindJobForms;

  /** Classic forms: prevent double submission. */
  function bindPlainForms() {
    document.querySelectorAll("form:not([data-job-form]):not([data-print-form])").forEach((form) => {
      form.addEventListener("submit", (ev) => {
        if (GPV.ds(form).confirm && !confirm(GPV.ds(form).confirm)) { ev.preventDefault(); return; }
        if (GPV.ds(form).submitted === "1") { ev.preventDefault(); return; }
        if (form.method.toLowerCase() === "post") {
          GPV.ds(form).submitted = "1";
          const btn = ev.submitter || form.querySelector("[type=submit]");
          // a disabled submitter is left out of the submitted data: keep its name/value (e.g. action=close)
          if (btn && btn.name) {
            form.querySelectorAll("input[data-submitter-copy]").forEach((x) => x.remove());
            const h = document.createElement("input");
            h.type = "hidden"; h.name = btn.name; h.value = btn.value; h.setAttribute("data-submitter-copy", "");
            form.appendChild(h);
          }
          GPV.setLoading(btn, true);
        }
        GPV.dirty = false;
      });
    });
  }

  /** Unsaved changes warning for forms marked data-dirty-check. */
  GPV.dirty = false;
  document.addEventListener("input", (e) => {
    if (e.target.closest("form[data-dirty-check]")) GPV.dirty = true;
  });
  window.addEventListener("beforeunload", (e) => {
    if (GPV.dirty) { e.preventDefault(); e.returnValue = ""; }
  });

  /** Persistent filters (per page) in localStorage. */
  function bindFilters() {
    document.querySelectorAll("form[data-persist-filters]").forEach((form) => {
      const key = "gpv.filters." + GPV.ds(form).persistFilters;
      try {
        if (!location.search && localStorage.getItem(key)) {
          location.replace(location.pathname + "?" + localStorage.getItem(key));
          return;
        }
        if (location.search) localStorage.setItem(key, location.search.slice(1));
      } catch (e) { /* storage unavailable */ }
      const clear = form.querySelector("[data-clear-filters]");
      if (clear) clear.addEventListener("click", () => { try { localStorage.removeItem(key); } catch (e) {} });
    });
  }

  /** Navigation + notifications polling. */
  function bindNav() {
    const t = document.querySelector("[data-nav-toggle]");
    const sb = document.querySelector("[data-sidebar]");
    if (t && sb) t.addEventListener("click", () => { const o = sb.classList.toggle("open"); t.setAttribute("aria-expanded", o ? "true" : "false"); });
  }

  function bindNotifications() {
    const root = document.querySelector("[data-notif]");
    if (!root) return;
    const btn = root.querySelector("[data-notif-toggle]");
    const panel = root.querySelector("[data-notif-panel]");
    const list = root.querySelector("[data-notif-list]");
    const count = root.querySelector("[data-notif-count]");
    const stamp = document.querySelector("[data-last-update]");
    const seconds = Math.max(10, parseInt(document.body.dataset.pollSeconds || "30", 10));
    let lastUnread = null;
    const poll = () => {
      if (document.hidden) return;
      GPV.api("/api/notificaciones/")
        .then((r) => {
          const d = r.data;
          count.hidden = !d.unread;
          count.textContent = d.unread > 99 ? "99+" : d.unread;
          if (stamp) stamp.textContent = "Actualizado " + d.server_time;
          if (lastUnread !== null && d.unread > lastUnread) GPV.toast("Tiene " + (d.unread - lastUnread) + " notificación(es) nueva(s).");
          lastUnread = d.unread;
          list.innerHTML = d.items.length ? d.items.map((n) =>
            '<li class="' + (n.read ? "" : "unread") + '"><a href="' + GPV.esc(n.url || "#") + '"><strong>' + GPV.esc(n.title) + "</strong><br><span class=\"muted small\">" + GPV.esc(n.created) + " · " + GPV.esc(n.body) + "</span></a></li>").join("") : '<li class="muted">Sin notificaciones.</li>';
        })
        .catch(() => { if (stamp) stamp.textContent = "Sin conexión"; });
    };
    btn.addEventListener("click", () => { panel.hidden = !panel.hidden; btn.setAttribute("aria-expanded", panel.hidden ? "false" : "true"); });
    document.addEventListener("click", (e) => { if (!root.contains(e.target)) panel.hidden = true; });
    root.querySelector("[data-notif-readall]").addEventListener("click", () => {
      const fd = new FormData();
      GPV.api("/api/notificaciones/leer/", { method: "POST", body: fd }).then(poll).catch((e) => GPV.toast(e.message, "error"));
    });
    poll();
    setInterval(poll, seconds * 1000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  }

  /** Drag & drop zones bound to a file input. */
  function bindDropzones() {
    document.querySelectorAll("[data-dropzone]").forEach((zone) => {
      const input = document.querySelector(zone.dataset.dropzone);
      const label = zone.querySelector("[data-drop-label]");
      if (!input) return;
      const show = () => { if (label) label.textContent = input.files.length ? Array.from(input.files).map((f) => f.name + " (" + Math.round(f.size / 1024) + " KB)").join(", ") : label.dataset.empty; };
      zone.addEventListener("click", () => input.click());
      zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
      zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("over"));
      zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); input.files = e.dataTransfer.files; show(); });
      input.addEventListener("change", show);
    });
  }

  /** Auto-submit selects marked data-autosubmit. */
  function bindAutosubmit() {
    document.querySelectorAll("[data-autosubmit]").forEach((el) => el.addEventListener("change", () => el.form && el.form.requestSubmit()));
  }

  /** Mark notifications as read when clicking on links with data-read-id. */
  function bindPrint() {
    document.querySelectorAll("[data-print]").forEach((b) => b.addEventListener("click", () => window.print()));
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindNav();
    bindNotifications();
    bindJobForms(document);
    bindPlainForms();
    bindFilters();
    bindDropzones();
    bindAutosubmit();
    bindPrint();
  });
})();
