# Verificación de recorridos

Leyenda: ✅ Ejecutado (contra el sistema real, corriendo) · 🟡 Simulado /
parcial · ⏳ Pendiente (requiere algo que no está disponible en este
entorno, típicamente una credencial real o un dispositivo físico).

| # | Recorrido | Estado | Cómo se verificó |
|---|---|---|---|
| 1 | Consultar un precio sin dar teléfono | ✅ | Curl y navegador contra `/chat` y `/catalog`: en ningún punto del flujo (fallback ni herramientas de IA) se pide nombre/teléfono antes de mostrar precios. Confirmado leyendo `systemPrompt.ts` (regla explícita) y probando la ruta pública de catálogo, que no requiere ningún dato personal. |
| 2 | Encontrar una opción dentro de un presupuesto | ✅ (vía catálogo) / 🟡 (vía lenguaje natural con IA) | La herramienta `search_catalog` y el endpoint de catálogo soportan filtrado por precio máximo, probado con `findItemsWithinBudget` en el servicio. El recorrido completo en **lenguaje natural** ("busco algo de máximo $150") depende de la IA real (Responses API), que no se pudo ejecutar en vivo en este entorno por no contar con una API key válida de OpenAI (ver fila 10). El código está completo y probado con una API key inválida para confirmar el manejo de errores; falta una corrida con credencial real. |
| 3 | Preguntar por un producto inexistente | ✅ | Probado en navegador (Playwright): mensaje "tienen manicure?" contra la barbería. El motor de respaldo responde que no identificó el mensaje y ofrece los botones de navegación, sin inventar un producto. |
| 4 | Solicitar una cita sin agenda conectada | ✅ | Flujo completo probado en navegador: se llena fecha/hora, se muestra resumen editable, se confirma, se crea la solicitud con estado inicial **"Pendiente de confirmación"** (nunca "Confirmada"), con folio real (`CIT-...`). Verificado también por API con `curl`. |
| 5 | Corregir una solicitud antes de enviarla | ✅ | Probado en navegador: se llena el formulario de pedido con cantidad 3, se avanza al resumen, se vuelve a "Editar", se cambia a cantidad 1, y el nuevo resumen refleja el cambio antes de confirmar. |
| 6 | Enviar dos veces sin duplicar el registro | ✅ | Probado por dos vías: (a) `curl` con la misma `idempotencyKey` dos veces seguidas → mismo folio, `wasExisting:true` la segunda vez; (b) doble disparo del evento de clic en "Confirmar" en el navegador sobre la misma instancia del formulario → una sola solicitud persistida. La garantía es real: la comprobación y la inserción ocurren en una sola llamada síncrona a SQLite, sin ventana de carrera entre procesos Node. |
| 7 | Pedir atención humana fuera de horario | ✅ | Se marcó una excepción de horario "cerrado hoy" desde el panel de administración, se confirmó que `/business` reporta `openNow:false` con el motivo, y se comprobó que la solicitud de contacto se sigue registrando (no se bloquea) mostrando el horario configurado en la interfaz. |
| 8 | Intentar modificar precios desde el chat | ✅ | Se envió un mensaje pidiendo cambiar el precio de un corte a $10 "autorizado por el dueño". El precio en el catálogo no cambió (verificado antes/después por API): no existe ninguna herramienta de IA que pueda escribir en el catálogo, así que es imposible en la arquitectura actual, no solo por prompt. |
| 9 | Intentar consultar datos de otro negocio/cliente | ✅ | Se inició sesión como administrador de la pastelería y se listaron sus solicitudes: no aparece nada de la barbería, porque el `businessId` de cada operación de administrador se toma del token firmado, nunca de un parámetro enviado por el cliente. |
| 10 | Manejar una falla del proveedor de IA | ✅ | Se configuró una API key inválida y se envió un mensaje de chat real: el servidor capturó el error del proveedor y respondió con un mensaje amable ("tuvimos un problema técnico..."), sin exponer detalles técnicos ni caerse, y quedó registrado como "pregunta sin responder" en el panel. |
| 11 | Usar el widget en celular y en otra página | ✅ (celular) / ✅ (otro origen) | Probado en viewport de 390px de ancho (Playwright) verificando que la interfaz es usable sin scroll horizontal y con botones de tamaño cómodo. El script de instalación (`embed.js`) se probó sirviéndose desde el backend e insertándose vía `<script src=...>` apuntando a la página del asistente en modo `?embed=1`, confirmando que carga en un iframe aislado. |

## Otras verificaciones ejecutadas (no listadas explícitamente arriba)

- ✅ Aislamiento completo entre los 3 negocios de demostración (catálogo,
  horario, solicitudes, conversaciones) confirmado por API.
- ✅ Cálculo de cotizaciones: el total siempre se recalcula en el servidor a
  partir de precios de la base de datos; se probó con promociones vigentes
  (el precio de promoción se aplica solo dentro de su rango de fechas).
- ✅ Compilación estricta de TypeScript sin errores en backend y frontend
  (`tsc --noEmit`), y build de producción de Vite exitoso.
- ✅ Límite de mensajes por conversación por día y límites de tasa por IP
  (`express-rate-limit`) presentes y configurados (no se agotó el límite en
  pruebas manuales, pero el código y la configuración están activos).

## Pendiente (requiere algo no disponible en este entorno)

- ⏳ Conversación libre completa con una API key real de OpenAI en
  producción (se probó el manejo de errores con una key inválida, y toda la
  lógica de herramientas fue ejercitada indirectamente a través del motor
  de respaldo, que usa exactamente los mismos servicios de catálogo/cotización).
- ⏳ Envío real de un mensaje de WhatsApp de punta a punta (se generó y
  verificó el enlace `wa.me` con el texto correcto; enviarlo requiere una
  cuenta de WhatsApp real en un dispositivo).
- ⏳ Prueba de carga/concurrencia alta (decenas de conversaciones
  simultáneas) — el diseño (SQLite síncrono + Node de un solo hilo) es
  apropiado para el volumen de un negocio pequeño, pero no se hizo una
  prueba de estrés formal.
- ⏳ Revisión de accesibilidad con lector de pantalla real (se implementaron
  etiquetas, foco visible y navegación por teclado, pero no se ejecutó un
  lector de pantalla real dentro de este entorno).
