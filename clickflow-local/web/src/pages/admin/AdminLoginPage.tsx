import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi } from "../../lib/api";
import { setAdminSession } from "../../lib/adminAuth";

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const [businessSlug, setBusinessSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await adminApi(null).login(businessSlug.trim(), email.trim(), password);
      setAdminSession(res.token, res.business.name);
      navigate("/admin");
    } catch (err: any) {
      setError(err.message || "No se pudo iniciar sesión.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 380, margin: "80px auto", padding: 24, fontFamily: "var(--cf-font)" }}>
      <h1 style={{ color: "var(--cf-petrol)", fontSize: 22 }}>Panel del negocio</h1>
      <p style={{ color: "var(--cf-text-muted)", fontSize: 14 }}>Entra con la cuenta que te dio ClickFlow Local.</p>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ fontSize: 13 }}>
          Identificador del negocio (slug)
          <input
            style={inputStyle}
            value={businessSlug}
            onChange={(e) => setBusinessSlug(e.target.value)}
            placeholder="barberia-don-cesar"
            required
          />
        </label>
        <label style={{ fontSize: 13 }}>
          Correo
          <input style={inputStyle} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label style={{ fontSize: 13 }}>
          Contraseña
          <input
            style={inputStyle}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p style={{ color: "var(--cf-danger)", fontSize: 13 }}>{error}</p>}
        <button type="submit" disabled={loading} style={buttonStyle}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
      <p style={{ fontSize: 12, color: "var(--cf-text-muted)", marginTop: 24 }}>
        Demo: barberia-don-cesar / admin@barberiadoncesar.mx / demo1234
      </p>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--cf-border)",
  borderRadius: "var(--cf-radius-sm)",
  padding: "10px 12px",
  fontSize: 14,
  minHeight: 44,
  marginTop: 4,
};

const buttonStyle: React.CSSProperties = {
  border: "none",
  borderRadius: "var(--cf-radius-sm)",
  padding: "12px 16px",
  background: "var(--cf-primary)",
  color: "var(--cf-primary-text)",
  fontWeight: 700,
  cursor: "pointer",
  minHeight: 44,
};
