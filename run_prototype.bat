@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo ProtoCube's local Python environment is missing.
    echo Follow the setup instructions in README.md first.
    pause
    exit /b 1
)

if not exist "launcher.py" (
    echo ProtoCube's launcher.py is missing.
    pause
    exit /b 1
)

start "ProtoCube" /D "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launcher.py"
