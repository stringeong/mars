param(
    [ValidateSet("auto", "native", "docker", "cpu", "nvidia", "detect", "setup", "stop", "status", "help")]
    [string]$Mode = "auto",

    [string]$ServerUrl = "https://marsflowlab.com/api"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$WorkerRoot = Join-Path $PSScriptRoot "worker"
$VenvRoot = Join-Path $WorkerRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$MarsDataRoot = Join-Path $env:LOCALAPPDATA "MarsFlowLab\Worker"
$RunRoot = Join-Path $MarsDataRoot "run"
$LogRoot = Join-Path $MarsDataRoot "logs"
$UiPidPath = Join-Path $RunRoot "ui.pid"
$RequirementsHashPath = Join-Path $VenvRoot ".requirements.sha256"
$RequirementsPath = Join-Path $WorkerRoot "requirements.txt"

$DockerDesktopUrl = "https://www.docker.com/products/docker-desktop/"
$OllamaWindowsUrl = "https://ollama.com/download/windows"
$PythonWindowsUrl = "https://www.python.org/downloads/windows/"
$WorkerUiUrl = "http://127.0.0.1:8765"
$script:ComposeExitCode = 0

function Write-Mars {
    param([string]$Message)
    Write-Host "[M.A.R.S] $Message"
}

function Show-Usage {
    Write-Host @"
사용법: start-worker.cmd [auto|native|docker|setup|status|stop] [-ServerUrl URL]
  auto     Windows 네이티브 Worker 실행 (기본값, BIOS 가상화 불필요)
  native   Windows 네이티브 Worker 실행
  docker   기존 Docker GPU 자동 감지 모드
  cpu      기존 Docker CPU 모드
  nvidia   기존 Docker NVIDIA 모드
  setup    네이티브 Python 가상환경과 패키지만 준비
  detect   네이티브 실행 환경 감지 결과 출력
  status   네이티브 Worker, Ollama, Docker 상태 표시
  stop     네이티브 Worker와 Docker Worker 중지

선택 사항:
  -ServerUrl URL  Worker가 등록될 서버의 DNS 및 TCP 연결을 미리 확인

예: start-worker.cmd auto -ServerUrl https://marsflowlab.com/api
"@
}

function Test-WorkerServerConnection {
    param([string]$Url)

    if ([string]::IsNullOrWhiteSpace($Url)) { return }

    try {
        $Uri = [System.Uri]$Url
    } catch {
        throw "서버 주소 형식이 올바르지 않습니다: $Url"
    }
    if (-not $Uri.IsAbsoluteUri -or $Uri.Scheme -notin @("http", "https") -or -not $Uri.Host) {
        throw "서버 주소는 http:// 또는 https://로 시작해야 합니다: $Url"
    }

    $Port = $Uri.Port
    Write-Mars "서버 연결 확인: $($Uri.Host):$Port"
    $Result = Test-NetConnection -ComputerName $Uri.Host -Port $Port -WarningAction SilentlyContinue
    if (-not $Result.TcpTestSucceeded) {
        throw "서버 $($Uri.Host):$Port 에 연결할 수 없습니다. DNS, VPN, 서버 방화벽 또는 Windows 아웃바운드 정책을 확인해 주세요."
    }
    Write-Mars "서버 TCP 연결 확인 완료"
}

function Initialize-NativeDirectories {
    foreach ($Path in @($MarsDataRoot, $RunRoot, $LogRoot)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    $LegacyConfigPath = Join-Path $WorkerRoot "agent_config.json"
    $NativeConfigPath = Join-Path $MarsDataRoot "agent_config.json"
    if ((Test-Path $LegacyConfigPath) -and -not (Test-Path $NativeConfigPath)) {
        Copy-Item $LegacyConfigPath $NativeConfigPath
        Write-Mars "기존 Worker 설정을 LocalAppData로 이전했습니다."
    }
}

function Get-SystemPython {
    $Candidates = @(
        @{ Command = "py.exe"; Arguments = @("-3") },
        @{ Command = "python.exe"; Arguments = @() },
        @{ Command = "python3.exe"; Arguments = @() }
    )
    foreach ($Candidate in $Candidates) {
        $Executable = Get-Command $Candidate.Command -ErrorAction SilentlyContinue
        if (-not $Executable) { continue }
        $CandidateArguments = $Candidate.Arguments
        $Version = & $Executable.Source @CandidateArguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$Version -ge [version]"3.11") {
            return @{ Path = $Executable.Source; Arguments = @($Candidate.Arguments) }
        }
    }
    return $null
}

function Install-NativeEnvironment {
    Initialize-NativeDirectories
    if (-not (Test-Path $VenvPython)) {
        $Python = Get-SystemPython
        if (-not $Python) {
            Start-Process $PythonWindowsUrl
            throw "Python 3.11 이상을 찾지 못했습니다. 열린 공식 페이지에서 Python을 설치할 때 'Add python.exe to PATH'를 선택해 주세요."
        }
        Write-Mars "Windows 네이티브 가상환경을 생성합니다."
        $PythonArguments = $Python.Arguments
        & $Python.Path @PythonArguments -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw "Python 가상환경 생성에 실패했습니다." }
    }
    $CurrentHash = (Get-FileHash -Algorithm SHA256 $RequirementsPath).Hash
    $SavedHash = if (Test-Path $RequirementsHashPath) { (Get-Content $RequirementsHashPath -Raw).Trim() } else { "" }
    if ($CurrentHash -ne $SavedHash) {
        Write-Mars "Worker Python 패키지를 설치합니다. 최초 실행에는 몇 분이 걸릴 수 있습니다."
        & $VenvPython -m pip install --disable-pip-version-check --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw "pip 업데이트에 실패했습니다." }
        & $VenvPython -m pip install --disable-pip-version-check -r $RequirementsPath
        if ($LASTEXITCODE -ne 0) { throw "Worker Python 패키지 설치에 실패했습니다." }
        Set-Content -Path $RequirementsHashPath -Value $CurrentHash -Encoding ASCII
    }
    Write-Mars "네이티브 Python 환경 준비 완료"
}

