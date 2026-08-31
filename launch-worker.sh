#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "오류: Python 3가 필요합니다."
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "오류: Docker를 설치한 뒤 다시 실행하세요."
    echo "https://docs.docker.com/engine/install/"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "오류: Docker 엔진이 실행 중이 아닙니다."
    exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "오류: Tkinter가 필요합니다. Ubuntu/Debian: sudo apt install python3-tk"
    exit 1
fi

exec python3 "$SCRIPT_DIR/mars_worker_launcher.py"
