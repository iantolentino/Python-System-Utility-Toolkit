$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (Get-Command winget.exe -ErrorAction SilentlyContinue) { exit 0 }

function Invoke-WithRetry {
    param([scriptblock]$Operation)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try { return (& $Operation) }
        catch {
            if ($attempt -eq 3) { throw }
            Write-Host "Download attempt $attempt/3 interrupted. Retrying in 3s..."
            Start-Sleep -Seconds 3
        }
    }
}

try {
    Write-Host 'Installing Microsoft App Installer (WinGet) and its dependencies...'
    $release = Invoke-WithRetry { Invoke-RestMethod 'https://api.github.com/repos/microsoft/winget-cli/releases/latest' -TimeoutSec 30 }
    $downloadDirectory = Join-Path $env:TEMP ('toolkit-winget-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
    $names = @('DesktopAppInstaller_Dependencies.zip', 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle')
    foreach ($name in $names) {
        $asset = $release.assets | Where-Object name -EQ $name | Select-Object -First 1
        if (-not $asset -or $asset.digest -notmatch '^sha256:([a-fA-F0-9]{64})$') {
            throw "The official release has no verified asset for $name."
        }
        $expected = $Matches[1]
        $destination = Join-Path $downloadDirectory $name
        Invoke-WithRetry { Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $destination -TimeoutSec 300 }
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $expected) {
            throw "Checksum mismatch for $name."
        }
    }
    $dependencyDirectory = Join-Path $downloadDirectory 'dependencies'
    Expand-Archive -LiteralPath (Join-Path $downloadDirectory $names[0]) -DestinationPath $dependencyDirectory
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    $architecture = switch ($architecture) { 'AMD64' { 'x64' } 'ARM64' { 'arm64' } 'x86' { 'x86' } default { throw "Unsupported architecture: $architecture" } }
    $dependencies = @(Get-ChildItem -LiteralPath $dependencyDirectory -Recurse -File | Where-Object {
        $_.Extension -in '.appx', '.msix' -and $_.FullName -match "[\\/]$architecture[\\/]"
    })
    if ($dependencies.Count -eq 0) { throw "No $architecture App Installer dependencies were found." }
    foreach ($dependency in $dependencies) {
        Write-Host "Installing dependency: $($dependency.Name)"
        try { Add-AppxPackage -Path $dependency.FullName }
        catch { if ($_ -notmatch '0x80073D06') { throw } }
    }
    Add-AppxPackage -Path (Join-Path $downloadDirectory $names[1])
    $env:PATH = "$env:LOCALAPPDATA\Microsoft\WindowsApps;$env:PATH"
    & winget.exe --version
    if ($LASTEXITCODE -ne 0) { throw 'WinGet did not start after installation.' }
    Write-Host 'WinGet is ready.'
    exit 0
} catch {
    Write-Error "Could not prepare WinGet: $_"
    exit 1
}
