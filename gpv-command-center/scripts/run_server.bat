@echo off
REM GPV FactoryLogix Command Center - arranque en Windows (cmd).
REM Ejecutar desde la carpeta raiz del proyecto con el entorno virtual activado o con Python en PATH.
REM Puerto y host configurables: run_server.bat 0.0.0.0 8080
setlocal
set HOST=%1
if "%HOST%"=="" set HOST=127.0.0.1
set PORT=%2
if "%PORT%"=="" set PORT=8080
cd /d "%~dp0.."
python -m uvicorn backend.app.main:create_app --factory --host %HOST% --port %PORT% --proxy-headers
endlocal
