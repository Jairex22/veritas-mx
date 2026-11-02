/*
 * End-to-end browser check (development tool, NOT required to run the portal).
 * Requires Node + Playwright with Chromium. Usage:
 *   node tools/e2e_smoke.js http://127.0.0.1:8000 admin <password>
 * Visits the main flows on desktop and mobile viewports, clicks key buttons and fails on
 * console errors, failed requests (CSS/JS/images) or HTTP errors.
 */
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const USER = process.argv[3] || "admin";
const PASS = process.argv[4] || "";
const results = [];

function record(name, ok, detail) {
  results.push({ name, ok, detail: detail || "" });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

async function run(viewportName, viewport) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  const problems = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push("console: " + m.text()); });
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  page.on("requestfailed", (r) => problems.push("requestfailed: " + r.url()));
  page.on("response", (r) => { if (r.status() >= 500 || (r.status() === 404 && /\/static\//.test(r.url()))) problems.push("http " + r.status() + " " + r.url()); });
  page.on("dialog", (d) => d.accept());

  const check = async (name, fn) => {
    const before = problems.length;
    try {
      await fn();
      const newProblems = problems.slice(before);
      record(viewportName + " · " + name, newProblems.length === 0, newProblems.join(" | "));
    } catch (e) {
      record(viewportName + " · " + name, false, e.message.split("\n")[0]);
    }
  };

  await check("login", async () => {
    await page.goto(BASE + "/entrar/");
    await page.fill("#id_username", USER);
    await page.fill("#id_password", PASS);
    await Promise.all([page.waitForNavigation(), page.click("button[type=submit]")]);
    if (!(await page.isVisible("text=Inicio"))) throw new Error("no se mostró Inicio");
    const css = await page.evaluate(() => getComputedStyle(document.querySelector(".topbar")).position);
    if (css !== "fixed") throw new Error("CSS no aplicado");
  });

  const pages = ["/", "/comunicados/", "/produccion/?period=all", "/produccion/importar/", "/produccion/registros/?period=all", "/analitica/dashboard/?period=all",
    "/analitica/reportes/", "/analitica/tableros/", "/hojas/", "/documentos/", "/etiquetas/", "/kaizen/", "/administracion/", "/administracion/diagnostico/"];
  for (const p of pages) {
    await check("página " + p, async () => {
      const r = await page.goto(BASE + p);
      if (!r || r.status() !== 200) throw new Error("HTTP " + (r && r.status()));
      await page.waitForLoadState("networkidle");
      const broken = await page.evaluate(() => [...document.images].filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.src));
      if (broken.length) throw new Error("imágenes rotas: " + broken.join(", "));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 4 && !/hojas|etiquetas\/\d/.test(location.pathname)) throw new Error("desbordamiento horizontal de " + overflow + "px");
    });
  }

  await check("dashboard filtra al hacer clic en una barra", async () => {
    await page.goto(BASE + "/analitica/dashboard/?period=all");
    await page.waitForSelector('[data-chart="by_line"] rect.bar');
    await page.locator('[data-chart="by_line"] rect.bar').first().click();
    await page.waitForSelector("[data-chips] .chip");
  });

  await check("generar reporte (PDF+XLSX)", async () => {
    await page.goto(BASE + "/analitica/reportes/");
    await page.selectOption("select[name=kind]", "daily");
    await page.selectOption('form[data-job-form] select[name=period]', "all");
    await page.click("text=Generar reporte >> nth=-1");
    await page.waitForSelector("#rep-box .alert-ok", { timeout: 60000 });
    const links = await page.locator("#rep-box a").count();
    if (links < 2) throw new Error("sin enlaces de descarga");
  });

  await check("hoja de cálculo: editar, fórmula y guardar", async () => {
    await page.goto(BASE + "/hojas/");
    await page.click("text=Crear");
    await page.waitForSelector("[data-viewport]");
    await page.click('.gcell[data-r="0"][data-c="0"]');
    await page.keyboard.type("5");
    await page.keyboard.press("Enter");
    await page.keyboard.type("=A1*3", { delay: 120 }); // human speed: recalculation may arrive mid-edit
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.querySelector('.gcell[data-r="1"][data-c="0"]').textContent === "15");
    await page.click('[data-act="save"]');
    await page.waitForSelector("text=Hoja guardada");
  });

  await check("documentos: cortar PDF", async () => {
    await page.goto(BASE + "/documentos/?q=muestra_5");
    await page.click("text=muestra_5_paginas.pdf");
    await page.fill("input[name=groups]", "1,3;2,4-5");
    await page.click("text=Cortar PDF >> nth=-1");
    await page.waitForSelector(".alert-ok", { timeout: 60000 });
  });

  await check("etiquetas: diseñador renderiza vista previa", async () => {
    await page.goto(BASE + "/etiquetas/");
    await page.click('a.btn:has-text("Diseñar") >> nth=0');
    await page.waitForSelector("[data-paper] svg.render", { timeout: 20000 });
    await page.click('[data-add="code128"]');
    await page.waitForTimeout(800);
  });

  await check("etiquetas: imprimir por navegador (PDF) con confirmación", async () => {
    await page.goto(BASE + "/etiquetas/");
    await page.click('a.btn:has-text("Imprimir") >> nth=0');
    const prompt = page.locator("input[name^=prompt_]");
    if (await prompt.count()) await prompt.first().fill("Prueba E2E");
    await page.click("[data-print-form] button[type=submit]");
    await page.waitForSelector("[data-print-box] .alert-ok", { timeout: 60000 });
  });

  await check("kaizen: nueva mejora", async () => {
    await page.goto(BASE + "/kaizen/nueva/");
    await page.fill("#id_title", "Mejora E2E");
    await page.fill("#id_problem", "Problema de prueba");
    await page.fill("#id_objective", "Objetivo de prueba");
    await page.selectOption("#id_area", { index: 1 });
    await Promise.all([page.waitForNavigation(), page.click("text=Registrar propuesta")]);
    if (!(await page.isVisible("text=Mejora E2E"))) throw new Error("no se creó");
  });

  if (viewport.width < 600) {
    await check("menú móvil", async () => {
      await page.goto(BASE + "/");
      await page.click("[data-nav-toggle]");
      await page.waitForSelector(".sidebar.open");
      await page.click(".sidebar >> text=Kaizen");
      await page.waitForURL(/kaizen/);
    });
  }
  await page.screenshot({ path: "e2e_" + viewportName + ".png", fullPage: false });
  await browser.close();
}

(async () => {
  await run("escritorio", { width: 1366, height: 860 });
  await run("movil", { width: 390, height: 844 });
  const failed = results.filter((r) => !r.ok);
  console.log("\nResumen: " + (results.length - failed.length) + "/" + results.length + " verificaciones correctas");
  process.exit(failed.length ? 1 : 0);
})();
