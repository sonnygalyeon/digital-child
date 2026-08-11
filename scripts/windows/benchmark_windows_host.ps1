param(
    [string]$Prompt = "Кратко объясни, почему небо голубое.",
    [int]$Runs = 3
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$HostDir = Join-Path $RepoRoot "windows_host"
$EnvPath = Join-Path $HostDir ".env"
if (-not (Test-Path $EnvPath)) {
    throw "windows_host\.env not found. Run setup_windows_host.ps1 first."
}

Push-Location $HostDir
try {
    uv run digital-child-host --env .env --benchmark --prompt $Prompt --runs $Runs
} finally {
    Pop-Location
}
