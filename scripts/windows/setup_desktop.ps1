param([switch]$NoShortcut)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Install uv first: winget install --id astral-sh.uv -e"
}

Push-Location $RepoRoot
try {
    uv sync --python 3.12 --extra desktop
    if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed." }
    if (-not (Test-Path ".env")) {
        @"
DIGITAL_CHILD_LLM_PROVIDER=ollama
DIGITAL_CHILD_LLM_BASE_URL=http://127.0.0.1:11434/v1
DIGITAL_CHILD_LLM_MODEL=digital-child-fast
DIGITAL_CHILD_LLM_TIMEOUT=180
DIGITAL_CHILD_LLM_MAX_TOKENS=512
DIGITAL_CHILD_LLM_REASONING_EFFORT=none
DIGITAL_CHILD_RESEARCH_PROVIDER=wikipedia
DIGITAL_CHILD_RESEARCH_MODE=background
DIGITAL_CHILD_AUTO_RESEARCH=1
DIGITAL_CHILD_DB=data/digital_child.db
"@ | Set-Content -Path ".env" -Encoding UTF8
    }
} finally {
    Pop-Location
}

if (-not $NoShortcut) {
    $Shell = New-Object -ComObject WScript.Shell
    $DesktopPath = [Environment]::GetFolderPath("Desktop")
    $Shortcut = $Shell.CreateShortcut((Join-Path $DesktopPath "Digital Child.lnk"))
    $Shortcut.TargetPath = Join-Path $RepoRoot ".venv\Scripts\digital-child-desktop.exe"
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "Digital Child desktop chat and emotional sphere"
    $Shortcut.Save()
}

Write-Host "Desktop installed. Start with the Digital Child shortcut." -ForegroundColor Green
Write-Host "Configure .env for your LLM. Existing configuration and memory are preserved."
Write-Host "Local Ollama model default: digital-child-fast (see docs/guides/WINDOWS_LLM_HOST.md)."
