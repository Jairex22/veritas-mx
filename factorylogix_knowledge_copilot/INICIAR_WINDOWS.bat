@echo off
setlocal EnableExtensions
REM ==================================================================
REM  FactoryLogix Knowledge Copilot - Inicio
REM  Uso: INICIAR_WINDOWS.bat          (solo este equipo, 127.0.0.1)
REM       INICIAR_WINDOWS.bat red      (red interna, 0.0.0.0)
REM ==================================================================
cd /d "%~dp0"
title FactoryLogix Knowledge Copilot
set "VPY=%~dp0.venv\Scripts\python.exe"

if not exist "%VPY%" (
    echo Primera ejecucion: instalando...
    call "%~dp0INSTALAR_WINDOWS.bat" /auto
    if errorlevel 1 goto :fail
)
if not exist "%VPY%" goto :fail

"%VPY%" "scripts\check_env.py" installed
if errorlevel 1 (
    echo Las dependencias cambiaron o estan incompletas: actualizando...
    call "%~dp0INSTALAR_WINDOWS.bat" /auto
    if errorlevel 1 goto :fail
)

set "BIND=local"
if /I "%~1"=="red" set "BIND=network"
if /I "%~1"=="network" set "BIND=network"

echo Iniciando en modo: %BIND%
"%VPY%" "scripts\launch.py" --bind %BIND%
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo ERROR: la aplicacion no pudo iniciar. Revisa los mensajes anteriores y logs\app.log
echo Esta ventana permanece abierta.
pause
exit /b 1
