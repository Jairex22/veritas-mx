# Manual de usuario

## 1. Qué es y qué no es

- **Es** un asistente que busca en procedimientos, instrucciones, manuales y Q&A **aprobados y vigentes** y
  responde con la fuente exacta.
- **No es** un sistema que ejecute transacciones: nunca hará Proceed, Unproceed, Reroute ni cerrará defectos.
- **Puede equivocarse**: valida siempre contra el procedimiento vigente. No promete precisión del 100 %.

## 2. Iniciar sesión

1. Abre la URL indicada por tu supervisor (por ejemplo `http://servidor-mes:8501`).
2. Ingresa usuario y contraseña. En el primer acceso se exige cambiar la contraseña
   (mínimo 12 caracteres, mayúscula, minúscula y número; no incluir tu usuario).
3. La sesión se cierra automáticamente tras 30 minutos sin actividad.

Idioma: selector **Español / English** en la barra lateral.

## 3. Hacer una pregunta

1. Ve a **Chat**.
2. Escribe la pregunta en el cuadro grande o pulsa una **pregunta sugerida**.
3. Opcional: abre **Filtros** para limitar por cliente, producto, línea, proceso, estación o módulo.
4. Pulsa **Preguntar**.

### Cómo leer la respuesta

| Elemento | Significado |
|---|---|
| Confianza (Alta/Media/Baja) | Combina relevancia, tipo de fuente, vigencia y respaldo. Contenido DEMO nunca es “Alta”. Conflictos = “Baja” |
| Respuesta breve | Resumen copiado de la fuente aprobada |
| Pasos | Pasos del procedimiento, en orden |
| Qué validar / Resultado esperado | Verificaciones antes de continuar |
| Cuándo detenerse | Condiciones para parar |
| Cuándo escalar + Ruta de escalamiento | A quién acudir |
| Fuentes | Código, título, versión, tipo, clasificación, sección/página. “Ver evidencia” muestra el fragmento |
| Avisos amarillos | DEMO, información no vigente, instrucciones ignoradas por seguridad |
| Aviso rojo de conflicto | Dos fuentes aprobadas se contradicen: **no actúes**, escala |
| “No especificado en la fuente aprobada” | El documento no trae esa sección; no se inventa |

Si no hay evidencia verás: *“No encontré información aprobada suficiente para confirmar esta respuesta. Consulta a
MES, Producto o al supervisor responsable.”*

### Profundidad por rol

- **Operador**: instrucciones breves y seguras; fuentes plegadas.
- **Supervisor**: diagnóstico y escalamiento; fuentes visibles con relevancia.
- **MES / Ingeniería / Calidad / NPI**: además, detalle técnico de recuperación.
- **Administrador**: además, modo, latencia e ID de correlación.

## 4. Acciones sobre una respuesta

- **Descargar evidencia**: archivo de texto con respuesta, fuentes y fragmentos.
- **Copiar / descargar respuesta**: texto listo para copiar.
- **👍 Útil / 👎 No útil**: feedback anónimo agregado.
- **Reportar respuesta incorrecta**: describe el error y, si sabes, la respuesta correcta. Va a una bandeja de
  revisión; **no se usa hasta que una persona la apruebe**.
- **Crear solicitud de escalamiento**: arma el paquete para MES (WO, serial, ensamble, estación, operación,
  mensaje de error, captura, fuentes, diagnóstico, urgencia, área).

## 5. Situaciones especiales

- **Seguridad física** (humo, chispa, descarga, lesión): el sistema muestra primero *detén la operación y avisa*.
- **Solicitudes de ejecutar transacciones**: se indica que el asistente no las ejecuta.
- **Urgencia**: si escribes “línea parada / urgente”, se muestran primero las acciones de escalamiento.

## 6. Análisis de sentimiento (aviso de transparencia)

Se usa solo para adaptar el tono (pasos más cortos si hay confusión, escalamiento primero si es urgente). No evalúa
personas, no crea rankings, no se usa para decisiones laborales, guarda solo la etiqueta por un tiempo limitado y
puede desactivarse.

## 7. Fuentes e incidentes

- **Fuentes**: lista de documentos publicados visibles para tu rol con su evidencia.
- **Incidentes**: tus solicitudes de escalamiento, estado y reporte imprimible (Ctrl+P → PDF).

## 8. Consulta en vivo de FactoryLogix (si está habilitada)

En el Chat, “Información consultada en FactoryLogix (solo lectura)” permite consultar entidades autorizadas
(por ejemplo WIP por Work Order). Esos datos se muestran separados de la información documental y de las
inferencias del sistema.
