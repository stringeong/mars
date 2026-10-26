# M.A.R.S — MAS And Resource Sharing

사용자가 보유한 여러 개인 기기를 하나의 실행 환경으로 묶어, 개인정보를 외부로 내보내지 않고
자연어만으로 다단계 AI 작업(Multi-Agent System)을 생성·실행하는 개인용 멀티 디바이스 AI 플랫폼.

## 구성

| 디렉터리 | 역할 |
|---|---|
| `server/` | 중앙 서버 (FastAPI) — 인증, 기기/서비스/실행 관리, DAG 생성·검증, 작업 분배 |
| `worker/` | Worker Agent (Python) — 기기 등록, 하트비트, 작업 실행(Ollama), 폴더 화이트리스트 |
| `web/`    | 웹 프론트엔드 (React + TypeScript + React Flow) |

## 빠른 시작

Linux 서버에 Docker Compose로 배포하는 절차는 [Linux 서버 실행 가이드](docs/linux-server.md)를 참고하세요.
인터넷에 공개하는 운영 배포는 [운영 HTTPS 배포 가이드](docs/production-deployment.md)를 함께 적용하세요.

### 1. 중앙 서버

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 문서: http://localhost:8000/docs
- 클라우드 LLM 노드를 사용하면 별도 터미널에서 `python -m app.cloud_worker`를 실행합니다. Docker Compose에서는 `cloud-worker` 서비스가 자동으로 실행됩니다.
- DB 스키마는 Alembic으로 관리되며 Docker 서버 시작 시 `alembic upgrade head`가 자동 실행됩니다.
- DB는 `server/mars.db` (SQLite) 에 자동 생성됩니다.
- 프롬프트→워크플로우 생성에 Ollama를 사용합니다. Ollama가 없으면 규칙 기반 폴백으로 동작합니다.
  - `OLLAMA_URL` (기본 `http://localhost:11434`), `MARS_DEFAULT_MODEL` (기본 `gemma3:4b`) 환경변수로 변경 가능.
  - 클라우드 LLM 키 암호화는 `MARS_CREDENTIAL_ENCRYPTION_KEY`(Fernet 키)를 권장합니다. 미설정 시 `MARS_SECRET_KEY`에서 파생합니다.
- `--host 0.0.0.0` 은 같은 네트워크의 다른 기기(팀원 노트북 등)가 Worker로 접속할 수 있게 합니다.
  로컬에서만 쓸 거면 생략해도 됩니다.

#### 여러 기기로 분산 실행하기 (데모 구성)

1. 서버 기기에서 위처럼 `--host 0.0.0.0` 으로 서버를 켜고, 서버 기기의 LAN IP를 확인합니다
   (`ipconfig getifaddr en0` → 예: `192.0.2.10`).
   `192.0.2.10`은 문서용 예시이므로 실제 서버의 LAN IP로 바꿔 사용합니다.
2. 다른 기기(팀원 노트북)에서 Worker를 설치하고 서버 IP로 등록합니다:
   `python -m agent register --server http://192.0.2.10:8000`
3. 각 기기에서 `python -m agent run` 을 켜두면, 워크플로우의 병렬 단계가
   서로 다른 기기에 분배되어 동시에 실행됩니다.
4. 개발 CORS는 localhost만 기본 허용합니다. 다른 Origin은 `MARS_ALLOWED_ORIGINS`에 명시합니다.

### 2. Worker Agent (작업을 실행할 기기마다)

작업을 실행할 기기마다 Worker를 설치해 서버에 등록한다. 서버로 연결을 여는 pull 방식이라 포트를 열 필요가 없다.

**등록 순서**

