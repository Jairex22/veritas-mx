# Matriz RBAC

> Generado automáticamente por `scripts/generate_docs.py` desde `security/rbac.py` y `config/settings.yaml`. No editar a mano.

## Permisos por rol

| Permiso | Descripción | Operator | Supervisor | Product Engineer | Quality | NPI | MES Support | Knowledge Manager | Data Steward | Administrator | Auditor |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `chat.query` | Consultar conocimiento aprobado | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `sources.view` | Ver fuentes y evidencias | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `sources.download` | Descargar archivo original |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `incident.create` | Crear incidentes/escalamientos | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |  |
| `incident.manage` | Gestionar todos los incidentes |  | ✔ |  |  |  | ✔ |  |  | ✔ |  |
| `analytics.view` | Ver analítica general |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `knowledge.upload` | Cargar documentos y nuevas versiones |  |  |  |  |  |  | ✔ |  | ✔ |  |
| `knowledge.edit` | Editar contenido y Q&A |  |  |  |  |  |  | ✔ |  | ✔ |  |
| `knowledge.approve` | Aprobar o rechazar contenido |  |  |  |  |  |  | ✔ | ✔ | ✔ |  |
| `knowledge.publish` | Publicar, desactivar, rollback |  |  |  |  |  |  | ✔ | ✔ | ✔ |  |
| `governance.manage` | Metadatos, vigencia, clasificación, retención |  |  |  |  |  |  |  | ✔ | ✔ |  |
| `governance.view` | Ver gobierno de datos y catálogo |  |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `documents.delete` | Eliminación autorizada |  |  |  |  |  |  |  | ✔ | ✔ |  |
| `feedback.review` | Revisar feedback y correcciones |  |  |  |  |  | ✔ | ✔ |  | ✔ |  |
| `eval.run` | Ejecutar evaluación RAG |  |  |  |  |  |  | ✔ | ✔ | ✔ |  |
| `eval.view` | Ver resultados de evaluación |  |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `users.manage` | Usuarios y roles |  |  |  |  |  |  |  |  | ✔ |  |
| `settings.manage` | Configuración |  |  |  |  |  |  |  |  | ✔ |  |
| `audit.view` | Ver auditoría |  |  |  |  |  |  |  |  | ✔ | ✔ |
| `health.view` | Ver salud del sistema |  |  |  |  |  | ✔ |  |  | ✔ | ✔ |
| `export.data` | Exportar datos y reportes |  | ✔ |  | ✔ |  | ✔ | ✔ | ✔ | ✔ | ✔ |
| `connectors.query` | Consultar FactoryLogix en vivo (solo lectura) |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |  |
| `debug.view` | Ver detalles técnicos de recuperación |  |  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

## Acceso por clasificación de información

| Rol | Public | Internal | Confidential | Restricted | Profundidad de respuesta |
|---|:-:|:-:|:-:|:-:|---|
| Operator | ✔ | ✔ | — | — | operator |
| Supervisor | ✔ | ✔ | ✔ | — | supervisor |
| Product Engineer | ✔ | ✔ | ✔ | — | engineering |
| Quality | ✔ | ✔ | ✔ | — | engineering |
| NPI | ✔ | ✔ | ✔ | — | engineering |
| MES Support | ✔ | ✔ | ✔ | ✔ | engineering |
| Knowledge Manager | ✔ | ✔ | ✔ | — | engineering |
| Data Steward | ✔ | ✔ | ✔ | ✔ | engineering |
| Administrator | ✔ | ✔ | ✔ | ✔ | admin |
| Auditor | ✔ | ✔ | ✔ | ✔ | engineering |

## Principios

- Mínimo privilegio: el Operador solo consulta conocimiento aprobado y crea escalamientos.
- Segregación de funciones: quien carga una versión no puede aprobarla (`governance.require_four_eyes`).
- El Auditor tiene acceso de solo lectura a evidencias y registros; no modifica contenido.
- La clasificación se filtra ANTES del ranking: el contenido no autorizado nunca llega a la respuesta.
- Los intentos de recuperar fuentes no autorizadas quedan en auditoría (`rag.restricted_source_denied`).
