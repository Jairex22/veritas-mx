# Política de retención

> Valores por defecto configurables en `config/settings.yaml → governance.retention_policies`. Deben ser
> validados por Calidad, Legal y TI antes de producción.

## Documentos

| Política | Eliminación elegible después de | Uso sugerido |
|---|---|---|
| `standard-3y` | 1095 días desde archivo/decisión | Procedimientos e instrucciones generales |
| `quality-10y` | 3650 días | Registros con requisitos de calidad/cliente |
| `temporary-1y` | 365 días | Avisos temporales |
| `demo` | 30 días | Contenido DEMO |

Reglas:

1. Solo versiones `Archived`, `Rejected` o `Expired` son elegibles; nunca la versión publicada vigente.
2. La eliminación **no es automática**: Gobierno → Retención lista las versiones elegibles y un Data Steward o
   Administrador ejecuta la **eliminación autorizada** con motivo obligatorio.
3. La eliminación borra archivo original, texto extraído y fragmentos; conserva una lápida en el catálogo
   (`deleted_at`, `deleted_reason`) y toda la auditoría.
4. Las versiones vencidas pasan a `Expired` automáticamente al arrancar o desde Gobierno.

## Datos operativos

| Dato | Retención | Mecanismo |
|---|---|---|
| Etiqueta de sentimiento | 30 días (configurable 1-365) | `sentiment_expires_at`; se borra al arrancar |
| Señales de sentimiento (palabras) | No se almacenan | Solo en memoria para la respuesta |
| Preguntas (`query_log`) | Según política interna (recomendado 12 meses) | Exportar/purgar por TI con respaldo previo |
| Incidentes | Según política de calidad | Estado `Closed`; exportación CSV |
| Auditoría | Mínimo 3 años (recomendado) | Append-only; archivar exportaciones fuera del equipo |
| Log técnico | 5 archivos × 5 MB rotativos | `RotatingFileHandler` |
| Respaldos | Últimos 14 | `BackupService.prune` |
