$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python이 필요합니다. https://www.python.org/downloads/windows/ 에서 설치하세요."
}
if (-not (Test-Path "docker-compose.yml")) {
    throw "docker-compose.yml을 찾을 수 없습니다."
}

py -m pip install --upgrade pip
py -m pip install -r requirements-launcher.txt
py -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "MARS-Worker-Launcher" `
    "mars_worker_launcher.py"

Write-Host ""
Write-Host "빌드 완료: dist\MARS-Worker-Launcher.exe"
Write-Host "EXE를 docker-compose.yml 및 docker-compose.nvidia.yml과 같은 폴더에 두세요."
