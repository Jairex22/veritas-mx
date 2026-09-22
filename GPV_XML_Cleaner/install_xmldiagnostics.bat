@echo off
rem One-time setup: makes the "xmldiagnostics" command available from any
rem CMD window, in any folder, permanently. No administrator rights needed
rem (it only touches your personal/user PATH, not the system-wide one).
rem
rem Run this ONCE by double-clicking it (or "xmldiagnostics.bat" and this
rem file must be in the same folder as GPV_XML_Cleaner_xmldiagnostic.py).

setlocal

set "TARGET=%LOCALAPPDATA%\GPV_XML_Cleaner"

echo.
echo ============================================================
echo  Installing the "xmldiagnostics" command
echo ============================================================
echo.
echo Destination folder:
echo   %TARGET%
echo.

if not exist "%TARGET%" mkdir "%TARGET%"

copy /Y "%~dp0GPV_XML_Cleaner_xmldiagnostic.py" "%TARGET%\" >nul
if errorlevel 1 (
    echo ERROR: Could not find/copy GPV_XML_Cleaner_xmldiagnostic.py
    echo Make sure it is in the same folder as this installer.
    echo.
    pause
    exit /b 1
)

copy /Y "%~dp0xmldiagnostics.bat" "%TARGET%\" >nul
if errorlevel 1 (
    echo ERROR: Could not find/copy xmldiagnostics.bat
    echo.
    pause
    exit /b 1
)

echo Files copied successfully.
echo.
echo Adding %TARGET% to your PATH...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$target = '%TARGET%'; $userPath = [Environment]::GetEnvironmentVariable('Path','User'); if (-not $userPath) { $userPath = '' }; $parts = $userPath -split ';' | Where-Object { $_ -ne '' -and $_.TrimEnd('\') -ne $target.TrimEnd('\') }; $newPath = ($parts + $target) -join ';'; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')"

if errorlevel 1 (
    echo.
    echo WARNING: Could not update PATH automatically.
    echo You can still run the tool using the full path:
    echo   "%TARGET%\xmldiagnostics.bat"
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done.
echo ============================================================
echo.
echo Close this window and open a NEW CMD window (the PATH change
echo only applies to windows opened after this point), then run:
echo.
echo     xmldiagnostics
echo     xmldiagnostics "C:\path\to\FLX"
echo.
pause