function Get-OllamaAppPath {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    foreach ($Candidate in $Candidates) { if (Test-Path $Candidate) { return $Candidate } }
    $Command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    return $null
}

function Wait-NativeOllama {
    if (Test-NativeOllama) { return }
    $Ollama = Get-OllamaAppPath
    if (-not $Ollama) {
        Start-Process $OllamaWindowsUrl
        throw "Windows용 Ollama를 찾지 못했습니다. 열린 공식 페이지에서 설치한 뒤 다시 실행해 주세요."
    }
    Write-Mars "Windows Ollama를 시작합니다."
    if ([System.IO.Path]::GetFileName($Ollama) -ieq "ollama.exe") {
        Start-Process -FilePath $Ollama -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    } else {
        Start-Process -FilePath $Ollama | Out-Null
    }
    for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
        Start-Sleep -Seconds 1
        if (Test-NativeOllama) { Write-Mars "Windows Ollama 준비 완료"; return }
    }
    throw "Ollama가 30초 안에 준비되지 않았습니다. Ollama 앱 상태를 확인해 주세요."
}

function Test-NativeUi {
    try {
        Invoke-RestMethod -Method Get -Uri "$WorkerUiUrl/api/status" -TimeoutSec 2 | Out-Null
        return $true
    } catch { return $false }
}

function Start-NativeWorker {
    Install-NativeEnvironment
    Wait-NativeOllama
    if (Test-NativeUi) {
        Write-Mars "Worker UI가 이미 실행 중입니다: $WorkerUiUrl"
        Start-Process $WorkerUiUrl
        return
    }
    Initialize-NativeDirectories
    $env:MARS_CONFIG_PATH = Join-Path $MarsDataRoot "agent_config.json"
    $env:MARS_SERVER_URL = $ServerUrl
    $env:MARS_OLLAMA_URL = "http://127.0.0.1:11434"
    $env:MARS_GPU_MODE = "native-windows"
    $StdoutPath = Join-Path $LogRoot "worker-ui.log"
    $StderrPath = Join-Path $LogRoot "worker-ui-error.log"
    $Process = Start-Process -FilePath $VenvPython -ArgumentList @("-m", "agent", "ui", "--host", "127.0.0.1", "--port", "8765") -WorkingDirectory $WorkerRoot -WindowStyle Hidden -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    Set-Content -Path $UiPidPath -Value $Process.Id -Encoding ASCII
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-NativeUi) {
            Write-Mars "Windows 네이티브 Worker UI 시작 완료: $WorkerUiUrl"
            Start-Process $WorkerUiUrl
            return
        }
        if ($Process.HasExited) { break }
    }
    throw "Worker UI 시작에 실패했습니다. 로그를 확인해 주세요: $StderrPath"
}

