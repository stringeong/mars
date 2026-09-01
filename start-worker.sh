#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-auto}"
PROFILE=(--profile worker-ui)
BASE=(docker compose -f docker-compose.yml)
NVIDIA=(docker compose -f docker-compose.yml -f docker-compose.nvidia.yml)
AMD=(docker compose -f docker-compose.yml -f docker-compose.amd.yml)
NATIVE=(docker compose -f docker-compose.yml -f docker-compose.native-ollama.yml)

log() { printf '[M.A.R.S] %s\n' "$*"; }
fail() { printf '[M.A.R.S] 오류: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
사용법: ./start-worker.sh [auto|cpu|nvidia|amd|native|detect|stop|status]
  auto    운영체제와 GPU를 감지하고 실패 시 CPU로 폴백 (기본값)
  cpu     내장 Ollama를 CPU 모드로 실행
  nvidia  NVIDIA GPU를 Docker Ollama에 연결
  amd     Linux AMD ROCm 장치를 Docker Ollama에 연결
  native  Windows에서 실행 중인 네이티브 Ollama 사용
  detect  자동 감지 결과만 출력하고 실행하지 않음
  stop    Worker UI와 Ollama 중지
  status  현재 컨테이너 상태 표시
USAGE
}

case "$MODE" in
    -h|--help|help) usage; exit 0 ;;
    auto|cpu|nvidia|amd|native|detect|stop|status) ;;
    *) usage; fail "지원하지 않는 모드: $MODE" ;;
esac

command -v docker >/dev/null 2>&1 || fail "Docker를 설치해 주세요."
docker info >/dev/null 2>&1 || fail "Docker 엔진 또는 Docker Desktop을 실행해 주세요."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2가 필요합니다."

if [ "$MODE" = "status" ]; then
    "${BASE[@]}" "${PROFILE[@]}" ps
    exit 0
fi

if [ "$MODE" = "stop" ]; then
    log "Worker UI와 Ollama를 중지합니다."
    "${NVIDIA[@]}" "${PROFILE[@]}" stop worker-ui ollama >/dev/null 2>&1 || true
    "${AMD[@]}" "${PROFILE[@]}" stop worker-ui ollama >/dev/null 2>&1 || true
    "${NATIVE[@]}" "${PROFILE[@]}" stop worker-ui >/dev/null 2>&1 || true
    "${BASE[@]}" "${PROFILE[@]}" stop worker-ui ollama >/dev/null 2>&1 || true
    log "중지 완료"
    exit 0
fi

is_windows_environment() {
    case "$(uname -s 2>/dev/null || true)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
    esac
    grep -qi microsoft /proc/version 2>/dev/null
}

has_nvidia_gpu() {
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi -L >/dev/null 2>&1
    elif command -v nvidia-smi.exe >/dev/null 2>&1; then
        nvidia-smi.exe -L >/dev/null 2>&1
    else
        return 1
    fi
}

windows_gpu_names() {
    if command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -NonInteractive -Command \
            "Get-CimInstance Win32_VideoController | ForEach-Object { \$_.Name }" \
            2>/dev/null | tr -d '\r'
    fi
}

host_ollama_available() {
    if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 3 \
        http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        return 0
    fi
    if command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -NonInteractive -Command \
            "try { Invoke-RestMethod -TimeoutSec 3 http://localhost:11434/api/tags | Out-Null; exit 0 } catch { exit 1 }" \
            >/dev/null 2>&1
        return $?
    fi
    return 1
}

select_mode() {
    if [ "$MODE" != "auto" ]; then
        printf '%s' "$MODE"
        return
    fi

    if has_nvidia_gpu; then
        printf 'nvidia'
        return
    fi

    if is_windows_environment; then
        local names
        names="$(windows_gpu_names)"
        if printf '%s' "$names" | grep -Eqi 'AMD|Radeon'; then
            if host_ollama_available; then
                printf 'native'
            else
                log "AMD GPU를 감지했지만 Windows Ollama가 실행 중이 아닙니다." >&2
                log "https://ollama.com/download/windows 에서 설치·실행하면 GPU를 사용할 수 있습니다." >&2
                printf 'cpu'
            fi
            return
        fi
        printf 'cpu'
        return
    fi

    if [ -e /dev/kfd ] && [ -d /dev/dri ]; then
        printf 'amd'
        return
    fi

    printf 'cpu'
}

stop_selected() {
    case "$1" in
        nvidia) "${NVIDIA[@]}" "${PROFILE[@]}" stop worker-ui ollama >/dev/null 2>&1 || true ;;
        amd) "${AMD[@]}" "${PROFILE[@]}" stop worker-ui ollama >/dev/null 2>&1 || true ;;
        native) "${NATIVE[@]}" "${PROFILE[@]}" stop worker-ui >/dev/null 2>&1 || true ;;
    esac
}

start_mode() {
    local selected="$1"
    case "$selected" in
        cpu)
            "${BASE[@]}" "${PROFILE[@]}" up --build -d --quiet-pull --force-recreate worker-ui
            ;;
        nvidia)
            "${NVIDIA[@]}" "${PROFILE[@]}" up --build -d --quiet-pull --force-recreate worker-ui
            ;;
        amd)
            "${AMD[@]}" "${PROFILE[@]}" up --build -d --quiet-pull --force-recreate worker-ui
            ;;
        native)
            host_ollama_available || return 1
            "${NATIVE[@]}" "${PROFILE[@]}" up --build -d --quiet-pull --force-recreate worker-ui
            # 컨테이너에서도 Windows Ollama에 접근 가능한지 확인한다.
            local attempt
            for attempt in 1 2 3 4 5; do
                if "${NATIVE[@]}" "${PROFILE[@]}" exec -T worker-ui python -c \
                    "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=3)" \
                    >/dev/null 2>&1; then
                    return 0
                fi
                sleep 2
            done
            return 1
            ;;
    esac
}

if [ "$MODE" = "detect" ]; then
    MODE="auto"
    SELECTED="$(select_mode)"
    log "자동 감지 결과: $SELECTED"
    exit 0
fi

SELECTED="$(select_mode)"
log "선택된 실행 모드: $SELECTED"

if start_mode "$SELECTED"; then
    log "Worker UI 시작 완료: http://127.0.0.1:${MARS_WORKER_UI_PORT:-8765}"
    "${BASE[@]}" "${PROFILE[@]}" ps
    exit 0
fi

stop_selected "$SELECTED"
if [ "$MODE" != "auto" ]; then
    fail "$SELECTED 모드 시작에 실패했습니다. auto 또는 cpu 모드로 다시 시도하세요."
fi

log "$SELECTED 모드 시작에 실패해 CPU 모드로 자동 재시도합니다."
start_mode cpu || fail "CPU 모드 Worker UI도 시작하지 못했습니다."
log "CPU 폴백 완료: http://127.0.0.1:${MARS_WORKER_UI_PORT:-8765}"
"${BASE[@]}" "${PROFILE[@]}" ps
