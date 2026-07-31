param(
    [string]$HostUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$EnvPath = Join-Path $RepoRoot "windows_host\.env"
if (-not (Test-Path $EnvPath)) {
    throw "windows_host\.env was not found. Run setup_windows_host.ps1 first."
}

$ApiKey = (Get-Content $EnvPath | Where-Object { $_ -like "WINDOWS_HOST_API_KEY=*" }).Split("=", 2)[1]
$Model = (Get-Content $EnvPath | Where-Object { $_ -like "WINDOWS_HOST_DEFAULT_MODEL=*" }).Split("=", 2)[1]
$Headers = @{ Authorization = "Bearer $ApiKey"; "X-Client-ID" = "windows-self-test" }

Write-Host "Health:" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$HostUrl/health" | ConvertTo-Json -Depth 5

Write-Host "`nModels:" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$HostUrl/v1/models" -Headers $Headers | ConvertTo-Json -Depth 5

Write-Host "`nCompletion:" -ForegroundColor Cyan
$Body = @{
    model = $Model
    stream = $false
    messages = @(
        @{ role = "system"; content = "Answer briefly in Russian." },
        @{ role = "user"; content = "Ответь одним словом: сервер работает?" }
    )
} | ConvertTo-Json -Depth 8
Invoke-RestMethod `
    -Method Post `
    -Uri "$HostUrl/v1/chat/completions" `
    -Headers $Headers `
    -ContentType "application/json" `
    -Body $Body | ConvertTo-Json -Depth 8