function Stop-NativeWorker {
    if (Test-Path $UiPidPath) {
        $WorkerProcessId = [int](Get-Content $UiPidPath -Raw).Trim()
        $WorkerProcess = Get-Process -Id $WorkerProcessId -ErrorAction SilentlyContinue
        if ($WorkerProcess) {
            try {
                Invoke-RestMethod -Method Post -Uri "$WorkerUiUrl/api/worker/stop" -ContentType "application/json" -Body "{}" -TimeoutSec 12 | Out-Null
            } catch { Write-Mars "Worker 자식 프로세스 정상 종료 요청에 실패해 UI를 종료합니다." }
            Stop-Process -Id $WorkerProcessId -Force
            Write-Mars "Windows 네이티브 Worker를 중지했습니다."
        }
        Remove-Item $UiPidPath -Force -ErrorAction SilentlyContinue
    } elseif (Test-NativeUi) {
        Write-Mars "PID 파일이 없어 실행 중인 Worker UI를 자동 종료하지 않았습니다. 작업 관리자에서 Python 프로세스를 확인해 주세요."
    }
}

function Get-DockerDesktopPath {
    $Candidates = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) { return $Candidate }
    }
    return $null
}

function Add-DockerToPath {
    $DockerBin = "$env:ProgramFiles\Docker\Docker\resources\bin"
    if ((Test-Path $DockerBin) -and -not (Get-Command docker -ErrorAction SilentlyContinue)) {
        $env:Path = "$DockerBin;$env:Path"
    }
}

function Wait-DockerEngine {
    Add-DockerToPath
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Start-Process $DockerDesktopUrl
        throw "Docker CLI를 찾을 수 없습니다. 열린 페이지에서 Docker Desktop을 설치해 주세요."
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        $Desktop = Get-DockerDesktopPath
        if (-not $Desktop) {
            Start-Process $DockerDesktopUrl
            throw "Docker Desktop을 찾을 수 없습니다. 열린 페이지에서 설치해 주세요."
        }

        Write-Mars "Docker Desktop을 시작합니다."
        Start-Process $Desktop | Out-Null
        for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
            Start-Sleep -Seconds 2
            & docker info *> $null
            if ($LASTEXITCODE -eq 0) {
                Write-Mars "Docker 엔진 준비 완료"
                break
            }
            if ($Attempt -eq 60) {
                throw "Docker 엔진이 120초 안에 준비되지 않았습니다. Docker Desktop 상태를 확인해 주세요."
            }
        }
    }

    $OsType = (& docker info --format "{{.OSType}}" 2>$null).Trim()
    if ($OsType -ne "linux") {
        throw "Docker Desktop을 Linux containers 모드로 전환해 주세요."
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose v2를 사용할 수 없습니다. Docker Desktop을 업데이트해 주세요."
    }
}

function Get-ComposeFiles {
    param([string]$SelectedMode)
    $Files = @("-f", "docker-compose.yml")
    switch ($SelectedMode) {
        "nvidia" { $Files += @("-f", "docker-compose.nvidia.yml") }
        "native" { $Files += @("-f", "docker-compose.native-ollama.yml") }
    }
    return $Files
}

function Invoke-Compose {
    param(
        [string]$SelectedMode,
        [string[]]$ComposeArguments,
        [switch]$Quiet
    )
    $Arguments = @("compose") + (Get-ComposeFiles $SelectedMode) + @("--profile", "worker-ui") + $ComposeArguments
    if (-not $Quiet) {
        Write-Mars ("docker " + ($Arguments -join " "))
        & docker @Arguments
    } else {
        & docker @Arguments *> $null
    }
    $script:ComposeExitCode = $LASTEXITCODE
}

function Get-GpuNames {
    try {
        return @(
            Get-CimInstance Win32_VideoController -ErrorAction Stop |
                ForEach-Object { $_.Name }
        )
    } catch {
        Write-Mars "Windows GPU 목록을 읽지 못했습니다: $($_.Exception.Message)"
        return @()
    }
}

function Test-NvidiaGpu {
    $Names = Get-GpuNames
    if (-not ($Names | Where-Object { $_ -match "NVIDIA" })) { return $false }
    $NvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $NvidiaSmi) {
        Write-Mars "NVIDIA GPU는 있지만 nvidia-smi를 찾지 못했습니다. 최신 NVIDIA 드라이버가 필요합니다."
        return $false
    }
    & $NvidiaSmi.Source -L *> $null
    return $LASTEXITCODE -eq 0
}

function Test-AmdGpu {
    return [bool](Get-GpuNames | Where-Object { $_ -match "AMD|Radeon" })
}

