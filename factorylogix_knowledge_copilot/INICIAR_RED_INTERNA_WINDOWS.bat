@echo off
REM Inicia la aplicacion accesible desde la red interna (0.0.0.0).
REM Los equipos de produccion solo necesitan un navegador: http://IP-DEL-SERVIDOR:PUERTO
cd /d "%~dp0"
call "%~dp0INICIAR_WINDOWS.bat" red
