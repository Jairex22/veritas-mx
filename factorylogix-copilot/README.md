# FactoryLogix Copilot

Asistente técnico de consulta para manufactura, procesos y trazabilidad en FactoryLogix (Aegis Software).

**Artifact publicado (versión funcional):** https://claude.ai/artifact/LaSW81Frdyfz89M4RAJWyG

El archivo `factorylogix-copilot.artifact.html` en esta carpeta es el mismo código fuente que corre en ese Artifact. Se guarda aquí como referencia de código; el Artifact publicado es la versión que realmente puede ejecutarse (necesita el runtime de Claude para las capacidades `sample`, `db`, `user` y `downloads` descritas abajo).

## 1. Qué es y qué no es

Es un asistente de **consulta de solo lectura**: ayuda a entender procedimientos, interpretar trazabilidad y armar diagnósticos, basado en lo que el usuario escribe y en la documentación que él mismo añade dentro de la app. **No** es un producto oficial de Aegis, no tiene acceso a ninguna planta o base de datos real, y no ejecuta acciones sobre FactoryLogix (no libera unidades, no modifica rutas, no imprime, no reinicia servicios).

## 2. Cómo genera las respuestas (motor de IA real, no simulado)

Verifiqué qué es realmente posible dentro de un Artifact de Claude antes de construir nada:

- Existe una capacidad nativa llamada **`sample`** que permite que la página le pregunte a Claude en tiempo real y reciba la respuesta genuina del modelo, usando el propio consentimiento y el propio uso del visor (no se necesita ni se pide ninguna API key).
- No hay memoria propia del modelo entre llamadas: en cada pregunta la app arma un mensaje que incluye (a) reglas de precisión fijas, (b) el historial reciente de la conversación, (c) los fragmentos de documentación que coincidan por palabra clave con la pregunta, el módulo y la versión seleccionados, y (d) la pregunta actual. Esa búsqueda por coincidencia de palabras es solo para *elegir qué fragmentos mostrarle a Claude*; quien razona y redacta la respuesta es Claude, no un buscador.
- Si el visor no concede o no soporta `sample`, la app lo indica explícitamente (banner visible) y no genera respuestas falsas. Ver la sección 6 para la alternativa dentro de un Project de Claude.

## 3. Documentación oficial: limitación real, no maquillada

Intenté revisar la documentación oficial (`docs.aiscorp.com/en/factorylogix-learning/FL/op`) antes de escribir cualquier contenido de conocimiento, para poder citar solo lo que hubiera leído de verdad. El proxy de red de este entorno de desarrollo bloquea el acceso a ese dominio, así que **no pude leer ni una sola página** de esa documentación. Por eso la base de conocimiento del asistente arranca **vacía**: no se fabricó contenido "oficial" simulado. Lo que el asistente sabrá vendrá de:

1. Lo que tú agregues manualmente en la pestaña "Documentación" (texto/Markdown autorizado: fragmentos de manuales oficiales, procedimientos internos de planta, notas de una captura de pantalla, etc.), con título, módulo, versión, revisión, origen y sección.
2. Conocimiento general de manufactura, siempre que el modelo lo etiquete como tal (regla explícita en las instrucciones del asistente).

No se admite subir PDF/Word directamente (el entorno del Artifact no soporta parsearlos): si tienes un PDF, extrae o pega el texto relevante en el chat de Claude primero y añade el resultado como documento en la app.

## 4. Persistencia y privacidad

- Declarar la capacidad `db` hace que el Artifact sea **interno de tu organización de Claude**: no se puede compartir públicamente por link. Esto es una limitación estructural de la plataforma, no una elección de diseño.
- Los documentos de la base de conocimiento son compartidos entre quienes puedan interactuar con el Artifact (nivel "interact" o superior); cualquiera de ellos puede añadir documentos por ahora (no hay roles de curador en esta primera versión).
- El historial de cada conversación se guarda en una ruta privada por usuario (`data/users/<id>/...`), que ni siquiera el dueño del Artifact puede leer.
- Si el visor no soporta `db` (por ejemplo, un enlace compartido fuera de la organización), la app lo indica y todo vive solo en memoria de esa sesión; no se simula persistencia.

## 5. Funciones operativas (v1)

- Chat con contexto de conversación, selector de módulo (Operations, Office/NPI, Trazabilidad, Calidad/Analytics, Integraciones) y de entorno (on-premise / FactoryLogix Online / ambas).
- Modo de respuesta Breve / Detallada (la detallada usa la plantilla de diagnóstico en 7 pasos cuando aplica).
- Base de documentación: alta de fragmentos con metadatos, listado, borrado, y panel de "fuentes usadas" en cada respuesta con el fragmento exacto enviado al modelo.
- Adjuntar una captura de pantalla a un mensaje, solo si el visor reporta que puede recibir imágenes.
- Copiar respuesta, reintentar tras un error (mostrando el error real, nunca una respuesta simulada), exportar la conversación a un archivo de texto, borrar los datos guardados.
- Indicador honesto del estado del motor de IA y de la persistencia.
- Diseño responsivo (móvil, 1366×768, 1920×1080) con barra lateral y panel de fuentes plegables.