function Test-NativeOllama {
    try {
        Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Select-Mode {
    if ($Mode -ne "auto") { return $Mode }
    if (Test-NvidiaGpu) { return "nvidia" }
    if (Test-AmdGpu) {
        if (Test-NativeOllama) { return "native" }
        Write-Mars "AMD GPU를 감지했지만 Windows Ollama가 실행 중이 아닙니다."
        Write-Mars "Ollama 설치: $OllamaWindowsUrl"
    }
    return "cpu"
}

function Stop-SelectedMode {
    param([string]$SelectedMode)
    switch ($SelectedMode) {
        "nvidia" { Invoke-Compose "nvidia" @("stop", "worker-ui", "ollama") -Quiet }
        "native" { Invoke-Compose "native" @("stop", "worker-ui") -Quiet }
        default { Invoke-Compose "cpu" @("stop", "worker-ui", "ollama") -Quiet }
    }
}

function Test-ContainerNativeOllama {
    for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
        Invoke-Compose "native" @(
            "exec", "-T", "worker-ui", "python", "-c",
            "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=3)"
        ) -Quiet
        if ($script:ComposeExitCode -eq 0) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-SelectedMode {
    param([string]$SelectedMode)
    if ($SelectedMode -eq "native" -and -not (Test-NativeOllama)) { return $false }

    Invoke-Compose $SelectedMode @(
        "up", "--build", "-d", "--quiet-pull", "--force-recreate", "worker-ui"
    )
    if ($script:ComposeExitCode -ne 0) { return $false }
    if ($SelectedMode -eq "native") { return Test-ContainerNativeOllama }
    return $true
}

try {
    if ($Mode -eq "help") {
        Show-Usage
        exit 0
    }

    if ($Mode -eq "status") {
        Write-Mars ("Windows 네이티브 Worker UI: " + $(if (Test-NativeUi) { "실행 중 ($WorkerUiUrl)" } else { "중지" }))
        Write-Mars ("Windows Ollama: " + $(if (Test-NativeOllama) { "실행 중 (127.0.0.1:11434)" } else { "중지" }))
        Add-DockerToPath
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            & docker info *> $null
            if ($LASTEXITCODE -eq 0) { Invoke-Compose "cpu" @("ps") }
            else { Write-Mars "Docker 엔진: 중지" }
        } else { Write-Mars "Docker: 설치되지 않음 (네이티브 실행에는 불필요)" }
        exit 0
    }

    if ($Mode -eq "stop") {
        Stop-NativeWorker
        Add-DockerToPath
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            & docker info *> $null
            if ($LASTEXITCODE -eq 0) {
                Invoke-Compose "nvidia" @("stop", "worker-ui", "ollama") -Quiet
                Invoke-Compose "native" @("stop", "worker-ui") -Quiet
                Invoke-Compose "cpu" @("stop", "worker-ui", "ollama") -Quiet
                Write-Mars "Docker Worker 중지 완료"
            }
        }
        Write-Mars "중지 완료"
        exit 0
    }

    if ($Mode -eq "detect") {
        $Python = Get-SystemPython
        Write-Mars ("Python 3.11+: " + $(if ($Python) { "사용 가능" } else { "설치 필요" }))
        Write-Mars ("Ollama: " + $(if (Get-OllamaAppPath) { "설치됨" } else { "설치 필요" }))
        Write-Mars ("Ollama API: " + $(if (Test-NativeOllama) { "실행 중" } else { "중지" }))
        Write-Mars "BIOS 가상화와 Docker는 네이티브 모드에 필요하지 않습니다."
        exit 0
    }

    Test-WorkerServerConnection $ServerUrl

    if ($Mode -eq "setup") {
        Install-NativeEnvironment
        exit 0
    }

    if ($Mode -in @("auto", "native")) {
        Write-Mars "Windows 네이티브 모드로 실행합니다. BIOS 가상화와 Docker는 필요하지 않습니다."
        Start-NativeWorker
        exit 0
    }

    Wait-DockerEngine
    $Selected = $Mode
    if ($Mode -eq "docker") {
        $Mode = "auto"
        $Selected = Select-Mode
        $Mode = "docker"
    }
    Write-Mars "Docker 실행 모드: $Selected"
    if (-not (Start-SelectedMode $Selected)) {
        Stop-SelectedMode $Selected
        throw "$Selected Docker 모드 시작에 실패했습니다. native 모드를 사용하거나 Docker 설정을 확인해 주세요."
    }
    Write-Mars "Docker Worker UI 시작 완료: $WorkerUiUrl"
    Invoke-Compose $Selected @("ps")
    Start-Process $WorkerUiUrl
    exit 0
} catch {
    Write-Host "[M.A.R.S] 오류: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
