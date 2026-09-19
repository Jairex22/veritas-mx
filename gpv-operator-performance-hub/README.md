# GPV Operator Performance Hub

Sistema web para medir, visualizar y comparar el rendimiento operativo de los
trabajadores de manufactura a partir de información equivalente a la de
**FactoryLogix Operations/Analytics**. Está pensado como apoyo para
supervisores, líderes de línea e ingeniería — **no** como una sentencia
automática ni como herramienta para castigar o evaluar despidos. Los
indicadores siempre se muestran junto con contexto operativo y, cuando la
evidencia es insuficiente, el sistema lo dice explícitamente ("Datos
insuficientes") en vez de forzar una clasificación.

> Este indicador es una herramienta de apoyo para mejora continua. Debe
> revisarse junto con el contexto operativo antes de tomar decisiones.

---

## 1. Arquitectura

```
gpv-operator-performance-hub/
├── backend/                     FastAPI + SQLAlchemy + SQLite (demo)
│   ├── app/
│   │   ├── main.py              App FastAPI, CORS, arranque, seed automático
│   │   ├── config.py            Variables de entorno centralizadas
│   │   ├── database.py          Motor SQLAlchemy (SQLite demo / SQL Server prod.)
│   │   ├── models.py            Operator, Station, Product, WorkOrder,
│   │   │                        ProductionEvent, QualityEvent, DowntimeEvent,
│   │   │                        Certification, PerformanceSnapshot,
│   │   │                        TrainingAction, SupervisorNote, AuditLog, User
│   │   ├── scoring.py           Motor de puntaje (documentado, ver más abajo)
│   │   ├── analytics.py         Agregaciones compartidas por los routers
│   │   ├── security.py          Hash de contraseñas, JWT, bloqueo, RBAC
│   │   ├── audit.py             Registro de auditoría
│   │   ├── seed_data.py         Generador de datos simulados
│   │   ├── schemas.py           Esquemas Pydantic
│   │   ├── routers/             Endpoints REST (uno por pantalla)
│   │   └── integrations/factorylogix/   Cliente OData + capa de normalización
│   ├── tests/                   Pruebas con pytest
│   ├── requirements.txt
│   └── .env.example
├── frontend/                    React + Vite + TypeScript
│   └── src/
│       ├── styles/              Sistema de diseño (tokens, base, componentes)
│       ├── lib/                 Cliente API, tipos, formato, auth, tema, filtros
│       ├── components/          Sidebar, Topbar, DataTable, StatCard, Badge...
│       └── pages/                Las 10 pantallas de navegación + Login + Detalle
├── start-backend.bat
├── start-frontend.bat
├── build-frontend.bat
├── run-backend-tests.bat
├── README.md                    (este archivo)
├── MANUAL_INSTALACION_WINDOWS.md
├── MANUAL_FACTORYLOGIX.md
├── DICCIONARIO_INDICADORES.md
└── FORMULA_PUNTAJE.md
```

**Por qué esta separación:** el backend no sabe si los datos vienen del
generador simulado o de FactoryLogix — ambos alimentan el mismo modelo
interno (`models.py`). Esto permite demostrar la aplicación completa sin
FactoryLogix disponible, y activar la integración real más adelante sin
tocar el resto del sistema (ver `MANUAL_FACTORYLOGIX.md`).

---

## 2. Inicio rápido (Windows)

1. Instala **Python 3.11+** y **Node.js 18+** (ver `MANUAL_INSTALACION_WINDOWS.md`
   para el detalle paso a paso).
2. Haz doble clic en **`start-backend.bat`** (crea el entorno virtual, instala
   dependencias, genera la base de datos con datos simulados y levanta la API
   en `http://localhost:8000`).
3. En otra ventana, haz doble clic en **`start-frontend.bat`** (instala
   dependencias de Node y levanta la interfaz en `http://localhost:5173`).
4. Abre `http://localhost:5173` en el navegador e inicia sesión con una de las
   cuentas de demostración (ver sección 4).

Ningún script depende de PowerShell; ambos son `.bat` estándar de `cmd.exe`.

---

## 3. Tecnología

| Capa | Tecnología |
|---|---|
| Frontend | React 18, Vite, TypeScript, CSS (tokens + CSS Modules), Recharts, Lucide React |
| Backend | Python, FastAPI, SQLAlchemy 2.0, Pydantic, Uvicorn |
| Base de datos (demo) | SQLite (`backend/veritas_mx.db`, se genera automáticamente) |
| Base de datos (producción) | SQL Server (cambiando `DATABASE_URL`, ver abajo) |
| Autenticación | JWT + bcrypt (passlib), bloqueo temporal tras intentos fallidos |
| Integración externa | FactoryLogix Analytics vía OData + Basic Auth (opcional, desactivada por defecto) |

### Migrar de SQLite a SQL Server

El modelo de datos se declara con SQLAlchemy y no usa características
específicas de SQLite. Para producción:

1. Instala `pyodbc` (`pip install pyodbc`) y el driver ODBC 17/18 de SQL Server.
2. En `backend/.env`, cambia:
   ```
   DATABASE_URL=mssql+pyodbc://usuario:password@servidor/GPV_MES?driver=ODBC+Driver+17+for+SQL+Server
   ```
3. Reinicia el backend. Las tablas se crean automáticamente al arrancar
   (`Base.metadata.create_all`); para un entorno productivo se recomienda
   además introducir Alembic para versionar el esquema.

---

## 4. Cuentas de demostración

**Estas credenciales son sólo para la demo. Nunca uses contraseñas reales en
el código fuente ni reutilices estas contraseñas en sistemas productivos.**

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `Admin#2026` | Administrador |
| `ingeniero.mes` | `Ingeniero#2026` | Ingeniero MES |
| `supervisor.t1` | `Supervisor#2026` | Supervisor |
| `lider.linea1` | `Lider#2026` | Líder de línea |
| `consulta.calidad` | `Consulta#2026` | Consulta |

Los roles Administrador e Ingeniero MES pueden editar los pesos del motor de
puntaje (pantalla Configuración) y consultar Auditoría. Supervisor y Líder de
línea pueden registrar observaciones y acciones de capacitación. Consulta
sólo tiene acceso de lectura.

---

## 5. Datos simulados

Al iniciar el backend por primera vez (`USE_SIMULATED_DATA=true` en `.env`,
valor por defecto), se genera automáticamente:

- 60 operadores en 3 turnos, con nombres, antigüedad e ingresos recientes.
- 12 estaciones: INITIALIZATION, THT AUTO INSERTION, HEATSINK INSERTION, AOI,
  POWER MODULE MEASUREMENT, ICT, FCT, DEPANEL, FINAL ASSEMBLY, FINAL TEST,
  PACKING y REWORK.
- 8 productos con distinta complejidad (afecta tiempos y tasa de defectos).
- 20 Work Orders, algunas de lote pequeño.
- 90 días de actividad con variaciones realistas: fines de semana con
  dotación reducida, ausentismo, operadores nuevos, una estación con
  problema de proceso conocido (ICT, para poder demostrar que "estación con
  riesgo" no es lo mismo que "operador con bajo desempeño"), retrabajos,
  paros y un grupo de operadores con muestra intencionalmente insuficiente.

Para regenerar los datos desde cero, borra `backend/veritas_mx.db` y vuelve
a iniciar el backend, o ejecuta manualmente:

```
cd backend
.venv\Scripts\python -m app.seed_data
```

---

## 6. Pantallas incluidas

1. **Resumen de planta** — KPIs con contexto, tendencia de producción por
   hora, calidad por estación, distribución de niveles de rendimiento,
   comparación entre turnos, anomalías recientes, "qué requiere atención
   hoy" y cobertura de datos.
2. **Rendimiento** — tabla densa con todas las columnas solicitadas, búsqueda,
   orden, paginación, filtros combinables, exportación CSV, selector de
   columnas, vista compacta y estados de carga/vacío/error.
3. **Detalle del operador** — página completa (no modal) con tendencia de 7,
   30 y 90 días, historial por estación, comparación contra el grupo
   equivalente, certificaciones, contexto del resultado, recomendaciones,
   observaciones del supervisor y acciones de capacitación.
4. **Operadores** — directorio/roster con búsqueda y acceso directo al detalle.
5. **Estaciones** — estado, operadores activos, tiempo estándar vs. real, FPY,
   retrabajo, cola estimada y alertas por estación.
6. **Calidad** — Pareto de defectos, defectos por estación/producto, FPY por
   turno, retrabajos por causa, tendencia semanal, unidades bloqueadas,
   validaciones fallidas y matriz estación-producto. Los defectos se
   clasifican por causa (proceso, material, equipo, programa, diseño,
   método, posible error operativo, causa sin confirmar) — nunca se atribuyen
   automáticamente al operador.
7. **Capacitación** — matriz de habilidades por operador y estación, niveles
   (No capacitado, En entrenamiento, Supervisado, Certificado, Instructor),
   vencimientos y necesidad de refuerzo.
8. **Comparaciones** — compara sólo operadores equivalentes (misma estación,
   mismo turno si se filtra, mismo periodo).
9. **Alertas** — estaciones con riesgo, operadores que requieren apoyo,
   certificaciones por vencer y cobertura de datos, con contexto explicativo.
10. **Configuración** — pesos del motor de puntaje editables (Administrador /
    Ingeniero MES) y estado de la conexión con FactoryLogix.
11. **Auditoría** — inicios de sesión, cambios de configuración y acciones
    registradas (sólo Administrador / Ingeniero MES).

---

## 7. Motor de puntaje

Ver `FORMULA_PUNTAJE.md` para la explicación completa y `DICCIONARIO_INDICADORES.md`
para el significado de cada indicador. Resumen:

```
puntaje = calidad_norm × 0.35 + ciclo_norm × 0.25 + productividad_norm × 0.20
        + consistencia_norm × 0.10 + retrabajo_norm(invertido) × 0.10
```

- Los pesos son configurables desde la pantalla Configuración.
- Si hay menos del mínimo de unidades configurado (20 por defecto), el
  sistema no publica un puntaje: clasifica como "Datos insuficientes".
- El resultado siempre se limita a 0–100 y expone su desglose completo
  (`breakdown`) para que sea trazable.
- Los tiempos muertos autorizados se excluyen antes de calcular ciclo y
  productividad.
- La normalización es por estación y producto (grupo equivalente), nunca
  entre contextos distintos sin ajustar.

---

## 8. Conector FactoryLogix

Ver `MANUAL_FACTORYLOGIX.md`. En resumen: el conector está desactivado por
defecto (`FACTORYLOGIX_ENABLED=false`) y la aplicación funciona por completo
con datos simulados. Cuando tengas URL, usuario y contraseña autorizados por
tu equipo de IT/MES, se configuran únicamente en `backend/.env` — nunca en el
frontend ni en el código fuente.

---

## 9. Pruebas

```
cd backend
start-backend.bat      (primera vez, para crear el entorno virtual)
run-backend-tests.bat
```

o manualmente:

```
cd backend
.venv\Scripts\pytest tests -v
```

Incluye pruebas del motor de puntaje (límites 0-100, división entre cero,
umbral de datos insuficientes, trazabilidad del desglose) y pruebas de humo
de la API (autenticación, bloqueo por intentos fallidos, permisos por rol,
endpoints principales).

---

## 10. Build de producción

**Frontend:** ejecuta `build-frontend.bat` (o `cd frontend && npm run build`).
El resultado queda en `frontend/dist/` — publícalo en cualquier servidor web
estático (IIS, Nginx, Apache, etc.), configurando `VITE_API_BASE_URL` en
`frontend/.env` antes de compilar para que apunte al backend de producción.

**Backend:** despliega `backend/` con un servidor ASGI de producción, por
ejemplo:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

detrás de un proxy inverso (Nginx/IIS) con HTTPS. Ajusta `CORS_ORIGINS` en
`.env` para incluir el dominio real del frontend.

---

## 11. Alcance de esta demostración (transparencia)

Para mantener el proyecto revisable en una sola entrega, algunas
simplificaciones deliberadas:

- El concepto de "línea de producción" se deriva del área del operador
  (`Línea {área}`) porque el modelo de datos no incluye una entidad `Line`
  independiente; agregarla es directo si FactoryLogix expone esa dimensión.
- El estado de sincronización con FactoryLogix se mantiene en memoria del
  proceso backend (no persistido) — en producción conviene guardarlo en base
  de datos o un caché compartido si hay múltiples instancias.
- El adaptador de FactoryLogix normaliza los tipos de entidad principales
  (actividad de producción, calidad, work orders, certificaciones); las
  entidades adicionales (WIP, Active Product Tracking Detail, Test and
  Measurement) siguen el mismo patrón y se añaden bajo demanda cuando haya
  acceso real a validar contra la respuesta exacta de tu instalación.
- No se implementó inicio de sesión con Active Directory; el modelo `User`
  ya incluye `external_directory_id` para esa integración futura.
