# Plan de respaldo y restauración

## Qué respaldar

| Elemento | Ruta | Criticidad |
|---|---|---|
| Base de datos (documentos, versiones, fragmentos, usuarios, auditoría) | `data\copilot.db` | Crítica |
| Archivos originales | `knowledge_base\files\` | Alta |
| Configuración | `config\*.yaml`, `.streamlit\config.toml` | Alta |
| Secretos | `.env` | Alta (respaldar en bóveda de TI, no junto a los datos) |
| Adjuntos de incidentes y logo | `data\attachments\`, `data\branding\` | Media |

## Cómo respaldar

1. **Desde la aplicación** (Administrador): Salud del sistema → *Crear respaldo ahora*. Genera
   `data\backups\respaldo_<fecha>.zip` con copia en caliente consistente de SQLite (API de backup) y los archivos
   originales. Conserva los 14 más recientes.
2. **Programado** (TI): tarea programada que copie `data\backups\` y `config\` a un recurso de red con
   control de acceso. Frecuencia sugerida: diaria; retención 30 días + mensual 12 meses.
3. Antes de actualizar la aplicación o cambiar el proveedor de embeddings, crear un respaldo manual.

## Restauración

1. Ejecutar `DETENER_WINDOWS.bat`.
2. Mover `data\copilot.db` actual a una carpeta de cuarentena (no borrarlo).
3. Extraer el ZIP de respaldo: copiar `copilot_<fecha>.db` como `data\copilot.db` y
   `knowledge_base_files\` como `knowledge_base\files\`.
4. Restaurar `config\` y `.env` si corresponde.
5. Ejecutar `INICIAR_WINDOWS.bat`, iniciar sesión como Administrador y revisar **Salud del sistema**:
   integridad SQLite = OK, cadena de auditoría = OK, índice con fragmentos.
6. Ejecutar **Evaluaciones** y comparar con el último resultado.
7. Registrar la restauración en el sistema de gestión de cambios de TI.

## Prueba de restauración

Realizarla al menos trimestralmente en un equipo distinto. Objetivos sugeridos: RPO 24 h, RTO 2 h.
