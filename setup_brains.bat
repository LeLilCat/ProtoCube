@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_brains.ps1"
if errorlevel 1 (
    echo.
    echo ProtoCube brain setup failed. See the error above.
    pause
    exit /b 1
)

echo.
echo ProtoCube brains are ready.
pause
