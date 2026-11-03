@echo off
REM Servicio OData SIMULADO para practicar (NO es FactoryLogix). Solo 127.0.0.1:8765.
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\fake_odata_server.py --port 8765
pause
