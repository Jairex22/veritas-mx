// Consulta directa OData: conectar a un servidor, buscar caja / serial / orden y listar seriales.
import { get, post } from "../api.js";
import { card, chip, dataTable, emptyState, errorAlert, h, icon, loading, mount, pageHead, statusChip, toast } from "../ui.js";

export async function render(root) {
  let status, entitySets = [];
  const connPanel = h("div");
  const searchPanel = h("div");
  const results = h("div", { class: "stack" });
  mount(root, pageHead("Consulta directa OData", "Conecte al servicio OData de FactoryLogix y busque una caja, serial u orden: se consulta en todas las entidades y se listan los seriales encontrados. Sólo lectura."),
    h("div", { class: "stack" }, connPanel, searchPanel, results));
  try { status = await get("/api/explorer/status"); } catch (e) { mount(connPanel, errorAlert(e)); return; }

  // ---------------- conexión ----------------
  const url = h("input", { class: "input mono", placeholder: "10.62.54.10/odata", value: status.session?.base_url || status.server_default_url || "", maxlength: 300 });
  const auth = h("select", { class: "input" }, [["none", "Sin credenciales"], ["basic", "Usuario y contraseña (Basic)"], ["ntlm", "Windows (NTLM)"]].map(([v, l]) => h("option", { value: v, selected: (status.session?.auth || "none") === v }, l)));
  const user = h("input", { class: "input", placeholder: "DOMINIO\\usuario", autocomplete: "off", value: status.session?.username || "" });
  const pass = h("input", { class: "input", type: "password", placeholder: "contraseña", autocomplete: "new-password" });
  const credRow = h("div", { class: "form-grid" }, h("label", { class: "field" }, "Usuario", user), h("label", { class: "field" }, "Contraseña (sólo en memoria durante la sesión)", pass));
  const syncCred = () => credRow.classList.toggle("hidden", auth.value === "none");
  auth.addEventListener("change", syncCred); syncCred();
  const connState = h("div");
  const connectBtn = h("button", { class: "btn primary", onclick: () => connect(false) }, icon("plug", "sm"), "Conectar");
  const serverBtn = status.server_default_url ? h("button", { class: "btn", onclick: () => connect(true), title: status.server_default_url }, icon("lock", "sm"), "Usar configuración del servidor") : null;

  async function connect(useServer) {
    connectBtn.classList.add("loading");
    mount(connState, h("span", { class: "muted" }, "Leyendo $metadata…"));
    try {
      const r = await post("/api/explorer/connect", { base_url: url.value.trim(), auth: auth.value, username: user.value.trim(), password: pass.value, use_server_config: useServer });
      status.session = r.session; entitySets = r.entity_sets; pass.value = "";
      drawConn();
      if (r.session.state === "OK") { toast(`Conectado: ${entitySets.length} entidades disponibles.`, "ok"); drawSearch(); searchInput.focus(); }
      else toast(r.session.message, "err");
    } catch (e) { mount(connState, errorAlert(e)); toast(e.message, "err", e.correlationId); }
    finally { connectBtn.classList.remove("loading"); }
  }
  function drawConn() {
    const s = status.session;
    mount(connState, s ? h("div", { class: "stack", style: { gap: "6px" } },
      h("div", { class: "row" }, statusChip(s.state), s.version ? chip(`OData ${s.version}`, "outline") : null, s.state === "OK" ? chip(`${s.entity_set_count} entidades`, "ok") : null,
        h("span", { class: "mono faint", style: { fontSize: "12px" } }, s.base_url)),
      h("div", { class: "muted", style: { fontSize: "12px" } }, s.message),
      s.diagnosis.length ? h("div", { class: "alert warn" }, icon("alert"), h("div", null, h("ul", { style: { margin: 0 } }, s.diagnosis.map((d) => h("li", null, d))))) : null) : null);
  }
  mount(connPanel, card("Servidor OData", h("div", { class: "stack", style: { gap: "10px" } },
    h("div", { class: "form-grid" }, h("label", { class: "field" }, "URL del servicio (ej. 10.62.54.10/odata)", url), h("label", { class: "field" }, "Autenticación", auth)),
    credRow, h("div", { class: "row" }, connectBtn, serverBtn), connState), { iconName: "plug" }));
  drawConn();

  // ---------------- búsqueda ----------------
  const searchInput = h("input", { class: "input scan-input", placeholder: "Escanee o escriba caja, serial u orden…", autocomplete: "off", maxlength: 128 });
  const match = h("select", { class: "input", style: { maxWidth: "200px" } }, h("option", { value: "eq" }, "Coincidencia exacta"), h("option", { value: "contains" }, "Contiene el texto"));
  const scope = h("select", { class: "input", style: { maxWidth: "280px" } });
  const propSel = h("select", { class: "input", style: { maxWidth: "280px" } });
  const browseBtn = h("button", { class: "btn", onclick: browse }, icon("file", "sm"), "Ver primeras filas de la entidad");
  function drawSearch() {
    mount(scope, h("option", { value: "" }, "Buscar en todas las entidades (automático)"), entitySets.map((e) => h("option", { value: e.name }, `${e.name} (${e.properties.length} propiedades)`)));
    syncProps();
    mount(searchPanel, card("Buscar", h("div", { class: "stack" },
      h("form", { onsubmit: (e) => { e.preventDefault(); search(); } }, searchInput),
      h("div", { class: "row" }, match, scope, propSel, h("button", { class: "btn primary", onclick: search }, icon("search", "sm"), "Buscar"), browseBtn),
      h("p", { class: "faint", style: { margin: 0, fontSize: "12px" } }, "Automático: consulta las propiedades de texto cuyo nombre sugiere serial, orden, caja, lote, panel o identificador. Elija una entidad y propiedad para una búsqueda precisa.")),
      { iconName: "scan" }));
  }
  function syncProps() {
    const es = entitySets.find((e) => e.name === scope.value);
    mount(propSel, h("option", { value: "" }, es ? "Todas las propiedades de texto" : "—"),
      es ? es.properties.filter((p) => p.type.endsWith("String")).map((p) => h("option", { value: p.name }, p.name)) : []);
    propSel.disabled = !es; browseBtn.disabled = !es;
  }
  scope.addEventListener("change", syncProps);

  async function search() {
    const value = searchInput.value.trim();
    if (!value) { searchInput.focus(); return; }
    mount(results, loading(3));
    let r;
    try { r = await post("/api/explorer/search", { value, match: match.value, entity_set: scope.value || null, property: propSel.value || null }); }
    catch (e) { mount(results, errorAlert(e)); return; }
    const serialList = h("div", { class: "row" }, r.serials.map((s) => h("span", { class: "chip outline mono", title: s.sources.join(", ") }, s.serial)));
    const csv = () => {
      const lines = ["serial,origen", ...r.serials.map((s) => `${s.serial},"${s.sources.join("; ")}"`)];
      const a = h("a", { href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: `seriales_${value}.csv` }); a.click();
    };
    const copy = async () => { try { await navigator.clipboard.writeText(r.serials.map((s) => s.serial).join("\n")); toast("Seriales copiados.", "ok"); } catch { toast("No se pudo copiar.", "warn"); } };
    mount(results,
      h("div", { class: "row" }, chip(`${r.queries} consultas`, "outline"), chip(`${r.hits.length} entidades con coincidencias`, r.hits.length ? "ok" : "neutral"),
        chip(`${r.serials.length} seriales`, r.serials.length ? "ok" : "neutral"), r.error_count ? chip(`${r.error_count} propiedades no filtrables`, "warn") : null,
        r.truncated ? chip("búsqueda recortada: elija una entidad", "warn") : null, h("span", { class: "source-tag" }, icon("database", "sm"), r.source.label)),
      card(`Seriales relacionados con “${r.value}”`, r.serials.length ? h("div", { class: "stack" }, serialList,
        h("div", { class: "row" }, h("button", { class: "btn sm", onclick: copy }, "Copiar lista"), h("button", { class: "btn sm", onclick: csv }, "Descargar CSV")))
        : emptyState("Sin seriales derivados", r.hits.length ? "Hubo coincidencias pero ninguna columna parece un serial; revise las tablas abajo." : "Ninguna entidad devolvió filas para ese valor. Pruebe “Contiene el texto” o una entidad concreta.", "trace"),
        { iconName: "trace" }),
      ...r.hits.map((hit) => card(`${hit.entity_set} · ${hit.property} (${hit.count} filas)`, rowsTable(hit.columns, hit.rows), { iconName: "layers" })),
      r.errors.length ? h("details", null, h("summary", { style: { cursor: "pointer" } }, `Propiedades que el servidor no pudo filtrar (${r.error_count})`),
        h("ul", null, r.errors.map((e) => h("li", { class: "faint", style: { fontSize: "12px" } }, `${e.entity_set}.${e.property}: ${e.error}`)))) : null);
  }

  async function browse() {
    if (!scope.value) return;
    mount(results, loading(2));
    try {
      const r = await post("/api/explorer/rows", { entity_set: scope.value, top: 50 });
      mount(results, card(`${r.entity_set} · primeras ${r.count} filas`, r.count ? rowsTable(r.columns, r.rows) : emptyState("Sin filas", null, "file"), { iconName: "file" }));
    } catch (e) { mount(results, errorAlert(e)); }
  }

  function rowsTable(columns, rows) {
    const cols = columns.slice(0, 18);
    return dataTable(cols.map((c) => ({ key: c, label: c, render: (r) => h("span", { class: "mono", style: { fontSize: "11px" } }, r[c] === null || r[c] === undefined ? "—" : String(r[c]).slice(0, 80)) })), rows);
  }

  if (status.session?.state === "OK") {
    try { const r = await post("/api/explorer/connect", { base_url: status.session.base_url, auth: "none", use_server_config: false }); entitySets = r.entity_sets; } catch { /* reconexión manual */ }
    if (entitySets.length) drawSearch();
  }
}
