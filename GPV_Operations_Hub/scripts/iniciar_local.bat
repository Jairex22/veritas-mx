@echo off
REM Atajo OPCIONAL para iniciar el portal local. Si su organizacion bloquea .bat, escriba los comandos de INSTALACION_WINDOWS.md.
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo No existe el entorno .venv. Siga INSTALACION_WINDOWS.md (pasos 3 a 7).
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py check || (pause & exit /b 1)
echo Abra http://127.0.0.1:8000/ en Edge o Chrome. Para detener: Ctrl+C
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
