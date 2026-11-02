@echo off
REM Planificador de reportes programados. Mantenga UNA sola ventana activa. Ctrl+C para detener.
cd /d "%~dp0\.."
".venv\Scripts\python.exe" manage.py run_scheduler
