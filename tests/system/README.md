# 시스템 테스트 재현

D07 시스템 테스트 결과서의 65개 케이스를 다시 돌리는 스크립트입니다.

수행 당시(2026-11-05, release0.0.3) 쓴 원본 스크립트는 보존되지 않았습니다. 이 스크립트들은 결과서의 케이스 정의(입력·기대 출력)와 5.2절의 대역 Ollama 설명을 기준으로 release0.0.5에 맞춰 다시 작성한 것입니다.

| 파일 | 역할 |
|---|---|
| `start_env.sh` | 임시 디렉터리에 빈 DB, Worker 2대 설정, 공유 폴더 `shareA`(`card_october.csv`, 폴더 밖을 가리키는 `leak.txt` 링크)를 새로 만듭니다. 그다음 대역 Ollama, 서버, cloud-worker, Worker UI 2개, 웹을 띄웁니다. |
| `fake_ollama.py` | Ollama API 대역 서버입니다. 표준 라이브러리만 씁니다. |
| `systest.py` | API 케이스를 순서대로 수행하고 `results.json`에 기록합니다. 화면 케이스는 `ui_checks.js`를 불러서 합칩니다. |
| `ui_checks.js` | Playwright로 화면 케이스 6개를 수행하고 `screenshots/`에 캡처합니다. |
| `fixtures/card_october.csv` | 가상 카드 내역(95자)입니다. 실제 거래 정보가 아닙니다. |

## 준비

저장소 README대로 `server/.venv`, `worker/.venv`, `web/node_modules`를 만들어 둡니다. 화면 케이스까지 돌리려면 아래 두 명령을 한 번 실행합니다.

```bash
cd tests/system && npm install && npx playwright install chromium
```

## 실행

```bash
tests/system/start_env.sh
source "$(cat tests/system/.last_run)/env.sh"
server/.venv/bin/python tests/system/systest.py   # 화면 케이스를 빼려면 --skip-ui
tests/system/start_env.sh stop
```

- 전체 수행에는 약 3~5분이 걸립니다. 단절·재할당 케이스가 30초 하트비트 만료를 기다립니다.
- 기본 포트는 서버 8000, 웹 5173, Worker 8765·8766, Ollama 11434입니다. 이미 쓰는 포트가 있으면 환경변수로 바꿉니다.

  ```bash
  SERVER_PORT=18000 WEB_PORT=15173 WORKER_A_PORT=18765 WORKER_B_PORT=18766 OLLAMA_PORT=21434 tests/system/start_env.sh
  ```

- 다른 Python 가상환경을 쓰면 `SERVER_PYTHON`, `WORKER_PYTHON`으로 지정합니다.
- 실행 로그와 대역 Ollama가 받은 요청(`ollama_requests.jsonl`)은 환경 디렉터리에 남습니다. 경로는 `tests/system/.last_run`에 있습니다.

## 결과서와 다른 점

- **STC-T05-004, STC-T12-006은 미수행입니다.** 툴 설치는 테스트 환경의 Python을 바꾸고, 외부 LLM 실제 호출에는 유효한 API 키가 필요합니다.
- **STC-T12-001, STC-T12-004는 실제 외부 서비스를 부릅니다.** 잘못된 키(`sk-test-invalid-1234`)를 OpenAI에 보내 확인합니다. 네트워크가 없으면 오류 메시지만 달라집니다.
- **STC-T13-003:** 이력이 남은 워크플로우는 `with_history=true`로 한 번 더 확인해야 지워집니다. release0.0.3 이후에 바뀐 동작에 맞췄습니다.
- **STC-T09-008(간트 보기):** STC-T08-001 실행(agent1은 worker-A, agent2는 worker-B)으로 확인합니다.
- **STC-T10-003(Markdown 렌더링):** 역할에 'Markdown'이 들어간 리포트 블록은 대역 Ollama가 입력 뒤에 요약 표를 붙여 돌려줍니다. 결과 화면에 HTML 표와 제목이 있고, `##`·`|---|` 같은 기호가 원문으로 보이지 않으면 통과입니다.
- **대역 Ollama의 파일 선별 응답:** Worker가 공유 폴더에서 쓸 파일을 고를 때 보내는 요청에는 미리보기가 붙은(읽을 수 있는) 파일만 고르도록 응답합니다. 결과서 5.2절에는 이 응답이 적혀 있지 않습니다.
