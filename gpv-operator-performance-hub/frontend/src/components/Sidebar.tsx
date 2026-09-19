import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Gauge,
  Users,
  Factory,
  ShieldCheck,
  GraduationCap,
  Columns3,
  AlertTriangle,
  Settings,
  ClipboardList,
  X,
} from "lucide-react";
import styles from "./Sidebar.module.css";

const NAV_ITEMS = [
  { to: "/", label: "Resumen de planta", icon: LayoutDashboard },
  { to: "/rendimiento", label: "Rendimiento", icon: Gauge },
  { to: "/operadores", label: "Operadores", icon: Users },
  { to: "/estaciones", label: "Estaciones", icon: Factory },
  { to: "/calidad", label: "Calidad", icon: ShieldCheck },
  { to: "/capacitacion", label: "Capacitación", icon: GraduationCap },
  { to: "/comparaciones", label: "Comparaciones", icon: Columns3 },
  { to: "/alertas", label: "Alertas", icon: AlertTriangle },
  { to: "/configuracion", label: "Configuración", icon: Settings },
  { to: "/auditoria", label: "Auditoría", icon: ClipboardList },
];

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      {open && <div className={styles.scrim} onClick={onClose} aria-hidden="true" />}
      <aside className={`${styles.sidebar} ${open ? styles.sidebarOpen : ""}`} aria-label="Navegación principal">
        <div className={styles.brand}>
          <div className={styles.brandMark}>GPV</div>
          <div>
            <div className={styles.brandName}>Operator Performance Hub</div>
            <div className={styles.brandTag}>Manufactura · MES</div>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar navegación">
            <X size={18} />
          </button>
        </div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={onClose}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className={styles.footerNote}>
          Herramienta de apoyo para mejora continua. No es una sentencia automática.
        </div>
      </aside>
    </>
  );
}
