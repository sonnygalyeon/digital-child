# Shared by the clean-Windows installer and the desktop launcher. Dot-source only.
Set-StrictMode -Version Latest

function Get-DesktopInstallConfig([string]$RepoRoot) {
    $ConfigPath = Join-Path $RepoRoot ".desktop-install.json"
    if (-not (Test-Path -LiteralPath $ConfigPath)) { return $null }
    return Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Set-LocalOllamaEnvironment($Config) {
    $env:OLLAMA_HOST = "127.0.0.1:$($Config.Port)"
    $env:OLLAMA_MODELS = $Config.ModelDirectory
    $env:OLLAMA_CONTEXT_LENGTH = "4096"
    $env:OLLAMA_NUM_PARALLEL = "1"
    $env:OLLAMA_MAX_LOADED_MODELS = "1"
    $env:OLLAMA_MAX_QUEUE = "8"
    $env:OLLAMA_KEEP_ALIVE = "60m"
}

function Get-OwnedOllamaProcess($Record, [string]$ExpectedExecutable) {
    try {
        $Candidate = Get-Process -Id ([int]$Record.ProcessId) -ErrorAction Stop
        if (
            [StringComparer]::OrdinalIgnoreCase.Equals($Candidate.Path, $ExpectedExecutable) -and
            $Candidate.StartTime.ToUniversalTime().Ticks -eq [long]$Record.StartTimeTicks
        ) { return $Candidate }
    } catch { }
    return $null
}

function Confirm-LocalOllama([int]$Port) {
    try {
        $Response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" `
            -TimeoutSec 2 -ErrorAction Stop
        return [bool]$Response.version
    } catch { return $false }
}

function Ensure-LocalOllama([string]$RepoRoot, $Config) {
    if (-not (Test-Path -LiteralPath $Config.OllamaExecutable -PathType Leaf)) {
        throw "Ollama не найдена. Повторите install_windows.cmd."
    }
    Set-LocalOllamaEnvironment $Config
    New-Item -ItemType Directory -Force -Path $Config.ModelDirectory | Out-Null
    $RuntimeRoot = Join-Path $RepoRoot ".runtime"
    $LogsRoot = Join-Path $RuntimeRoot "logs"
    New-Item -ItemType Directory -Force -Path $LogsRoot | Out-Null
    $RecordPath = Join-Path $RuntimeRoot "ollama-server.json"
    $ServerProcess = $null
    if (Test-Path -LiteralPath $RecordPath) {
        try {
            $Record = Get-Content -LiteralPath $RecordPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $ServerProcess = Get-OwnedOllamaProcess $Record $Config.OllamaExecutable
            if ($null -ne $ServerProcess) {
                $SameDirectory = [StringComparer]::OrdinalIgnoreCase.Equals(
                    $Record.ModelDirectory, $Config.ModelDirectory
                )
                if ([int]$Record.Port -ne [int]$Config.Port -or -not $SameDirectory) {
                    Stop-Process -Id $ServerProcess.Id -ErrorAction Stop
                    $ServerProcess.WaitForExit(5000) | Out-Null
                    $ServerProcess = $null
                }
            }
        } catch {
            throw "Не удалось прочитать состояние собственного сервера Ollama: $($_.Exception.Message)"
        }
    }
    if ($null -eq $ServerProcess) {
        # Do not attach to or stop an unrelated Ollama using another model directory.
        $Listener = [Net.Sockets.TcpListener]::new(
            [Net.IPAddress]::Loopback, [int]$Config.Port
        )
        try { $Listener.Start() }
        catch {
            throw "Порт $($Config.Port) занят. Повторите установку с параметром -Port 11535."
        } finally { $Listener.Stop() }
        $ServerProcess = Start-Process -FilePath $Config.OllamaExecutable `
            -ArgumentList "serve" -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $LogsRoot "ollama-out.log") `
            -RedirectStandardError (Join-Path $LogsRoot "ollama-error.log")
        @{
            ProcessId = $ServerProcess.Id
            StartTimeTicks = $ServerProcess.StartTime.ToUniversalTime().Ticks
            Port = [int]$Config.Port
            ModelDirectory = $Config.ModelDirectory
        } | ConvertTo-Json | Set-Content -LiteralPath $RecordPath -Encoding UTF8
    }
    $Deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $Deadline) {
        if (Confirm-LocalOllama ([int]$Config.Port)) { return }
        $ServerProcess.Refresh()
        if ($ServerProcess.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    throw "Ollama не запустилась. Журнал: $(Join-Path $LogsRoot 'ollama-error.log')"
}
