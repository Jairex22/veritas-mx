import { get, post } from "../api.js";
import { card, chip, errorAlert, fmtDate, h, icon, loading, mount, pageHead, statusChip, toast } from "../ui.js";

const INTEGRATIONS = [
  ["Generador DEMO", "Implementado", "ok", "Datos sintéticos deterministas; sólo modo DEMO."],
  ["OData · prueba de conexión", "Implementado", "ok", "GET $metadata, diagnóstico 401/403/404/5xx/TLS/timeout, descubrimiento de EntitySets."],
  ["OData · lectura de trazabilidad", "Implementado · requiere mapeo", "warn", "Requiere config/odata_mapping.json verificado tras inspeccionar $metadata. No se asumen nombres de entidades."],
  ["OData · autenticación Windows (NTLM/Negotiate)", "Pendiente", "neutral", "Requiere aprobación de TI y librería adicional."],
  ["xTend API · transacciones", "Pendiente de verificación", "neutral", "Sin métodos verificados. Documentación oficial no accesible desde el entorno de desarrollo."],
  ["FactoryLogixAPI", "Pendiente de verificación", "neutral", "Sólo endpoints documentados y verificados para esta instalación (ninguno registrado)."],
  ["Archivos auxiliares CSV", "Implementado", "ok", "events.csv / defects.csv en GPV_AUX_DIR, sólo lectura."],
  ["Archivos XML de diagnóstico", "Parcial", "warn", "Listado de archivos; el parser depende del formato de exportación de GPV."],
  ["Impresoras Zebra/CAB (estado TCP)", "Implementado", "ok", "Comprobación de puerto (sin enviar datos). Impresión real deshabilitada en v1.0."],
  ["BarTender Integration", "Pendiente", "neutral", "Requiere Integration Builder / REST API aprobado."],
  ["Autenticación corporativa (SSO)", "Pendiente", "neutral", "OIDC/Entra ID o LDAP aprobado por TI."],
];

