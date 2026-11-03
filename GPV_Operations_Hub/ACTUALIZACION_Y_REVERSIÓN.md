# Actualización y reversión (v1.0.x → v1.1.0)

La versión 1.1.0 **agrega** el portal del turno (`apps/shift`) sin modificar tablas existentes:
la migración `shift/0001_initial` solo crea tablas nuevas. Los datos y funciones de v1.0.x se conservan.

## Actualizar

1. En la versión anterior: `.venv\Scripts\python.exe manage.py gpv_backup` y copie el ZIP fuera de la carpeta.
2. Cierre las ventanas del portal.
3. Extraiga `GPV_SMT_Portal_Turno_Piloto.zip` en una carpeta **nueva**.
4. Copie desde la versión anterior a la nueva: la carpeta `data\` completa y el archivo `.env`.
   (Si `GPV_DATA_DIR` apunta fuera de la carpeta, basta con copiar `.env`.)
5. Doble clic en `INSTALAR.bat` (instala dependencias y aplica migraciones; responda **N** a crear
   administrador y a datos de demostración si ya los tiene).
6. Doble clic en `INICIAR.bat`.

Verificado con una copia de la base v1.0.1: migración aplicada y datos previos intactos (ver
`PRUEBAS_Y_RESULTADOS.md`).

## Revertir

1. Cierre las ventanas del portal.
2. Vuelva a usar la carpeta de la versión anterior (no se modificó) con su `data\` original, **o**
   restaure el respaldo del paso 1 en la versión anterior:
   `.venv\Scripts\python.exe manage.py gpv_restore <respaldo.zip> --confirmar`.
3. Los datos capturados en el portal del turno después de actualizar se pierden al revertir; respáldelos
   antes con `gpv_backup` si se necesitan para análisis.

Nunca se escribe en FactoryLogix, así que actualizar o revertir no afecta a FactoryLogix.
