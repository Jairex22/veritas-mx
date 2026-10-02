# Guía para agregar conocimiento

> “Entrenar” mediante RAG = **agregar y aprobar conocimiento recuperable**. No modifica pesos de modelos y el
> bot no aprende de las conversaciones.

## 1. Preparar el documento

Formatos: PDF con texto, DOCX, XLSX, CSV, TXT, Markdown, HTML (imágenes solo con OCR instalado).
Límites por defecto: 25 MB, 400 páginas, 20 000 filas.

**Plantilla recomendada** (Markdown o DOCX con estilos Título 1/2/3). Cada tema (`##`) se vuelve un fragmento
autocontenido y las subsecciones (`###`) se convierten en las partes de la respuesta estándar:

```markdown
# Procedimiento: <nombre>

## <Tema o pregunta que resuelve>
Palabras clave: <sinónimos en español e inglés>

### Respuesta breve
<1-3 oraciones>

### Pasos
1. ...
2. ...

### Qué validar
- ...

### Resultado esperado
...

### Cuándo detenerse
...

### Cuándo escalar
...
```

Encabezados reconocidos (ES/EN): Respuesta breve/Summary, Pasos/Steps, Qué validar/What to check, Resultado
esperado/Expected result, Cuándo detenerse/When to stop, Cuándo escalar/When to escalate, Advertencias/Warnings.

FAQ en CSV: columnas `pregunta,respuesta[,modulo]` (o `question,answer`) — cada fila se convierte en un tema.

Buenas prácticas: un tema por pregunta real de piso; cifras explícitas (tolerancias, reintentos); evitar
contradicciones con otras fuentes; incluir sinónimos en “Palabras clave”.

## 2. Cargar (Knowledge Manager)

Training Center → **Cargar documento**: archivo + metadatos obligatorios (código, título, descripción, tipo,
propietario, aprobador, área, módulo, clasificación, retención, fechas efectiva y de revisión; expiración opcional).
Se muestra: texto extraído, duplicados exactos/similares, posibles prompt injection y advertencias de extracción.

Nueva versión de un documento existente: **Nueva versión** (conserva el código).

## 3. Revisar y aprobar (otra persona: Data Steward / Knowledge Manager)

**Revisión y aprobación**: leer el texto extraído completo → *Enviar a revisión* → *Aprobar* / *Rechazar*
(motivo obligatorio) / *Regresar a Draft*. Si hay hallazgos de injection, se debe confirmar explícitamente.

## 4. Publicar

**Publicar** → *Ejecutar pruebas previas*:

| Prueba | Crítica |
|---|---|
| Texto suficiente, metadatos completos, no expirado, fecha efectiva, injection revisado, fragmentos indexados | Sí (bloquea) |
| Revisión vigente, sin duplicado aprobado, recuperable por sus temas, sin contradicciones | No (advertencia) |

Al publicar, la versión anterior pasa a `Archived`.

## 5. Mantener

- **Versiones y rollback**: comparar versiones (diff) y restaurar una versión aprobada anterior con motivo.
- **Catálogo**: editar metadatos (con motivo), vigencia, activar/desactivar.
- **Q&A aprobadas**: proponer Q&A; otra persona aprueba y se publica como fuente “Approved Q&A”.
- **Feedback Review**: convertir reportes de respuestas incorrectas en Q&A propuestas.
- Después de cambios importantes: **Evaluaciones → Ejecutar evaluación**.