export async function render(root, { can, refreshStatus }) {
  const body = h("div", null, loading(4));
  mount(root, pageHead("Conectores", "Detección de capacidades y diagnóstico de conexión. La configuración se gestiona en el servidor; las credenciales nunca llegan al navegador."), body);
  let d;
  try { d = await get("/api/connectors"); } catch (e) { mount(body, errorAlert(e)); return; }

  const connCard = (c) => {
    const slot = h("div");
    const draw = (c) => mount(slot, card(c.name, h("div", { class: "stack", style: { gap: "10px" } },
      h("div", { class: "row" }, statusChip(c.state), chip(c.kind, "outline"), c.capabilities.read ? chip("LECTURA", "ok") : chip("SIN LECTURA", "neutral"), chip(c.capabilities.write ? "ESCRITURA" : "SIN ESCRITURA", c.capabilities.write ? "err" : "neutral")),
      h("p", { style: { margin: 0 } }, c.message),
      h("dl", { class: "kv", style: { fontSize: "12px" } },
        h("dt", null, "Propósito"), h("dd", null, c.purpose),
        h("dt", null, "URL / ruta"), h("dd", { class: "mono" }, c.base_url || "—"),
        h("dt", null, "Credencial"), h("dd", null, c.credential),
        h("dt", null, "HTTP"), h("dd", null, c.http_status ?? "—"),
        h("dt", null, "Latencia"), h("dd", null, c.latency_ms != null ? `${c.latency_ms} ms` : "—"),
        h("dt", null, "Comprobado"), h("dd", null, c.checked_at ? fmtDate(c.checked_at) : "nunca")),
      c.diagnosis.length ? h("div", { class: `alert ${["OK", "SIMULATED"].includes(c.state) ? "info" : "warn"}` }, icon("info"), h("div", null, h("b", null, "Diagnóstico"), h("ul", null, c.diagnosis.map((x) => h("li", null, x))))) : null,
      c.discovered && c.discovered.entity_sets ? h("details", null, h("summary", { style: { cursor: "pointer" } }, `EntitySets descubiertos (${c.discovered.entity_set_count})`),
        h("div", { class: "row", style: { marginTop: "8px" } }, c.discovered.entity_sets.map((x) => chip(x, "outline")))) : null,
      c.discovered && c.discovered.files ? h("details", null, h("summary", { style: { cursor: "pointer" } }, `Archivos (${c.discovered.files.length})`),
        h("div", { class: "row", style: { marginTop: "8px" } }, c.discovered.files.map((x) => chip(x, "outline")))) : null),
      { iconName: c.kind === "FILES" ? "file" : c.kind === "DEMO" ? "cpu" : "plug",
        actions: can("connectors.probe") ? [h("button", { class: "btn sm", onclick: async (e) => {
          const b = e.currentTarget; b.classList.add("loading");
          try { const r = await post(`/api/connectors/${c.id}/probe`); draw(r); toast(`${r.name}: ${r.message}`, r.state === "OK" || r.state === "SIMULATED" ? "ok" : r.state === "NOT_CONFIGURED" ? "info" : "err"); refreshStatus(); }
          catch (err) { toast(err.message, "err"); } finally { b.classList.remove("loading"); }
        } }, icon("refresh", "sm"), "Probar conexión")] : null }));
    draw(c);
    return slot;
  };
  const cfg = d.configuration;
  mount(body, h("div", { class: "stack" },
    h("div", { class: "grid g-2" },
      card("Fuente de datos activa", h("div", { class: "stack", style: { gap: "8px" } },
        h("div", { class: "row" }, h("b", { style: { fontSize: "16px" } }, d.active_source.label), d.active_source.synthetic ? chip("SINTÉTICO", "demo") : chip(d.active_source.kind, d.active_source.kind === "NONE" ? "err" : "info")),
        d.source_note ? h("div", { class: "alert warn" }, icon("alert"), h("div", null, d.source_note)) : null), { iconName: "database" }),
      card("Configuración del servidor", h("dl", { class: "kv", style: { fontSize: "12px" } },
        h("dt", null, "Modo"), h("dd", null, chip(cfg.mode, cfg.mode === "DEMO" ? "demo" : "info")),
        h("dt", null, "Fuente REAL"), h("dd", { class: "mono" }, cfg.real_data_source),
        h("dt", null, "Mapeo OData"), h("dd", { class: "mono" }, cfg.odata_mapping_file),
        h("dt", null, "Timeout HTTP"), h("dd", null, `${cfg.http_timeout_seconds} s`),
        h("dt", null, "Verificación TLS"), h("dd", null, cfg.verify_tls ? chip("ACTIVA", "ok") : chip("DESACTIVADA", "err"), cfg.ca_bundle ? " · CA corporativa" : ""),
        h("dt", null, "Escrituras en producción"), h("dd", null, cfg.allow_production_writes ? chip("INTERRUPTOR ACTIVO", "warn") : chip("DESHABILITADAS", "ok")),
        h("dt", null, "Ejecutores reales"), h("dd", null, cfg.real_executors_registered.length ? cfg.real_executors_registered.join(", ") : "Ninguno registrado (v1.0)"),
        h("dt", null, "Gestión"), h("dd", null, cfg.managed_by)), { iconName: "lock" })),
    h("div", { class: "grid g-2" }, d.connectors.map(connCard)),
    card("Integraciones verificadas y pendientes", h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", null, h("tr", null, h("th", null, "Integración"), h("th", null, "Estado"), h("th", null, "Notas"))),
      h("tbody", null, INTEGRATIONS.map(([n, st, tone, note]) => h("tr", null, h("td", null, h("b", null, n)), h("td", null, chip(st, tone)), h("td", { class: "muted" }, note)))))),
      { iconName: "layers" })));
}
