@echo off
REM GPV - Portal del turno (piloto SMT). Inicio local en ESTE equipo (doble clic).
REM Solo escucha en 127.0.0.1 (no se abre a la red ni se cambia el firewall).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecute INSTALAR.bat
  pause & exit /b 1
)
echo Iniciando servicio local del turno (sincronizacion OData de solo lectura, recordatorios y borradores de reporte)...
start "GPV servicio del turno" /min ".venv\Scripts\python.exe" manage.py run_scheduler
echo Abriendo http://127.0.0.1:8000/ ... Deje esta ventana abierta mientras use el portal.
echo Si cierra las ventanas o el equipo se suspende, al volver se generan una sola vez los borradores pendientes
echo y se informa el periodo sin consulta (ver RESPALDO_RESTAURACION_Y_SOPORTE.md).
start "" "http://127.0.0.1:8000/"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000 --noreload
pause
