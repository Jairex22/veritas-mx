import { Link } from "react-router-dom";

const DEMOS = [
  { slug: "barberia-don-cesar", label: "Barbería Don César", tag: "Demo principal" },
  { slug: "pasteleria-dulce-trigo", label: "Pastelería Dulce Trigo", tag: "Demo de ejemplo" },
  { slug: "carniceria-la-res-buena", label: "Carnicería La Res Buena", tag: "Demo de ejemplo" },
];

export default function HomePage() {
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "48px 20px", fontFamily: "var(--cf-font)" }}>
      <h1 style={{ color: "var(--cf-petrol)", marginBottom: 4 }}>ClickFlow Local</h1>
      <p style={{ color: "var(--cf-text-muted)", marginTop: 0 }}>
        Asistente virtual configurable para negocios locales. Esta es la demostración: elige un negocio para
        probar su página del asistente (también se puede embeber como widget en cualquier sitio).
      </p>

      <div style={{ display: "grid", gap: 16, marginTop: 32 }}>
        {DEMOS.map((d) => (
          <Link
            key={d.slug}
            to={`/assistant/${d.slug}`}
            style={{
              display: "block",
              padding: 20,
              borderRadius: "var(--cf-radius-md)",
              background: "var(--cf-surface)",
              border: "1px solid var(--cf-border)",
              textDecoration: "none",
              color: "var(--cf-text)",
              boxShadow: "var(--cf-shadow)",
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--cf-coral)", textTransform: "uppercase" }}>
              {d.tag}
            </div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{d.label}</div>
            <div style={{ fontSize: 14, color: "var(--cf-text-muted)" }}>Abrir asistente →</div>
          </Link>
        ))}
      </div>

      <p style={{ marginTop: 40, fontSize: 14 }}>
        ¿Eres dueño de un negocio? <Link to="/admin/login">Entra a tu panel</Link>.
      </p>
    </div>
  );
}
