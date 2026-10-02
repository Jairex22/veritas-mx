@echo off
setlocal EnableExtensions
REM Ejecutar en un equipo Windows CON Internet y la MISMA version de Python que produccion.
REM Genera la carpeta "wheelhouse" para instalar sin Internet con INSTALAR_WINDOWS.bat.
cd /d "%~dp0.."
set "PY_EXE=py"
set "PY_ARGS=-3"
where py >nul 2>nul
if errorlevel 1 (
    set "PY_EXE=python"
    set "PY_ARGS="
)
%PY_EXE% %PY_ARGS% -m pip download -r requirements.txt -d wheelhouse --only-binary=:all:
if errorlevel 1 (
    echo ERROR: no se pudieron descargar los paquetes.
    pause
    exit /b 1
)
echo Listo. Copia la carpeta "wheelhouse" junto con la aplicacion al equipo destino.
pause
exit /b 0
