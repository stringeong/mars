#!/usr/bin/env bash
# 시스템 테스트 환경을 새로 만들고 띄운다 (D07 시스템 테스트 결과서 4.1·5절).
#
#   tests/system/start_env.sh          # 환경 생성 + 프로세스 기동
#   tests/system/start_env.sh stop     # 마지막으로 띄운 환경의 프로세스 종료
#
# 매번 임시 디렉터리에 빈 DB, Worker 2대의 설정, 공유 폴더 shareA를 새로 만든다.
# 띄우는 것: 대역 Ollama, 서버, cloud-worker, Worker UI 2개(worker-A·worker-B), 웹 개발 서버.
# 실행 정보는 <임시 디렉터리>/env.sh에 남기고, 그 경로를 tests/system/.last_run에 적는다.
set -euo pipefail

# ---- 포트: 이미 쓰는 포트가 있으면 환경변수로 바꿔서 실행한다 ----
SERVER_PORT="${SERVER_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
WORKER_A_PORT="${WORKER_A_PORT:-8765}"
WORKER_B_PORT="${WORKER_B_PORT:-8766}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/../.." && pwd)"
LAST_RUN_FILE="$HERE/.last_run"

# 각 구성요소의 Python. 기본은 README대로 만든 가상환경이다.
SERVER_PYTHON="${SERVER_PYTHON:-$REPO_ROOT/server/.venv/bin/python}"
WORKER_PYTHON="${WORKER_PYTHON:-$REPO_ROOT/worker/.venv/bin/python}"
NPM="${NPM:-npm}"

stop_env() {
  [ -f "$LAST_RUN_FILE" ] || { echo "띄운 환경이 없습니다."; return 0; }
  local run_dir pid
  run_dir="$(cat "$LAST_RUN_FILE")"
  if [ -f "$run_dir/pids" ]; then
    while read -r pid; do
      # 자식 프로세스(Worker run, vite)까지 함께 끈다
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
    done < "$run_dir/pids"
    # 포트가 풀릴 때까지 최대 10초 기다린다(바로 다시 띄울 때 '포트 사용 중'이 나지 않게)
    for _ in $(seq 20); do
      alive=0
      while read -r pid; do kill -0 "$pid" 2>/dev/null && alive=1; done < "$run_dir/pids"
      [ "$alive" = 0 ] && break
      sleep 0.5
    done
  fi
  rm -f "$LAST_RUN_FILE"
  echo "환경 종료: $run_dir"
}

if [ "${1:-}" = "stop" ]; then
  stop_env
  exit 0
fi

for bin in "$SERVER_PYTHON" "$WORKER_PYTHON"; do
  [ -x "$bin" ] || { echo "Python을 찾을 수 없습니다: $bin (SERVER_PYTHON·WORKER_PYTHON으로 지정)"; exit 1; }
done
for port in "$SERVER_PORT" "$WEB_PORT" "$WORKER_A_PORT" "$WORKER_B_PORT" "$OLLAMA_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "포트 $port 를 이미 쓰고 있습니다. 해당 포트 변수를 바꿔서 실행하세요 (예: SERVER_PORT=18000)."
    exit 1
  fi
done

# 이전 환경이 남아 있으면 끈다
[ -f "$LAST_RUN_FILE" ] && stop_env

RUN_DIR="${SYSTEST_RUN_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/mars-systest.XXXXXX")}"
RUN_DIR="$(cd "$RUN_DIR" && pwd -P)"
mkdir -p "$RUN_DIR/logs" "$RUN_DIR/uploads" "$RUN_DIR/worker-A" "$RUN_DIR/worker-B"
: > "$RUN_DIR/pids"

# ---- 테스트 데이터: 공유 폴더 shareA와 폴더 밖 파일(심볼릭 링크 차단 시험용) ----
mkdir -p "$RUN_DIR/shareA" "$RUN_DIR/outside"
cp "$HERE/fixtures/card_october.csv" "$RUN_DIR/shareA/"
printf 'SECRET_OUTSIDE\n' > "$RUN_DIR/outside/secret.txt"
ln -s "$RUN_DIR/outside/secret.txt" "$RUN_DIR/shareA/leak.txt"

