# Decisiones pendientes y funciones bloqueadas

## GPV Operations HUB 2.0

| # | Pendiente / bloqueado | Bloqueado por | Acción de GPV |
|---|---|---|---|
| A1 | Verificar conectividad real con `http://10.62.54.10:6065/odata/` | Servidor solo accesible en la red interna | Ejecutar `DIAGNOSTICO_FACTORYLOGIX.bat` en un equipo de GPV |
| A2 | Método de autenticación real (anónimo, Basic, Negotiate/Kerberos, NTLM) | Desconocido hasta el diagnóstico | Revisar «Métodos de autenticación» del reporte y configurar `GPV_FLX_AUTH` |
| A3 | Cuenta de servicio de **solo lectura** (si el servidor la exige) | Administración MES / TI | Crearla y definir `GPV_FLX_USER` / `GPV_FLX_PASSWORD` en el equipo |
| A4 | Autorización para el sondeo controlado `$top=1` de los EntitySets | Administrador MES | Autorizar y ejecutar `--sondear --confirmar-sondeo` |
| A5 | Propiedades reales de cada EntitySet (no se suponen) | `$metadata` real | Compartir el reporte JSON o el XML de `$metadata` |
| A6 | Parámetros y semántica de los FunctionImports | `$metadata` real + documentación del proveedor | Confirmar cuáles son de lectura antes de invocarlos |
| B1 | Fase 4: Dashboard general, Serial Intelligence, Smart Work Order Center | A1–A5 | — |
| B2 | Fase 5: Quality Intelligence, SMT Live Monitor | A1–A5 y definiciones de indicadores con Calidad | — |
| B3 | Fase 6: Loop Detector (secuencias de proceso y reglas de rework autorizado), reportes con procedencia | A5 + rutas de proceso reales (ProcessFlow) | Definir qué secuencias son rework autorizado |
| B4 | Fase 7: GPV AI Assistant | Aprobación de GPV para IA externa (si no, modo local con reglas) | Decidir política de datos |
| B5 | Fase 8: modo oscuro, WCAG 2.2 AA completo, virtualización de tablas grandes, medición con usuarios | Fases 4–7 | — |
| B6 | Unificar el conector del portal del turno con `apps/flx` | A5 | — |

## Portal del turno (POR CONFIRMAR con GPV)

Nada de lo siguiente se inventó en el código ni en la configuración: el portal funciona con
captura web y queda listo para recibir estos datos.

| # | Decisión | Quién | Impacto si falta | Dónde se configura |
|---|---|---|---|---|
| 1 | Línea SMT del piloto | Producción SMT | Se usa la línea de EJEMPLO | Admin. técnica › Líneas |
| 2 | Estaciones y **código de la operación de conteo** como aparecen en FactoryLogix | Ingeniería / FactoryLogix | Sin operación de conteo no hay buenas confirmadas | Líneas › estaciones |
| 3 | Turno específico, horario y descansos | Producción | Tiempo planeado y ventanas del reporte | Administración › Turnos; Descansos |
| 4 | URL del servicio OData, versión y certificado (HTTP/HTTPS) | TI / FactoryLogix | La fuente queda «Requiere revisión»; solo captura web | Fuentes › conexión |
| 5 | Método de autenticación que el servidor admite y cuenta de **solo lectura** | TI | No se supone anónimo ni Windows integrada | Variables de entorno del equipo autorizado |
| 6 | Conjunto(s) de entidades, claves estables y propiedades a mapear (desde `$metadata`) | FactoryLogix | No se sincroniza | Fuentes › mapeo |
| 7 | ¿Existe un campo de modificación fiable? | FactoryLogix | Si no, ventana acotada de 24 h (configurable) | Conexión › campo de modificación |
| 8 | Zona horaria de los instantes sin desfase | FactoryLogix | Supuesto actual: America/Mexico_City | Documentado; ajustar en el mapeo |
| 9 | ¿Las cantidades vienen en piezas o paneles? Factor de panelización confirmado | Ingeniería de procesos | Sin factor confirmado: «No calculable» | Líneas › factor |
| 10 | Grupos de atención, integrantes y tiempos de recordatorio/escalamiento | Supervisión | Se usan los de EJEMPLO | Grupos; Motivos de ayuda |
| 11 | Motivos de paro oficiales | Producción | Se usan los de EJEMPLO | Motivos de paro |
| 12 | Lista de disposiciones de calidad y registro oficial de referencia | Calidad | Disposición sin referencia | Calidad |
| 13 | Instrucciones y listas aprobadas para la línea | Ingeniería / Calidad | Solo ejemplos | Instrucciones; Listas |
| 14 | Plantillas de etiqueta del operador y su validación física | Ingeniería | Se usa el PDF a tamaño exacto | Etiquetas; Líneas › plantillas |
| 15 | Si se notificará por correo u otro servicio | Gerencia / TI | Desactivado (solo notificaciones internas) | Requiere alcance expreso |
| 16 | Crecimiento después del piloto (servidor interno, PostgreSQL, HTTPS) | TI | El piloto corre en 127.0.0.1 de un equipo | `DESPLIEGUE_INTERNO.md` |
