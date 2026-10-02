@echo off
setlocal EnableExtensions
REM ==================================================================
REM  FactoryLogix Knowledge Copilot - Instalacion (sin PowerShell,
REM  sin permisos de administrador, sin Node/npm/Docker).
REM  Uso: INSTALAR_WINDOWS.bat            (instalacion normal)
REM       INSTALAR_WINDOWS.bat /force     (reinstalar dependencias)
REM ==================================================================
cd /d "%~dp0"
title FactoryLogix Knowledge Copilot - Instalacion
set "AUTO="
set "FORCE="
if /I "%~1"=="/auto" set "AUTO=1"
if /I "%~1"=="/force" set "FORCE=1"
if /I "%~2"=="/force" set "FORCE=1"

echo ==================================================================
echo  FactoryLogix Knowledge Copilot - Instalacion
echo  Carpeta: %CD%
echo ==================================================================

call :find_python
if errorlevel 1 goto :no_python

echo.
echo [1/5] Validando version de Python...
%PY_EXE% %PY_ARGS% "scripts\check_env.py" python
if errorlevel 2 goto :bad_python

echo.
echo [2/5] Preparando entorno virtual .venv ...
if exist ".venv\Scripts\python.exe" goto :venv_ok
%PY_EXE% %PY_ARGS% -m venv .venv
if errorlevel 1 goto :venv_fail
:venv_ok
if not exist ".venv\Scripts\python.exe" goto :venv_fail
set "VPY=%~dp0.venv\Scripts\python.exe"
echo Entorno virtual: "%VPY%"

echo.
echo [3/5] Verificando dependencias...
if defined FORCE goto :install
"%VPY%" "scripts\check_env.py" installed
if not errorlevel 1 (
    echo Dependencias ya instaladas y actualizadas. No se reinstala.
    goto :init
)

:install
echo Instalando dependencias. Puede tardar varios minutos...
if exist "wheelhouse\" (
    echo Modo sin Internet: usando la carpeta wheelhouse
    "%VPY%" -m pip install --no-index --find-links wheelhouse -r requirements.txt
) else (
    "%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
)
if errorlevel 1 goto :pip_fail
"%VPY%" "scripts\check_env.py" mark-installed
if errorlevel 1 goto :pip_fail

:init
echo.
echo [4/5] Inicializando base de datos y conocimiento DEMO...
"%VPY%" "scripts\launch.py" --check-only --no-browser
if errorlevel 1 goto :init_fail

echo.
echo [5/5] Instalacion completada.
echo  - Para iniciar: INICIAR_WINDOWS.bat
echo  - Para red interna: INICIAR_RED_INTERNA_WINDOWS.bat
echo  - Si aparecio una contrasena temporal de admin, guardala en un lugar seguro.
if not defined AUTO pause
exit /b 0

REM ------------------------------------------------------------------
:find_python
set "PY_EXE="
set "PY_ARGS="
where py >nul 2>nul
if errorlevel 1 goto :try_python
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto :try_python
set "PY_EXE=py"
set "PY_ARGS=-3"
exit /b 0
:try_python
where python >nul 2>nul
if errorlevel 1 exit /b 1
python -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 1
set "PY_EXE=python"
set "PY_ARGS="
exit /b 0

REM ------------------------------------------------------------------
:no_python
echo.
echo ERROR: no se encontro Python ("py" o "python").
echo  - Instala Python 3.11 o 3.12 desde el instalador aprobado por TI.
echo  - Puedes instalarlo "solo para el usuario actual" (no requiere administrador)
echo    y marcar "Add python.exe to PATH".
echo  - Si "python" abre la Microsoft Store, desactiva el alias en
echo    Configuracion ^> Aplicaciones ^> Alias de ejecucion de aplicaciones.
goto :fail

:bad_python
echo.
echo ERROR: version de Python no soportada. Se requiere 3.10 o superior (recomendado 3.11/3.12).
goto :fail

:venv_fail
echo.
echo ERROR: no se pudo crear .venv\Scripts\python.exe
echo  - Verifica que tu Python incluya el modulo venv.
echo  - Verifica permisos de escritura en esta carpeta (no uses Archivos de programa).
goto :fail

:pip_fail
echo.
echo ERROR: fallo la instalacion de dependencias.
echo  - Sin Internet: copia la carpeta "wheelhouse" preparada con
echo    scripts\PREPARAR_WHEELS_OFFLINE.bat en un equipo con acceso.
echo  - Con proxy corporativo: define HTTPS_PROXY antes de ejecutar este archivo.
echo  - Para reintentar desde cero: INSTALAR_WINDOWS.bat /force
goto :fail

:init_fail
echo.
echo ERROR: no se pudo inicializar la aplicacion. Revisa logs\app.log
goto :fail

:fail
echo.
echo La instalacion NO se completo. Esta ventana permanece abierta.
pause
exit /b 1