SERVER_URL="http://127.0.0.1:$SERVER_PORT"
WEB_URL="http://127.0.0.1:$WEB_PORT"
OLLAMA_URL="http://127.0.0.1:$OLLAMA_PORT"

export MARS_ENV=test
export MARS_DATABASE_URL="sqlite:///$RUN_DIR/mars.db"
export MARS_UPLOAD_DIR="$RUN_DIR/uploads"
export OLLAMA_URL
export MARS_ALLOWED_ORIGINS="$WEB_URL,http://localhost:$WEB_PORT"
export MARS_HEARTBEAT_TIMEOUT=30
export PYTHONUNBUFFERED=1

start() {  # start <이름> <작업 폴더> <명령...>
  local name="$1" dir="$2"; shift 2
  (cd "$dir" && exec "$@") > "$RUN_DIR/logs/$name.log" 2>&1 &
  echo $! >> "$RUN_DIR/pids"
}

wait_http() {  # wait_http <이름> <URL> [초]
  local name="$1" url="$2" limit="${3:-60}" i
  for ((i = 0; i < limit * 2; i++)); do
    if "$SERVER_PYTHON" -c "import sys,httpx;sys.exit(0 if httpx.get(sys.argv[1],timeout=2).status_code<500 else 1)" "$url" 2>/dev/null; then
      echo "  $name 준비됨: $url"
      return 0
    fi
    sleep 0.5
  done
  echo "헬스 확인 실패: $name ($url). 로그: $RUN_DIR/logs/$name.log"
  exit 1
}

echo "환경 디렉터리: $RUN_DIR"
echo "빈 DB 만들기"
(cd "$REPO_ROOT/server" && "$SERVER_PYTHON" -m alembic upgrade head) > "$RUN_DIR/logs/alembic.log" 2>&1

echo "프로세스 기동"
FAKE_OLLAMA_LOG="$RUN_DIR/ollama_requests.jsonl" \
  start fake-ollama "$HERE" "$SERVER_PYTHON" fake_ollama.py --port "$OLLAMA_PORT"
start server "$REPO_ROOT/server" "$SERVER_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$SERVER_PORT"
start cloud-worker "$REPO_ROOT/server" "$SERVER_PYTHON" -m app.cloud_worker

for name in A B; do
  port_var="WORKER_${name}_PORT"
  MARS_DATA_DIR="$RUN_DIR/worker-$name" \
  MARS_CONFIG_PATH="$RUN_DIR/worker-$name/agent_config.json" \
  MARS_SERVER_URL="$SERVER_URL" \
  MARS_OLLAMA_URL="$OLLAMA_URL" \
    start "worker-$name" "$REPO_ROOT/worker" "$WORKER_PYTHON" -m agent ui --host 127.0.0.1 --port "${!port_var}"
done

# 웹은 Vite 프록시 대신 서버 주소를 직접 쓴다(프록시 대상이 8000으로 고정되어 있음)
VITE_API_URL="$SERVER_URL" \
  start web "$REPO_ROOT/web" "$NPM" run dev -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort

wait_http fake-ollama "$OLLAMA_URL/api/tags"
wait_http server "$SERVER_URL/docs"
wait_http worker-A "http://127.0.0.1:$WORKER_A_PORT/api/status"
wait_http worker-B "http://127.0.0.1:$WORKER_B_PORT/api/status"
wait_http web "$WEB_URL/" 90

cat > "$RUN_DIR/env.sh" <<EOF
export SYSTEST_RUN_DIR='$RUN_DIR'
export SERVER_URL='$SERVER_URL'
export WEB_URL='$WEB_URL'
export OLLAMA_URL='$OLLAMA_URL'
export WORKER_A_URL='http://127.0.0.1:$WORKER_A_PORT'
export WORKER_B_URL='http://127.0.0.1:$WORKER_B_PORT'
export SHARE_A='$RUN_DIR/shareA'
export MARS_DATABASE_URL='$MARS_DATABASE_URL'
EOF
echo "$RUN_DIR" > "$LAST_RUN_FILE"

echo
echo "준비 완료. 시험 실행:"
echo "  source $RUN_DIR/env.sh && $SERVER_PYTHON tests/system/systest.py"
echo "종료: tests/system/start_env.sh stop"
