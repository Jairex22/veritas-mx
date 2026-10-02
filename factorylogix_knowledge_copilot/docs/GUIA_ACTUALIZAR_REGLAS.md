# Guía para actualizar reglas

Las reglas están en `config/rules.yaml` (texto YAML, editable con el Bloc de notas). Tras modificarlas:

1. Crear un respaldo (Salud del sistema).
2. Guardar el archivo en UTF-8.
3. Reiniciar la aplicación (`DETENER_WINDOWS.bat` → `INICIAR_WINDOWS.bat`).
4. Ejecutar **Evaluaciones** y, si cambió el glosario, **Reindexar** en Training Center.
5. Registrar el cambio (quién, qué, por qué) en el control de cambios de MES.

## 1. Glosario bilingüe (`glossary`)

Grupos de sinónimos que se tratan como un mismo concepto en la búsqueda (no modifican documentos):

```yaml
glossary:
  - ["work order", "orden de trabajo", "wo", "orden de produccion"]
```

- Escribir sin acentos y en minúsculas (la normalización elimina acentos).
- Agregar términos de planta, abreviaturas internas y equivalentes en inglés.
- Evitar grupos demasiado amplios (aumentan falsos positivos).

## 2. Patrones de prompt injection (`injection_patterns`)

Expresiones regulares evaluadas sobre texto normalizado (minúsculas, sin acentos). Al detectar una, el documento
requiere confirmación del aprobador y la oración se excluye de respuestas y del contexto del LLM.

## 3. Solicitudes de transacción (`production_action_patterns`)

Detectan peticiones como “haz el unproceed…”. El asistente responde que no ejecuta transacciones.

## 4. Seguridad física (`safety_patterns`)

Palabras de riesgo (humo, fuego, descarga…). La respuesta muestra primero detener y escalar a EHS.

## 5. Escalamiento (`escalation_keywords`) y ruta por defecto

`escalation_keywords` agrega una inferencia de impacto operativo. La ruta por defecto se configura en
`settings.yaml → escalation.default_route_es/en` y las áreas en `escalation.areas`.

## 6. Léxico de sentimiento (`sentiment`)

Listas por idioma para `confused`, `frustrated`, `urgent`, `satisfied` y `negations`. Recordatorio ético: el
sentimiento solo adapta el tono; no debe ampliarse para evaluar personas.

## 7. Parámetros de recuperación (`settings.yaml → rag`)

| Parámetro | Efecto |
|---|---|
| `min_relevance` | Umbral para responder (más alto = más “No encontré…”) |
| `high_confidence` / `medium_confidence` | Cortes de nivel de confianza |
| `top_k`, `candidate_pool`, `rrf_k`, `rerank` | Recuperación y fusión |
| `review_soon_days` | Aviso de revisión próxima |

Cambiar un parámetro siempre debe acompañarse de una evaluación RAG.
