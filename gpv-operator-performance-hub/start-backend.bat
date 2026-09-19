@echo off
REM ============================================================================
REM  GPV Operator Performance Hub - Inicio del backend (Windows, sin PowerShell)
REM ============================================================================
setlocal
cd /d "%~dp0backend"

if not exist ".env" (
    echo Creando backend\.env a partir de .env.example...
    copy ".env.example" ".env" >nul
)

if not exist ".venv" (
    echo Creando entorno virtual de Python en backend\.venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo crear el entorno virtual. Verifica que Python 3.11+ este instalado y en el PATH.
        pause
        exit /b 1
    )
)

echo Instalando/actualizando dependencias...
call ".venv\Scripts\pip.exe" install -q --upgrade pip
call ".venv\Scripts\pip.exe" install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias. Revisa el mensaje anterior.
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo  Iniciando backend en http://localhost:8000
echo  (La primera vez generara automaticamente datos simulados de demostracion)
echo  Presiona Ctrl+C para detener el servidor.
echo ============================================================================
echo.
call ".venv\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8000 --reload

pause
