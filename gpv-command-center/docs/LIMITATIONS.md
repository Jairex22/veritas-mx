# Limitaciones conocidas de v1.0 y siguientes fases

## Limitaciones (declaradas, no ocultas)

1. **Ninguna transacción real de FactoryLogix está implementada.** La documentación oficial de xTend no fue
   accesible desde el entorno de desarrollo; no se inventaron métodos. Todas las acciones reales muestran
   NO DISPONIBLE con requisitos faltantes. En DEMO se simulan en memoria.
2. **Lectura OData no validada contra un FactoryLogix real.** Está probada con un servidor OData simulado.
   Requiere mapeo verificado de entidades/campos. Carga hasta `max_rows` (2000 por defecto) para métricas y
   diagnóstico; instalaciones grandes requerirán consultas agregadas o vistas de sólo lectura.
3. **Autenticación NTLM/Negotiate hacia OData no soportada.** Si el servidor la exige, el diagnóstico lo indica.
4. **SSO:** disponible sólo vía IIS + Autenticación de Windows; OIDC/Entra ID pendiente.
5. **Impresión real deshabilitada.** Sólo se comprueba el puerto TCP de impresoras configuradas. La
   previsualización es esquemática (el código de barras no es escaneable). BarTender pendiente.
6. **Packing real:** la consulta de cajas sólo existe en DEMO; en REAL responde NO DISPONIBLE hasta identificar el
   método oficial.
7. **Ruta de proceso:** en fuentes reales se infiere del historial (marcada como inferida) salvo que la fuente la reporte.
8. **Estado DEMO en memoria:** se reinicia al reiniciar el servicio (la auditoría sí persiste).
9. **Escalabilidad:** SQLite y un solo proceso son adecuados para un servicio departamental; para alta
   concurrencia, migrar la BD propia a SQL Server (instancia separada de FactoryLogix).
10. **Diagnóstico:** reglas deterministas con umbrales fijos (configurables en código); no aprende de datos históricos.
11. **Parser XML de diagnóstico** pendiente del formato real de los archivos de GPV.

## Fases sugeridas

| Fase | Alcance |
|------|---------|
| 1 (esta entrega) | DEMO completo, conectores con diagnóstico, lectura OData mapeada, CSV, auditoría, seguridad, pruebas |
| 2 | Validar OData real; OIDC/Entra ID; umbrales configurables; parser XML; exportes CSV/PDF de reportes |
| 3 | Verificación formal de métodos xTend (con AEGIS) y habilitación individual de acciones en ambiente de validación |
| 4 | Impresión real Zebra/CAB/BarTender con impresoras autorizadas; packing real; notificaciones |
