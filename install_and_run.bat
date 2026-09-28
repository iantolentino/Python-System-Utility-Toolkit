@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "TOOLKIT_LAUNCHER=%~f0"

:: Relaunch elevated if not already running as administrator
:: (most actions in master_gui.py touch HKLM / system policy and require admin)
powershell.exe -NoProfile -Command "$p = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()); if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 1 }"
if errorlevel 1 (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -Command "try { $p = Start-Process -FilePath $env:TOOLKIT_LAUNCHER -Verb RunAs -Wait -PassThru; exit $p.ExitCode } catch { Write-Error $_; exit 1 }"
    exit /b
)

echo ============================================
echo  Master Script - Setup and Launch
echo ============================================

where winget >nul 2>nul
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure-winget.ps1"
    if errorlevel 1 (
        echo [ERROR] Could not prepare WinGet. See the output above.
        pause
        exit /b 1
    )
)
set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"

:: Note: "where python" is NOT enough to detect Python - fresh Windows installs ship a
:: python.exe "App Execution Alias" stub under WindowsApps that's always on PATH, resolves
:: fine via "where", but just prints a Microsoft Store redirect message and exits nonzero
:: when actually run. Gate on "python --version" actually succeeding instead.
set "PYTHON_EXE="
for /f "delims=" %%p in ('where python.exe 2^>nul') do call :check_python "%%p"
for /d %%d in ("%ProgramFiles%\Python3*" "%LocalAppData%\Programs\Python\Python3*") do call :check_python "%%~d\python.exe"
if not defined PYTHON_EXE (
    echo Python not found ^(or only the Microsoft Store shortcut is present^). Installing Python via winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] winget is not available on this system.
        echo Please install Python manually from https://www.python.org/downloads/ and re-run this script.
        pause
        exit /b 1
    )

    call :install_python
    if errorlevel 1 (
        echo [WARN] winget reported an issue installing Python - checking if it installed anyway...
    )

    echo Refreshing PATH for this session...
)
for /d %%d in ("%ProgramFiles%\Python3*" "%LocalAppData%\Programs\Python\Python3*") do call :check_python "%%~d\python.exe"

if not defined PYTHON_EXE (
    echo [ERROR] Python still not usable after installation attempt.
    echo Close this window, open a new terminal, and re-run install_and_run.bat.
    pause
    exit /b 1
)

echo Using:
"%PYTHON_EXE%" --version

if exist requirements.txt (
    echo Installing dependencies from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
) else (
    echo No requirements.txt found - skipping dependency install ^(no third-party packages required^).
)

echo Launching Master Script...
"%PYTHON_EXE%" "%~dp0master_gui.py"

if errorlevel 1 (
    echo [ERROR] Master Script exited with an error.
    pause
    exit /b 1
)

exit /b 0

:check_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys, tkinter, winreg; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0

:install_python
for /l %%a in (1,1,3) do (
    echo Installing Python - attempt %%a/3...
    winget install -e --id Python.Python.3.12 --source winget --scope machine --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 exit /b 0
    if exist "%ProgramFiles%\Python312\python.exe" exit /b 0
    if %%a LSS 3 timeout /t 3 /nobreak >nul
)
exit /b 1
