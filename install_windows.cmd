@echo off
setlocal

echo ========================================
echo ATAK Pipeline Installer
echo ========================================
echo.

:: Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python not found. Installing Python...

    powershell -Command "Start-Process 'https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe' -Wait"

    echo.
    echo Please run the installer:
    echo IMPORTANT: Check "Add Python to PATH"
    echo Then rerun this script.
    pause
    exit
)

echo Python found.

echo Launching installer...
powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0scripts\install_windows.ps1"

pause
