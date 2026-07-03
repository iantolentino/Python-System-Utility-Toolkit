@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Relaunch elevated if not already running as administrator
:: (most actions in master_gui.py touch HKLM / system policy and require admin)
net session >nul 2>nul
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  Master Script - Setup and Launch
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Installing Python via winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] winget is not available on this system.
        echo Please install Python manually from https://www.python.org/downloads/ and re-run this script.
        pause
        exit /b 1
    )

    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERROR] Automatic Python installation failed. Please install Python manually.
        pause
        exit /b 1
    )

    echo Python installed. Refreshing PATH for this session...
    set "PYDIR="
    for /d %%d in ("%LocalAppData%\Programs\Python\Python3*") do set "PYDIR=%%d"
    if not defined PYDIR (
        for /d %%d in ("%ProgramFiles%\Python3*") do set "PYDIR=%%d"
    )
    if defined PYDIR set "PATH=!PYDIR!;!PYDIR!\Scripts;%PATH%"
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python still not found on PATH after installation.
    echo Close this window, open a new terminal, and re-run install_and_run.bat.
    pause
    exit /b 1
)

echo Using:
python --version

if exist requirements.txt (
    echo Installing dependencies from requirements.txt...
    python -m pip install --upgrade pip >nul
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
) else (
    echo No requirements.txt found - skipping dependency install ^(no third-party packages required^).
)

echo Launching Master Script...
python "%~dp0master_gui.py"

if errorlevel 1 (
    echo [ERROR] Master Script exited with an error.
    pause
    exit /b 1
)

endlocal
