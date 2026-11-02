/*
 * Role-based audit (development tool). Requires Node + Playwright and a server loaded with
 * "manage.py seed_demo --password <DEMO_PASSWORD>". Usage:
 *   node tools/e2e_crawl_roles.js http://127.0.0.1:8000 <DEMO_PASSWORD> <ADMIN_PASSWORD>
 */
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8000";
const DEMO = process.argv[3] || "", ADMIN = process.argv[4] || "";
const roles = [["operador1",DEMO],["lector1",DEMO],["supervisor1",DEMO],["ingeniero1",DEMO],["admin",ADMIN]];
let total = 0;
(async () => {
  const b = await chromium.launch();
  for (const [u, pw] of roles) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } }); const p = await ctx.newPage();
    const issues = []; let cur = "";
    p.on("console", m => { if (m.type()==="error") issues.push(`console ${cur}: ${m.text().slice(0,160)}`); });
    p.on("pageerror", e => issues.push(`pageerror ${cur}: ${e.message.slice(0,160)}`));
    p.on("dialog", d => d.dismiss());
    await p.goto(BASE+"/entrar/"); await p.fill("#id_username",u); await p.fill("#id_password",pw);
    await Promise.all([p.waitForNavigation(), p.click("button[type=submit]")]);
    if (p.url().includes("contrasena")) issues.push("redirigido a cambio de contraseña");
    const seen = new Set(), queue = ["/"]; let n = 0;
    while (queue.length && n < 260) {
      const path = queue.shift(); if (seen.has(path)) continue; seen.add(path); n++; cur = path;
      let r; try { r = await p.goto(BASE+path, { waitUntil: "load", timeout: 30000 }); } catch (e) { issues.push(`goto ${path}: ${e.message.slice(0,100)}`); continue; }
      const ct = (r && r.headers()["content-type"]) || "";
      if (!r || r.status() >= 400) { issues.push(`HTTP ${r && r.status()} ${path}`); continue; }
      if (!ct.includes("text/html")) continue;
      await p.waitForTimeout(250);
      const links = await p.evaluate(() => [...document.querySelectorAll("a[href]")].map(a => a.getAttribute("href")));
      for (let h of links) {
        if (!h || h.startsWith("#") || h.startsWith("http") || h.startsWith("javascript") || h.startsWith("mailto")) continue;
        if (!h.startsWith("/")) { try { h = new URL(h, BASE+path).pathname + new URL(h, BASE+path).search; } catch { continue; } }
        if (/\/salir\/|\/archivos\/|exportar|\.pdf|\.zpl|\.svg|\.json|zip\/|page=|django-admin|\/versiones\/\?v=/.test(h)) continue;
        const key = h.replace(/\d+/g, "N");
        if ([...seen].filter(s => s.replace(/\d+/g,"N")===key).length >= 2) continue;
        if (!seen.has(h)) queue.push(h);
      }
    }
    console.log(`== ${u}: ${n} páginas, ${issues.length} problemas`);
    issues.forEach(i => console.log("   " + i));
    total += issues.length;
    await ctx.close();
  }
  await b.close();
  console.log(total ? `Resultado: ${total} problemas` : "Resultado: 0 problemas");
  process.exit(total ? 1 : 0);
})();
