@echo off
REM Ejecutar en un equipo AUTORIZADO con acceso a PyPI (o al repositorio interno de paquetes).
REM Genera la carpeta wheels\ para instalar en el servidor sin acceso a Internet.
cd /d "%~dp0.."
python -m pip download -r requirements.txt -d wheels
echo Copie la carpeta wheels\ al servidor y ejecute:
echo   python -m pip install --no-index --find-links wheels -r requirements.txt
