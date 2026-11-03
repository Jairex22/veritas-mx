# Respaldo, restauración y soporte

## Respaldo

```bat
.venv\Scripts\python.exe manage.py gpv_backup
```

Genera `data\backups\gpv_backup_AAAAMMDD_HHMMSS.zip` con **toda** la base (incluye el portal del
turno: líneas, estaciones, eventos con su conciliación, ayudas, paros, reportes y relevos) y los
archivos privados (fotos, evidencias, PDF de reportes). Las credenciales OData **no** están en la
base, por lo que tampoco en el respaldo. Copie el ZIP a otro equipo o carpeta autorizada.
Recomendado: antes de cada actualización y al final de cada día del piloto.

## Restauración

```bat
.venv\Scripts\python.exe manage.py gpv_restore data\backups\gpv_backup_AAAAMMDD_HHMMSS.zip --confirmar
```

Reemplaza los datos actuales (pide `--confirmar`). Probado en `apps/core/tests/test_backup.py`
(incluye datos del portal del turno y vínculos de conciliación).

## Qué pasa si la computadora se suspende, se apaga o se cierra INICIAR.bat

| Situación | Efecto | Al volver a abrir INICIAR.bat |
|---|---|---|
| Nadie consulta el portal | Nada: el servicio local sigue trabajando sin pestañas abiertas | — |
| Equipo suspendido/apagado o ventana del servicio cerrada | No hay consultas a OData, recordatorios ni borradores | Se registra la **laguna** (desde/hasta) en *Fuentes* y en *Supervisión* |
| Laguna con campo de modificación fiable | Recuperable: la consulta incremental relee desde la última marca con solape | Se marca «recuperable» |
| Laguna sin campo de modificación y mayor que la ventana (24 h) | El tramo anterior a la ventana **no** se reconsulta automáticamente | Se marca «no recuperable automáticamente»; use captura manual o un ajuste de ventana autorizado |
| Turnos que terminaron mientras estaba apagado | — | Se generan **una sola vez** los borradores pendientes (últimos 7 días, solo turnos posteriores al alta de la línea) y sus relevos |
| Datos que llegan después del cierre | — | Se crea una revisión nueva del reporte; la cerrada se conserva |
| OData falla | Se conserva el último dato con su hora; estado «Desconectado»; reintentos con espera creciente | La captura web sigue disponible |

Los navegadores guardan sin red solo las **solicitudes de ayuda** (bajo riesgo) y las reenvían con el
mismo identificador, de modo que no se duplican.

## Diagnóstico y registros

* `manage.py gpv_diagnose` — revisión de configuración, base, carpetas y dependencias.
* `data\logs\` — registros de la aplicación (sin credenciales).
* *Administración › Auditoría* — quién hizo qué (cambios de meta, cierres, disposiciones, configuración).

## Soporte

| Síntoma | Revisar |
|---|---|
| «Requiere revisión» en la fuente | Conexión no validada o desactivada: ejecutar *Diagnosticar por etapas* |
| «Desconectado» | Red/VPN, URL, credenciales (variables de entorno), permisos de la cuenta en FactoryLogix |
| «Con retraso» | El servicio local no está corriendo (ventana minimizada «GPV servicio del turno») |
| No llegan ayudas a un equipo | Grupo del motivo y sus integrantes; áreas del perfil |
| El reporte no se genera | Servicio local corriendo; línea marcada «piloto»; turno configurado |
