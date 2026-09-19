@echo off
REM ============================================================================
REM  GPV Operator Performance Hub - Ejecutar pruebas del backend (Windows)
REM ============================================================================
setlocal
cd /d "%~dp0backend"

if not exist ".venv" (
    echo No se encontro el entorno virtual. Ejecuta primero start-backend.bat una vez.
    pause
    exit /b 1
)

call ".venv\Scripts\pytest.exe" tests -v
pause
