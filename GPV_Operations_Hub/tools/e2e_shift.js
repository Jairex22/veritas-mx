/*
 * Portal del turno: browser flows (development tool, synthetic data).
 * Requires Node + Playwright, a server loaded with "manage.py seed_demo --password <DEMO>" and the
 * SIMULATED OData service (tools/fake_odata_server.py) on 127.0.0.1:8765.
 *   node tools/e2e_shift.js http://127.0.0.1:8000 <DEMO_PASSWORD> <ADMIN_USER> <ADMIN_PASSWORD>
 * Mobile viewport (390x844): GPV_MOBILE=1
 */
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8000", PW = process.argv[3] || "", ADMIN = process.argv[4] || "admin", APW = process.argv[5] || "";
const MOBILE = !!process.env.GPV_MOBILE;
const RUN = Date.now().toString(36);
const res = [];
async function session(b, user, pw) {
  const ctx = await b.newContext({ viewport: MOBILE ? { width: 390, height: 844 } : { width: 1280, height: 860 } });
  const p = await ctx.newPage();
  p.errs = []; p.on("pageerror", (e) => p.errs.push(e.message));
  p.on("console", (m) => { if (m.type() === "error" && !/403|Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  p.on("dialog", (d) => d.accept());
  await p.goto(BASE + "/entrar/"); await p.fill("#id_username", user); await p.fill("#id_password", pw || PW);
  await Promise.all([p.waitForNavigation(), p.click("button[type=submit]")]);
  return p;
}
async function step(role, name, p, fn) {
  const before = p.errs.length;
  try {
    await fn();
    if (MOBILE) {
      const [over, where] = await p.evaluate(() => [document.documentElement.scrollWidth - window.innerWidth, location.pathname]);
      if (over > 2) p.errs.push("desbordamiento horizontal de " + over + " px en " + where);
    }
    const e = p.errs.slice(before); res.push([role, name, e.length ? "FAIL" : "OK", e.join(" | ").slice(0, 220)]);
  } catch (e) { res.push([role, name, "FAIL", e.message.split("\n")[0].slice(0, 220)]); }
}
(async () => {
  const b = await chromium.launch();
  // ---------- ADMIN: OData source (simulated) diagnosis + enable
  let p = await session(b, ADMIN, APW);
  await step("admin", "diagnosticar fuente OData SIMULADA por etapas", p, async () => {
    await p.goto(BASE + "/turno/fuentes/"); await p.click("a:has-text('OData SIMULADO')");
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Diagnosticar por etapas')")]);
    await p.waitForSelector("text=Acceso real al conjunto de entidades");
    if (await p.locator(".tag-err:has-text('Falla')").count()) throw new Error("diagnóstico con fallas (¿está corriendo tools/fake_odata_server.py?)");
    const t = p.locator("button:has-text('Activar sincronización automática')");
    if (await t.count()) await Promise.all([p.waitForNavigation(), t.click()]);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Sincronizar ahora')")]);
    await p.waitForSelector("text=Sincronización ok"); });
  await p.context().close();

  // ---------- OPERADOR
  p = await session(b, "operador1");
  await step("operador", "aterriza en Mi turno y ve las 4 acciones", p, async () => {
    if (!p.url().endsWith("/turno/")) throw new Error("no aterrizó en /turno/: " + p.url());
    for (const t of ["Ver mi trabajo", "Necesito ayuda", "Imprimir etiqueta", "Revisar cierre de turno"]) await p.waitForSelector(".big-btn:has-text('" + t + "')"); });
  await step("operador", "elige estación y orden (contexto confirmado)", p, async () => {
    await p.goto(BASE + "/turno/contexto/");
    const opt = await p.locator("select[name=station] option", { hasText: "SMT-EJ-AOI-B" }).getAttribute("value");
    await p.selectOption("select[name=station]", opt); await p.fill("input[name=work_order]", "OT-EJ-1001");
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Confirmar')")]);
    await p.waitForSelector("text=Contexto confirmado"); await p.waitForSelector(".kpi-label:has-text('Buenas confirmadas')"); });
  await step("operador", "Mi turno se actualiza (hora del servidor)", p, async () => {
    await p.waitForFunction(() => /\d\d:\d\d:\d\d/.test(document.querySelector("[data-server-time]").textContent), null, { timeout: 15000 }); });
  await step("operador", "pedir ayuda (Mantenimiento) en dos toques", p, async () => {
    await p.click(".big-btn:has-text('Necesito ayuda')"); await p.click(".reason-btn:has-text('Falla de equipo')");
    await p.fill("textarea[name=comment]", "Alimentador atorado " + RUN);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Enviar solicitud')")]);
    await p.waitForSelector("text=enviada a Mantenimiento"); });
  await step("operador", "iniciar y terminar paro", p, async () => {
    await p.goto(BASE + "/turno/paros/");
    if (await p.locator("button:has-text('Terminar paro')").count() === 0) await Promise.all([p.waitForNavigation(), p.click("button:has-text('Iniciar paro')")]);
    await p.waitForSelector("button:has-text('Terminar paro')");
    await p.selectOption("form.row-form select[name=reason] >> nth=0", { index: 1 });
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Terminar paro') >> nth=0")]); await p.waitForSelector("text=Paro cerrado"); });
  await step("operador", "captura manual queda pendiente de conciliación", p, async () => {
    await p.goto(BASE + "/turno/captura/"); await p.fill("input[name=qty]", "6"); await p.fill("input[name=reason]", "Prueba de contingencia " + RUN);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Guardar captura')")]); await p.waitForSelector("text=Manual pendiente de conciliación"); });
  await step("operador", "buscar serie y ver historial", p, async () => {
    await p.goto(BASE + "/turno/escanear/"); await p.fill("[data-scan-input]", "SN-EJ-00039"); await p.keyboard.press("Enter");
    await p.waitForSelector("text=Historial de SN-EJ-00039"); });
  await step("operador", "etiqueta desde contexto: Enter del escáner NO imprime", p, async () => {
    await p.goto(BASE + "/turno/etiqueta/"); await p.click("main ul a.btn >> nth=0");
    await p.waitForSelector("text=Datos del contexto del turno");
    const before = await p.locator("[data-print-box]").isHidden();
    const pr = p.locator("input[name^=prompt_]");
    if (await pr.count()) { await pr.first().fill("SCAN123"); await pr.first().press("Enter"); } else { await p.locator("input[name=copies]").press("Enter"); }
    await p.waitForTimeout(800);
    if (before && !(await p.locator("[data-print-box]").isHidden())) throw new Error("Enter disparó una impresión");
    await p.click("[data-print-form] button[type=submit]"); await p.waitForSelector("[data-print-box] .alert-ok", { timeout: 30000 }); });
  await step("operador", "confirmar impresión física registra «Confirmado» (botón con valor)", p, async () => {
    await p.click("[data-print-box] a[href*='/etiquetas/trabajos/']");
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Confirmar impresión física')")]);
    await p.waitForSelector("text=Confirmado"); if (await p.locator("text=Fallido").count()) throw new Error("se registró como fallido"); });
  await step("operador", "observación de calidad (no disposición)", p, async () => {
    await p.goto(BASE + "/turno/calidad/"); await p.fill("input[name=category]", "Soldadura"); await p.fill("textarea[name=description]", "Puente " + RUN);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Registrar observación')")]); await p.waitForSelector("text=no es una disposición"); });
  await p.context().close();

  // ---------- INGENIERO (grupo Mantenimiento) atiende
  p = await session(b, "ingeniero1");
  await step("mantenimiento", "recibe, atiende y resuelve la ayuda", p, async () => {
    await p.goto(BASE + "/turno/ayuda/"); await p.click("#inbox tr:has-text('Falla de equipo') a >> nth=0");
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Recibir')")]);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Empezar atención')")]);
    await p.fill("input[name=note]", "Se liberó el alimentador");
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Marcar resuelta')")]); await p.waitForSelector(".tag:has-text('Resuelto')"); });
  await p.context().close();

  // ---------- SUPERVISOR
  p = await session(b, "supervisor1");
  await step("supervisor", "tablero del turno", p, async () => { await p.goto(BASE + "/turno/supervisor/"); await p.waitForSelector("h2:has-text('SMT-EJEMPLO')"); });
  await step("supervisor", "conciliar captura manual (producción adicional)", p, async () => {
    await p.goto(BASE + "/turno/conciliacion/");
    const card = p.locator("section.card:has-text('" + RUN + "')").first();
    await card.locator("input[name=note]").fill("Lote adicional verificado " + RUN);
    await Promise.all([p.waitForNavigation(), card.locator("button:has-text('producción adicional')").click()]); await p.waitForSelector("text=Manual aceptado"); });
  await step("supervisor", "asignar meta con motivo", p, async () => {
    await p.goto(BASE + "/turno/plan/"); await p.fill("input[name=work_order]", "OT-EJ-1001"); await p.fill("input[name=target]", "150");
    await p.fill("input[name=reason]", "Ajuste de meta " + RUN);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Guardar meta')")]); await p.waitForSelector("text=Meta del turno guardada"); });
  await step("supervisor", "cierre: generar borrador del último turno", p, async () => {
    await p.goto(BASE + "/turno/cierre/"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Generar borrador')")]);
    await p.waitForSelector("text=Reporte SMT del turno"); });
  await step("supervisor", "pantalla del área (solo lectura) se llena", p, async () => {
    await p.goto(BASE + "/turno/pantalla/SMT-EJEMPLO/");
    await p.waitForFunction(() => document.querySelector("[data-a-time]").textContent !== "—", null, { timeout: 15000 }); });
  await p.context().close();
  await b.close();
  const fails = res.filter((r) => r[2] !== "OK");
  console.log((MOBILE ? "[móvil 390x844] " : "[escritorio] ") + res.length + " pasos, " + fails.length + " fallas");
  for (const r of res) console.log(r.join(" · "));
  process.exit(fails.length ? 1 : 0);
})();
