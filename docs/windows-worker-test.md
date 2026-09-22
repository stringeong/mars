# Windows 네이티브 Worker 실기기 점검표

Windows 10/11 x64의 일반 사용자 계정에서 수행한다. BIOS 가상화, WSL 2,
Docker Desktop은 네이티브 테스트의 선행 조건이 아니다.

## 깨끗한 PC

1. `start-worker.cmd detect`가 Python과 Ollama의 설치 상태를 한글로 표시한다.
2. Python이 없으면 공식 다운로드 페이지가 열리고 안전하게 종료된다.
3. Ollama가 없으면 공식 다운로드 페이지가 열리고 안전하게 종료된다.
4. 두 프로그램 설치 후 `start-worker.cmd`가 `.venv`를 만들고 UI를 연다.
5. `https://marsflowlab.com/api`가 등록 화면의 기본 서버 주소로 표시된다.
6. BIOS/Hyper-V/WSL/Docker 설정을 요구하지 않는다.

## 등록과 실행

1. 계정 로그인 후 `%LOCALAPPDATA%\MarsFlowLab\Worker\agent_config.json`이 생성된다.
2. Worker 시작 버튼을 누르면 Status가 실행 중으로 전환된다.
3. Windows Ollama의 모델 목록과 다운로드 진행률이 표시된다.
4. 허용한 `C:\` 또는 `D:\` 폴더 안의 파일만 읽을 수 있다.
5. Worker UI와 Ollama가 각각 `127.0.0.1:8765`, `127.0.0.1:11434`에만 노출된다.

## 프로세스 관리

1. `start-worker.cmd status`가 UI와 Ollama 상태를 정확히 표시한다.
2. 이미 실행 중일 때 다시 시작해도 중복 UI 프로세스가 생기지 않는다.
3. `start-worker.cmd stop` 후 UI와 자식 Worker Python 프로세스가 모두 종료된다.
4. 다시 실행하면 기존 등록 정보와 공유 폴더 설정이 유지된다.
5. 기존 `worker\agent_config.json`이 있으면 LocalAppData로 한 번만 이전된다.

## Docker 회귀

1. `start-worker.cmd docker`가 기존 GPU 자동 감지 Compose 구성을 실행한다.
2. `cpu`, `nvidia` 명시 모드가 계속 동작한다.
3. Docker가 없어도 `auto`, `native`, `detect`, `status`가 Docker 설치를 요구하지 않는다.

## 오류 상황

- `8765` 포트가 사용 중일 때 로그 경로를 포함한 오류가 표시된다.
- `marsflowlab.com:443` 연결 실패 시 VPN/방화벽 진단 문구가 표시된다.
- 공백 또는 한글이 포함된 Windows 사용자 경로에서 설치와 실행이 성공한다.
- `%LOCALAPPDATA%\MarsFlowLab\Worker\logs`에서 UI 표준 출력과 오류 로그를 확인할 수 있다.
