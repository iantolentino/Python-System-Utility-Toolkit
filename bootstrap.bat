@echo off
setlocal enabledelayedexpansion

set "REPO_URL=https://github.com/iantolentino/Python-System-Utility-Toolkit.git"
set "DEST=%USERPROFILE%\Python-System-Utility-Toolkit"

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

    winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERROR] Automatic Git installation failed. Please install Git manually from https://git-scm.com/download/win
        pause
        exit /b 1
    )

    echo Git installed. Refreshing PATH for this session...
    set "GITDIR="
    for /d %%d in ("%ProgramFiles%\Git") do set "GITDIR=%%d"
    if not defined GITDIR (
        for /d %%d in ("%ProgramFiles(x86)%\Git") do set "GITDIR=%%d"
    )
    if defined GITDIR set "PATH=!GITDIR!\cmd;!GITDIR!\bin;%PATH%"
)

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git still not found on PATH after installation.
    echo Close this window, open a new terminal, and re-run this command.
    pause
    exit /b 1
)

if exist "%DEST%\.git" (
    echo Repository already exists at "%DEST%" - pulling latest changes...
    git -C "%DEST%" pull --ff-only
) else (
    echo Cloning repository to "%DEST%"...
    git clone "%REPO_URL%" "%DEST%"
)

if errorlevel 1 (
    echo [ERROR] Failed to clone or update the repository.
    pause
    exit /b 1
)

call "%DEST%\install_and_run.bat"

endlocal
