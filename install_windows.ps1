#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallDir,
    [string]$ModelDirectory,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._:/-]*$')]
    [string]$BaseModel = "qwen3:4b-instruct",
    [ValidateRange(1024, 65535)]
    [int]$Port = 11534,
    [switch]$NoLaunch,
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$RepositoryRef = "developmental-psychology-windows"
$ScratchRoot = Join-Path $env:TEMP ("digital-child-install-" + [Guid]::NewGuid().ToString("N"))

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Resolve-InstallDirectory([string]$Value, [string]$Default, [string]$Prompt) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        $Value = Read-Host "$Prompt [$Default]"
        if ([string]::IsNullOrWhiteSpace($Value)) { $Value = $Default }
    }
    $Value = [Environment]::ExpandEnvironmentVariables($Value.Trim().Trim('"'))
    if (-not [IO.Path]::IsPathRooted($Value)) {
        throw "Укажите полный путь к каталогу, например D:\DigitalChild."
    }
    $FullPath = [IO.Path]::GetFullPath($Value).TrimEnd('\')
    if ($FullPath -match '^[A-Za-z]:$') {
        throw "Выберите отдельный каталог, а не корень диска."
    }
    New-Item -ItemType Directory -Force -Path $FullPath | Out-Null
    $ProbePath = Join-Path $FullPath (".write-probe-" + [Guid]::NewGuid().ToString("N"))
    try { [IO.File]::WriteAllText($ProbePath, "") }
    finally { Remove-Item -LiteralPath $ProbePath -Force -ErrorAction SilentlyContinue }
    return $FullPath
}

