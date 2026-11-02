/*
 * Role-based audit (development tool). Requires Node + Playwright and a server loaded with
 * "manage.py seed_demo --password <DEMO_PASSWORD>". Usage:
 *   node tools/e2e_roles.js http://127.0.0.1:8000 <DEMO_PASSWORD> <ADMIN_PASSWORD>
 * Mobile viewport (390x844): set GPV_MOBILE=1
 */
const { chromium } = require("playwright");
const fs = require("fs"), os = require("os"), path = require("path");
const BASE = process.argv[2] || "http://127.0.0.1:8000", PW = process.argv[3] || "";
const CSV = path.join(os.tmpdir(), "gpv_analista.csv");
fs.writeFileSync(CSV, "Fecha,Turno,Linea,Area,OT,Estacion,Buenas,Rechazo\r\n2026-11-01,T1,SMT-1,SMT,000002,FINAL,11,1\r\n2026-11-01,T2,SMT-1,SMT,000002,FINAL,9,0\r\n2026-13-45,T2,SMT-1,SMT,000002,FINAL,9,0\r\n");
const res = [];
const RUN = Date.now().toString(36); // unique titles: the tool can be repeated on the same database
async function session(b, user, pw) {
  const ctx = await b.newContext({ viewport: process.env.GPV_MOBILE ? { width: 390, height: 844 } : { width: 1280, height: 860 } }); const p = await ctx.newPage();
  p.errs = []; p.on("pageerror", e => p.errs.push(e.message)); p.on("console", m => { if (m.type()==="error" && !/403/.test(m.text())) p.errs.push(m.text()); });
  p.on("dialog", d => d.type()==="prompt" ? d.accept(p.nextPrompt || "") : d.accept());
  await p.goto(BASE+"/entrar/"); await p.fill("#id_username",user); await p.fill("#id_password",pw||PW);
  await Promise.all([p.waitForNavigation(), p.click("button[type=submit]")]); return p;
}
async function step(role, name, p, fn) {
  const before = p.errs.length;
  try { await fn(); const e = p.errs.slice(before); res.push([role,name,e.length?"FAIL":"OK", e.join(" | ").slice(0,200)]); }
  catch (e) { res.push([role,name,"FAIL",e.message.split("\n")[0].slice(0,200)]); }
}
(async () => {
  const b = await chromium.launch();
  // ---------- OPERADOR
  let p = await session(b, "operador1");
  await step("operador","confirmar lectura de comunicado", p, async () => {
    await p.goto(BASE+"/comunicados/"); await p.click("main article h2 a");
    const btn = p.locator("main button:has-text('Confirmar lectura')"); if (await btn.count()) await btn.click();
    await p.waitForSelector("text=Usted confirmó la lectura"); });
  await step("operador","capturar avance en orden asignada", p, async () => {
    await p.goto(BASE+"/"); const link = p.locator("section:has-text('Mis órdenes asignadas') a").first(); await link.click();
    await p.fill("input[name=qty_good]","7"); await Promise.all([p.waitForNavigation(), p.click("text=Registrar avance")]); await p.waitForSelector("text=Avance registrado"); });
  await step("operador","registrar incidencia en la orden", p, async () => {
    await p.selectOption("#comentarios > form select[name=kind]","incident"); await p.fill("#comentarios > form textarea[name=body]","Falta material en alimentador 3 " + RUN);
    await Promise.all([p.waitForNavigation(), p.click("#comentarios > form button[type=submit]")]); await p.waitForSelector("text=Falta material en alimentador 3 " + RUN); });
  await step("operador","proponer Kaizen", p, async () => {
    await p.goto(BASE+"/kaizen/nueva/"); await p.fill("#id_title","Propuesta operador " + RUN); await p.fill("#id_problem","x"); await p.fill("#id_objective","y");
    await p.selectOption("#id_area",{index:1}); await Promise.all([p.waitForNavigation(), p.click("text=Registrar propuesta")]); await p.waitForSelector("text=registrada"); });
  await step("operador","imprimir etiqueta por PDF", p, async () => {
    await p.goto(BASE+"/etiquetas/"); await p.click("a.btn:has-text('Imprimir') >> nth=0");
    const pr = p.locator("input[name^=prompt_]"); if (await pr.count()) await pr.first().fill("Op1");
    await p.click("[data-print-form] button[type=submit]"); await p.waitForSelector("[data-print-box] .alert-ok",{timeout:30000}); });
  await step("operador","ver dashboard y documentos", p, async () => {
    await p.goto(BASE+"/analitica/dashboard/?period=all"); await p.waitForSelector("[data-kpis] .kpi"); await p.goto(BASE+"/documentos/"); });
  await p.context().close();
  // ---------- SUPERVISOR
  p = await session(b, "supervisor1");
  await step("supervisor","publicar comunicado dirigido", p, async () => {
    await p.goto(BASE+"/comunicados/nuevo/"); await p.fill("#id_title","Aviso de supervisor"); await p.fill("#id_body","Contenido");
    await p.check("input[name=areas] >> nth=0"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Publicar')")]); await p.waitForSelector("text=notificado"); });
  await step("supervisor","ver incidencia y marcarla resuelta", p, async () => {
    await p.goto(BASE+"/comunicados/incidencias/"); await p.click("tr:has-text('" + RUN + "') a");
    const card = p.locator(".card:has-text('" + RUN + "')").first(); await card.locator("button:has-text('Marcar resuelta')").click();
    await p.waitForSelector("text=Resuelta por"); await p.goto(BASE+"/comunicados/incidencias/");
    if (await p.locator("tr:has-text('" + RUN + "')").count()) throw new Error("la incidencia resuelta sigue abierta"); });
  await step("supervisor","cambiar meta con motivo", p, async () => {
    await p.goto(BASE+"/produccion/?period=all"); await p.click("table.data tbody tr a >> nth=0");
    await p.fill("#id_qty_planned","321"); await p.fill("#id_reason","Ajuste por pedido del cliente");
    await Promise.all([p.waitForNavigation(), p.click("text=Guardar cambios")]); await p.waitForSelector("text=Ajuste por pedido del cliente"); });
  await step("supervisor","aprobar Kaizen", p, async () => {
    await p.goto(BASE+"/kaizen/"); await p.click("main a:has-text('Propuesta operador " + RUN + "')"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('→ Evaluación')")]);
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('→ Aprobada')")]); await p.waitForSelector("text=Aprobada por"); });
  await step("supervisor","programar reporte", p, async () => {
    await p.goto(BASE+"/analitica/programaciones/nueva/"); await p.fill("input[name=name]","Diario T1"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Guardar')")]);
    await p.waitForSelector("text=Próxima generación"); });
  await step("supervisor","revertir importación", p, async () => {
    await p.goto(BASE+"/produccion/importaciones/"); await p.click("main table.data tbody tr:has-text('Importado') a >> nth=0"); await p.fill("input[name=reason]","Prueba de reversión");
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Revertir')")]); await p.waitForSelector(".flash"); });
  await step("supervisor","reimprimir etiqueta con motivo", p, async () => {
    await p.goto(BASE+"/etiquetas/"); await p.click("table.data a[href*='/trabajos/'] >> nth=0"); await p.fill("input[name=reason]","Etiqueta dañada");
    await p.click("button:has-text('Reimprimir')"); await p.waitForSelector(".jobbox .alert-ok",{timeout:30000}); });
  await p.context().close();
  // ---------- ANALISTA
  p = await session(b, "ingeniero1");
  await step("analista","importar CSV por el asistente (con fila inválida)", p, async () => {
    await p.goto(BASE+"/produccion/importar/"); const val = await p.$eval("select[name=dataset]", s => [...s.options].find(o => o.text.includes("Producción por turno")).value); await p.selectOption("select[name=dataset]", val);
    await p.setInputFiles("#importfile", CSV); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Cargar CSV')")]);
    await p.selectOption("select[name=map_qty_good]","Buenas"); await p.selectOption("select[name=map_qty_reject]","Rechazo");
    await p.check("input[name=allow_partial]"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Validar')")]);
    await p.waitForSelector("text=errores"); await p.click("button:has-text('Importar')"); await p.waitForSelector("#commit-box .alert-ok",{timeout:30000}); });
  await step("analista","crear dashboard con widget y guardar", p, async () => {
    await p.goto(BASE+"/analitica/tableros/"); await p.fill("input[name=name]","Tablero analista"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Crear dashboard')")]);
    await p.click("[data-add]"); await p.click("[data-save]"); await p.waitForSelector("text=Dashboard guardado"); });
  await step("analista","generar reporte de calidad", p, async () => {
    await p.goto(BASE+"/analitica/reportes/"); await p.selectOption("select[name=kind]","quality"); await p.selectOption("form[data-job-form] select[name=period]","all");
    await p.click("button:has-text('Generar reporte')"); await p.waitForSelector("#rep-box .alert-ok",{timeout:60000}); });
  await step("analista","hoja: fórmula, guardar y exportar", p, async () => {
    await p.goto(BASE+"/hojas/"); await p.click("button:has-text('Crear')"); await p.click('.gcell[data-r="0"][data-c="0"]');
    await p.keyboard.type("4"); await p.keyboard.press("Enter"); await p.keyboard.type("=SUMA(A1;6)", { delay: 120 }); await p.keyboard.press("Enter");
    await p.waitForFunction(() => document.querySelector('.gcell[data-r="1"][data-c="0"]').textContent === "10");
    await p.click('[data-act="save"]'); await p.waitForSelector("text=Hoja guardada"); await p.click('[data-act="xlsx"]'); await p.waitForSelector("[data-sheet-result] a"); });
  await step("analista","documento: extraer páginas PDF", p, async () => {
    await p.goto(BASE+"/documentos/?q=muestra_5"); await p.click("a:has-text('muestra_5_paginas.pdf')"); await p.fill("input[name=pages]","2,4");
    await p.click("button:has-text('Generar') >> nth=1"); await p.waitForSelector(".alert-ok",{timeout:30000}); });
  await step("analista","diseñar etiqueta y guardar borrador", p, async () => {
    await p.goto(BASE+"/etiquetas/"); await p.click("a.btn:has-text('Diseñar') >> nth=0"); await p.waitForSelector("[data-paper] svg.render");
    await p.click('[data-add="qr"]'); await p.click('[data-d="save"]'); await p.waitForSelector("text=Borrador guardado"); });
  await p.context().close(); await b.close();
  for (const r of res) console.log(r.join(" · "));
  const bad = res.filter(r => r[2] !== "OK").length;
  console.log(`Resultado: ${res.length - bad}/${res.length} flujos correctos`);
  process.exit(bad ? 1 : 0);
})();
