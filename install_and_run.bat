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

:: Note: "where python" is NOT enough to detect Python - fresh Windows installs ship a
:: python.exe "App Execution Alias" stub under WindowsApps that's always on PATH, resolves
:: fine via "where", but just prints a Microsoft Store redirect message and exits nonzero
:: when actually run. Gate on "python --version" actually succeeding instead.
python --version >nul 2>nul
if errorlevel 1 (
    echo Python not found ^(or only the Microsoft Store shortcut is present^). Installing Python via winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] winget is not available on this system.
        echo Please install Python manually from https://www.python.org/downloads/ and re-run this script.
        pause
        exit /b 1
    )

    winget install -e --id Python.Python.3.12 --source winget --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [WARN] winget reported an issue installing Python - checking if it installed anyway...
    )

    echo Refreshing PATH for this session...
    set "PYDIR="
    for /d %%d in ("%LocalAppData%\Programs\Python\Python3*") do set "PYDIR=%%d"
    if not defined PYDIR (
        for /d %%d in ("%ProgramFiles%\Python3*") do set "PYDIR=%%d"
    )
    if defined PYDIR set "PATH=!PYDIR!;!PYDIR!\Scripts;%PATH%"
)

python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python still not usable after installation attempt.
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
