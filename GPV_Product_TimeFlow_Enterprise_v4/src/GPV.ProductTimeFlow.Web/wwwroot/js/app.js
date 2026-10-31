// GPV Product TimeFlow · utilidades de interfaz. JavaScript solo donde Blazor no tiene equivalente (tema, lienzo de firma, PWA).
export function getTheme() { return document.documentElement.getAttribute("data-theme") || "light"; }
export function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("tf-theme", theme); } catch (e) { }
}
export function getSidebarCollapsed() { try { return localStorage.getItem("tf-sidebar") === "collapsed"; } catch (e) { return false; } }
export function setSidebarCollapsed(value) { try { localStorage.setItem("tf-sidebar", value ? "collapsed" : "expanded"); } catch (e) { } }
export function focusElement(selector) { const el = document.querySelector(selector); if (el) el.focus(); }
export function openInNewTab(url) { window.open(url, "_blank", "noopener"); }

const pads = new Map();

/** Lienzo de firma con eventos de puntero (mouse, lápiz y touch). */
export function initSignature(canvas, dotnet) {
  const ctx = canvas.getContext("2d");
  const state = { drawing: false, empty: true, last: null };
  function resize() {
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    ctx.lineWidth = 2.4; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#0f172a";
    state.empty = true;
  }
  function pos(e) { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  function down(e) { e.preventDefault(); canvas.setPointerCapture(e.pointerId); state.drawing = true; state.last = pos(e); ctx.beginPath(); ctx.arc(state.last.x, state.last.y, 1.1, 0, Math.PI * 2); ctx.fillStyle = "#0f172a"; ctx.fill(); }
  function move(e) {
    if (!state.drawing) return;
    e.preventDefault();
    const p = pos(e);
    ctx.beginPath(); ctx.moveTo(state.last.x, state.last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    state.last = p;
    if (state.empty) { state.empty = false; dotnet.invokeMethodAsync("OnSignatureChanged", true); }
  }
  function up() { state.drawing = false; }
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointerleave", up);
  resize();
  pads.set(canvas, { resize, state, dispose() { canvas.removeEventListener("pointerdown", down); canvas.removeEventListener("pointermove", move); canvas.removeEventListener("pointerup", up); canvas.removeEventListener("pointerleave", up); } });
}
export function clearSignature(canvas) { const p = pads.get(canvas); if (p) { p.resize(); } }
export function signatureData(canvas) {
  const p = pads.get(canvas);
  if (!p || p.state.empty) return null;
  return canvas.toDataURL("image/png").split(",")[1];
}
export function disposeSignature(canvas) { const p = pads.get(canvas); if (p) { p.dispose(); pads.delete(canvas); } }

/** Dibuja un trazo de prueba (usado por las pruebas E2E automatizadas). */
export function drawTestSignature(selector) {
  const canvas = document.querySelector(selector);
  if (!canvas) return false;
  const r = canvas.getBoundingClientRect();
  const fire = (type, x, y) => canvas.dispatchEvent(new PointerEvent(type, { clientX: r.left + x, clientY: r.top + y, pointerId: 1, bubbles: true }));
  fire("pointerdown", 30, 90);
  for (let x = 30; x < r.width - 30; x += 6) fire("pointermove", x, 90 + Math.sin(x / 18) * 30);
  fire("pointerup", r.width - 30, 90);
  return true;
}

// PWA: registro del service worker (solo cachea recursos estáticos; nunca datos de solicitudes).
if ("serviceWorker" in navigator && location.protocol === "https:") {
  window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js").catch(() => { }));
}
