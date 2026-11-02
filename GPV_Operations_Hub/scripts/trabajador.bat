@echo off
REM Proceso de trabajos persistentes (solo si GPV_JOBS_MODE=worker). Ctrl+C para detener.
cd /d "%~dp0\.."
".venv\Scripts\python.exe" manage.py run_worker
