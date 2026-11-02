@echo off
setlocal
REM GPV Operations Hub - instalacion local (doble clic). No requiere administrador ni PowerShell.
cd /d "%~dp0"
if not exist "manage.py" (
  echo ERROR: este archivo debe estar en la carpeta que contiene manage.py.
  pause & exit /b 1
)
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")
%PY% --version || (echo No se encontro Python 3.11-3.13. Solicitelo a TI. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno .venv ...
  %PY% -m venv .venv || (pause & exit /b 1)
)
echo Instalando dependencias (requiere Internet o carpeta de ruedas, ver INSTALACION_WINDOWS.md) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" manage.py migrate || (pause & exit /b 1)
".venv\Scripts\python.exe" manage.py check || (pause & exit /b 1)
echo.
set /p CREAR=Crear ahora el usuario administrador? (S/N): 
if /i "%CREAR%"=="S" ".venv\Scripts\python.exe" manage.py createsuperuser
set /p DEMO=Cargar datos de demostracion sinteticos? (S/N): 
if /i "%DEMO%"=="S" ".venv\Scripts\python.exe" manage.py seed_demo
echo.
echo Instalacion terminada. Para usar el portal ejecute INICIAR.bat
pause
