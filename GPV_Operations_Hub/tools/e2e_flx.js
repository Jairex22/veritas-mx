/*
 * FactoryLogix Connection Center (development tool) against the SIMULATED server tools/fake_flx_dev.py.
 *   node tools/e2e_flx.js http://127.0.0.1:8040 <ADMIN_PASSWORD> <TECH_PASSWORD> <DEMO_PASSWORD>
 * Mobile viewport: GPV_MOBILE=1
 */
const { chromium } = require("playwright");
const [BASE, APW, TPW, DPW] = [process.argv[2] || "http://127.0.0.1:8040", process.argv[3], process.argv[4], process.argv[5]];
const MOBILE = !!process.env.GPV_MOBILE, res = [];
async function session(b, u, pw) {
  const ctx = await b.newContext({ viewport: MOBILE ? { width: 390, height: 844 } : { width: 1280, height: 860 } }); const p = await ctx.newPage();
  p.errs = []; p.on("pageerror", (e) => p.errs.push(e.message)); p.on("console", (m) => { if (m.type() === "error" && !/40[03]|502|Failed to load/.test(m.text())) p.errs.push(m.text()); });
  p.on("dialog", (d) => d.accept());
  await p.goto(BASE + "/entrar/"); await p.fill("#id_username", u); await p.fill("#id_password", pw);
  await Promise.all([p.waitForNavigation(), p.click("button[type=submit]")]); return p;
}
async function step(who, name, p, fn) {
  const n = p.errs.length;
  try { await fn();
    if (MOBILE) { const [o, w] = await p.evaluate(() => [document.documentElement.scrollWidth - innerWidth, location.pathname]); if (o > 2) p.errs.push(`desborde ${o}px ${w}`); }
    const e = p.errs.slice(n); res.push([who, name, e.length ? "FAIL" : "OK", e.join(" | ").slice(0, 200)]);
  } catch (e) { res.push([who, name, "FAIL", e.message.split("\n")[0].slice(0, 200)]); }
}
(async () => {
  const b = await chromium.launch();
  let p = await session(b, "admin", APW);
  await step("admin", "Connection Center antes de leer esquema", p, async () => { await p.goto(BASE + "/factorylogix/"); await p.waitForSelector("text=Aún no se ha leído el $metadata"); });
  await step("admin", "Probar y leer $metadata (etapas)", p, async () => {
    await Promise.all([p.waitForNavigation(), p.click("button:has-text('Probar y leer $metadata')")]);
    await p.waitForSelector("text=Lectura de $metadata"); if (await p.locator("section:has-text('Resultado de la prueba') .tag-err").count()) throw new Error("etapa con error"); });
  await step("admin", "sondeo controlado requiere autorización y muestra estados", p, async () => {
    await p.check("input[name=confirm]"); await p.click("button:has-text('Sondear entidades')");
    await p.waitForSelector("td:has-text('FORBIDDEN')", { timeout: 60000 }); /* the finished job reloads the page */ await p.waitForSelector("td:has-text('SCHEMA MISMATCH')"); });
  await step("admin", "probar capacidades de WIP", p, async () => {
    await p.click("a:has-text('WIP')"); await Promise.all([p.waitForNavigation(), p.click("button:has-text('Probar capacidades')")]);
    await p.waitForSelector("text=Capacidades verificadas"); await p.waitForSelector(".tag-err:has-text('$skip: no')"); });
  await step("admin", "consulta controlada con filtro y procedencia", p, async () => {
    await p.selectOption("select[name=f0_prop]", "WorkOrder"); await p.fill("input[name=f0_value]", "W07481"); await p.check("input[name=count]");
    await p.click("button:has-text('Consultar')"); await p.waitForSelector("[data-flx-out] table");
    const t = await p.locator("[data-flx-out]").innerText(); if (!/de 3/.test(t) || !/FactoryLogix OData/.test(t)) throw new Error("conteo/fuente: " + t.slice(0, 120)); });
  await step("admin", "valor inválido muestra error comprensible", p, async () => {
    await p.selectOption("select[name=f0_prop]", "Qty"); await p.fill("input[name=f0_value]", "abc"); await p.click("button:has-text('Consultar')");
    await p.waitForSelector("[data-flx-out] .alert-err:has-text('no es numérico')"); });
  await p.context().close();
  p = await session(b, "tecnico1", TPW);
  await step("técnico", "ve estado pero no acciones ni consultas", p, async () => {
    await p.goto(BASE + "/factorylogix/"); await p.waitForSelector("text=FactoryLogix Connection Center");
    if (await p.locator("button:has-text('Probar conexión')").count()) throw new Error("ve acciones de administrador");
    await p.goto(BASE + "/factorylogix/entidad/WIP/"); if (await p.locator("[data-flx-query]").count()) throw new Error("ve consulta"); });
  await p.context().close();
  p = await session(b, "operador1", DPW);
  await step("operador", "sin acceso (403) y sin enlace en el menú", p, async () => {
    if (await p.locator("nav a[href='/factorylogix/']").count()) throw new Error("enlace visible");
    const r = await p.goto(BASE + "/factorylogix/"); if (r.status() !== 403) throw new Error("status " + r.status()); });
  await b.close();
  const f = res.filter((r) => r[2] !== "OK");
  console.log((MOBILE ? "[móvil] " : "[escritorio] ") + res.length + " pasos, " + f.length + " fallas"); res.forEach((r) => console.log(r.join(" · ")));
  process.exit(f.length ? 1 : 0);
})();
