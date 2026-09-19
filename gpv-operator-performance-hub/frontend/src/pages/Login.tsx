import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Factory, LogIn } from "lucide-react";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import styles from "./Login.module.css";

const DEMO_ACCOUNTS = [
  { user: "admin", pass: "Admin#2026", role: "Administrador" },
  { user: "ingeniero.mes", pass: "Ingeniero#2026", role: "Ingeniero MES" },
  { user: "supervisor.t1", pass: "Supervisor#2026", role: "Supervisor" },
  { user: "lider.linea1", pass: "Lider#2026", role: "Líder de línea" },
  { user: "consulta.calidad", pass: "Consulta#2026", role: "Consulta" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No fue posible iniciar sesión.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.panel}>
        <div className={styles.brandRow}>
          <div className={styles.brandMark}>
            <Factory size={20} color="#fff" />
          </div>
          <div>
            <h1 className={styles.title}>GPV Operator Performance Hub</h1>
            <p className={styles.subtitle}>Medición y mejora continua del desempeño operativo</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div>
            <label className="field-label" htmlFor="username">
              Usuario
            </label>
            <input
              id="username"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="field-label" htmlFor="password">
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <button type="submit" className="btn btn-primary" disabled={loading} style={{ justifyContent: "center" }}>
            <LogIn size={16} />
            {loading ? "Ingresando…" : "Iniciar sesión"}
          </button>
        </form>

        <div className={styles.demoBox}>
          <p className={styles.demoTitle}>Cuentas de demostración (no usar en producción)</p>
          <ul className={styles.demoList}>
            {DEMO_ACCOUNTS.map((acc) => (
              <li key={acc.user}>
                <button
                  type="button"
                  className={styles.demoItem}
                  onClick={() => {
                    setUsername(acc.user);
                    setPassword(acc.pass);
                  }}
                >
                  <span>{acc.role}</span>
                  <code>
                    {acc.user} / {acc.pass}
                  </code>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