## 6. Limitaciones conocidas / pendientes

- **No pude ejecutar pruebas end-to-end reales del motor de IA desde esta sesión de desarrollo**: llamar a `sample` requiere un visor real de Claude que conceda consentimiento, algo que no puede simularse por fuera del Artifact publicado. Ver la sección 7 (resultados de pruebas) para el detalle de qué sí se verificó y qué queda pendiente de que tú lo abras y lo pruebes.
- No hay control de roles para editar la base de conocimiento compartida más allá de lo que la plataforma resuelve automáticamente (cualquiera con nivel "interact" puede añadir/borrar documentos).
- La búsqueda de fragmentos relevantes es por coincidencia de palabras, no semántica; con bases de conocimiento grandes convendrá afinar títulos/secciones para que la recuperación sea precisa.
- Sin integración real a OData/xTend/sistemas externos: las preguntas sobre esas áreas se responden con lo documentado + conocimiento general, nunca consultando un sistema real.
- Un chat muy largo puede acercarse al límite de tamaño de documento (256 KB); si eso ocurre, conviene iniciar una conversación nueva.

## 7. Resultados de pruebas realmente ejecutadas

| # | Prueba (según el pedido original) | Resultado |
|---|---|---|
| 1 | Pregunta abierta recibe respuesta del modelo real | **Pendiente** — requiere abrir el Artifact y conceder el permiso de IA; no se puede invocar `sample` fuera de un visor real. |
| 2 | Pregunta reformulada mantiene el significado | **Pendiente** (depende de 1). |
| 3 | Pregunta de seguimiento conserva contexto | **Pendiente** (depende de 1); el mecanismo de historial se revisó por código y es correcto. |
| 4 | Respuesta documental cita el fragmento correcto | **Pendiente** (depende de 1); la función de recuperación (`retrieveFragments`) se probó por lectura de código, no en ejecución real. |
| 5 | Una opción inexistente no se presenta como real | Cubierto por instrucción explícita al modelo (regla de precisión); no puede verificarse en ejecución sin 1. |
| 6 | Fuentes de versiones distintas no se mezclan silenciosamente | Cubierto por instrucción explícita al modelo; **pendiente** de verificación en ejecución real. |
| 7 | Falla de conexión muestra error, no respuesta simulada | **Verificado por código**: todo error de `sample` cae en un mapeo de códigos a mensajes reales y nunca genera texto de relleno; no se pudo forzar un fallo real de red para verlo en pantalla. |
| 8 | Archivo no compatible no aparece como procesado | **Verificado por diseño**: no existe carga de PDF/Word; solo texto pegado, y solo se marca "añadido" tras una escritura exitosa a la base de datos (con manejo de error si falla). |
| 9 | Instrucciones maliciosas dentro de un documento no se obedecen | Cubierto por instrucción explícita al modelo (tratar los fragmentos como datos, nunca como instrucciones); **pendiente** de verificación en ejecución real. |
| 10 | La interfaz no se encima en pantallas pequeñas | **Verificado por código/CSS** (breakpoints en 900px y 700px, paneles pasan a superposición con `position:fixed`); no se verificó con captura visual real en un dispositivo. |

Adicionalmente se verificó, con herramientas de desarrollo: sintaxis de JavaScript válida (`node --check`), balance de etiquetas HTML (div/select/aside/main/form/button), y que la ruta de datos por documento (`data/users/<id>/profile/chats/<id>`) respeta la gramática de rutas de la capacidad `db` (segmentos pares = documento, impares = colección).

## 8. Guía breve para incorporar documentación

1. Abre el Artifact y despliega el panel derecho (ícono ▤ en la barra superior) → pestaña "Documentación".
2. Copia el fragmento de texto autorizado (una sección de un manual, un procedimiento interno, la descripción de una captura) — evita pegar manuales completos; mejor un fragmento por sección.
3. Completa: Título, Módulo, Versión aplicable (si se conoce), Revisión/fecha, Origen (oficial / procedimiento interno / ejemplo) y Sección.
4. Pega el contenido y pulsa "Añadir a la base de conocimiento".
5. El asistente lo usará automáticamente cuando una pregunta coincida por palabras clave con ese fragmento, y lo citará por título y sección en la respuesta.

## 9. Alternativa si el motor de IA no está disponible en tu visor

Si al abrir el Artifact ves el aviso de que el motor de IA no está disponible, usa el mismo enfoque dentro de un **Project de Claude**:

1. Crea un Project nuevo en Claude.
2. Pega como instrucciones del Project el bloque de reglas que se muestra en el botón "Cómo funciona este asistente" dentro de la app (o pide el texto `RULES_BLOCK` del archivo fuente).
3. Sube como archivos del Project la documentación autorizada que quieras que el asistente use (texto/Markdown; extrae primero el texto de cualquier PDF/Word).
4. Conversa normalmente dentro del Project — tendrás el mismo comportamiento, con las citas y los límites de seguridad definidos en las instrucciones.
