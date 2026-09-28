@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "REPO_URL=https://github.com/iantolentino/Python-System-Utility-Toolkit.git"
set "REPO_BRANCH=main"
if not "%~1"=="" set "REPO_BRANCH=%~1"
set "TOOLKIT_BOOTSTRAP_REF=%REPO_BRANCH%"
set "DEST=%USERPROFILE%\Python-System-Utility-Toolkit"
set "TOOLKIT_BOOTSTRAP=%~f0"

powershell.exe -NoProfile -Command "$p = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()); if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 1 }"
if errorlevel 1 (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -Command "try { $p = Start-Process -FilePath $env:TOOLKIT_BOOTSTRAP -ArgumentList $env:TOOLKIT_BOOTSTRAP_REF -Verb RunAs -Wait -PassThru; exit $p.ExitCode } catch { Write-Error $_; exit 1 }"
    exit /b
)

if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"

echo Checking Windows Time before downloading prerequisites...
sc.exe start w32time >nul 2>nul
w32tm /resync /rediscover
if errorlevel 1 echo [INFO] Time sync unavailable. If HTTPS downloads fail, correct Windows date/time and retry.

where winget >nul 2>nul
if errorlevel 1 (
    echo Preparing Microsoft App Installer and WinGet...
    curl.exe --fail --location --retry 2 -o "%TEMP%\toolkit-ensure-winget.ps1" https://raw.githubusercontent.com/iantolentino/Python-System-Utility-Toolkit/%REPO_BRANCH%/ensure-winget.ps1
    if errorlevel 1 (
        echo [ERROR] Could not download the WinGet setup helper. Check your connection and retry.
        pause
        exit /b 1
    )
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\toolkit-ensure-winget.ps1"
    if errorlevel 1 (
        echo [ERROR] Could not install WinGet. See the output above.
        pause
        exit /b 1
    )
)
set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"

echo ============================================
echo  Master Script - Bootstrap
echo ============================================

where git >nul 2>nul
if errorlevel 1 (
    echo Git not found. Installing Git via winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] winget is not available on this system.
        echo Install Git manually from https://git-scm.com/download/win and re-run this command.
        pause
        exit /b 1
    )

    call :install_git
    if errorlevel 1 (
        echo [WARN] winget reported an issue installing Git - checking if it installed anyway...
    )

    echo Refreshing PATH for this session...
)
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git still not found on PATH after installation.
    echo Close this window, open a new terminal, and re-run this command.
    pause
    exit /b 1
)

if exist "%DEST%\.git" (
    git -C "%DEST%" remote get-url origin | findstr /i /x /c:"%REPO_URL%" /c:"https://github.com/iantolentino/Python-System-Utility-Toolkit" >nul
    if errorlevel 1 (
        echo [ERROR] This folder belongs to another repository. Rename "%DEST%" and retry.
        pause
        exit /b 1
    )
    echo Repository already exists at "%DEST%" - pulling latest changes...
    call :fetch_repo
) else (
    echo Cloning repository to "%DEST%"...
    call :fetch_repo
)

if errorlevel 1 (
    echo [ERROR] Failed to clone or update the repository.
    pause
    exit /b 1
)

call "%DEST%\install_and_run.bat"
exit /b %errorlevel%

:install_git
for /l %%a in (1,1,3) do (
    echo Installing Git - attempt %%a/3...
    winget install -e --id Git.Git --source winget --scope machine --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 exit /b 0
    if exist "%ProgramFiles%\Git\cmd\git.exe" exit /b 0
    if %%a LSS 3 timeout /t 3 /nobreak >nul
)
exit /b 1

:fetch_repo
for /l %%a in (1,1,3) do (
    echo Downloading toolkit - attempt %%a/3...
    if exist "%DEST%\.git" (
        git -C "%DEST%" pull --ff-only origin "%REPO_BRANCH%"
    ) else (
        git clone --branch "%REPO_BRANCH%" "%REPO_URL%" "%DEST%"
    )
    if not errorlevel 1 exit /b 0
    if %%a LSS 3 timeout /t 3 /nobreak >nul
)
exit /b 1
