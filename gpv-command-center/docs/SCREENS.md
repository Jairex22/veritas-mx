# C. Diseño de pantallas

Sistema visual: tema oscuro por defecto y claro (botón sol/luna, persistente), tipografía del sistema
(Segoe UI en Windows; sin fuentes externas), iconografía SVG propia, sidebar colapsable, búsqueda global
(atajo `/`), toasts de éxito/fallo, modales de confirmación y estados de carga/vacío/error. Responsivo
hasta 390 px (menú lateral desplegable en móvil/tableta).

**Distintivos de entorno** (barra superior, siempre visibles):

| Distintivo | Cuándo aparece |
|------------|----------------|
| `DEMO` + cinta morada superior | `GPV_MODE=DEMO`. Datos sintéticos, operaciones simuladas |
| `REAL` | `GPV_MODE=REAL` |
| `CONECTADO` | REAL y la fuente activa (OData/archivos) superó su prueba de conexión |
| `SOLO LECTURA` | REAL sin transacciones verificadas (siempre en v1.0) |
| `PRODUCCIÓN` | REAL + ejecutor real registrado + interruptor de escrituras activo (inalcanzable en v1.0) |

Indicador de conexión: punto de color + texto (`Simulado`, `Conectado`, `Sin conexión verificada`).

| # | Pantalla | Contenido |
|---|----------|-----------|
| 1 | **Login** | Panel de marca + selección de acceso. SSO corporativo visible como *NO DISPONIBLE* con el requisito. Accesos DEMO por rol (Operador, Ingeniería, Calidad, Administrador), sólo en DEMO. |
| 2 | **Dashboard** | 6 KPI con tooltip de definición; tendencia (unidades empacadas/h); donut de estados; FPY por estación; WIP por estación; resumen del diagnóstico de rework; defectos principales; órdenes de trabajo; pie con la fuente de datos. |
| 3 | **Trazabilidad – búsqueda** | Campo + selector (Serial, Work Order, Assembly, Batch, Revision, Station, Area, Line, Panel). Tabla ordenable con estado, estación actual, último resultado, defectos abiertos, última actividad. |
| 4 | **Trazabilidad – unidad** | Encabezado con serial y estado; tarjetas: estación actual, última completada, último resultado, defectos abiertos, actividad. **Diagrama de flujo de estaciones** (PASS/FAIL/HOLD/actual, contador de visitas ×N, estaciones fuera de ruta como DEBUG). Pestañas: Historial (línea de tiempo), Defectos, Reparaciones, Síntomas, Componentes, Escaneos, Panel (rejilla por posición), Diagnóstico. |
| 5 | **Rework inteligente** | Filtros por regla y severidad, umbrales, lista de hallazgos con barra de confianza. Panel lateral con las 7 secciones: problema, evidencia (HECHO CONFIRMADO + IDs de evento), posibles causas (HIPÓTESIS · NO CONFIRMADA), confianza, acciones recomendadas, historial, riesgo de intervenir. |
| 6 | **Operaciones** | Catálogo por categoría con disponibilidad (SIMULADA · DEMO / NO DISPONIBLE) y autorización por rol. Detalle con requisitos de integración (método, endpoint, licencia, autenticación, privilegios, consecuencias, reversión, requisitos faltantes). Paso 1: parámetros → verificación previa (estado + validaciones de flujo). Paso 2: modal con checkbox obligatorio → resultado con respuesta del servidor (marcada SIMULADO), comprobaciones posteriores, estado posterior, id de auditoría y correlación. |
| 7 | **Packing** | Entrada grande con foco permanente para escáner; paso 1 caja, paso 2 unidades; sonido y animación de acierto/error; lista con validación por serial; tarjeta de caja con barra de progreso; panel de discrepancias; empaque mediante el flujo de operaciones controladas. |
| 8 | **Label Control** | Impresora autorizada + estado; plantilla y datos validados; previsualización esquemática (no escaneable) y código ZPL; impresión con confirmación; reimpresión con permiso y justificación; historial de trabajos. |
| 9 | **Production Intelligence** | Ventana 8 h / 24 h / 72 h / 7 d; KPIs; tendencia; FPY; tiempo mediano por estación; distribución de estados; defectos; WIP; tabla de definiciones formales con fuente. |
| 10 | **Conectores** | Fuente activa, configuración del servidor (sin secretos), tarjeta por conector con estado, HTTP, latencia, credencial (origen, nunca el valor), diagnóstico, EntitySets descubiertos y botón *Probar conexión*. Matriz de integraciones verificadas/pendientes. |
| 11 | **Auditoría** | Estado de integridad de la cadena, filtros por categoría/texto, tabla con detalle JSON y hash; pestaña de bitácora de accesos (método, ruta, HTTP, duración, correlación). |
