# Linux 서버 실행 가이드

이 문서는 Ubuntu 등 Linux 서버 한 대에서 M.A.R.S 서버와 웹 UI를 Docker Compose로 실행하고, 여러 Worker가 같은 공유 디렉터리를 읽도록 구성하는 방법을 설명한다. 현재 CORS 설정은 사설 네트워크 주소만 허용하므로, 이 구성은 VPN 또는 사내/LAN 환경을 전제로 한다.

## 1. 준비

Linux 서버에 Docker Engine, Docker Compose plugin, Git을 설치한다. 설치가 끝나면 다음 명령이 동작해야 한다.

```bash
docker --version
docker compose version
git --version
```

방화벽을 사용한다면 웹 UI와 API 포트를 허용한다. 외부 인터넷에 그대로 공개하지 말고 VPN, 방화벽 규칙 또는 리버스 프록시(TLS) 뒤에 둔다.

```bash
sudo ufw allow 5173/tcp
sudo ufw allow 8000/tcp
```

## 2. 서버와 웹 UI 실행

```bash
git clone <REPOSITORY_URL> mars
cd mars
cp .env.example .env
```

`.env`를 편집한다. `MARS_SECRET_KEY`는 예시 값 그대로 두지 말고, 안전한 임의 문자열로 교체한다.

```bash
openssl rand -hex 32
```

```dotenv
MARS_SECRET_KEY=<openssl로 생성한 값>
MARS_SERVER_PORT=8000
MARS_WEB_PORT=5173
MARS_DEFAULT_MODEL=gemma3:4b
MARS_HEARTBEAT_TIMEOUT=30
```

웹 UI는 같은 origin의 `/api` 경로를 통해 서버에 연결하므로 별도의 브라우저 API 주소 설정은 필요하지 않다.

서버 호스트에서 Ollama를 실행한다면 `OLLAMA_URL=http://host.docker.internal:11434`를 유지한다. Ollama가 다른 서버에 있다면 그 서버가 접근 가능한 주소로 바꾼다. Ollama가 없어도 서비스 생성은 규칙 기반 폴백으로 동작하지만, Worker가 작업을 처리하려면 각 Worker에서 Ollama와 모델이 준비되어 있어야 한다.

컨테이너를 빌드하고 실행한다.

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/
```

`192.0.2.10`은 문서 전용 예시 주소다. 아래 웹·Worker 주소는 실제 서버의 LAN IP 또는 도메인으로 바꿔 사용한다.

정상이라면 브라우저에서 `http://192.0.2.10:5173`을 열어 회원가입을 한다. 로그 확인과 중지는 다음 명령을 사용한다.

```bash
docker compose logs -f server web
docker compose down
```

SQLite DB는 Docker volume `mars-data`에 보존된다. 컨테이너를 다시 만들더라도 `docker compose down -v`를 실행하지 않는 한 DB는 삭제되지 않는다.

## 3. 공유 디렉터리 준비

이 프로젝트에서 하나의 디렉터리를 여러 Worker가 읽을 때 각 Worker의 로컬 경로는 달라도 된다. 기기 관리에서 같은 디렉터리 별명을 Worker별로 등록하고, 각 Worker의 실제 경로를 입력한다.

예를 들어 서버 Worker용 실제 디렉터리를 `/srv/mars/shared`로 만든다.

```bash
sudo mkdir -p /srv/mars/shared/project
sudo chown -R "$USER":"$USER" /srv/mars/shared
```

`.env`에 다음을 설정한다.

```dotenv
MARS_WORKER_SHARED_DIR=/srv/mars/shared
```

다른 Linux Worker에서는 NFS/SMB 등의 방법으로 같은 데이터를 각 호스트에 마운트한다. 컨테이너 내부 대상 경로도 Worker별로 달라도 된다.

```text
Worker A: /mnt/team-share  ->  /shared
Worker B: /data/team-share ->  /workspace/team-share
```

웹에서 같은 별명을 Worker마다 한 번씩 등록하고, 해당 Worker 컨테이너 기준 경로를 입력한다. 예: Worker A는 `/shared/project`, Worker B는 `/workspace/team-share/project`. 작업은 할당된 Worker에 맞는 경로를 받는다.

## 4. 서버에 Worker 하나 추가하기

서버 머신도 작업을 실행하게 하려면 Worker 프로필을 활성화한다. 먼저 설정 파일을 만든다.

```bash
mkdir -p worker/shared
touch worker/agent_config.json
docker compose --profile worker run --rm worker python -m agent register --server http://server:8000
```

명령이 계정, 비밀번호, Worker 이름을 묻는다. 웹 UI에서 만든 계정으로 등록한다. 등록이 끝난 뒤 상시 Worker를 실행한다.

```bash
docker compose --profile worker up -d worker
docker compose logs -f worker
```

`agent_config.json`에는 Worker 인증 키가 들어 있으므로 Git에 올리거나 다른 사람에게 전달하지 않는다.

## 5. 다른 Linux 머신에 Worker 추가하기

다른 머신에는 저장소의 `worker/` 디렉터리만 복사하거나 저장소를 clone한다. 해당 머신에서 공유 저장소를 마운트하고, Docker로 실행하는 경우 Compose의 Worker volume이 그 경로를 `/shared`로 연결하도록 설정한다.

호스트 Python으로 실행할 때도 공유 경로를 `/shared`로 마운트한 뒤 아래처럼 등록·실행한다.

```bash
cd worker
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m agent register --server http://192.0.2.10:8000
python -m agent run
```

Worker는 서버로 연결을 여는 pull 방식이므로, Worker 쪽에서 8000 포트를 열 필요는 없다. Worker가 서버의 `8000/tcp`에 연결할 수 있고, 로컬 Ollama가 준비되어 있으면 된다.

## 6. 운영 점검

```bash
# 컨테이너 상태
docker compose ps

# API 상태
curl http://localhost:8000/

# 최근 로그
docker compose logs --tail=100 server web worker

# 이미지 갱신 후 재배포
git pull
docker compose up -d --build
```

Worker를 에이전트 블록에 직접 지정했다면 그 Worker가 온라인이어야 해당 작업이 시작된다. 자동 배정인 에이전트는 같은 사용자의 온라인 Worker 중 하나가 가져간다.
