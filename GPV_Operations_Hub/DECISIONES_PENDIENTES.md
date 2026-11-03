# Decisiones pendientes (POR CONFIRMAR con GPV)

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
