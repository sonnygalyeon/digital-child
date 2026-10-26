#Requires -Version 5.1
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Build on Windows x64." }
if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x64 is required." }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PreviousEnvironment = $env:UV_PROJECT_ENVIRONMENT
$env:UV_PROJECT_ENVIRONMENT = Join-Path $RepoRoot ".venv-build"
Push-Location $RepoRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "Install uv, then rerun this script. See docs/WINDOWS_BUILD.md."
    }
    & uv run --python 3.12 --locked --no-dev --extra desktop --with pyinstaller==6.16.0 `
        python -m PyInstaller --noconfirm --clean packaging/windows.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)." }
    $Bundle = Join-Path $RepoRoot "dist\DigitalChild"
    Copy-Item .env.example (Join-Path $Bundle "settings.env.example") -Force
    Copy-Item docs\WINDOWS_BUILD.md (Join-Path $Bundle "WINDOWS_BUILD.md") -Force
    $Archive = Join-Path $RepoRoot "dist\DigitalChild-windows-x64.zip"
    Compress-Archive -Path $Bundle -DestinationPath $Archive -Force
    $Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  DigitalChild-windows-x64.zip" | Set-Content "$Archive.sha256" -Encoding ASCII
    Write-Host "Ready: $Archive"
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $PreviousEnvironment
    Pop-Location
}
