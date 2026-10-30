import { api, post } from "../api.js";
import { brandMark, chip, errorAlert, h, icon, mount, toast } from "../ui.js";

const ROLE_ICON = { operator: "user", engineering: "cpu", quality: "shield", admin: "lock" };
const ROLE_DESC = {
  operator: "Consulta, packing, etiquetas y registro en estación.",
  engineering: "Diagnóstico, trazabilidad completa y conectores.",
  quality: "HOLD / liberación, reimpresiones y auditoría.",
  admin: "Todos los permisos autorizados y reinicio DEMO.",
};

export async function render(root, { state, onLogin }) {
  const st = state.status || {};
  const panel = h("div", { class: "stack" }, h("div", { class: "skeleton", style: { height: "240px" } }));
  mount(root, h("div", { class: "login-wrap" },
    h("section", { class: "login-hero" }, h("div", { class: "hero-grid" }),
      h("div", { class: "row", style: { position: "relative" } }, brandMark(), h("b", { style: { letterSpacing: ".1em" } }, "GPV AMERICAS")),
      h("div", { style: { position: "relative" } },
        h("h1", null, "FactoryLogix", h("br"), "Command Center"),
        h("p", null, "Trazabilidad, diagnóstico inteligente de rework y operaciones controladas sobre FactoryLogix, con auditoría completa y estados de conexión veraces."),
        h("div", { class: "features" },
          [["trace", "Trazabilidad por serial, orden, panel y estación"], ["rework", "Diagnóstico con evidencia y nivel de confianza"],
           ["shield", "Acciones con confirmación, roles y auditoría"], ["plug", "Conectores OData / xTend con detección de capacidades"]]
            .map(([i, t]) => h("div", { class: "feature" }, icon(i), t)))),
      h("div", { class: "faint", style: { position: "relative", fontSize: "12px" } }, `v${st.version || "1.0"} · Uso interno GPV Americas`)),
    h("section", { class: "login-panel" }, panel)));

  let providers;
  try {
    providers = await api("/api/auth/providers");
  } catch (e) {
    mount(panel, errorAlert(e, "No se pudo contactar al servidor"));
    return;
  }
  const demo = providers.providers.find((p) => p.id === "demo");
  const corp = providers.providers.find((p) => p.id === "corporate");
  const badges = h("div", { class: "row" }, (st.badges || []).map((b) => h("span", { class: `badge-env ${b.tone}`, title: b.description }, b.label)));

  const login = async (btn, username) => {
    btn.classList.add("loading");
    try {
      onLogin(await post("/api/auth/login", { provider: "demo", username }));
    } catch (e) {
      toast(e.message, "err", e.correlationId ? `ID: ${e.correlationId}` : undefined);
      btn.classList.remove("loading");
    }
  };

  const loginCorp = async (btn) => {
    btn.classList.add("loading");
    try { onLogin(await post("/api/auth/login", { provider: "corporate" })); }
    catch (e) { toast(e.message, "err", e.correlationId ? `ID: ${e.correlationId}` : undefined); btn.classList.remove("loading"); }
  };

  mount(panel,
    h("div", null, h("h2", { style: { margin: "0 0 6px", fontSize: "22px" } }, "Iniciar sesión"), h("p", { class: "muted", style: { margin: 0 } }, "Seleccione el mecanismo de acceso.")),
    badges,
    st.mode === "DEMO" ? h("div", { class: "alert demo" }, icon("cpu"), h("div", null, h("b", null, "Entorno de demostración"),
      "Todos los datos son sintéticos (prefijo DEMO) y las operaciones se simulan en memoria. Ninguna acción alcanza FactoryLogix.")) : null,
    st.mode === "REAL" && st.source_note ? h("div", { class: "alert warn" }, icon("alert"), h("div", null, h("b", null, "Estado de la fuente de datos"), st.source_note)) : null,
    corp ? (corp.available
      ? (() => { const b = h("button", { class: "role-card", onclick: () => loginCorp(b) }, h("span", { class: "avatar" }, icon("lock")),
          h("div", { style: { flex: 1 } }, h("b", null, corp.label), h("div", { class: "muted", style: { fontSize: "12px" } }, "Autenticación Integrada de Windows a través del servidor IIS autorizado.")), icon("chevronRight")); return b; })()
      : h("div", { class: "role-card", style: { cursor: "default", opacity: .75 } }, h("span", { class: "avatar" }, icon("lock")),
          h("div", { style: { flex: 1 } }, h("b", null, corp.label, " "), chip("NO DISPONIBLE", "neutral"), h("div", { class: "muted", style: { fontSize: "12px", marginTop: "4px" } }, corp.reason)))) : null,
    demo && demo.available
      ? h("div", { class: "stack", style: { gap: "10px" } }, h("div", { class: "nav-group", style: { margin: "6px 0 0" } }, "ACCESO DEMO · SIN CONTRASEÑA"),
          demo.users.map((u) => {
            const btn = h("button", { class: "role-card", onclick: () => login(btn, u.username) },
              h("span", { class: "avatar" }, icon(ROLE_ICON[u.role] || "user")),
              h("div", { style: { flex: 1 } }, h("b", null, u.role_label, " "), chip("DEMO", "demo"),
                h("div", { class: "muted", style: { fontSize: "12px" } }, ROLE_DESC[u.role] || ""), h("div", { class: "faint mono", style: { fontSize: "11px" } }, u.username)),
              icon("chevronRight"));
            return btn;
          }))
      : h("div", { class: "alert info" }, icon("info"), h("div", null, h("b", null, "Acceso DEMO deshabilitado"), demo ? demo.reason : "")),
  );
}
