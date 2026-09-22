@echo off
rem Launcher for the "xmldiagnostics" command.
rem After install_xmldiagnostics.bat has been run once, this file lives
rem next to GPV_XML_Cleaner_xmldiagnostic.py in %LOCALAPPDATA%\GPV_XML_Cleaner
rem and its folder is on the User PATH, so "xmldiagnostics" works from any
rem CMD window, in any folder.

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    python "%~dp0GPV_XML_Cleaner_xmldiagnostic.py" %*
) else (
    py "%~dp0GPV_XML_Cleaner_xmldiagnostic.py" %*
)
