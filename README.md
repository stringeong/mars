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

### 1. 중앙 서버

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 문서: http://localhost:8000/docs
- DB는 `server/mars.db` (SQLite) 에 자동 생성됩니다.
- 프롬프트→워크플로우 생성에 Ollama를 사용합니다. Ollama가 없으면 규칙 기반 폴백으로 동작합니다.
  - `OLLAMA_URL` (기본 `http://localhost:11434`), `MARS_DEFAULT_MODEL` (기본 `gemma3:4b`) 환경변수로 변경 가능.
- `--host 0.0.0.0` 은 같은 네트워크의 다른 기기(팀원 노트북 등)가 Worker로 접속할 수 있게 합니다.
  로컬에서만 쓸 거면 생략해도 됩니다.

#### 여러 기기로 분산 실행하기 (데모 구성)

1. 서버 기기에서 위처럼 `--host 0.0.0.0` 으로 서버를 켜고, 서버 기기의 LAN IP를 확인합니다
   (`ipconfig getifaddr en0` → 예: `192.168.0.10`).
2. 다른 기기(팀원 노트북)에서 Worker를 설치하고 서버 IP로 등록합니다:
   `python -m agent register --server http://192.168.0.10:8000`
3. 각 기기에서 `python -m agent run` 을 켜두면, 워크플로우의 병렬 단계가
   서로 다른 기기에 분배되어 동시에 실행됩니다.
4. 같은 공유기(사설 IP 대역) 안에서만 동작하도록 CORS가 설정되어 있습니다.

### 2. Worker Agent (작업을 실행할 기기마다)

```bash
cd worker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 최초 1회: 기기 등록 (서버 주소, 계정, 기기명, 허용 폴더 지정)
python -m agent register --server http://localhost:8000

# 상시 실행: 하트비트 전송 + 작업 폴링·실행
python -m agent run
```

- 등록 정보는 `worker/agent_config.json` 에 저장됩니다.
- 에이전트는 등록 시 지정한 **허용 폴더 밖의 파일에 절대 접근하지 않습니다** (최소 권한 원칙).

### 3. 웹 프론트엔드

```bash
cd web
npm install
npm run dev
```

- http://localhost:5173 접속 → 회원가입 → 로그인
- 서버 주소는 `web/.env` 의 `VITE_API_URL` (기본 `http://localhost:8000`).

## 테스트

서버와 워커는 pytest로 테스트한다. CI(GitHub Actions)에서 매 PR마다
서버/워커 테스트와 웹 타입체크·빌드가 실행된다.

```bash
# 서버 (DAG 검증, 오케스트레이터, 생성기 파싱)
cd server
pip install -r requirements-dev.txt
pytest

# 워커 (폴더 화이트리스트 sandbox)
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
