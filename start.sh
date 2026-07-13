#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# .env 파일이 없으면 예제 파일에서 생성
if [ ! -f .env ]; then
    echo ".env 파일이 없어 .env.example에서 생성합니다."

    if [ ! -f .env.example ]; then
        echo "오류: .env.example 파일도 존재하지 않습니다."
        exit 1
    fi

    cp .env.example .env
else
    echo ".env 파일이 이미 존재합니다. 기존 파일을 사용합니다."
fi

# .env에서 값을 읽는 함수
# 값이 없으면 두 번째 인자인 기본값 사용
read_env_value() {
    local key="$1"
    local default_value="$2"
    local value

    value="$(
        grep -E "^[[:space:]]*${key}=" .env 2>/dev/null \
            | tail -n 1 \
            | cut -d '=' -f 2- \
            | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
            || true
    )"

    printf '%s' "${value:-$default_value}"
}

SERVER_PORT="$(read_env_value "MARS_SERVER_PORT" "8000")"
WEB_PORT="$(read_env_value "MARS_WEB_PORT" "5173")"

echo
echo "확인할 포트:"
echo "  서버: ${SERVER_PORT}"
echo "  웹:   ${WEB_PORT}"
echo

# 컨테이너 ID를 중복 없이 저장
declare -A CONTAINER_IDS=()

check_port() {
    local port="$1"
    local service_name="$2"
    local found=false

    echo "${service_name} 포트 ${port} 확인 중..."

    while IFS='|' read -r container_id container_name container_ports; do
        # 결과가 없으면 건너뜀
        [ -n "$container_id" ] || continue

        if [ "$found" = false ]; then
            echo "  ${port}번 포트를 사용하는 컨테이너:"
            found=true
        fi

        echo "    - 이름: ${container_name}"
        echo "      ID:   ${container_id}"
        echo "      포트: ${container_ports}"

        CONTAINER_IDS["$container_id"]="$container_name"
    done < <(
        docker ps \
            --filter "publish=${port}" \
            --format '{{.ID}}|{{.Names}}|{{.Ports}}'
    )

    if [ "$found" = false ]; then
        echo "  사용 중인 Docker 컨테이너가 없습니다."
    fi

    echo
}

check_port "$SERVER_PORT" "서버"
check_port "$WEB_PORT" "웹"

# 포트를 사용하는 컨테이너가 있을 경우 사용자 확인
if [ "${#CONTAINER_IDS[@]}" -gt 0 ]; then
    echo "종료 대상 컨테이너:"

    for container_id in "${!CONTAINER_IDS[@]}"; do
        echo "  - ${CONTAINER_IDS[$container_id]} (${container_id})"
    done

    echo
    read -r -p "위 컨테이너를 종료하고 새 프로젝트를 실행할까요? [y/yes]: " ANSWER

    # 소문자로 변환
    ANSWER="${ANSWER,,}"

    case "$ANSWER" in
        y|yes)
            echo
            echo "포트를 사용 중인 컨테이너를 종료합니다."

            for container_id in "${!CONTAINER_IDS[@]}"; do
                container_name="${CONTAINER_IDS[$container_id]}"
                echo "  종료 중: ${container_name}"
                docker stop "$container_id"
            done
            ;;
        *)
            echo
            echo "사용자가 종료를 승인하지 않아 실행을 중단합니다."
            exit 1
            ;;
    esac
else
    echo "8000번과 5173번 포트를 사용하는 Docker 컨테이너가 없습니다."
fi

echo
echo "현재 Compose 프로젝트의 기존 컨테이너와 고아 컨테이너를 정리합니다."
docker compose down --remove-orphans

echo
echo "Docker Compose 컨테이너를 빌드하고 실행합니다."
docker compose up --build -d

echo
echo "실행 상태:"
docker compose ps
