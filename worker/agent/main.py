"""M.A.R.S Worker Agent CLI.

사용법:
  python -m agent register --server http://localhost:8000   # 최초 1회 기기 등록
  python -m agent run                                       # 하트비트 + 작업 폴링·실행
"""

import argparse
import getpass
import platform
import sys
import threading
import time

import httpx
import psutil

from . import config as cfg
from . import executor


def collect_specs() -> dict:
    """기기 정보 자동 수집 (UC-103 F1-303)."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
    }


def cmd_register(args: argparse.Namespace) -> None:
    config = cfg.load()
    config["server_url"] = args.server.rstrip("/")

    print("=== M.A.R.S 기기 등록 ===")
    username = input("아이디: ").strip()
    password = getpass.getpass("비밀번호: ")

    # 사용자 로그인
    resp = httpx.post(
        f"{config['server_url']}/auth/login",
        data={"username": username, "password": password},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"로그인 실패: {resp.json().get('detail', resp.text)}")
        sys.exit(1)
    token = resp.json()["access_token"]

    default_name = platform.node() or "내 기기"
    name = input(f"기기 이름 [{default_name}]: ").strip() or default_name

    print("에이전트가 접근을 허용할 폴더를 입력하세요 (쉼표로 구분, 비우면 없음)")
    folders_raw = input("허용 폴더: ").strip()
    folders = [f.strip() for f in folders_raw.split(",") if f.strip()]

    specs = collect_specs()
    print(f"자동 수집된 기기 정보: {specs}")

    resp = httpx.post(
        f"{config['server_url']}/devices",
        json={"name": name, "specs": specs, "allowed_folders": folders},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code != 201:
        print(f"기기 등록 실패: {resp.json().get('detail', resp.text)}")  # e601/e701
        sys.exit(1)
    data = resp.json()

    config.update(
        device_id=data["id"],
        device_name=data["name"],
        api_key=data["api_key"],
        allowed_folders=folders,
    )
    cfg.save(config)
    print(f"등록 완료! device_id={data['id']} (설정 저장: {cfg.CONFIG_PATH})")
    print("이제 `python -m agent run` 으로 에이전트를 실행하세요.")


def _run_with_cancel_watch(
    task: dict, config: dict, server: str, headers: dict
) -> dict | None:
    """LLM 작업을 별도 스레드로 실행하면서 서버의 중단 지시를 감시한다 (F2-407).

    사용자가 실행을 중단하면 서버가 이 작업을 failed로 바꾸므로, status가
    'running'이 아니게 되는 즉시 결과를 버리고 None을 반환한다.
    (진행 중인 Ollama 추론 자체는 강제 종료할 수 없지만, 워커는 곧바로
    다음 작업을 받을 수 있는 상태로 돌아간다.)
    """
    box: dict = {}

    def _work():
        try:
            box["result"] = {
                "status": "done", "output": executor.run_task(task, config), "error": "",
            }
        except Exception as e:
            box["result"] = {"status": "failed", "output": "", "error": str(e)}

    thread = threading.Thread(target=_work, daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(timeout=3)
        if not thread.is_alive():
            break
        try:
            status = httpx.get(
                f"{server}/worker/tasks/{task['task_id']}/status",
                headers=headers,
                timeout=10,
            ).json().get("status")
            if status != "running":
                return None
        except Exception:
            pass  # 일시적 통신 오류는 무시하고 계속 감시

    result = box.get("result", {"status": "failed", "output": "", "error": "알 수 없는 오류"})
    if result["status"] == "done":
        print(f"✔ 작업 완료: #{task['task_id']} ({len(result['output'])}자)")
    else:
        print(f"✘ 작업 실패: #{task['task_id']} — {result['error']}")
    return result


def cmd_run(_args: argparse.Namespace) -> None:
    config = cfg.load()
    if not config.get("api_key"):
        print("등록된 기기가 없습니다. 먼저 `python -m agent register` 를 실행하세요.")
        sys.exit(1)

    server = config["server_url"]
    headers = {"X-Device-Key": config["api_key"]}
    interval = config.get("poll_interval_sec", 3)
    print(f"[M.A.R.S Worker] {config['device_name']} — {server} 폴링 시작 (Ctrl+C로 종료)")

    while True:
        try:
            # 하트비트 겸 작업 요청
            resp = httpx.post(
                f"{server}/worker/tasks/next", headers=headers, timeout=15
            )
            if resp.status_code == 200 and resp.content and resp.text != "null":
                task = resp.json()
                print(f"▶ 작업 수신: #{task['task_id']} {task['agent_name']}")
                result = _run_with_cancel_watch(task, config, server, headers)
                if result is None:
                    # 사용자가 실행을 중단함 (F2-407) — 결과를 버리고 다음 폴링으로
                    print(f"■ 작업 중단됨: #{task['task_id']} (서버 지시)")
                else:
                    httpx.post(
                        f"{server}/worker/tasks/{task['task_id']}/result",
                        headers=headers,
                        json=result,
                        timeout=15,
                    )
            else:
                # 대기 중에도 주기적으로 상태(사양) 보고
                httpx.post(
                    f"{server}/worker/heartbeat",
                    headers=headers,
                    json={"specs": {"cpu_percent": psutil.cpu_percent(),
                                    "ram_percent": psutil.virtual_memory().percent}},
                    timeout=15,
                )
        except KeyboardInterrupt:
            print("\n종료합니다.")
            return
        except Exception as e:
            print(f"통신 오류(재시도 예정): {e}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n종료합니다.")
            return


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent", description="M.A.R.S Worker Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_reg = sub.add_parser("register", help="이 기기를 M.A.R.S에 등록")
    p_reg.add_argument("--server", default="http://localhost:8000", help="서버 주소")
    p_reg.set_defaults(func=cmd_register)

    p_run = sub.add_parser("run", help="에이전트 실행 (하트비트 + 작업 처리)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
