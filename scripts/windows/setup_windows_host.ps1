param(
    [string]$Model = "qwen3:8b",
    [switch]$WithPostgres,
    [switch]$OpenFirewall
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$HostDir = Join-Path $RepoRoot "windows_host"

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

Write-Step "Checking uv"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
    } else {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    }
    $env:Path = "$HOME\.local\bin;$env:Path"
}

Write-Step "Checking Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Ollama is not installed and winget is unavailable. Install OllamaSetup.exe first."
    }
    winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    $env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:Path"
}

Write-Step "Installing Python 3.12 and host dependencies"
Push-Location $HostDir
try {
    uv python install 3.12
    uv python pin 3.12
    uv sync --extra dev
} finally {
    Pop-Location
}

Write-Step "Applying CPU-oriented Ollama settings"
$OllamaSettings = @{
    OLLAMA_CONTEXT_LENGTH = "8192"
    OLLAMA_NUM_PARALLEL = "1"
    OLLAMA_MAX_LOADED_MODELS = "1"
    OLLAMA_MAX_QUEUE = "8"
    OLLAMA_KEEP_ALIVE = "30m"
}
foreach ($Entry in $OllamaSettings.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($Entry.Key, $Entry.Value, "User")
    Set-Item -Path "Env:$($Entry.Key)" -Value $Entry.Value
}

Write-Step "Restarting Ollama with the new settings"
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Step "Downloading model $Model"
ollama pull $Model

Write-Step "Creating gateway configuration"
$ApiBytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($ApiBytes)
$ApiKey = [Convert]::ToBase64String($ApiBytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
$EnvPath = Join-Path $HostDir ".env"
$AllowedModels = "$Model,qwen3:4b"
$PostgresDsn = ""

if ($WithPostgres) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker is required for -WithPostgres. Install Docker Desktop or configure native PostgreSQL manually."
    }
    $PasswordBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($PasswordBytes)
    $PostgresPassword = [Convert]::ToBase64String($PasswordBytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
    $ComposeEnv = Join-Path $HostDir ".env.postgres"
    "POSTGRES_PASSWORD=$PostgresPassword" | Set-Content -Path $ComposeEnv -Encoding UTF8
    Push-Location $HostDir
    try {
        docker compose --env-file .env.postgres -f docker-compose.postgres.yml up -d
    } finally {
        Pop-Location
    }
    $EscapedPassword = [Uri]::EscapeDataString($PostgresPassword)
    $PostgresDsn = "postgresql://digital_child:$EscapedPassword@127.0.0.1:5432/digital_child_host"
}

@"
WINDOWS_HOST_BIND=0.0.0.0
WINDOWS_HOST_PORT=8787
WINDOWS_HOST_API_KEY=$ApiKey
WINDOWS_HOST_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
WINDOWS_HOST_DEFAULT_MODEL=$Model
WINDOWS_HOST_ALLOWED_MODELS=$AllowedModels
WINDOWS_HOST_REQUEST_TIMEOUT=300
WINDOWS_HOST_MAX_REQUEST_BYTES=4194304
WINDOWS_HOST_POSTGRES_DSN=$PostgresDsn
WINDOWS_HOST_STORE_CONTENT=false
WINDOWS_HOST_LOG_REQUESTS=true
WINDOWS_HOST_INSTANCE_NAME=windows-5700x
"@ | Set-Content -Path $EnvPath -Encoding UTF8

if ($OpenFirewall) {
    Write-Step "Adding LocalSubnet firewall rule"
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warning "PowerShell is not elevated; firewall rule was not added. Re-run as Administrator with -OpenFirewall."
    } else {
        Get-NetFirewallRule -DisplayName "Digital Child LLM Host" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule `
            -DisplayName "Digital Child LLM Host" `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort 8787 `
            -RemoteAddress LocalSubnet | Out-Null
    }
}

Write-Step "Configuration complete"
Write-Host "API key: $ApiKey" -ForegroundColor Yellow
Write-Host "Save this key on the Mac client. It is also stored in windows_host\.env."
Write-Host "Start host: .\scripts\windows\start_windows_host.ps1"
