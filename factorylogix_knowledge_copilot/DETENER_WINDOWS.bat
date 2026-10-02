@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title FactoryLogix Knowledge Copilot - Detener
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo No hay instalacion en esta carpeta.
    pause
    exit /b 1
)
"%VPY%" "scripts\stop.py"
pause
exit /b 0
