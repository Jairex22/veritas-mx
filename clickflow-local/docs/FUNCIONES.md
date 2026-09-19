# Lista honesta de funciones: operativas y pendientes

## Operativo hoy (probado, ver `QA_CHECKLIST.md`)

- Widget de chat embebible vía `<script>` + iframe aislado, y página del
  asistente independiente compartible por enlace.
- Panel privado del dueño con autenticación por token, aislado por negocio.
- Base de datos persistente real (SQLite) con negocio, catálogo, horarios,
  excepciones, FAQs, conversaciones, mensajes, solicitudes y consumo de IA.
- Motor de IA real (OpenAI Responses API, function calling) configurable
  por modelo, con límite de pasos por turno e historial acotado — activo
  en cuanto se configure `OPENAI_API_KEY`.
- Motor de respaldo determinista y transparente cuando la IA no está
  configurada (nunca simula ser una IA que no está activa).
- Consulta de catálogo, precios (incluyendo promociones con vigencia),
  políticas y preguntas frecuentes — siempre desde datos reales, con
  búsqueda por palabra clave y por presupuesto.
- Cálculo de cotizaciones 100% en código de servidor a partir de precios
  reales (el modelo de IA nunca calcula ni inventa un total).
- Creación real de solicitudes de pedido, cita y contacto, con:
  - Resumen editable y confirmación explícita antes de guardar.
  - Folio real y estado (Borrador, Solicitud recibida, Pendiente de
    confirmación, Confirmada, Cancelada).
  - Prevención de duplicados por doble clic o reintento (idempotencia).
  - Las citas nunca nacen "Confirmadas" (no hay agenda conectada todavía).
- Panel del dueño: editar negocio/catálogo/horario/políticas/FAQs,
  revisar y cambiar el estado de solicitudes, ver conversaciones, pausar
  una conversación para atenderla en persona, ver preguntas sin responder,
  ver consumo de IA, pausar el asistente completo, y métricas verificables
  (conteos reales, nunca "ventas").
- Salida a WhatsApp con mensaje preparado (`wa.me`) y aviso claro de que la
  persona debe enviarlo ella misma.
- Aislamiento multi-negocio en el servidor (no solo ocultar botones en el
  cliente): cada operación resuelve el negocio por slug o por token
  firmado, nunca por un dato que mande el cliente.
- Límites de tasa (por IP) y de mensajes por conversación por día;
  historial de conversación acotado para controlar costo.
- Validación de entradas con esquemas (zod) en cada endpoint que recibe
  datos externos.
- Identidad visual configurable (colores, logo) con la paleta base de
  ClickFlow Local (marfil, grafito, verde petróleo, coral) verificada por
  contraste.
- Diseño responsivo desde 360px de ancho, navegación por teclado y foco
  visible.

## Pendiente / fuera de alcance de esta primera versión

- **Agenda real conectada**: hoy las citas quedan "pendientes de
  confirmación" y el dueño las confirma manualmente desde el panel; no hay
  integración con Google Calendar/Calendly ni verificación automática de
  disponibilidad.
- **Pagos**: no se procesan pagos ni se piden datos bancarios, por diseño
  explícito de esta versión.
- **WhatsApp automatizado de punta a punta** (recibir y responder sin abrir
  la app): requiere integrar la API oficial de WhatsApp Business con sus
  propias credenciales y costos (ver `COSTOS.md`).
- **Recuperación de contraseña por correo** para el panel del dueño: hoy
  requiere que un administrador de la instalación cree una nueva cuenta o
  cambie la contraseña manualmente.
- **Roles múltiples dentro de un mismo negocio** (por ejemplo, "solo
  lectura" para un empleado): el esquema soporta un campo `role`, pero el
  panel actual no diferencia permisos entre roles todavía.
- **Eliminación/retención automática de datos por vencimiento**: el campo
  `retentionDays` existe y es configurable, pero la limpieza automática
  (borrado programado) no está implementada como tarea recurrente; hoy es
  un valor informativo que puede usarse para un script de limpieza manual.
- **Pruebas de carga/concurrencia alta** y **revisión con lector de
  pantalla real**: no ejecutadas en este entorno (ver `QA_CHECKLIST.md`).
- **Multi-idioma**: el asistente y el panel están en español de México
  únicamente.