1. Ollama를 설치하고 모델을 하나 받는다. 예: `ollama pull qwen3:4b`
2. 운영체제에 맞게 Worker UI를 실행하고 http://127.0.0.1:8765 를 연다(아래 참고).
3. Server address `https://marsflowlab.com/api`, Worker name, 웹 계정(https://marsflowlab.com 에서 가입)을 입력하고 **Connect worker**를 누른다.
4. Status 화면에서 **시작**을 누른다. 웹 사이드바의 워커가 온라인으로 바뀌면 끝이다.

**Windows**: `start-worker.cmd`를 더블클릭한다. Python 3.11 이상과 [Windows용 Ollama](https://ollama.com/download/windows)가 없으면 설치 방법을 안내한다. 등록 정보는 `%LOCALAPPDATA%\MarsFlowLab\Worker`에 저장된다.

**macOS**: Docker는 Apple GPU를 쓰지 못하므로 Python으로 직접 실행한다. [맥용 Ollama 앱](https://ollama.com/download/mac)을 먼저 설치한다.

```bash
cd worker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m agent ui
```

**Linux**: `./start-worker.sh`로 Worker UI와 Ollama를 Docker로 실행한다(GPU 자동 감지, 실패 시 CPU). Docker 없이 쓰려면 macOS와 같은 명령으로 실행한다.

UI 없이 등록하려면 `python -m agent register --server https://marsflowlab.com/api`로 한 번 등록한 뒤 `python -m agent run`을 켜 둔다.

- Apple Silicon 맥에서 `Bad CPU type`이 나오면 arm64 Python(python.org 설치본 또는 `/opt/homebrew`)을 쓴다.
- 업로드 파일은 서버를 거쳐 전달되고, 공유 디렉터리 파일은 해당 기기 안에서만 읽힌다.
- `agent_config.json`에는 Worker 인증 키가 들어 있으므로 Git에 올리거나 공유하지 않는다.

### 3. 웹 프론트엔드

```bash
cd web
npm install
npm run dev
```

- http://localhost:5173 접속 → 회원가입 → 로그인
- 개발 서버는 기본적으로 `/api` 요청을 `http://localhost:8000`으로 프록시합니다. 필요한 경우 `VITE_API_URL`로 덮어쓸 수 있습니다.

## 테스트

서버와 워커는 pytest로 테스트한다. CI(GitHub Actions)에서 매 PR마다
서버/워커 테스트와 웹 타입체크·빌드가 실행된다.
각 스위트가 구체적으로 무엇을 검증하는지는 [docs/테스트_가이드.md](docs/테스트_가이드.md) 참고.

```bash
# 서버 (DAG 검증, 오케스트레이터, 생성기, 인증/JWT, API 통합)
cd server
pip install -r requirements-dev.txt
pytest

# 워커 (폴더 화이트리스트 sandbox, 실행기)
cd worker
pip install -r requirements-dev.txt
pytest
```

## 핵심 흐름 (요구사항 추적)

1. 회원가입/로그인 (UC-101, UC-102) — JWT 인증
2. 기기 등록 + 폴더 접근권한 설정 (UC-103) — Worker CLI에서 등록, 웹에서 상태 확인 (UC-104)
3. 서비스 생성 (UC-201) — 자연어 프롬프트 → 에이전트 구성 + DAG 자동 생성 → React Flow 시각화
4. 서비스 수정 (UC-202) — 노드 추가/삭제/연결 변경, 에이전트별 프롬프트·모델·폴더 설정, DAG 유효성 검증
5. 실행 프롬프트 입력 → 실행 (UC-203, UC-204) — 등록 기기에 작업 분배, 진행률 표시, 기기 단절 시 재할당
6. 결과 확인 / 이력 조회 (UC-205, UC-206)

## 아키텍처 메모

- **작업 분배**: 서버가 DAG 위상순서에 따라 실행 가능한 작업을 큐에 올리고, Worker가 주기적으로
  폴링하여 가져간다(Pull 방식 — NAT 뒤의 개인 기기에서도 동작).
- **장애 대응**: 하트비트가 일정 시간 끊긴 기기에 할당된 작업은 자동으로 대기 상태로 되돌려
  다른 기기가 가져가게 한다 (UC-204 e203).
- **권한 경계**: 폴더 화이트리스트는 Worker 쪽에서 강제한다. 서버가 어떤 경로를 지시하더라도
  Worker의 sandbox 검사를 통과하지 못하면 거부된다.
