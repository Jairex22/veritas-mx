# Limitaciones conocidas

1. **Conexión real no probada.** El desarrollo se hizo sin acceso a `10.62.54.10`. Todas las pruebas usan fixtures y un servidor HTTP falso. Los tiempos de respuesta citados en el requerimiento no se han reproducido.
2. **Tipos de Quality/QualityHistory supuestos.** Los nombres de propiedades están verificados, pero los tipos (p. ej. `DefectID` como `Edm.Guid`, `DateCreated` como `Edm.DateTimeOffset`) se asumieron hasta leer el `$metadata` real. En modo real se usan los tipos del servidor; la pantalla de Diagnóstico muestra diferencias.
3. **Mapeo del caso Mirion.** "Foreign Object on Board" se ubicó en `AegisInspectionCodeName` y "Y43054" en `InspectionWorkstation` dentro del fixture; el campo exacto no fue confirmado. Los campos no confirmados se dejaron en `null`.
4. **Zona horaria de QualityHistory.** El fixture registra 11:45:28 con −06:00; esto produce la alerta R09 "Orden temporal a revisar" (defecto creado antes del primer AOI). Verificar con MES la zona horaria de `DateCreated`/`DefectHistoryTime`.
5. **Sin PASS final.** Ninguna de las tres entidades contiene un resultado de aprobación final; el resultado se muestra siempre como NO VERIFICABLE.
6. **Línea.** `SMT` no expone `Line`; el filtro de línea en Production Pulse está deshabilitado. En Quality es "línea registrada en el defecto".
7. **Bucles confirmados** requieren configurar `rework.process_flows` por ensamble; no hay flujos cargados.
8. **PDF** no se genera directamente (sin dependencias); usar HTML imprimible → Guardar como PDF.
9. **Timeout único.** `urllib` aplica un solo timeout a conexión y lectura de cada operación de socket; no hay timeout total separado.
10. **Paginación** limitada a `max_pages` (3) y `$top`; resultados mayores se marcan como truncados.
11. **Turnos** no configurados por defecto (`pulse.shifts = []`).
12. **Servidor local de un solo usuario**, vinculado a 127.0.0.1. Uso multiusuario en red requeriría autenticación de usuarios y aprobación de TI.
13. Probado en Python 3.11 (Linux) en el entorno de desarrollo; el objetivo es 3.14 en Windows 11. No se usan APIs eliminadas en 3.12–3.14 (`cgi`, `datetime.utcnow`, adaptadores implícitos de SQLite).
14. El Administrador de credenciales de Windows se usa vía `ctypes`; no se pudo probar en Windows desde el entorno de desarrollo.
