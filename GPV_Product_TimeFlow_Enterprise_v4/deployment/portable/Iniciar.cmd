@echo off
title GPV Product TimeFlow (DEMO portatil)
cd /d "%~dp0"
set ASPNETCORE_ENVIRONMENT=Development
set ASPNETCORE_URLS=http://localhost:5101
set TimeFlow__DataRoot=App_Data
set TimeFlow__PublicBaseUrl=http://localhost:5101
set Serilog__MinimumLevel__Default=Warning
echo.
echo  GPV Product TimeFlow - modo DEMO (datos sinteticos)
echo  La primera vez tarda ~20 s en crear la base de datos.
echo  Abre en tu navegador:  http://localhost:5101
echo  Cierra esta ventana para detener el servidor.
echo.
start "" http://localhost:5101
GPV.ProductTimeFlow.Web.exe
pause
