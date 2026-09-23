@echo off
REM GPV PRODUCT CONFIGURATION - launcher (relative paths only)
setlocal
cd /d "%~dp0"

where py >/dev/null 2>nul
if not errorlevel 1 (
    py "%~dp0GPV_Product_Configuration.py" %*
    goto :done
)

where python >/dev/null 2>nul
if not errorlevel 1 (
    python "%~dp0GPV_Product_Configuration.py" %*
    goto :done
)

echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ (tkinter is included).
pause
exit /b 1

:done
if errorlevel 1 (
    echo.
    echo The application ended with an error. See logs\app.log
    pause
)
endlocal