function Save-Download([string]$Uri, [string]$Destination, [string]$Sha256 = "") {
    if (Test-Path -LiteralPath $Destination) {
        if ($Sha256 -and (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Sha256) {
            return
        }
    }
    $PartialPath = "$Destination.partial"
    for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $PartialPath -UseBasicParsing `
                -UserAgent "DigitalChild-Windows-Installer" -TimeoutSec 1800
            if ($Sha256) {
                $Actual = (Get-FileHash -LiteralPath $PartialPath -Algorithm SHA256).Hash
                if ($Actual -ne $Sha256) { throw "Контрольная сумма скачанного файла не совпала." }
            }
            Move-Item -LiteralPath $PartialPath -Destination $Destination -Force
            return
        } catch {
            Remove-Item -LiteralPath $PartialPath -Force -ErrorAction SilentlyContinue
            if ($Attempt -eq 3) { throw }
            Write-Host "Загрузка прервана. Повтор $($Attempt + 1) из 3…"
            Start-Sleep -Seconds 2
        }
    }
}

function Install-ZipTool(
    [string]$Uri, [string]$Sha256, [string]$Destination, [string]$Executable
) {
    $ExecutablePath = Join-Path $Destination $Executable
    $MarkerPath = Join-Path $Destination ".installed-sha256"
    if (
        (Test-Path -LiteralPath $ExecutablePath) -and
        (Test-Path -LiteralPath $MarkerPath) -and
        (Get-Content -LiteralPath $MarkerPath -Raw).Trim() -eq $Sha256
    ) { return $ExecutablePath }
    $ArchivePath = Join-Path $ScratchRoot ($Executable + ".zip")
    Save-Download $Uri $ArchivePath $Sha256
    $UnpackPath = Join-Path $ScratchRoot ([Guid]::NewGuid().ToString("N"))
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $UnpackPath -Force
    $Found = Get-ChildItem -LiteralPath $UnpackPath -Recurse -File -Filter $Executable |
        Select-Object -First 1
    if ($null -eq $Found) { throw "В архиве не найден $Executable." }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Found.DirectoryName -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
    $Sha256 | Set-Content -LiteralPath $MarkerPath -Encoding ASCII
    Remove-Item -LiteralPath $UnpackPath -Recurse -Force
    Remove-Item -LiteralPath $ArchivePath -Force
    return $ExecutablePath
}

function Install-VisualCppRuntime {
    $RegistryPath = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
    $Existing = Get-ItemProperty -LiteralPath $RegistryPath -ErrorAction SilentlyContinue
    if ($null -ne $Existing -and $Existing.Installed -eq 1) { return }
    Write-Step "Установка библиотек Microsoft Visual C++"
    $InstallerPath = Join-Path $ScratchRoot "vc_redist.x64.exe"
    Save-Download "https://aka.ms/vc14/vc_redist.x64.exe" $InstallerPath
    $Signature = Get-AuthenticodeSignature -LiteralPath $InstallerPath
    if ($Signature.Status -ne "Valid" -or $Signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw "Не удалось проверить подпись установщика Microsoft."
    }
    Write-Host "Windows может запросить разрешение администратора для системных библиотек."
    $RuntimeInstaller = Start-Process -FilePath $InstallerPath `
        -ArgumentList "/install /quiet /norestart" -Verb RunAs -Wait -PassThru
    if ($RuntimeInstaller.ExitCode -notin @(0, 1638, 3010)) {
        throw "Установка Microsoft Visual C++ завершилась с кодом $($RuntimeInstaller.ExitCode)."
    }
    if ($RuntimeInstaller.ExitCode -eq 3010) {
        Write-Host "Windows рекомендует перезагрузку после установки системных библиотек."
    }
}

function Copy-Project([string]$Source, [string]$Destination) {
    if ([StringComparer]::OrdinalIgnoreCase.Equals($Source.TrimEnd('\'), $Destination)) { return }
    foreach ($Name in @(
        "src", "scripts", "windows_host", "docs", "pyproject.toml", "uv.lock",
        "README.md", "CHANGELOG.md", "install_windows.ps1", "install_windows.cmd", "start_windows.cmd"
    )) {
        $SourcePath = Join-Path $Source $Name
        if (Test-Path -LiteralPath $SourcePath) {
            Copy-Item -LiteralPath $SourcePath -Destination $Destination -Recurse -Force
        }
    }
}

function Set-DotEnvValue([string]$Path, [string]$Name, [string]$Value) {
    $Lines = @()
    if (Test-Path -LiteralPath $Path) { $Lines = @(Get-Content -LiteralPath $Path -Encoding UTF8) }
    $Pattern = '^\s*' + [Regex]::Escape($Name) + '\s*='
    $Lines = @($Lines | Where-Object { $_ -notmatch $Pattern })
    $Lines += "$Name=$Value"
    $Lines | Set-Content -LiteralPath $Path -Encoding UTF8
}

function New-DesktopShortcut([string]$RepoRoot) {
    $LauncherPath = Join-Path $RepoRoot ".runtime\start-desktop.vbs"
    $PowerShellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $ScriptPath = Join-Path $RepoRoot "scripts\windows\start_desktop.ps1"
    $CommandLine = '"' + $PowerShellPath + '" -NoProfile -ExecutionPolicy Bypass -File "' + $ScriptPath + '"'
    $VbsCommand = $CommandLine.Replace('"', '""')
    $VbsRoot = $RepoRoot.Replace('"', '""')
    @"
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "$VbsRoot"
shell.Run "$VbsCommand", 0, False
"@ | Set-Content -LiteralPath $LauncherPath -Encoding Unicode
    $Shell = New-Object -ComObject WScript.Shell
    $DesktopPath = [Environment]::GetFolderPath("Desktop")
    $Shortcut = $Shell.CreateShortcut((Join-Path $DesktopPath "Digital Child.lnk"))
    $Shortcut.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
    $Shortcut.Arguments = '"' + $LauncherPath + '"'
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "Digital Child — локальная модель, диалог и эмоциональная сфера"
    $Shortcut.Save()
}

try {
    if ($env:OS -ne "Windows_NT" -or -not [Environment]::Is64BitProcess) {
        throw "Нужна 64-битная Windows и 64-битный PowerShell. Запустите install_windows.cmd."
    }
    $Architecture = $env:PROCESSOR_ARCHITEW6432
    if (-not $Architecture) { $Architecture = $env:PROCESSOR_ARCHITECTURE }
    if ($Architecture -ne "AMD64") { throw "Этот установщик рассчитан на Windows x64 (Intel/AMD)." }
    $WindowsBuild = [Environment]::OSVersion.Version.Build
    if ($WindowsBuild -lt 19045) { throw "Нужна Windows 10 22H2 или Windows 11." }
    Write-Host "Digital Child — установка на чистую Windows" -ForegroundColor Green
    Write-Host "Будут загружены Python, Qt, Ollama и модель $BaseModel. Нужен интернет."
    Write-Host "Установка занимает несколько гигабайт; модель и приложение могут быть на разных дисках."
    $DefaultInstall = Join-Path $env:LOCALAPPDATA "DigitalChild"
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "pyproject.toml")) {
        $DefaultInstall = $PSScriptRoot
    }
    $InstallDir = Resolve-InstallDirectory $InstallDir $DefaultInstall "Куда установить приложение"
    $PreviousConfig = Join-Path $InstallDir ".desktop-install.json"
    $DefaultModels = Join-Path $InstallDir "models"
    if (Test-Path -LiteralPath $PreviousConfig) {
        $Saved = Get-Content -LiteralPath $PreviousConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        $DefaultModels = $Saved.ModelDirectory
        if (-not $PSBoundParameters.ContainsKey("Port")) { $Port = [int]$Saved.Port }
    }
    $ModelDirectory = Resolve-InstallDirectory $ModelDirectory $DefaultModels "Куда скачать и хранить модель"
    New-Item -ItemType Directory -Force -Path $ScratchRoot | Out-Null
    $SourceRoot = $PSScriptRoot
    if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "src\digital_child\desktop_app.py"))) {
        Write-Step "Загрузка проекта с GitHub"
        $ProjectArchive = Join-Path $ScratchRoot "digital-child.zip"
        Save-Download "https://github.com/sonnygalyeon/digital-child/archive/refs/heads/$RepositoryRef.zip" $ProjectArchive
        $ProjectUnpack = Join-Path $ScratchRoot "project"
        Expand-Archive -LiteralPath $ProjectArchive -DestinationPath $ProjectUnpack -Force
        $SourceRoot = (Get-ChildItem -LiteralPath $ProjectUnpack -Directory | Select-Object -First 1).FullName
    }
    Copy-Project $SourceRoot $InstallDir
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "uv.lock"))) {
        throw "Архив проекта повреждён: отсутствует uv.lock."
    }
    $RuntimeRoot = Join-Path $InstallDir ".runtime"
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    Install-VisualCppRuntime
    Write-Step "Загрузка uv и Python 3.12"
    $UvVersion = "0.12.23"
    $UvExecutable = Install-ZipTool `
        "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" `
        "75d05de6762778c31ee183398de7dd15093fad0ed90b1f236d8205ea5ec00c90" `
        (Join-Path $RuntimeRoot "uv\$UvVersion") "uv.exe"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeRoot "python"
    $env:UV_PYTHON_CACHE_DIR = Join-Path $RuntimeRoot "python-cache"
    $env:UV_PYTHON_BIN_DIR = Join-Path $RuntimeRoot "python-bin"
    $env:UV_PYTHON_INSTALL_BIN = "false"
    $env:UV_PYTHON_NO_REGISTRY = "true"
    $env:UV_PYTHON_PREFERENCE = "only-managed"
    $env:UV_CACHE_DIR = Join-Path $RuntimeRoot "uv-cache"
    $env:UV_LINK_MODE = "copy"
    & $UvExecutable python install 3.12
    if ($LASTEXITCODE -ne 0) { throw "Не удалось установить Python 3.12." }
    Write-Step "Установка приложения и Qt"
    Push-Location $InstallDir
    try {
        & $UvExecutable sync --frozen --python 3.12 --extra desktop
        if ($LASTEXITCODE -ne 0) { throw "Не удалось установить зависимости приложения." }
    } finally { Pop-Location }
    Write-Step "Загрузка переносимой Ollama"
    $OllamaVersion = "v0.35.1"
    $OllamaExecutable = Install-ZipTool `
        "https://github.com/ollama/ollama/releases/download/$OllamaVersion/ollama-windows-amd64.zip" `
        "dc50b9ca7f9023c86525012632cd1615b093d0407987444a7f62ecab617e8e93" `
        (Join-Path $RuntimeRoot "ollama\$OllamaVersion") "ollama.exe"
    $Config = [PSCustomObject]@{
        SchemaVersion = 1
        ModelDirectory = $ModelDirectory
        BaseModel = $BaseModel
        ModelName = "digital-child-fast"
        Port = $Port
        OllamaExecutable = $OllamaExecutable
    }
    . (Join-Path $InstallDir "scripts\windows\local_ollama.ps1")
    Write-Step "Запуск локального сервера модели"
    Ensure-LocalOllama $InstallDir $Config
    Write-Step "Загрузка модели $BaseModel в $ModelDirectory"
    & $OllamaExecutable pull $BaseModel
    if ($LASTEXITCODE -ne 0) { throw "Загрузка модели не завершилась. Повторите установку для продолжения." }
    $Template = Get-Content -LiteralPath (Join-Path $InstallDir "windows_host\Modelfile.fast") -Raw
    $GeneratedModelfile = Join-Path $RuntimeRoot "Modelfile.desktop"
    $Template = $Template -replace '(?m)^FROM\s+.+$', "FROM $BaseModel"
    # UTF-8 without BOM is required by Modelfile readers.
    [IO.File]::WriteAllText($GeneratedModelfile, $Template, [Text.UTF8Encoding]::new($false))
    & $OllamaExecutable create $Config.ModelName -f $GeneratedModelfile
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать профиль digital-child-fast." }
    $EnvPath = Join-Path $InstallDir ".env"
    if (Test-Path -LiteralPath $EnvPath) {
        $BackupPath = Join-Path $InstallDir ".env.windows-backup"
        if (-not (Test-Path -LiteralPath $BackupPath)) {
            Copy-Item -LiteralPath $EnvPath -Destination $BackupPath
        }
    }
    foreach ($Entry in @{
        DIGITAL_CHILD_LLM_PROVIDER = "ollama"
        DIGITAL_CHILD_LLM_BASE_URL = "http://127.0.0.1:$Port/v1"
        DIGITAL_CHILD_LLM_MODEL = $Config.ModelName
    }.GetEnumerator()) { Set-DotEnvValue $EnvPath $Entry.Key $Entry.Value }
    if (-not (Select-String -LiteralPath $EnvPath -Pattern '^DIGITAL_CHILD_RESEARCH_MODE=' -Quiet)) {
        Set-DotEnvValue $EnvPath "DIGITAL_CHILD_RESEARCH_MODE" "background"
    }
    $Config | ConvertTo-Json | Set-Content -LiteralPath $PreviousConfig -Encoding UTF8
    if (-not $NoShortcut) { New-DesktopShortcut $InstallDir }
    Write-Host "`nГотово. Приложение: $InstallDir" -ForegroundColor Green
    Write-Host "Модель: $ModelDirectory"
    Write-Host "Запуск: ярлык Digital Child или start_windows.cmd в каталоге приложения."
    if (-not $NoLaunch) {
        & (Join-Path $InstallDir "scripts\windows\start_desktop.ps1") -NoDialog
        if ($LASTEXITCODE -ne 0) { throw "Запуск окна не завершился успешно." }
    }
} catch {
    Write-Host "`nУстановка остановлена: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Сохранённая личность и загруженные файлы модели не удаляются."
    exit 1
} finally {
    if (Test-Path -LiteralPath $ScratchRoot) {
        Remove-Item -LiteralPath $ScratchRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
