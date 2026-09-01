param(
    [ValidateSet("auto", "cpu", "nvidia", "native", "detect", "stop", "status", "help")]
    [string]$Mode = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$DockerDesktopUrl = "https://www.docker.com/products/docker-desktop/"
$OllamaWindowsUrl = "https://ollama.com/download/windows"
$WorkerUiUrl = "http://127.0.0.1:8765"
$script:ComposeExitCode = 0

function Write-Mars {
    param([string]$Message)
    Write-Host "[M.A.R.S] $Message"
}

function Show-Usage {
    Write-Host @"
사용법: start-worker.cmd [auto|cpu|nvidia|native|detect|stop|status]
  auto     GPU를 감지하고 실패 시 CPU로 폴백 (기본값)
  cpu      내장 Ollama를 CPU 모드로 실행
  nvidia   NVIDIA GPU를 Docker Ollama에 연결
  native   Windows에서 실행 중인 네이티브 Ollama 사용
  detect   자동 감지 결과만 출력
  stop     Worker UI와 Ollama 중지
  status   현재 컨테이너 상태 표시
"@
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

    Wait-DockerEngine

    if ($Mode -eq "status") {
        Invoke-Compose "cpu" @("ps")
        exit $script:ComposeExitCode
    }

    if ($Mode -eq "stop") {
        Write-Mars "Worker UI와 Ollama를 중지합니다."
        Invoke-Compose "nvidia" @("stop", "worker-ui", "ollama") -Quiet
        Invoke-Compose "native" @("stop", "worker-ui") -Quiet
        Invoke-Compose "cpu" @("stop", "worker-ui", "ollama") -Quiet
        Write-Mars "중지 완료"
        exit 0
    }

    if ($Mode -eq "detect") {
        $Mode = "auto"
        $Detected = Select-Mode
        Write-Mars "자동 감지 결과: $Detected"
        exit 0
    }

    $Selected = Select-Mode
    Write-Mars "선택된 실행 모드: $Selected"
    if (Start-SelectedMode $Selected) {
        Write-Mars "Worker UI 시작 완료: $WorkerUiUrl"
        Invoke-Compose "cpu" @("ps")
        Start-Process $WorkerUiUrl
        exit 0
    }

    Stop-SelectedMode $Selected
    if ($Mode -ne "auto") {
        throw "$Selected 모드 시작에 실패했습니다. auto 또는 cpu 모드로 다시 시도하세요."
    }

    Write-Mars "$Selected 모드 시작에 실패해 CPU 모드로 자동 재시도합니다."
    if (-not (Start-SelectedMode "cpu")) {
        throw "CPU 모드 Worker UI도 시작하지 못했습니다."
    }
    Write-Mars "CPU 폴백 완료: $WorkerUiUrl"
    Invoke-Compose "cpu" @("ps")
    Start-Process $WorkerUiUrl
    exit 0
} catch {
    Write-Host "[M.A.R.S] 오류: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
