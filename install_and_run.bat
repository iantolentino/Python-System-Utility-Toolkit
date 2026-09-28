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
    if errorlevel 1 (
        echo [ERROR] Administrator approval or elevated setup failed. Review the error and rerun setup.
        exit /b 1
    )
    exit /b 0
)

echo ============================================
echo  Master Script - Setup and Launch
echo ============================================

set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"

:: Note: "where python" is NOT enough to detect Python - fresh Windows installs ship a
:: python.exe "App Execution Alias" stub under WindowsApps that's always on PATH, resolves
:: fine via "where", but just prints a Microsoft Store redirect message and exits nonzero
:: when actually run. Gate on "python --version" actually succeeding instead.
set "PYTHON_EXE="
for /f "delims=" %%p in ('where python.exe 2^>nul') do call :check_python "%%p"
for /d %%d in ("%ProgramFiles%\Python3*" "%LocalAppData%\Programs\Python\Python3*") do call :check_python "%%~d\python.exe"
if not defined PYTHON_EXE (
    echo Preparing Python with WinGet repair and an official installer fallback...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-prerequisites.ps1" -Component Python
    if errorlevel 1 (
        echo [ERROR] Python setup failed. Resolve the error above and rerun setup.
        pause
        exit /b 1
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

echo Preparing WinGet for Microsoft Windows App...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-prerequisites.ps1" -Component WinGet
if errorlevel 1 echo [WARN] WinGet preparation failed. Normal Setup and Front remain available; Windows App will need WinGet repaired before retrying.

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
echo "%~1" | findstr /i /l /c:"\WindowsApps\" >nul
if not errorlevel 1 exit /b 0
"%~1" -c "import sys, tkinter, winreg; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 0 if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0
