@echo off
REM ============================================================================
REM  GPV Operator Performance Hub - Build de produccion del frontend (Windows)
REM  Genera la carpeta frontend\dist con los archivos estaticos listos para
REM  publicar en cualquier servidor web (IIS, Nginx, Apache, etc.).
REM ============================================================================
setlocal
cd /d "%~dp0frontend"

if not exist ".env" (
    echo Creando frontend\.env a partir de .env.example...
    copy ".env.example" ".env" >nul
    echo Recuerda ajustar VITE_API_BASE_URL en frontend\.env apuntando al backend de produccion.
)

if not exist "node_modules" (
    echo Instalando dependencias de Node.js...
    call npm install
)

echo.
echo Generando build de produccion...
call npm run build
if errorlevel 1 (
    echo.
    echo [ERROR] El build fallo. Revisa los mensajes anteriores.
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo  Build generado en frontend\dist
echo  Copia el contenido de esa carpeta a tu servidor web de produccion.
echo ============================================================================
pause
