import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { clearAdminSession, getAdminBusinessName, getAdminToken } from "../../lib/adminAuth";

const NAV_ITEMS = [
  { to: "/admin", label: "Panel", end: true },
  { to: "/admin/business", label: "Negocio" },
  { to: "/admin/catalog", label: "Catálogo" },
  { to: "/admin/requests", label: "Solicitudes" },
  { to: "/admin/conversations", label: "Conversaciones" },
  { to: "/admin/unanswered", label: "Preguntas sin responder" },
  { to: "/admin/ai-usage", label: "Consumo de IA" },
];

export default function AdminLayout() {
  const token = getAdminToken();
  const navigate = useNavigate();
  if (!token) return <Navigate to="/admin/login" replace />;

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "var(--cf-font)" }}>
      <aside style={{ width: 220, background: "var(--cf-graphite)", color: "var(--cf-ivory)", padding: 16, flexShrink: 0 }}>
        <div style={{ fontWeight: 800, marginBottom: 4 }}>ClickFlow Local</div>
        <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 20 }}>{getAdminBusinessName()}</div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              style={({ isActive }) => ({
                padding: "10px 12px",
                borderRadius: 8,
                textDecoration: "none",
                color: "var(--cf-ivory)",
                background: isActive ? "rgba(217,108,86,0.25)" : "transparent",
                fontSize: 14,
              })}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={() => {
            clearAdminSession();
            navigate("/admin/login");
          }}
          style={{
            marginTop: 24,
            width: "100%",
            border: "1px solid rgba(247,244,238,0.3)",
            background: "transparent",
            color: "var(--cf-ivory)",
            borderRadius: 8,
            padding: "10px 12px",
            cursor: "pointer",
          }}
        >
          Cerrar sesión
        </button>
      </aside>
      <main style={{ flex: 1, padding: 24, background: "var(--cf-bg)", minWidth: 0 }}>
        <Outlet />
      </main>
    </div>
  );
}
