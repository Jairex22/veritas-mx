# GPV SMT Quality Intelligence

**GPV Americas E-MXG** · Trazabilidad de unidades, actividad SMT, defectos y detección de reprocesos sobre **FactoryLogix OData** (`SMT`, `Quality`, `QualityHistory`).

Versión 1.0.0 · Python estándar (sin pip, sin Node, sin Docker, sin permisos de administrador) · SQLite · HTML/CSS/JS nativo.

> ⚠️ Estado: **lista para prueba piloto en modo demostración**. La conexión real a FactoryLogix **no ha sido probada** desde el entorno de desarrollo (red privada de GPV). Ver `docs/LIMITATIONS.md` y `docs/PENDING_AUTHORIZATION.md`.

---

## 1. Inicio rápido (Windows 11)

```bat
cd GPV_SMT_Quality_Intelligence
py -3.14 main.py
```

Se abre el navegador en `http://127.0.0.1:8765/`. Si no se abre, cópielo manualmente.
Detener: `Ctrl + C` en la consola.

Opciones:

| Comando | Uso |
|---|---|
| `py -3.14 main.py --no-browser` | No abre el navegador |
| `py -3.14 main.py --port 8800` | Otro puerto |
| `py -3.14 main.py --check` | Verifica configuración y sale |
| `py -3.14 main.py --set-credential` | Guarda usuario/contraseña en el Administrador de credenciales de Windows |
| `py -3.14 -m unittest discover -s tests -t . -v` | Ejecuta las 100 pruebas automatizadas (sin red) |

No se requiere `requirements.txt` con paquetes: solo la biblioteca estándar.

## 2. Modo demostración (por defecto)

Sin configuración, la app arranca en **MODO DEMOSTRACIÓN** (barra naranja + chip "DEMO"). No se contacta FactoryLogix.

Identificadores útiles para la demostración:

| Identifier | Qué muestra |
|---|---|
| `W07632100028` | Caso histórico Mirion confirmado (FOD, 2× AOI Top, SMT REPAIR, cierre, QA SMT) |
| `DEMO-00009`, `DEMO-00018` … | Unidades sintéticas con defecto (cerrado / abierto) |
| `DEMO-QH-FAIL` | SMT y Quality responden, **QualityHistory agota el tiempo** (fallo parcial) |
| `DEMO-ERR-401`, `DEMO-ERR-403`, `DEMO-ERR-500`, `DEMO-TIMEOUT`, `DEMO-INVALID-JSON` | Errores OData simulados |
| `NOEXISTE123` | Respuesta válida sin registros (≠ PASS) |

Batches demo para Rework Detector: `W076321`, `DEMO-B100`, `DEMO-B200`, `DEMO-B300`.

Los datos sintéticos usan nombres `DEMO …` y nunca se mezclan con la caché del modo real (columna `data_source`). El caso Mirion solo aparece en búsquedas por unidad/batch, nunca en Production Pulse.

## 3. Habilitar conexión real (requiere aprobación de TI/MES)

1. Copie `config.example.json` a `config.json`.
2. Ajuste `odata.base_url` si es necesario.
3. TI debe aprobar y poner `"security": {"live_mode_approved": true}`.
4. Autenticación:
   - `"auth_method": "none"` si el servidor acepta acceso sin credenciales.
   - `"auth_method": "basic"`: **sobre HTTP la contraseña viaja sin cifrar**. La app lo **bloquea** salvo que TI configure HTTPS/proxy corporativo (`base_url` con `https://`) o apruebe explícitamente `"allow_basic_auth_over_http": true`.
5. Credenciales (nunca en código, `config.json` ni SQLite; la app rechaza un `config.json` con contraseña):
   - Variables de entorno de usuario: `GPV_ODATA_USER`, `GPV_ODATA_PASSWORD` (`"credential_source": "env"`), o
   - Administrador de credenciales de Windows: `py -3.14 main.py --set-credential` y `"credential_source": "windows_credential_manager"`.
