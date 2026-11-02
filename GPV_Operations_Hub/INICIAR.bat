@echo off
REM GPV Operations Hub - iniciar el sitio local (doble clic). Ctrl+C o cerrar la ventana para detener.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecute INSTALAR.bat
  pause & exit /b 1
)
echo Abriendo http://127.0.0.1:8000/ ... Deje esta ventana abierta mientras use el portal.
start "" "http://127.0.0.1:8000/"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
pause
