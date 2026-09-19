import { useEffect, useState } from "react";
import { Menu, RefreshCw, Sun, Moon, ChevronDown, Wifi, WifiOff, CloudOff } from "lucide-react";
import { useTheme } from "../lib/theme";
import { useAuth } from "../lib/auth";
import { useFilters } from "../lib/filters";
import { api } from "../lib/api";
import { relativeFromNow } from "../lib/format";
import type { SystemStatus } from "../lib/types";
import styles from "./Topbar.module.css";

const SHIFT_OPTIONS = [
  { value: "", label: "Todos los turnos" },
  { value: "Turno 1", label: "Turno 1" },
  { value: "Turno 2", label: "Turno 2" },
  { value: "Turno 3", label: "Turno 3" },
];

const PERIOD_OPTIONS = [
  { value: 7, label: "Últimos 7 días" },
  { value: 30, label: "Últimos 30 días" },
  { value: 90, label: "Últimos 90 días" },
];

export default function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const { periodDays, setPeriodDays, shift, setShift } = useFilters();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  async function loadStatus() {
    try {
      const data = await api.get<SystemStatus>("/api/system/status");
      setStatus(data);
    } catch {
      setStatus(null);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  async function handleSync() {
    setSyncing(true);
    try {
      const data = await api.post<SystemStatus>("/api/system/sync");
      setStatus((prev) => (prev ? { ...prev, ...data } : (data as SystemStatus)));
    } finally {
      setSyncing(false);
    }
  }

  const connectionTone = status?.status === "conectado" ? "ok" : status?.status === "offline" ? "bad" : "warn";

  return (
    <header className={styles.topbar}>
      <button className={styles.iconBtn} onClick={onMenuClick} aria-label="Abrir navegación">
        <Menu size={20} />
      </button>

      <div className={styles.plant}>
        <span className={styles.plantName}>{status?.plant_name ?? "GPV Operator Performance Hub"}</span>
        <span className={`${styles.connectionPill} ${styles[connectionTone]}`}>
          {connectionTone === "ok" ? <Wifi size={13} /> : connectionTone === "bad" ? <WifiOff size={13} /> : <CloudOff size={13} />}
          {status ? status.message : "Verificando conexión con FactoryLogix…"}
        </span>
      </div>

      <div className={styles.filters}>
        <select className="select" value={shift} onChange={(e) => setShift(e.target.value)} aria-label="Turno">
          {SHIFT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={periodDays}
          onChange={(e) => setPeriodDays(Number(e.target.value))}
          aria-label="Periodo"
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.actions}>
        <span className={styles.lastSync} title="Última sincronización con FactoryLogix">
          Sync: {relativeFromNow(status?.last_sync)}
        </span>
        <button className="btn btn-secondary btn-sm" onClick={handleSync} disabled={syncing}>
          <RefreshCw size={14} className={syncing ? styles.spin : ""} />
          {syncing ? "Actualizando…" : "Actualizar datos"}
        </button>
        <button className={styles.iconBtn} onClick={toggleTheme} aria-label="Cambiar tema">
          {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        <div className={styles.profile}>
          <button className={styles.profileBtn} onClick={() => setMenuOpen((v) => !v)}>
            <span className={styles.avatar}>{(user?.display_name || "?").slice(0, 2).toUpperCase()}</span>
            <span className={styles.profileText}>
              <span className={styles.profileName}>{user?.display_name}</span>
              <span className={styles.profileRole}>{user?.role}</span>
            </span>
            <ChevronDown size={14} />
          </button>
          {menuOpen && (
            <div className={styles.profileMenu}>
              <button className="btn btn-ghost btn-sm" onClick={logout}>
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
