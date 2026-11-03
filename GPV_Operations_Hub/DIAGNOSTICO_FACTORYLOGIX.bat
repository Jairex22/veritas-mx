@echo off
REM Diagnostico de FactoryLogix (OData, solo lectura). Ejecutar en un equipo de la red de GPV.
REM Etapa 1 (siempre): configuracion, autenticacion ofrecida, documento de servicio y $metadata.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecute INSTALAR.bat en esta misma carpeta.
  pause & exit /b 1
)
".venv\Scripts\python.exe" manage.py flx_diagnose
echo.
set /p SONDEO=Sondear cada EntitySet con una consulta $top=1 (solo si esta AUTORIZADO por el administrador MES)? (S/N): 
if /i "%SONDEO%"=="S" ".venv\Scripts\python.exe" manage.py flx_diagnose --sondear --confirmar-sondeo
echo.
echo Los reportes quedaron en la carpeta data\diagnosticos (no contienen datos de registros ni credenciales).
pause
