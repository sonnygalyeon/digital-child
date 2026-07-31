param([switch]$NoOllamaStart)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$HostDir = Join-Path $RepoRoot "windows_host"

if (-not $NoOllamaStart) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
    } catch {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
}

Push-Location $HostDir
try {
    uv run digital-child-host --env .env
} finally {
    Pop-Location
}
