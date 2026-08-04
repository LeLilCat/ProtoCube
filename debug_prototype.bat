@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ProtoCube's local Python environment is missing.
    echo Follow the setup instructions in README.md first.
    pause
    exit /b 1
)

echo Starting ProtoCube in diagnostic mode...
echo If startup fails, this window will show the error and protocube_startup.log will contain it.
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0launcher.py"

if errorlevel 1 (
    echo.
    echo ProtoCube stopped with an error. See protocube_startup.log.
    pause
)
