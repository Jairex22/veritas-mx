/* Portal del turno: refresh, idempotent submits, low-risk offline queue for help requests, area screen.
   The browser only talks to this portal (never to OData). */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const seconds = Math.max(10, parseInt(document.body.dataset.pollSeconds || "60", 10));
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(16) + Math.random().toString(16).slice(2));

  // 1) every form with [data-client-uuid] gets a stable id: a double click or a retry never creates two records
  document.querySelectorAll("[data-client-uuid]").forEach((el) => { if (!el.value) el.value = uuid(); });

  // 2) Mi turno: refresh state; on failure keep the last data and say so (never show zero)
  const timeEl = document.querySelector("[data-server-time]");
  if (timeEl) {
    const strip = document.querySelector("[data-sources]");
    const tick = async () => {
      try {
        const r = await GPV.api("/turno/api/estado/");
        timeEl.textContent = r.data.server_time;
        timeEl.classList.remove("stale");
        if (strip && r.data.sources) {
          strip.innerHTML = r.data.sources.length ? r.data.sources.map((s) => {
            const cls = s.health === "connected" ? "tag-ok" : s.health === "delayed" ? "tag-warn" : s.health === "disconnected" ? "tag-err" : "tag-info";
            return '<span class="tag ' + cls + '">' + GPV.esc(s.name) + ": " + GPV.esc(s.health_label) + " · último éxito " + GPV.esc(s.last_success) + (s.synthetic ? " · SIMULADA" : "") + "</span>";
          }).join(" ") : '<span class="tag tag-info">Sin fuente OData configurada: solo captura web (manual pendiente de conciliación)</span>';
        }
      } catch (e) {
        timeEl.textContent = (timeEl.textContent || "—").replace(/ \(sin conexión.*\)$/, "") + " (sin conexión: se muestran los últimos datos)";
        timeEl.classList.add("stale");
      }
    };
    tick();
    setInterval(tick, seconds * 1000);
  }

  // 3) help request: if the server is unreachable, keep it in this browser and resend (same client_uuid => no duplicates)
  const KEY = "gpv.helpQueue";
  const readQ = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } };
  const writeQ = (q) => { try { localStorage.setItem(KEY, JSON.stringify(q)); } catch (e) { /* storage blocked */ } };
  const qStatus = document.querySelector("[data-queue-status]");
  const showQ = () => { if (qStatus) { const n = readQ().length; qStatus.textContent = n ? n + " solicitud(es) guardada(s) en este equipo, pendiente(s) de envío." : ""; } };
  const flush = async () => {
    const q = readQ();
    if (!q.length) return;
    const left = [];
    for (const item of q) {
      try {
        const r = await GPV.api("/turno/ayuda/", { method: "POST", body: item });
        GPV.toast("Solicitud #" + r.data.id + " enviada (estaba pendiente).", "ok");
      } catch (e) {
        if (e.status && e.status < 500) GPV.toast("Una solicitud guardada fue rechazada: " + e.message, "error");
        else left.push(item);
      }
    }
    writeQ(left);
    showQ();
  };
  const helpForm = document.querySelector("[data-help-form]");
  if (helpForm) {
    showQ();
    helpForm.addEventListener("submit", (ev) => {
      if (navigator.onLine !== false) return; // normal submit (supports photo)
      ev.preventDefault();
      const fd = new FormData(helpForm);
      const item = { reason: fd.get("reason"), comment: fd.get("comment") || "", client_uuid: fd.get("client_uuid"), relate_to: fd.get("relate_to") || "" };
      if (!item.reason) return;
      const q = readQ();
      if (!q.some((x) => x.client_uuid === item.client_uuid)) q.push(item);
      writeQ(q);
      showQ();
      GPV.toast("Sin red: la solicitud quedó guardada en este equipo y se enviará al reconectar (la foto no se guarda sin red).", "error");
      helpForm.reset();
      helpForm.querySelector("[data-client-uuid]").value = uuid();
    });
  }
  window.addEventListener("online", flush);
  if (readQ().length) { flush(); setInterval(flush, 30000); }

  // 4) read-only area screen
  const area = document.querySelector("[data-area-screen]");
  if (area) {
    const $ = (s) => area.querySelector(s);
    const draw = async () => {
      try {
        const r = await GPV.api(GPV.ds(area).url);
        const d = r.data;
        $("[data-a-time]").textContent = d.server_time;
        $("[data-a-shift]").textContent = d.shift ? "Turno " + d.shift + " · " + d.window.join(" → ") : "Fuera de turno";
        if (!d.shift) return;
        $("[data-a-comp]").textContent = d.compliance.status === "ok" ? d.compliance.value.toFixed(1) + " %" : (d.compliance.status === "insufficient" ? "Datos insuficientes" : "No calculable");
        $("[data-a-down]").textContent = d.downtime_minutes;
        $("[data-a-help]").textContent = d.open_help;
        $("[data-a-orders]").innerHTML = d.orders.map((o) => "<tr><td>" + GPV.esc(o.work_order) + "</td><td>" + GPV.esc(o.target) + " " + GPV.esc(o.unit) + "</td><td>" +
          (o.good === null ? "No calculable" : GPV.esc(o.good)) + (o.provisional ? ' <small>(+' + GPV.esc(o.provisional) + " manual pendiente)</small>" : "") + "</td><td>" + (o.pending === null ? "—" : GPV.esc(o.pending)) + "</td></tr>").join("") ||
          '<tr><td colspan="4">Sin metas asignadas</td></tr>';
        $("[data-a-sources]").textContent = d.sources.length ? d.sources.map((s) => s.name + ": " + s.health_label + " (último éxito " + s.last_success + ")").join(" · ") : "Solo captura web";
        area.classList.remove("stale");
      } catch (e) {
        area.classList.add("stale");
        $("[data-a-time]").textContent = "Sin conexión: últimos datos conservados";
      }
    };
    draw();
    setInterval(draw, seconds * 1000);
  }
});