6. En la app: **Configuración → Modo = live**, luego **Diagnóstico OData → Probar $metadata**.

Verificar en Diagnóstico que `$metadata` publique las propiedades esperadas (tabla "Propiedades esperadas ausentes" vacía) y revisar "Diferencias de tipo": los tipos de Quality/QualityHistory se tomarán del `$metadata` real.

## 4. Módulos

| Módulo | Qué hace | Fuentes |
|---|---|---|
| Dashboard | Buscador grande, salud de fuentes, consultas recientes | — |
| Buscar serial (Trazabilidad) | Fusiona SMT + Quality + QualityHistory, línea de tiempo, defectos únicos, alertas, evidencia confirmada / inferida / no verificable, exportación | 3 entidades |
| Production Pulse | KPIs de eventos en ventanas 5 min / 15 min / 1 h / 4 h / turno / personalizado; filtros cliente, assembly, batch, operación | SMT |
| Quality Intelligence | Defectos únicos por DefectID, desgloses, tiempos de cierre bajo demanda (máx. 10) | Quality (+ QualityHistory bajo demanda) |
| Rework Detector | Reglas R01–R09 auditables por unidad o batch, con panel "¿Por qué se generó la alerta?" | SMT (+ Quality por unidad) |
| Historial | Búsquedas locales y auditoría de cada solicitud OData con tiempos | SQLite |
| Reportes | XLSX, CSV, HTML imprimible (PDF vía "Imprimir → Guardar como PDF") | Último análisis |
| Configuración | Ajustes no sensibles; banderas de seguridad solo lectura | SQLite |
| Diagnóstico OData | Prueba mínima por entidad, `$metadata`, comparación de esquema, copiar diagnóstico, abrir logs | — |

Reglas de interpretación aplicadas en todo el sistema:

- El resultado final de una unidad es siempre **NO VERIFICABLE**: ninguna entidad registra aprobación final. La app **nunca muestra PASS**.
- "El cierre de un defecto no constituye por sí mismo evidencia de aprobación final de la unidad."
- Los defectos se cuentan por **DefectID único**; las filas de QualityHistory no son defectos.
- Un resultado vacío **no** es PASS; un error **no** es "sin registros" (estados explícitos `OK`, `EMPTY`, `AUTH_ERROR`, `TIMEOUT`, …).
- Eventos ≠ tarjetas producidas; `Attempts`/`Placements` y `BatchQuantity`/`CompletedQuantity` no se interpretan como unidades.
- La línea solo se muestra como "registrada en el defecto", nunca como verificada para todas las operaciones.
- Un bucle de proceso solo se **confirma** si existe un flujo autorizado en `rework.process_flows`.

## 5. Estructura

```
GPV_SMT_Quality_Intelligence/
├── main.py                 Punto de entrada (servidor local + CLI)
├── config.example.json     Configuración de ejemplo SIN contraseñas
├── requirements.txt        (vacío: solo biblioteca estándar)
├── backend/                Servidor HTTP, API, configuración, credenciales, seguridad, logs
├── services/               Cliente OData, filtros, metadata, fuente demo, servicios de módulos
├── models/                 Estados y especificaciones de consulta, catálogo de entidades
├── repositories/           Acceso a SQLite (caché, auditoría, ajustes)
├── database/               schema.sql + conexión
├── analytics/              Defectos, línea de tiempo, reglas de reproceso, evidencia
├── reports/                Constructor de reportes y exportadores CSV/XLSX/HTML
├── frontend/               index.html, css/, js/ (sin build, sin npm)
├── fixtures/               Caso Mirion + $metadata de muestra
├── tests/                  100 pruebas unittest (sin red)
├── logs/                   app_YYYY-MM-DD.log
└── docs/                   Arquitectura, errores, evidencia de pruebas, limitaciones, pendientes
```

Documentación: `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md`, `docs/TEST_EVIDENCE.md`, `docs/LIMITATIONS.md`, `docs/PENDING_AUTHORIZATION.md`.
