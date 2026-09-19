# Manual breve para el dueño del negocio

Bienvenido a tu panel de ClickFlow Local. Este manual está pensado para que
lo puedas usar sin conocimientos técnicos.

## Entrar a tu panel

1. Ve a la dirección que te compartieron (termina en `/admin/login`).
2. Escribe el identificador de tu negocio, tu correo y tu contraseña.
3. Si olvidas tu contraseña, pide a quien administra la instalación que te
   cree una nueva (por ahora no hay recuperación automática por correo).

## ¿Qué puedes hacer en el panel?

- **Panel (inicio):** cuántas conversaciones ha tenido tu asistente, cuántas
  solicitudes se han registrado y cuántas personas pidieron que las
  contactaras. Son conteos reales, no estimaciones de ventas.
- **Negocio:** edita tu descripción, dirección, horario, políticas de
  entrega/cancelación/cambios, datos de contacto, colores y preguntas
  frecuentes. El asistente **siempre** usa esta información antes de
  responder — si algo está mal aquí, corrígelo aquí y el asistente lo dirá
  bien la próxima vez.
- **Catálogo:** agrega, edita o desactiva productos y servicios, sus
  precios, duración (si aplica), variantes y promociones con fecha de
  inicio y fin. Publicar algo aquí no significa que siempre haya
  existencias: el asistente lo aclara a las personas cuando corresponde.
- **Solicitudes:** aquí llegan los pedidos, citas y peticiones de contacto
  que las personas confirmaron con el asistente. Cada una tiene un folio y
  un estado: *Borrador, Solicitud recibida, Pendiente de confirmación,
  Confirmada o Cancelada*. Tú decides cuándo pasar una solicitud a
  "Confirmada" (por ejemplo, después de checar tu agenda o tu inventario)
  o "Cancelada".
- **Conversaciones:** revisa lo que tu asistente conversó con las personas.
  Si vas a atender tú mismo a alguien por otro medio, puedes "pausar" esa
  conversación por una hora para que el asistente no responda mientras tú
  lo haces.
- **Preguntas sin responder:** mensajes que el asistente no pudo resolver
  bien con la información que le diste. Revísalas seguido: normalmente
  significan que falta algo en tu catálogo, tus políticas o tus preguntas
  frecuentes.
- **Consumo de IA:** cuántas veces se usó la inteligencia artificial y
  cuántos "tokens" (unidad de medida del proveedor de IA) consumió. Te
  sirve para vigilar el costo.
- **Pausar el asistente:** en el Panel puedes pausar TODAS las respuestas
  automáticas de tu negocio (por ejemplo, si te vas de vacaciones y quieres
  que la gente solo vea que está pausado).

## Cosas importantes que debes saber

- El asistente **nunca** pide nombre o teléfono solo para mostrar precios.
- El asistente **nunca** puede cambiar tus precios o políticas, aunque el
  cliente insista o diga que tú se lo autorizaste — esos datos solo los
  cambias tú, desde este panel.
- Una solicitud de **cita no es una reserva confirmada**: siempre debes
  revisarla y confirmarla tú (o rechazarla) desde "Solicitudes".
- Si no tienes configurada la inteligencia artificial (API key), tu
  asistente sigue funcionando para catálogo, cotizaciones, citas y
  contacto — solo la charla libre es más limitada, y el sistema lo dice de
  forma honesta a tus clientes en vez de fingir que es una IA completa.
- El botón de WhatsApp abre una conversación con un mensaje ya escrito; la
  persona todavía tiene que darle "enviar" desde su WhatsApp. Que abra el
  enlace no significa que tú ya recibiste el mensaje.

## ¿Qué NO hace todavía esta primera versión?

- No cobra ni pide tarjetas o datos bancarios.
- No confirma citas automáticamente contra una agenda en tiempo real.
- No envía ni recibe WhatsApp de forma automática (eso es una integración
  futura, con costo y configuración aparte con Meta).

Si algo del asistente no te convence, corrígelo desde "Negocio" o
"Catálogo": el asistente aprende de lo que tú configuras, no inventa por su
cuenta.
