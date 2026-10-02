# knowledge_base

Almacén local de los archivos originales cargados desde el Training Center.

- `files/<id-documento>/v<N>_<archivo>`: archivo original de cada versión (nombre sanitizado).
- Los archivos solo se escriben mediante la aplicación (validación de tipo, tamaño y ruta).
- Incluir esta carpeta en los respaldos junto con `data/copilot.db` (ver `docs/PLAN_RESPALDO_RESTAURACION.md`).
