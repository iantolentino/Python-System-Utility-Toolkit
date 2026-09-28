param(
    [ValidateSet('Git', 'Python', 'WinGet')][string]$Component = 'Git',
    [switch]$Library
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$script:PrerequisiteDirectory = $PSScriptRoot

function Invoke-Native {
    param([string]$File, [string[]]$Arguments)
    # HRESULTs such as 0x8a15000f are negative signed integers, NOT success.
    $ErrorActionPreference = 'Continue'
    & $File @Arguments 2>&1 | ForEach-Object { Write-Host "$_" }
    return $LASTEXITCODE
}

function Find-Tool {
    param([string]$Name)
    $candidates = @()
    $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    if ($Name -eq 'git') {
        $candidates += "$env:ProgramFiles\Git\cmd\git.exe", "${env:ProgramFiles(x86)}\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
    } else {
        $candidates += @(Get-ChildItem "$env:ProgramFiles\Python3*\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        # Skip the Store alias, which may open the Store instead of running Python.
        if ($Name -eq 'python' -and $candidate -like '*\WindowsApps\*') { continue }
        $arguments = if ($Name -eq 'git') { @('--version') } else { @('-c', 'import sys, tkinter, winreg; sys.exit(0 if sys.version_info >= (3, 10) else 1)') }
        if ((Invoke-Native $candidate $arguments) -eq 0) { return $candidate }
    }
    return $null
}

function Repair-WingetSource {
    param([string]$Winget)
    Write-Host 'Repairing the WinGet community source...'
    $reset = Invoke-Native $Winget @('source', 'reset', '--name', 'winget', '--force', '--disable-interactivity')
    $update = Invoke-Native $Winget @('source', 'update', '--name', 'winget', '--disable-interactivity')
    if ($reset -ne 0 -or $update -ne 0) {
        Write-Host "[WARN] Source repair returned reset=$reset, update=$update. Installation will still be retried."
    }
}

function Install-WithWinget {
    param([string]$Id, [scriptblock]$Check)
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { return $false }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Write-Host "Installing $Id with WinGet - attempt $attempt/3..."
        $code = Invoke-Native $winget.Source @('install', '--exact', '--id', $Id, '--source', 'winget', '--scope', 'machine', '--silent', '--disable-interactivity', '--accept-package-agreements', '--accept-source-agreements')
        if (& $Check) { return $true }
        Write-Host "[WARN] WinGet exit code: $code; the required application is not usable yet."
        if ($attempt -eq 1) { Repair-WingetSource $winget.Source }
        if ($attempt -lt 3) { Start-Sleep -Seconds 3 }
    }
    return $false
}

function Invoke-DownloadRetry {
    param([scriptblock]$Operation)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try { return (& $Operation) }
        catch {
            Write-Host "[WARN] Download attempt $attempt/3 failed: $_"
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds 3
        }
    }
}

function Get-Architecture {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    switch ($architecture) {
        'AMD64' { return 'x64' }
        'ARM64' { return 'arm64' }
        'x86' { return 'x86' }
        default { throw "Unsupported processor architecture: $architecture" }
    }
}

function Install-Direct {
    param([string]$Name)
    $architecture = Get-Architecture
    $directory = Join-Path $env:TEMP ('toolkit-prerequisite-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $directory | Out-Null
    $expectedHash = $null
    if ($Name -eq 'git') {
        Write-Host 'Using the official Git for Windows installer fallback...'
        if ($architecture -eq 'x86') {
            # Last official 32-bit Git for Windows release.
            $releaseUrl = 'https://api.github.com/repos/git-for-windows/git/releases/tags/v2.48.1.windows.1'
            $pattern = '^Git-.*-32-bit\.exe$'
        } else {
            $releaseUrl = 'https://api.github.com/repos/git-for-windows/git/releases/latest'
            $pattern = if ($architecture -eq 'arm64') { '^Git-.*-arm64\.exe$' } else { '^Git-.*-64-bit\.exe$' }
        }
        $release = Invoke-DownloadRetry { Invoke-RestMethod -Uri $releaseUrl -TimeoutSec 30 }
        $asset = $release.assets | Where-Object name -Match $pattern | Select-Object -First 1
        if (-not $asset) { throw "No official Git installer found for $architecture." }
        $url = $asset.browser_download_url
        if ($asset.digest -match '^sha256:([a-fA-F0-9]{64})$') { $expectedHash = $Matches[1] }
        $arguments = '/VERYSILENT /NORESTART /SP- /SUPPRESSMSGBOXES /DIR="' + $env:ProgramFiles + '\Git"'
    } else {
        Write-Host 'Using the official Python installer fallback (includes Tkinter)...'
        $suffix = switch ($architecture) { 'x64' { '-amd64' } 'arm64' { '-arm64' } 'x86' { '' } }
        $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10$suffix.exe"
        $arguments = '/quiet InstallAllUsers=1 Include_tcltk=1 Include_pip=1 Include_test=0 PrependPath=1 /norestart TargetDir="' + $env:ProgramFiles + '\Python312"'
    }
    $installer = Join-Path $directory 'installer.exe'
    Write-Host "Downloading $url"
    Invoke-DownloadRetry { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $installer -TimeoutSec 300 }
    if ($expectedHash -and (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expectedHash) {
        throw 'Installer checksum mismatch; installation stopped.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid') { throw "Installer signature is not valid: $($signature.Status). Check Windows date/time and retry." }
    Write-Host "Verified installer signature: $($signature.SignerCertificate.Subject)"
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -notin 0, 1641, 3010) { throw "$Name installer failed with exit code $($process.ExitCode)." }
    if ($process.ExitCode -in 1641, 3010) { Write-Host '[INFO] Restart required to complete installation.' }
}

function Install-Prerequisite {
    param([string]$Name)
    if (Find-Tool $Name) { Write-Host "$Name is already usable."; return }
    $id = if ($Name -eq 'git') { 'Git.Git' } else { 'Python.Python.3.12' }
    $check = { Find-Tool $Name }
    if (-not (Install-WithWinget $id $check)) { Install-Direct $Name }
    $path = Find-Tool $Name
    if (-not $path) { throw "$Name is still not usable after installation. Review the installer output and retry." }
    Write-Host "SUCCESS: $Name is ready at $path"
}

if ($Library) { return }
try {
    if ($Component -eq 'WinGet') {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $script:PrerequisiteDirectory 'ensure-winget.ps1')
            if ($LASTEXITCODE -ne 0) { throw 'Microsoft App Installer setup failed.' }
        }
        Write-Host 'WinGet is available for Microsoft Windows App.'
    } else {
        Install-Prerequisite $Component.ToLowerInvariant()
    }
    exit 0
} catch {
    Write-Host "[ERROR] Prerequisite setup failed: $_"
    Write-Host 'Check internet access and Windows date/time, resolve the error above, then rerun setup.'
    exit 1
}
