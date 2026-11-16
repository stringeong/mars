"""M.A.R.S. 시스템 테스트 실행기 (D07 시스템 테스트 결과서 3장·6.1절의 65개 케이스).

start_env.sh로 띄운 환경에 HTTP API로 사용자 시나리오를 수행하고 results.json에 기록한다.
화면 케이스 6개는 ui_checks.js(Playwright)로 수행해 결과를 합친다.

    tests/system/start_env.sh
    source <환경 디렉터리>/env.sh
    server/.venv/bin/python tests/system/systest.py [--skip-ui]

결과서의 원본 스크립트는 보존되지 않아 결과서의 케이스 정의(입력·기대 출력)를 기준으로 다시 작성했다.
전체 수행은 약 4~5분이며 단절·재할당 케이스가 30초 하트비트 만료를 기다린다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"환경변수 {name}가 없습니다. start_env.sh가 만든 env.sh를 먼저 source 하세요.")
    return value


SERVER_URL = env("SERVER_URL")
WEB_URL = env("WEB_URL")
WORKER_URL = {"A": env("WORKER_A_URL"), "B": env("WORKER_B_URL")}
RUN_DIR = Path(env("SYSTEST_RUN_DIR"))
SHARE_A = env("SHARE_A")
DB_PATH = env("MARS_DATABASE_URL").removeprefix("sqlite:///")
OLLAMA_LOG = RUN_DIR / "ollama_requests.jsonl"
RESULTS_PATH = Path(os.getenv("SYSTEST_RESULTS", HERE / "results.json"))
STATE_PATH = RUN_DIR / "ui_state.json"

PASSWORD = "test1234"
RUN_PROMPT = "10월 카드 사용 내역을 분석해줘"
GEN_PROMPT = "카드 사용 내역으로 지출을 분류하고 이상 거래를 찾아 월간 리포트를 써줘"

api = httpx.Client(base_url=SERVER_URL, timeout=30)
ctx: dict = {}  # 케이스끼리 넘겨주는 값(토큰, id 등)
results: dict[str, dict] = {}

# 결과서 표 22의 케이스 순서와 설명. (id, 설명, 입력, 예상결과)
CASES = [
    ("STC-T01-001", "유효한 정보로 회원가입", "email=tester1@example.com, username=tester1, password=test1234", "201, 계정 생성(username=tester1)"),
    ("STC-T01-002", "가입 완료 후 즉시 로그인 가능", "가입한 tester1/test1234로 로그인", "200, access_token 발급"),
    ("STC-T01-003", "아이디 중복 가입 거부", "username=tester1(기존), email=other@example.com", "409, 중복 메시지"),
    ("STC-T01-004", "이메일 중복 가입 거부", "email=tester1@example.com(기존), username=tester9", "409, 중복 메시지"),
    ("STC-T01-005", "형식 오류 입력 거부", "email=abc, username=t, password=12", "422, 이메일·아이디·비밀번호 형식 오류"),
    ("STC-T02-001", "올바른 계정으로 로그인", "tester1 / test1234", "200, bearer 토큰"),
    ("STC-T02-002", "JWT로 보호 API 접근, 토큰 없으면 거부", "Authorization: Bearer <토큰> / 헤더 없음", "200 / 401"),
    ("STC-T02-003", "잘못된 비밀번호 로그인 실패", "tester1 / wrongpass", "401, 실패 메시지"),
    ("STC-T03-001", "Worker UI에서 기기 등록 시 사양 자동 수집", "Worker UI /api/register: tester1, 기기 이름 worker-A·worker-B", "등록 성공, specs에 os·cpu_count·ram_gb 포함"),
    ("STC-T03-002", "같은 이름 재등록 시 기존 기기로 재연결", "POST /devices name=worker-A(기존)", "200, 기존 device id 유지·새 인증키 발급"),
    ("STC-T03-003", "잘못된 계정으로 기기 등록 실패 안내", "Worker UI /api/register password=badpass", "오류 응답과 원인(아이디·비밀번호 불일치) 표시"),
    ("STC-T03-004", "기기 전용 인증키 발급·검증·해시 저장", "Worker 설정 파일의 api_key / 임의 키 48자", "200 / 401, DB에는 평문 키 없음"),
    ("STC-T04-001", "등록 기기 목록 조회", "GET /devices (tester1)", "worker-A, worker-B 2건"),
    ("STC-T04-002", "Worker 실행 후 온라인·사양·사용률 표시", "Worker UI /api/worker/start 후 GET /devices", "두 기기 online=true, cpu_percent·models 표시"),
    ("STC-T04-003", "기기 CPU 상한 변경", "PATCH /devices/{worker-B} max_cpu_percent=90", "200, 상한 90 반영"),
    ("STC-T04-004", "Worker 인증키로 이름 변경·등록 해제", "temp-device 등록 → 이름 worker-A로 변경 → temp-renamed로 변경 → DELETE /worker/device", "409 / 200 / 204, 목록에서 제거"),
    ("STC-T05-001", "설치 모델 조회와 서버 동기화", "Worker UI GET /api/models, 서버 GET /devices/{id}/models", "gemma3:4b가 두 곳에 표시"),
    ("STC-T05-002", "LLM 모델 다운로드 진행률 표시", "Worker UI POST /api/models/pull name=llama3.2:1b", "202, 작업이 완료 상태·100%"),
    ("STC-T05-003", "LLM 모델 삭제", "Worker UI POST /api/models/delete name=llama3.2:1b", "200 ok"),
    ("STC-T05-004", "툴 설치·삭제·재설치", "Worker UI POST /api/tools/install id=<승인된 툴>", "설치 완료 표시, 실패 시 오류 메시지"),
    ("STC-T05-005", "공유 폴더 지정과 별칭 중복 거부", "POST /devices/{worker-A}/directories alias=카드내역, path=shareA / 같은 별칭 재등록", "201 / 409"),
    ("STC-T05-006", "Worker 비활성화(중지)·활성화(시작)", "Worker UI /api/worker/stop → 45초 대기 → /api/worker/start", "offline 전환 후 다시 online"),
    ("STC-T05-007", "공유 폴더 밖을 가리키는 심볼릭 링크 차단", "shareA/leak.txt → outside/secret.txt(SECRET_OUTSIDE)", "모델 입력에 SECRET_OUTSIDE 없음, leak.txt는 파일 목록에서 제외"),
    ("STC-T06-001", "자연어로 워크플로우 생성(서버 로컬 LLM)", f"prompt='{GEN_PROMPT}'", "201, 에이전트 3개 DAG, source=llm"),
    ("STC-T06-002", "너무 짧은 생성 프롬프트 거부", "prompt='abc'(5자 미만)", "422"),
    ("STC-T06-003", "사용자 Worker의 Ollama로 워크플로우 생성", "POST /services/generation-jobs device=worker-A, model=gemma3:4b", "202 → Worker가 가져가 done, 워크플로우 저장"),
    ("STC-T06-004", "생성 실패 단계 안내와 기본 워크플로우 선택", "LLM이 JSON이 아닌 응답을 2회 반환", "502(실패 단계 표시) → use_fallback 201"),
    ("STC-T06-005", "생성 워크플로우를 노드·연결선으로 표시", "편집기 /services/{id} 열기", "에이전트 블록 3개와 연결선 2개 표시"),
    ("STC-T07-001", "에이전트 블록 추가·삭제 저장", "agent4(검토) 추가 후 삭제", "200 / 200, 블록 수 4 → 3"),
    ("STC-T07-002", "연결 변경 시 실행 단계 재계산", "edges: agent1→agent2→agent3(직렬)", "단계 3개로 갱신"),
    ("STC-T07-003", "구성 검사: 파일 필요 블록 누락 오류와 단계·최종 블록 계산", "생성된 3블록 그래프(agent1·2는 카드 내역 파일 필요, 아직 미연결) + 실행 프롬프트", "valid=false, agent1·2 missing_file 오류, 2단계, 최종 블록 agent3"),
    ("STC-T07-004", "순환 구성 저장 차단과 사유 안내", "edge agent3→agent1 추가", "저장 422, 검사 결과 cycle 오류"),
    ("STC-T07-005", "에이전트별 역할 프롬프트 저장", "agent1.role_prompt='거래를 식비·교통·쇼핑으로 분류한다.'", "200, 값 반영"),
    ("STC-T07-006", "에이전트별 폴더 범위 지정과 타인 폴더 차단", "tester2가 tester1의 폴더(카드내역) 지정 / tester1이 agent1에 폴더·worker-A, agent2에 worker-B 지정", "거부(4xx) / 200, 이후 구성 검사 valid=true"),
    ("STC-T08-001", "실행 프롬프트 입력 후 실행 요청", f"run_prompt='{RUN_PROMPT}'", "201, status=running"),
    ("STC-T08-002", "입력 없는 실행 요청 거부", "시작 블록에 파일·폴더 없음 + 실행 프롬프트 빈 값", "422, no_input 오류"),
    ("STC-T09-001", "Worker 폴링으로 작업 수신(60초 이내 분배)", "STC-T08-001 실행", "60초 안에 작업 시작"),
    ("STC-T09-002", "DAG 의존 순서에 따른 분배", "agent1·2 병렬 → agent3", "agent1(worker-A)·agent2(worker-B) 병렬, agent3은 둘 다 끝난 뒤 시작, status=completed"),
    ("STC-T09-003", "Worker 로컬 LLM 실행·결과만 제출", "agent1에 공유 폴더(카드내역) 지정", "로컬 모델이 폴더 파일을 읽어 결과 제출, 외부 LLM 호출 0건"),
    ("STC-T09-004", "진행률과 작업별 상태·배정 기기 표시", "GET /executions/{id}", "progress=100, 모든 작업 done과 기기 이름"),
    ("STC-T09-005", "실행 중 서비스 중단", "SLOW 블록 실행 중 POST /executions/{id}/cancel", "status=cancelled, 남은 작업 중단 처리"),
    ("STC-T09-006", "작업 수행 중 모델 오류 시 실행 실패 안내", "블록 역할에 FAIL_TASK(대역 Ollama가 HTTP 500 반환)", "status=failed, 오류 사유 표시"),
    ("STC-T09-007", "Worker 단절 시 작업 재할당", "worker-B가 SLOW 작업 실행 중 중지, worker-A 시작", "30초 하트비트 만료 후 worker-A가 재실행해 completed"),
    ("STC-T09-008", "실행 타임라인 간트 보기", "실행 결과에서 '간트 보기' 클릭", "Worker별 레인 2개 표시"),
    ("STC-T09-009", "공유 폴더 파일 청크 표기", "card_october.csv(95자, 청크 1개)", "'(part 1/1)'처럼 정수 표기"),
    ("STC-T10-001", "실행 완료 상태·완료 시각", "STC-T08-001 실행", "status=completed, finished_at 기록"),
    ("STC-T10-002", "최종 블록 결과를 실행 결과로 통합", "STC-T08-001 실행", "result = 최종 블록 출력"),
    ("STC-T10-003", "실행 결과를 Markdown으로 렌더링", "실행 결과 /executions/{id} 열기", "Markdown 표가 HTML 표로 렌더링"),
    ("STC-T11-001", "실행 이력 목록 조회", "GET /executions", "200, 앞 실행 포함"),
    ("STC-T11-002", "특정 실행 결과 조회", "GET /executions/{id}", "200, 결과·작업 목록"),
    ("STC-T11-003", "조회할 수 없는 결과의 실패 메시지", "id=99999 / tester2가 tester1 실행 조회", "404, 조회 실패 메시지"),
    ("STC-T12-001", "외부 LLM API 키 저장·마스킹·검증 실패 표시", "openai api_key=sk-test-invalid-1234", "200·'••••••1234', DB 암호화 저장, 잘못된 키는 400·status=error"),
    ("STC-T12-002", "블록별 실행 위치를 외부 LLM으로 지정", "agent3: executor=cloud, provider=openai, model=gpt-5-mini", "200, 값 저장"),
    ("STC-T12-003", "외부 전송 항목 확인·동의 후에만 실행", "동의 토큰 없이 실행 / preview 후 토큰 사용 / 프롬프트 변경 / 토큰 재사용", "428 / 201 / 428 / 428"),
    ("STC-T12-004", "유효하지 않은 키로 외부 LLM 블록 실행 시 실패 안내", "STC-T12-003의 동의 후 실행(키 sk-test-invalid-1234)", "agent3 실패, '클라우드 LLM 호출 실패' 메시지"),
    ("STC-T12-005", "제공자별 토큰 사용량 조회", "GET /settings/llm-usage?days=30", "200, 제공자별 집계 목록(성공 호출이 없어 빈 목록)"),
    ("STC-T12-006", "유효한 키로 외부 LLM 실제 호출과 토큰 기록", "OpenAI·Anthropic·Gemini 유효 키", "블록 done, llm_usage에 입력·출력 토큰 기록"),
    ("STC-T13-001", "워크플로우 복제와 같은 입력으로 다시 실행", "POST /services/{id}/duplicate, 같은 run_prompt로 실행", "201 / 201"),
    ("STC-T13-002", "워크플로우 이름 변경과 폴더 정리", "name='카드 리포트 사본', 폴더 '가계부' 생성 후 이동", "200 / 201 / folder_id 반영"),
    ("STC-T13-003", "실행 이력·워크플로우 삭제(실행 중 차단)", "실행 중 이력 삭제 → 완료 후 삭제 → 중단된 이력 삭제 → 워크플로우 삭제", "409 / 204 / 204 / 204"),
    ("STC-T14-001", "커뮤니티 공유(개인 참조 제거)와 가져오기", "tester1이 공유 → 비로그인 목록 조회 → tester2가 가져오기", "200, worker_id·폴더·파일 없음, 201, import_count=1"),
    ("STC-T14-002", "로그인 없이 제품 소개 확인", "비로그인 상태로 / 접속", "제품 소개 문구 표시"),
    ("STC-T14-003", "Worker 다운로드 안내", "/download 접속", "OS별 설치 안내와 서버 주소(/api) 표시"),
    ("STC-T14-004", "활용 사례 검색", "/examples에서 '회의록' 검색", "검색 후 사례 수 감소, 회의록 사례 표시"),
    ("STC-NF-001", "일반 요청 응답 시간 3초 이내", "GET /devices 100회", "최대 3초 미만"),
]
UI_CASES = {"STC-T06-005", "STC-T09-008", "STC-T10-003", "STC-T14-002", "STC-T14-003", "STC-T14-004"}
SKIPPED = {
    "STC-T05-004": "미수행: pip 패키지를 실제로 설치·삭제해야 하며 테스트 환경의 Python을 변경함",
    "STC-T12-006": "미수행: 유효한 외부 LLM API 키가 테스트 환경에 없음",
}


# ---------------------------------------------------------------- 도우미

class CaseFailed(Exception):
    pass


def check(condition: bool, actual: str) -> str:
    if not condition:
        raise CaseFailed(actual)
    return actual


def record(case_id: str, ok: bool, actual: str) -> None:
    results[case_id] = {"result": "P" if ok else "F", "actual": actual}
    mark = "P" if ok else "F"
    print(f"[{mark}] {case_id} {actual}", flush=True)


def case(case_id: str):
    """케이스 함수 데코레이터. 함수는 수행결과 문자열을 돌려주고, 기대와 다르면 CaseFailed를 던진다."""
    def wrap(func):
        def run():
            try:
                record(case_id, True, func())
            except CaseFailed as exc:
                record(case_id, False, str(exc))
            except Exception as exc:  # 시험 대상 오류도 실패로 기록하고 다음 케이스로 넘어간다
                record(case_id, False, f"예외: {type(exc).__name__}: {exc}")
                traceback.print_exc()
        run.case_id = case_id
        return run
    return wrap


def auth(user: str = "tester1") -> dict:
    return {"Authorization": f"Bearer {ctx['token'][user]}"}


def login(username: str, password: str) -> httpx.Response:
    return api.post("/auth/login", data={"username": username, "password": password})


def worker_ui(name: str, method: str, path: str, **kw) -> httpx.Response:
    return httpx.request(method, WORKER_URL[name] + path, timeout=60, **kw)


def devices() -> list[dict]:
    return api.get("/devices", headers=auth()).json()


def device(name: str) -> dict:
    return next(d for d in devices() if d["name"] == f"worker-{name}")


def wait_until(predicate, timeout: float, interval: float = 1.0, what: str = "조건"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise CaseFailed(f"{timeout:.0f}초 안에 {what}이(가) 충족되지 않음")


def execution(execution_id: int, user: str = "tester1") -> dict:
    return api.get(f"/executions/{execution_id}", headers=auth(user)).json()


def wait_execution(execution_id: int, timeout: float = 120) -> dict:
    def done():
        data = execution(execution_id)
        return data if data["status"] not in ("pending", "running") else None
    return wait_until(done, timeout, what=f"실행 #{execution_id} 종료")


def start_run(service_id: int, run_prompt: str = RUN_PROMPT, **body) -> httpx.Response:
    return api.post(f"/services/{service_id}/executions", json={"run_prompt": run_prompt, **body}, headers=auth())


def service(service_id: int) -> dict:
    return api.get(f"/services/{service_id}", headers=auth()).json()


def save_graph(service_id: int, graph: dict, user: str = "tester1") -> httpx.Response:
    return api.put(f"/services/{service_id}", json={"graph": graph}, headers=auth(user))


def node(graph: dict, node_id: str) -> dict:
    return next(n for n in graph["nodes"] if n["id"] == node_id)


def single_block_service(name: str, role_prompt: str, worker: str | None = None) -> int:
    """역할 프롬프트로 대역 Ollama 동작(SLOW·FAIL_TASK)을 고르는 1블록 워크플로우."""
    created = api.post(f"/services/{ctx['service']}/duplicate", headers=auth()).json()
    graph = {
        "nodes": [{
            "id": "solo", "type": "agent", "name": name, "role_prompt": role_prompt,
            "final": True, "final_manual": True, "needs_file": False, "needs_file_manual": True,
            "worker_id": device(worker)["id"] if worker else None,
        }],
        "edges": [], "input_slots": [],
    }
    check(save_graph(created["id"], graph).status_code == 200, f"{name} 워크플로우 저장 실패")
    return created["id"]


def db_contains(value: str) -> int:
    """DB 모든 텍스트 칸에서 value가 그대로 들어 있는 행 수."""
    con = sqlite3.connect(DB_PATH)
    try:
        hits = 0
        for (table,) in con.execute("select name from sqlite_master where type='table'"):
            columns = [row[1] for row in con.execute(f'pragma table_info("{table}")')]
            for column in columns:
                hits += con.execute(
                    f'select count(*) from "{table}" where cast("{column}" as text) like ?', (f"%{value}%",)
                ).fetchone()[0]
        return hits
    finally:
        con.close()


def ollama_requests() -> list[dict]:
    if not OLLAMA_LOG.exists():
        return []
    return [json.loads(line) for line in OLLAMA_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def user_text(entry: dict) -> str:
    return "\n".join(m.get("content", "") for m in entry.get("messages") or [] if m.get("role") == "user")


# ---------------------------------------------------------------- T-01 회원가입 · T-02 로그인

@case("STC-T01-001")
def t01_001():
    r = api.post("/auth/register", json={"email": "tester1@example.com", "username": "tester1", "password": PASSWORD})
    check(r.status_code == 201 and r.json().get("username") == "tester1", f"{r.status_code} {r.text}")
    # 이후 케이스에서 쓸 두 번째 계정
    api.post("/auth/register", json={"email": "tester2@example.com", "username": "tester2", "password": PASSWORD})
    return f"201 {r.json()}"


@case("STC-T01-002")
def t01_002():
    r = login("tester1", PASSWORD)
    check(r.status_code == 200 and r.json().get("access_token"), f"{r.status_code} {r.text}")
    ctx["token"] = {"tester1": r.json()["access_token"], "tester2": login("tester2", PASSWORD).json()["access_token"]}
    return "200, 토큰 발급"


@case("STC-T01-003")
def t01_003():
    r = api.post("/auth/register", json={"email": "other@example.com", "username": "tester1", "password": PASSWORD})
    return check(r.status_code == 409, f"{r.status_code} {r.json().get('detail')}")


@case("STC-T01-004")
def t01_004():
    r = api.post("/auth/register", json={"email": "tester1@example.com", "username": "tester9", "password": PASSWORD})
    return check(r.status_code == 409, f"{r.status_code} {r.json().get('detail')}")


@case("STC-T01-005")
def t01_005():
    r = api.post("/auth/register", json={"email": "abc", "username": "t", "password": "12"})
    fields = sorted({e["loc"][-1] for e in r.json().get("detail", [])}) if r.status_code == 422 else []
    return check(r.status_code == 422 and fields == ["email", "password", "username"],
                 f"{r.status_code}, 오류 필드 {fields}")


@case("STC-T02-001")
def t02_001():
    r = login("tester1", PASSWORD)
    return check(r.status_code == 200 and r.json().get("token_type") == "bearer",
                 f"{r.status_code} token_type={r.json().get('token_type')}")


@case("STC-T02-002")
def t02_002():
    me = api.get("/auth/me", headers=auth())
    anonymous = api.get("/services")
    return check(me.status_code == 200 and anonymous.status_code == 401,
                 f"/auth/me {me.status_code}({me.json().get('username')}), 토큰 없이 /services {anonymous.status_code}")


@case("STC-T02-003")
def t02_003():
    r = login("tester1", "wrongpass")
    return check(r.status_code == 401, f"{r.status_code} {r.json().get('detail')}")


# ---------------------------------------------------------------- T-03 기기 등록 · T-04 기기 관리

def register_worker(name: str, password: str = PASSWORD) -> httpx.Response:
    return worker_ui(name, "POST", "/api/register", json={
        "server_url": SERVER_URL, "username": "tester1", "password": password, "device_name": f"worker-{name}",
    })


@case("STC-T03-001")
def t03_001():
    a, b = register_worker("A"), register_worker("B")
    check(a.status_code == 200 and b.status_code == 200, f"Worker UI 등록 {a.status_code}/{b.status_code} {a.text} {b.text}")
    specs = device("A")["specs"]
    missing = [k for k in ("os", "cpu_count", "ram_gb") if k not in specs]
    return check(not missing, f"Worker UI 등록 {a.status_code}/{b.status_code}, worker-A specs: "
                 f"os={specs.get('os')}, cpu_count={specs.get('cpu_count')}, ram_gb={specs.get('ram_gb')}")


@case("STC-T03-002")
def t03_002():
    before = device("A")
    r = api.post("/devices", json={"name": "worker-A", "specs": before["specs"]}, headers=auth())
    data = r.json()
    # 새 키가 발급되어 Worker 설정의 키가 무효가 되므로 Worker UI로 다시 등록해 맞춘다
    register_worker("A")
    return check(r.status_code == 200 and data["id"] == before["id"] and bool(data.get("api_key")),
                 f"{r.status_code}, id {data.get('id')}(기존 {before['id']}), 새 키 발급={bool(data.get('api_key'))}")


@case("STC-T03-003")
def t03_003():
    r = register_worker("B", password="badpass")
    message = r.json().get("error", "")
    return check(r.status_code >= 400 and "일치하지 않습니다" in message, f"{r.status_code} {message}")


@case("STC-T03-004")
def t03_004():
    config = json.loads((RUN_DIR / "worker-A" / "agent_config.json").read_text(encoding="utf-8"))
    key = config["api_key"]
    ok = api.post("/worker/heartbeat", json={}, headers={"X-Device-Key": key})
    forged = api.post("/worker/heartbeat", json={}, headers={"X-Device-Key": secrets.token_urlsafe(36)[:48]})
    plain = db_contains(key)
    return check(ok.status_code == 200 and forged.status_code == 401 and plain == 0,
                 f"발급 키 하트비트 {ok.status_code}, 위조 키 {forged.status_code}, DB 평문 키 저장 {plain}건")


@case("STC-T04-001")
def t04_001():
    names = sorted(d["name"] for d in devices())
    return check(names == ["worker-A", "worker-B"], str(names))


def start_worker(name: str):
    worker_ui(name, "POST", "/api/worker/start", json={})


def stop_worker(name: str):
    worker_ui(name, "POST", "/api/worker/stop", json={})


def online(name: str) -> bool:
    return device(name)["online"]


@case("STC-T04-002")
def t04_002():
    start_worker("A")
    start_worker("B")
    wait_until(lambda: online("A") and online("B") and "cpu_percent" in device("B")["specs"], 30, what="두 기기 online")
    listed = {d["name"]: d for d in devices()}
    models = api.get(f"/devices/{listed['worker-A']['id']}/models", headers=auth()).json().get("models", [])
    return f"online={[listed['worker-A']['online'], listed['worker-B']['online']]}, " \
           f"cpu_percent={listed['worker-A']['specs'].get('cpu_percent')}, models={models}"


@case("STC-T04-003")
def t04_003():
    r = api.patch(f"/devices/{device('B')['id']}", json={"resource_limits": {"max_cpu_percent": 90}}, headers=auth())
    limits = r.json().get("resource_limits", {})
    return check(r.status_code == 200 and limits.get("max_cpu_percent") == 90, f"{r.status_code} {limits}")


@case("STC-T04-004")
def t04_004():
    temp = api.post("/devices", json={"name": "temp-device", "specs": {}}, headers=auth()).json()
    key = {"X-Device-Key": temp["api_key"]}
    duplicate = api.patch("/worker/device", json={"name": "worker-A"}, headers=key)
    renamed = api.patch("/worker/device", json={"name": "temp-renamed"}, headers=key)
    removed = api.delete("/worker/device", headers=key)
    names = sorted(d["name"] for d in devices())
    return check((duplicate.status_code, renamed.status_code, removed.status_code) == (409, 200, 204)
                 and names == ["worker-A", "worker-B"],
                 f"중복 이름 변경 {duplicate.status_code}, 이름 변경 {renamed.status_code}, "
                 f"등록 해제 {removed.status_code}, 목록 {names}")


# ---------------------------------------------------------------- T-05 워커 초기 설정

@case("STC-T05-001")
def t05_001():
    local = [m["name"] for m in worker_ui("A", "GET", "/api/models").json().get("models", [])]
    synced = api.get(f"/devices/{device('A')['id']}/models", headers=auth()).json().get("models", [])
    return check("gemma3:4b" in local and "gemma3:4b" in synced, f"Worker UI 모델 {local}, 서버 동기화 모델 {synced}")


@case("STC-T05-002")
def t05_002():
    r = worker_ui("A", "POST", "/api/models/pull", json={"name": "llama3.2:1b"})
    check(r.status_code == 202, f"{r.status_code} {r.text}")
    job_id = r.json()["job"]["id"]

    def finished():
        job = next((j for j in worker_ui("A", "GET", "/api/jobs").json()["jobs"] if j["id"] == job_id), None)
        return job if job and job["status"] in ("done", "failed") else None
    job = wait_until(finished, 30, interval=0.5, what="다운로드 완료")
    return check(job["status"] == "done" and job.get("percent") == 100, f"202, 작업 상태 {job['status']}, {job.get('percent')}%")


@case("STC-T05-003")
def t05_003():
    r = worker_ui("A", "POST", "/api/models/delete", json={"name": "llama3.2:1b"})
    return check(r.status_code == 200 and r.json().get("ok") is True, f"{r.status_code} {r.json()}")


@case("STC-T05-005")
def t05_005():
    path = f"/devices/{device('A')['id']}/directories"
    first = api.post(path, json={"alias": "카드내역", "local_path": SHARE_A}, headers=auth())
    again = api.post(path, json={"alias": "카드내역", "local_path": SHARE_A}, headers=auth())
    if first.status_code == 201:
        ctx["directory"] = first.json()["id"]
    return check(first.status_code == 201 and again.status_code == 409,
                 f"등록 {first.status_code}(id={first.json().get('id')}), 같은 별칭 {again.status_code}")


@case("STC-T05-006")
def t05_006():
    stop_worker("A")
    check(worker_ui("A", "GET", "/api/status").json()["running"] is False, "중지 후에도 Worker 프로세스가 실행 중")
    wait_until(lambda: not online("A"), 60, interval=2, what="offline 전환")
    start_worker("A")
    wait_until(lambda: online("A"), 30, what="다시 online")
    return "중지 200 → offline 전환 확인(하트비트 30초 기준) → 재시작 후 online 확인"


# ---------------------------------------------------------------- T-06 서비스 생성

@case("STC-T06-001")
def t06_001():
    r = api.post("/services/generate", json={"prompt": GEN_PROMPT}, headers=auth())
    check(r.status_code == 201, f"{r.status_code} {r.text[:300]}")
    data = r.json()
    ctx["service"] = data["id"]
    names = [n["name"] for n in data["graph"]["nodes"] if n.get("type", "agent") == "agent"]
    source = (data.get("generation_info") or {}).get("source")
    return check(len(names) == 3 and source == "llm", f"201, 이름 '{data['name']}', 블록 {names}, source={source}")


@case("STC-T06-002")
def t06_002():
    r = api.post("/services/generate", json={"prompt": "abc"}, headers=auth())
    return check(r.status_code == 422, str(r.status_code))


@case("STC-T06-003")
def t06_003():
    r = api.post("/services/generation-jobs", headers=auth(),
                 json={"prompt": GEN_PROMPT, "device_id": device("A")["id"], "model": "gemma3:4b"})
    check(r.status_code == 202, f"{r.status_code} {r.text[:300]}")
    job_id = r.json()["id"]

    def finished():
        job = api.get(f"/services/generation-jobs/{job_id}", headers=auth()).json()
        return job if job["status"] in ("done", "failed", "canceled") else None
    job = wait_until(finished, 60, what="생성 작업 종료")
    return check(job["status"] == "done" and job.get("service_id"),
                 f"202, 최종 상태 {job['status']}, service_id={job.get('service_id')}")


@case("STC-T06-004")
def t06_004():
    prompt = "BROKEN 응답으로 실패 단계 안내를 확인하는 요청"
    failed = api.post("/services/generate", json={"prompt": prompt}, headers=auth())
    error = (failed.json().get("detail") or {}).get("generation_error") or {} if failed.status_code == 502 else {}
    fallback = api.post("/services/generate", headers=auth(),
                        json={"prompt": prompt, "use_fallback": True, "fallback_reason": error.get("message", "")})
    source = (fallback.json().get("generation_info") or {}).get("source") if fallback.status_code == 201 else None
    return check(failed.status_code == 502 and error.get("stage") and fallback.status_code == 201 and source == "fallback",
                 f"{failed.status_code} generation_error.stage={error.get('stage')}('{error.get('message')}'), "
                 f"기본 워크플로우 선택 {fallback.status_code} source={source}")


# ---------------------------------------------------------------- T-07 서비스 수정

@case("STC-T07-001")
def t07_001():
    graph = service(ctx["service"])["graph"]
    added = {**graph, "nodes": graph["nodes"] + [{"id": "agent4", "type": "agent", "name": "검토 에이전트", "role_prompt": "검토한다."}]}
    first = save_graph(ctx["service"], added)
    count_added = len(service(ctx["service"])["graph"]["nodes"])
    second = save_graph(ctx["service"], graph)
    count_removed = len(service(ctx["service"])["graph"]["nodes"])
    return check(first.status_code == 200 and second.status_code == 200 and (count_added, count_removed) == (4, 3),
                 f"추가 {first.status_code}({count_added}블록), 삭제 {second.status_code}({count_removed}블록)")


def validate(graph: dict | None = None, run_prompt: str = RUN_PROMPT, user: str = "tester1", service_id=None) -> dict:
    body = {"run_prompt": run_prompt, **({"graph": graph} if graph else {})}
    return api.post(f"/services/{service_id or ctx['service']}/validate", json=body, headers=auth(user)).json()


@case("STC-T07-002")
def t07_002():
    graph = service(ctx["service"])["graph"]
    serial = {**graph, "edges": [{"source": "agent1", "target": "agent2"}, {"source": "agent2", "target": "agent3"}]}
    stages = validate(serial)["stages"]
    return check(stages == [["agent1"], ["agent2"], ["agent3"]], f"연결 변경 후 단계 {stages}")


@case("STC-T07-003")
def t07_003():
    result = validate()
    errors = [(e["code"], e["node_ids"]) for e in result["errors"]]
    final = result.get("final_node_ids") or result.get("final")
    missing = sorted(n for code, ids in errors if code == "missing_file" for n in ids)
    return check(result["valid"] is False and missing == ["agent1", "agent2"]
                 and result["stages"] == [["agent1", "agent2"], ["agent3"]] and final == ["agent3"],
                 f"valid={result['valid']}, 오류 {errors}, stages={result['stages']}, final={final}")


@case("STC-T07-004")
def t07_004():
    graph = service(ctx["service"])["graph"]
    cyclic = {**graph, "edges": graph["edges"] + [{"source": "agent3", "target": "agent1"}]}
    saved = save_graph(ctx["service"], cyclic)
    codes = [e["code"] for e in validate(cyclic)["errors"]]
    return check(saved.status_code == 422 and "cycle" in codes, f"저장 {saved.status_code}, 검사 오류 {codes}")


@case("STC-T07-005")
def t07_005():
    graph = service(ctx["service"])["graph"]
    role = "거래를 식비·교통·쇼핑으로 분류한다."
    node(graph, "agent1")["role_prompt"] = role
    r = save_graph(ctx["service"], graph)
    saved = node(service(ctx["service"])["graph"], "agent1")["role_prompt"]
    return check(r.status_code == 200 and saved == role, f"{r.status_code}, 저장된 역할 '{saved}'")


def upload_card() -> int:
    with open(HERE / "fixtures" / "card_october.csv", "rb") as f:
        r = api.post("/files", files={"file": ("card_october.csv", f, "text/csv")}, headers=auth())
    check(r.status_code == 201, f"파일 업로드 실패 {r.status_code} {r.text}")
    return r.json()["id"]


@case("STC-T07-006")
def t07_006():
    # tester2가 자기 워크플로우에 tester1의 폴더를 지정
    other = api.post("/services/generate", json={"prompt": GEN_PROMPT}, headers=auth("tester2")).json()
    other_graph = other["graph"]
    node(other_graph, "agent1")["directory_ids"] = [ctx["directory"]]
    denied = save_graph(other["id"], other_graph, user="tester2")

    # tester1: agent1은 공유 폴더+worker-A, agent2는 worker-B, 카드 내역 슬롯에는 같은 파일을 올린다
    ctx["card_file"] = upload_card()
    graph = service(ctx["service"])["graph"]
    node(graph, "agent1").update(directory_ids=[ctx["directory"]], worker_id=device("A")["id"])
    node(graph, "agent2").update(worker_id=device("B")["id"])
    for slot in graph.get("input_slots", []):
        slot["file_ids"] = [ctx["card_file"]]
    allowed = save_graph(ctx["service"], graph)
    result = validate()
    detail = denied.json().get("detail")
    return check(400 <= denied.status_code < 500 and allowed.status_code == 200 and result["valid"] is True,
                 f"타인 폴더 지정 {denied.status_code}({detail}), 본인 폴더 지정 {allowed.status_code}, "
                 f"지정 후 구성 검사 valid={result['valid']} {[e['code'] for e in result['errors']]}")


# ---------------------------------------------------------------- T-08 실행 프롬프트 · T-09 서비스 실행

@case("STC-T08-001")
def t08_001():
    ctx["run_started"] = time.monotonic()
    r = start_run(ctx["service"])
    check(r.status_code == 201, f"{r.status_code} {r.text[:300]}")
    ctx["run"] = r.json()["id"]
    return check(r.json()["status"] == "running", f"201 status={r.json()['status']}")


@case("STC-T08-002")
def t08_002():
    created = api.post(f"/services/{ctx['service']}/duplicate", headers=auth()).json()
    graph = {"nodes": [{"id": "solo", "type": "agent", "name": "입력 없는 블록", "role_prompt": "요약한다.",
                        "final": True, "final_manual": True, "needs_file": False, "needs_file_manual": True}],
             "edges": [], "input_slots": []}
    save_graph(created["id"], graph)
    r = start_run(created["id"], run_prompt="")
    codes = [e["code"] for e in ((r.json().get("detail") or {}).get("validation") or {}).get("errors", [])] if r.status_code == 422 else []
    api.delete(f"/services/{created['id']}", headers=auth())
    return check(r.status_code == 422 and "no_input" in codes, f"{r.status_code} {codes}")


def started_at(task: dict) -> datetime | None:
    return datetime.fromisoformat(task["started_at"]) if task.get("started_at") else None


def finished_at(task: dict) -> datetime | None:
    return datetime.fromisoformat(task["finished_at"]) if task.get("finished_at") else None


@case("STC-T09-001")
def t09_001():
    def first_start():
        return any(t.get("started_at") for t in execution(ctx["run"])["tasks"])
    wait_until(first_start, 60, interval=0.2, what="첫 작업 시작")
    seconds = time.monotonic() - ctx["run_started"]
    return check(seconds <= 60, f"첫 작업 배정까지 {seconds:.1f}초 (Worker 3초 폴링)")


@case("STC-T09-002")
def t09_002():
    data = wait_execution(ctx["run"])
    ctx["run_data"] = data
    tasks = {t["node_id"]: t for t in data["tasks"]}
    assigned = {k: t.get("assigned_device_name") for k, t in tasks.items()}
    after = all(started_at(tasks["agent3"]) >= finished_at(tasks[k]) for k in ("agent1", "agent2")) \
        if all(finished_at(tasks[k]) for k in ("agent1", "agent2")) and started_at(tasks["agent3"]) else False
    return check(data["status"] == "completed" and assigned.get("agent1") == "worker-A"
                 and assigned.get("agent2") == "worker-B" and after,
                 f"status={data['status']}, 배정 {assigned}, 최종 블록이 선행 2개 완료 후 시작={after}")


@case("STC-T09-003")
def t09_003():
    output = next(t for t in ctx["run_data"]["tasks"] if t["node_id"] == "agent1").get("output") or ""
    usage = api.get("/settings/llm-usage", params={"days": 30}, headers=auth()).json()
    calls = sum(item.get("requests", 0) for item in usage)
    has_file = "가상마트" in output
    return check(has_file and calls == 0, f"agent1 출력에 공유 폴더 파일 내용 포함={has_file}, 외부 LLM 사용 기록 {calls}건")


@case("STC-T09-004")
def t09_004():
    data = execution(ctx["run"])
    tasks = [(t["agent_name"], t["status"], t.get("assigned_device_name")) for t in data["tasks"]]
    return check(data["progress"] == 100 and all(s == "done" and d for _, s, d in tasks),
                 f"progress={data['progress']}, 작업 {tasks}")


@case("STC-T05-007")
def t05_007():
    # STC-T09-003 실행에서 agent1(공유 폴더 shareA 지정)이 모델에 보낸 입력을 대역 Ollama 기록에서 확인한다
    sent = [user_text(e) for e in ollama_requests() if "가상마트" in user_text(e)]
    check(bool(sent), "공유 폴더 파일을 읽은 모델 요청을 찾지 못함")
    leaked = any("SECRET_OUTSIDE" in text for text in sent)
    listing = [text.split("[이 작업에 사용할 파일 목록]")[1].split("\n\n")[0] for text in sent if "[이 작업에 사용할 파일 목록]" in text]
    listed = any("leak.txt" in part for part in listing)
    return check(not leaked and not listed, f"폴더 밖 파일 내용 유출={leaked}, leak.txt가 파일 목록에 포함={listed}")


@case("STC-T09-009")
def t09_009():
    marks = sorted({m for e in ollama_requests() for m in re.findall(r"card_october\.csv \(part ([^)]*)\)", user_text(e))})
    check(bool(marks), "모델 입력에서 card_october.csv 청크 머리글을 찾지 못함")
    return check(marks == ["1/1"], f"모델에 전달된 청크 표기 {[f'(part {m})' for m in marks]}")


@case("STC-T09-005")
def t09_005():
    ctx["slow"] = single_block_service("느린 블록", "SLOW 작업을 수행한다.")
    run_id = start_run(ctx["slow"]).json()["id"]
    wait_until(lambda: any(t["status"] == "running" for t in execution(run_id)["tasks"]), 30, interval=0.5, what="작업 실행")
    r = api.post(f"/executions/{run_id}/cancel", headers=auth())
    data = r.json()
    ctx["cancelled_run"] = run_id
    errors = [t.get("error") for t in data["tasks"]]
    return check(r.status_code == 200 and data["status"] == "cancelled",
                 f"중단 {r.status_code}, status={data['status']}, 작업 오류 {errors}")


@case("STC-T09-006")
def t09_006():
    failing = single_block_service("정보 수집 에이전트", "FAIL_TASK 를 일으키는 블록")
    data = wait_execution(start_run(failing).json()["id"], 60)
    return check(data["status"] == "failed" and data.get("error"), f"status={data['status']}, error='{data.get('error')}'")


@case("STC-T09-007")
def t09_007():
    # worker-A를 끄고 worker-B가 SLOW 작업을 받게 한 뒤, worker-B를 끄고 worker-A를 켠다
    stop_worker("A")
    wait_until(lambda: not online("A"), 60, interval=2, what="worker-A offline")
    run_id = start_run(ctx["slow"]).json()["id"]
    ctx["reassigned_run"] = run_id

    def running_on_b():
        task = execution(run_id)["tasks"][0]
        return task if task["status"] == "running" and task.get("assigned_device_name") == "worker-B" else None
    wait_until(running_on_b, 30, interval=0.5, what="worker-B 실행 시작")
    stop_worker("B")
    start_worker("A")
    data = wait_execution(run_id, 120)
    final = data["tasks"][0].get("assigned_device_name")
    start_worker("B")
    wait_until(lambda: online("B"), 30, what="worker-B online")
    return check(data["status"] == "completed" and final == "worker-A",
                 f"처음 배정 worker-B → 중단 후 최종 {final}, status={data['status']}")


# ---------------------------------------------------------------- T-10 결과 확인 · T-11 실행 이력

@case("STC-T10-001")
def t10_001():
    data = execution(ctx["run"])
    return check(data["status"] == "completed" and data.get("finished_at"),
                 f"status={data['status']}, finished_at={data.get('finished_at')}")


@case("STC-T10-002")
def t10_002():
    data = execution(ctx["run"])
    task = next(t for t in data["tasks"] if t["node_id"] == "agent3")
    # 결과는 최종 블록마다 '## 블록 이름' 머리글 뒤에 출력을 붙여 만든다(orchestrator)
    same = data.get("result") == f"## {task['agent_name']}\n\n{task.get('output') or ''}"
    return check(same, f"결과 길이 {len(data.get('result') or '')}자, 최종 블록(agent3) 출력과 일치={same}")


@case("STC-T11-001")
def t11_001():
    r = api.get("/executions", headers=auth())
    ids = [e["id"] for e in r.json()]
    return check(r.status_code == 200 and ctx["run"] in ids, f"{r.status_code}, 이력 {len(ids)}건, 대상 포함={ctx['run'] in ids}")


@case("STC-T11-002")
def t11_002():
    r = api.get(f"/executions/{ctx['run']}", headers=auth())
    data = r.json()
    return check(r.status_code == 200 and data.get("result") and len(data["tasks"]) == 3,
                 f"{r.status_code}, 결과 {len(data.get('result') or '')}자, 작업 {len(data['tasks'])}건")


@case("STC-T11-003")
def t11_003():
    missing = api.get("/executions/99999", headers=auth())
    other = api.get(f"/executions/{ctx['run']}", headers=auth("tester2"))
    return check(missing.status_code == 404 and other.status_code == 404,
                 f"없는 id {missing.status_code} '{missing.json().get('detail')}', 타 사용자 {other.status_code}")


# ---------------------------------------------------------------- T-12 외부 LLM 연동

INVALID_KEY = "sk-test-invalid-1234"


@case("STC-T12-001")
def t12_001():
    saved = api.put("/settings/llm-providers/openai", json={"api_key": INVALID_KEY}, headers=auth())
    masked = saved.json().get("masked_key")
    plain = db_contains(INVALID_KEY)
    verify = api.post("/settings/llm-providers/openai/verify", headers=auth())
    status = next(p for p in api.get("/settings/llm-providers", headers=auth()).json() if p["provider"] == "openai")["status"]
    return check(saved.status_code == 200 and masked and masked.endswith("1234") and plain == 0
                 and verify.status_code == 400 and status == "error",
                 f"저장 {saved.status_code} 표시 '{masked}', DB 평문 {plain}건, 잘못된 키 확인 {verify.status_code} → 상태 {status}")


@case("STC-T12-002")
def t12_002():
    # 외부 LLM 시험은 사본에서 한다(원본은 T-13에서 로컬 실행에 다시 쓴다)
    ctx["cloud"] = api.post(f"/services/{ctx['service']}/duplicate", headers=auth()).json()["id"]
    graph = service(ctx["cloud"])["graph"]
    node(graph, "agent3").update(executor="cloud", provider="openai", model="gpt-5-mini")
    r = save_graph(ctx["cloud"], graph)
    saved = node(service(ctx["cloud"])["graph"], "agent3")
    return check(r.status_code == 200 and saved["executor"] == "cloud" and saved["provider"] == "openai",
                 f"{r.status_code}, agent3 executor={saved['executor']} provider={saved['provider']} model={saved.get('model')}")


@case("STC-T12-003")
def t12_003():
    sid = ctx["cloud"]
    without = start_run(sid)
    preview = api.post(f"/services/{sid}/executions/preview", json={"run_prompt": RUN_PROMPT}, headers=auth()).json()
    token = preview.get("consent_token")
    items = sorted({t.get("kind") or t.get("type") or str(t) for t in preview.get("transfers", [])})
    changed = start_run(sid, run_prompt=RUN_PROMPT + " (변경)", consent_token=token)
    agreed = start_run(sid, consent_token=token)
    reused = start_run(sid, consent_token=token)
    if agreed.status_code == 201:
        ctx["cloud_run"] = agreed.json()["id"]
    codes = (without.status_code, agreed.status_code, changed.status_code, reused.status_code)
    return check(codes == (428, 201, 428, 428),
                 f"동의 없이 {without.status_code}, 전송 항목 {items}, 프롬프트 변경 후 {changed.status_code}, "
                 f"동의 후 {agreed.status_code}, 토큰 재사용 {reused.status_code}")


@case("STC-T12-004")
def t12_004():
    data = wait_execution(ctx["cloud_run"], 120)
    task = next(t for t in data["tasks"] if t["node_id"] == "agent3")
    return check(data["status"] == "failed" and task["status"] == "failed" and "클라우드 LLM 호출 실패" in (task.get("error") or ""),
                 f"status={data['status']}, agent3 오류 '{(task.get('error') or '')[:120]}'")


@case("STC-T12-005")
def t12_005():
    r = api.get("/settings/llm-usage", params={"days": 30}, headers=auth())
    return check(r.status_code == 200 and isinstance(r.json(), list), f"{r.status_code}, 집계 {r.json()}")


# ---------------------------------------------------------------- T-13 워크플로우 관리

@case("STC-T13-001")
def t13_001():
    copy = api.post(f"/services/{ctx['service']}/duplicate", headers=auth())
    check(copy.status_code == 201, f"복제 {copy.status_code} {copy.text[:200]}")
    ctx["copy"] = copy.json()["id"]
    again = start_run(ctx["copy"])
    if again.status_code == 201:
        wait_execution(again.json()["id"])
    return check(again.status_code == 201, f"복제 201(새 id {ctx['copy']}), 같은 입력 재실행 {again.status_code}")


@case("STC-T13-002")
def t13_002():
    renamed = api.put(f"/services/{ctx['copy']}", json={"name": "카드 리포트 사본"}, headers=auth())
    folder = api.post("/folders", json={"name": "가계부"}, headers=auth())
    moved = api.put(f"/services/{ctx['copy']}/folder", json={"folder_id": folder.json().get("id")}, headers=auth())
    folder_id = moved.json().get("folder_id")
    return check(renamed.status_code == 200 and renamed.json()["name"] == "카드 리포트 사본"
                 and folder.status_code == 201 and folder_id == folder.json().get("id"),
                 f"이름 변경 {renamed.status_code} '{renamed.json().get('name')}', 폴더 생성 {folder.status_code}, 이동 folder_id={folder_id}")


@case("STC-T13-003")
def t13_003():
    run_id = start_run(ctx["slow"]).json()["id"]
    wait_until(lambda: any(t["status"] == "running" for t in execution(run_id)["tasks"]), 30, interval=0.5, what="작업 실행")
    while_running = api.delete(f"/executions/{run_id}", headers=auth())
    wait_execution(run_id, 60)
    after = api.delete(f"/executions/{run_id}", headers=auth())
    cancelled = api.delete(f"/executions/{ctx['cancelled_run']}", headers=auth())
    # 이력이 남은 워크플로우는 with_history=true로 한 번 더 확인해야 지워진다(release0.0.3 이후 추가)
    unconfirmed = api.delete(f"/services/{ctx['copy']}", headers=auth())
    workflow = api.delete(f"/services/{ctx['copy']}", params={"with_history": "true"}, headers=auth())
    codes = (while_running.status_code, after.status_code, cancelled.status_code, workflow.status_code)
    return check(codes == (409, 204, 204, 204) and unconfirmed.status_code in (204, 409),
                 f"실행 중 삭제 {codes[0]}, 완료 후 삭제 {codes[1]}, 중단된 이력 삭제 {codes[2]}, "
                 f"워크플로우 삭제 {codes[3]}(이력 확인 전 {unconfirmed.status_code})")


# ---------------------------------------------------------------- T-14 공개 페이지·커뮤니티 · 비기능

@case("STC-T14-001")
def t14_001():
    shared = api.put(f"/services/{ctx['service']}/publication", headers=auth(),
                     json={"title": "카드 지출 리포트", "description": "시스템 테스트 공유"})
    listing = api.get("/community/workflows")
    entry = next((e for e in listing.json() if e.get("service_id") == ctx["service"]), None) if listing.status_code == 200 else None
    graph = json.dumps(entry["graph"] if entry else {}, ensure_ascii=False)
    personal = bool(re.search(
        r'"worker_id": [1-9]|"directory_ids": \[[^\]]|"uploaded_file_ids": \[[^\]]|"file_ids": \[[^\]]', graph))
    imported = api.post(f"/community/workflows/{entry['id']}/import", headers=auth("tester2")) if entry else None
    count = next((e["import_count"] for e in api.get("/community/workflows").json() if entry and e["id"] == entry["id"]), None)
    return check(shared.status_code == 200 and entry and not personal and imported is not None
                 and imported.status_code == 201 and count == 1,
                 f"공유 {shared.status_code}, 비로그인 목록 조회 {listing.status_code}, 개인 참조 남음={personal}, "
                 f"tester2 가져오기 {imported.status_code if imported is not None else '-'}, import_count={count}")


@case("STC-NF-001")
def nf_001():
    times = []
    for _ in range(100):
        start = time.perf_counter()
        r = api.get("/devices", headers=auth())
        times.append((time.perf_counter() - start) * 1000)
        check(r.status_code == 200, f"응답 {r.status_code}")
    return check(max(times) < 3000, f"100회 평균 {statistics.mean(times):.1f}ms, 최대 {max(times):.1f}ms")


# ---------------------------------------------------------------- 화면 케이스(ui_checks.js)

def run_ui_checks() -> None:
    STATE_PATH.write_text(json.dumps({
        "web_url": WEB_URL, "token": ctx.get("token", {}).get("tester1"),
        "service_id": ctx.get("service"), "run_id": ctx.get("run"), "gantt_run_id": ctx.get("reassigned_run"),
        "screenshot_dir": str(HERE / "screenshots"),
    }, ensure_ascii=False), encoding="utf-8")
    out = RUN_DIR / "ui_results.json"
    out.unlink(missing_ok=True)
    try:
        proc = subprocess.run(["node", str(HERE / "ui_checks.js"), str(STATE_PATH), str(out)],
                              cwd=HERE, capture_output=True, text=True, timeout=300)
        print(proc.stdout, end="")
        if proc.returncode and not out.exists():
            raise RuntimeError((proc.stderr or proc.stdout)[-500:])
        for case_id, item in json.loads(out.read_text(encoding="utf-8")).items():
            record(case_id, item["ok"], item["actual"])
    except Exception as exc:
        for case_id in sorted(UI_CASES - results.keys()):
            results[case_id] = {"result": "-", "actual": f"미수행: 화면 시험을 실행하지 못함 ({exc})"}


# ---------------------------------------------------------------- 실행

ORDER = [
    t01_001, t01_002, t01_003, t01_004, t01_005, t02_001, t02_002, t02_003,
    t03_001, t03_002, t03_003, t03_004, t04_001, t04_002, t04_003, t04_004,
    t05_001, t05_002, t05_003, t05_005, t05_006,
    t06_001, t06_002, t06_003, t06_004,
    t07_001, t07_002, t07_003, t07_004, t07_005, t07_006,
    t08_001, t08_002, t09_001, t09_002, t09_003, t09_004, t05_007, t09_009,
    t09_005, t09_006, t09_007,
    t10_001, t10_002, t11_001, t11_002, t11_003,
    t12_001, t12_002, t12_003, t12_004, t12_005,
    t13_001, t13_002, t13_003, t14_001, nf_001,
]


def main() -> None:
    parser = argparse.ArgumentParser(description="M.A.R.S. 시스템 테스트")
    parser.add_argument("--skip-ui", action="store_true", help="화면 케이스(ui_checks.js)를 건너뛴다")
    args = parser.parse_args()

    started = datetime.now().astimezone()
    for run in ORDER:
        run()
    if args.skip_ui:
        for case_id in UI_CASES:
            results[case_id] = {"result": "-", "actual": "미수행: --skip-ui"}
    else:
        run_ui_checks()
    for case_id, reason in SKIPPED.items():
        results[case_id] = {"result": "-", "actual": reason}

    rows = []
    for case_id, title, given, expected in CASES:
        item = results.get(case_id, {"result": "-", "actual": "미수행: 케이스가 실행되지 않음"})
        rows.append({"id": case_id, "title": title, "input": given, "expected": expected,
                     "executed": "N" if item["result"] == "-" else "Y", **item})
    counts = {k: sum(r["result"] == k for r in rows) for k in ("P", "F", "-")}
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    RESULTS_PATH.write_text(json.dumps({
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "commit": commit, "summary": {"total": len(rows), "passed": counts["P"], "failed": counts["F"], "not_run": counts["-"]},
        "cases": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(rows)}건 중 통과 {counts['P']}, 실패 {counts['F']}, 미수행 {counts['-']} → {RESULTS_PATH}")


if __name__ == "__main__":
    main()
