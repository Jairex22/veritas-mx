@echo off
REM ============================================================================
REM  GPV Operator Performance Hub - Inicio del frontend (Windows, sin PowerShell)
REM ============================================================================
setlocal
cd /d "%~dp0frontend"

if not exist ".env" (
    echo Creando frontend\.env a partir de .env.example...
    copy ".env.example" ".env" >nul
)

if not exist "node_modules" (
    echo Instalando dependencias de Node.js (esto puede tardar unos minutos)...
    call npm install
    if errorlevel 1 (
        echo.
        echo [ERROR] Fallo "npm install". Verifica que Node.js 18+ este instalado y en el PATH.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================================
echo  Iniciando frontend en http://localhost:5173
echo  Asegurate de haber iniciado el backend con start-backend.bat en otra ventana.
echo  Presiona Ctrl+C para detener el servidor.
echo ============================================================================
echo.
call npm run dev

pause
