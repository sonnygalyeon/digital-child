#Requires -Version 5.1
param([switch]$NoDialog)

$ErrorActionPreference = "Stop"
try {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $DesktopExe = Join-Path $RepoRoot ".venv\Scripts\digital-child-desktop.exe"
    if (-not (Test-Path -LiteralPath $DesktopExe)) {
        throw "Сначала запустите install_windows.cmd в корне проекта."
    }
    . (Join-Path $PSScriptRoot "local_ollama.ps1")
    $Config = Get-DesktopInstallConfig $RepoRoot
    if ($null -ne $Config) { Ensure-LocalOllama $RepoRoot $Config }
    Start-Process -FilePath $DesktopExe -WorkingDirectory $RepoRoot
} catch {
    $Message = "Digital Child: $($_.Exception.Message)"
    Write-Host $Message -ForegroundColor Red
    if (-not $NoDialog) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($Message, "Digital Child") | Out-Null
    }
    exit 1
}
