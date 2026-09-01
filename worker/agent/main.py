"""M.A.R.S Worker Agent CLI.

사용법:
  python -m agent register --server http://localhost:8000   # 최초 1회 기기 등록
  python -m agent run                                       # 하트비트 + 작업 폴링·실행
"""

import argparse
import getpass
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import psutil

from . import config as cfg
from . import executor
from . import sandbox


def collect_specs() -> dict:
    """기기 정보 자동 수집 (UC-103 F1-303)."""
    gpu_mode = os.getenv("MARS_GPU_MODE", "cpu")
    return {
        "hostname": platform.node(),
        "gpu_mode": gpu_mode,
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "gpus": collect_gpu_devices(),
    }


def collect_gpu_devices() -> list[dict]:
    """Detect NVIDIA and Linux DRM GPUs without vendor SDKs."""
    devices = []
    vendors = {"0x1002": "AMD", "0x8086": "Intel", "0x10de": "NVIDIA"}
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        device = card / "device"
        try:
            vendor_id = (device / "vendor").read_text().strip().lower()
            device_id = (device / "device").read_text().strip().lower()
            uevent = (device / "uevent").read_text()
            match = re.search(r"^DRIVER=(.+)$", uevent, re.MULTILINE)
            driver = match.group(1) if match else ""
            vendor = vendors.get(vendor_id, vendor_id)
            devices.append({"vendor": vendor, "name": f"{vendor} GPU ({driver or device_id})", "id": f"{vendor_id}:{device_id}", "card": card.name})
        except OSError:
            continue
    return devices


def collect_runtime_stats() -> dict:
    """Report CPU and, when NVIDIA tools are available, GPU utilization."""
    stats = {
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": psutil.virtual_memory().percent,
    }
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
        values = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        if values:
            stats["gpu_percent"] = max(values)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    if "gpu_percent" not in stats:
        values = []
        for busy_file in Path("/sys/class/drm").glob("card[0-9]*/device/gpu_busy_percent"):
            try:
                values.append(float(busy_file.read_text().strip()))
            except (OSError, ValueError):
                continue
        if values:
            stats["gpu_percent"] = max(values)
            stats["gpu_source"] = "drm"
    stats["gpu_devices"] = collect_gpu_devices()
    stats["gpu_mode"] = os.getenv("MARS_GPU_MODE", "cpu")
    if not stats["gpu_devices"] and stats["gpu_mode"] != "cpu":
        stats["gpu_devices"] = [{
            "vendor": stats["gpu_mode"],
            "name": f"Ollama GPU ({stats['gpu_mode']})",
            "id": stats["gpu_mode"],
        }]
    return stats


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

    specs = collect_specs()
    print(f"자동 수집된 기기 정보: {specs}")

    resp = httpx.post(
        f"{config['server_url']}/devices",
        json={"name": name, "specs": specs},
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
    )
    cfg.save(config)
    print(f"등록 완료! device_id={data['id']} (설정 저장: {cfg.CONFIG_PATH})")
    print("이제 `python -m agent run` 으로 에이전트를 실행하세요.")


def process_directory_inspection(server: str, headers: dict) -> bool:
    """Run one server-requested, sandboxed file listing when available."""
    response = httpx.post(
        f"{server}/worker/directory-inspections/next", headers=headers, timeout=15
    )
    if response.status_code != 200 or not response.content:
        return False
    inspection = response.json()
    try:
        files = sandbox.list_files([inspection["local_path"]])
        result = {"files": files, "error": ""}
    except Exception as exc:
        result = {"files": [], "error": str(exc)}
    httpx.post(
        f"{server}/worker/directory-inspections/{inspection['inspection_id']}/result",
        headers=headers,
        json=result,
        timeout=30,
    ).raise_for_status()
    return True


def stage_uploaded_files(server: str, headers: dict, task: dict) -> str | None:
    """Download files selected in the agent block to a private, temporary folder."""
    uploads = task.get("uploaded_files") or []
    if not uploads:
        return None
    staging_dir = Path(tempfile.mkdtemp(prefix="mars-task-files-"))
    staged_paths: list[str] = []
    try:
        for uploaded in uploads:
            file_id = uploaded.get("id")
            name = Path(str(uploaded.get("original_name") or "upload")).name
            if not isinstance(file_id, int) or not name:
                raise ValueError("Invalid uploaded file metadata")
            response = httpx.get(
                f"{server}/worker/files/{file_id}", headers=headers, timeout=60
            )
            response.raise_for_status()
            destination = staging_dir / f"{file_id}_{name}"
            destination.write_bytes(response.content)
            staged_paths.append(str(destination))
        task["directory_paths"] = [
            *(task.get("directory_paths") or []), str(staging_dir)
        ]
        task["uploaded_file_paths"] = staged_paths
        return str(staging_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


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
            if process_directory_inspection(server, headers):
                continue
            resp = httpx.post(
                f"{server}/worker/tasks/next", headers=headers, timeout=15
            )
            if resp.status_code == 200 and resp.content and resp.text != "null":
                task = resp.json()
                print(f"▶ 작업 수신: #{task['task_id']} {task['agent_name']}")
                staging_dir = None
                try:
                    staging_dir = stage_uploaded_files(server, headers, task)
                    output = executor.run_task(task, config)
                    result = {"status": "done", "output": output, "error": ""}
                    print(f"✔ 작업 완료: #{task['task_id']} ({len(output)}자)")
                except Exception as e:  # LLM 실패 등 -> 서버에 실패 보고
                    result = {"status": "failed", "output": "", "error": str(e)}
                    print(f"✘ 작업 실패: #{task['task_id']} — {e}")
                finally:
                    if staging_dir:
                        shutil.rmtree(staging_dir, ignore_errors=True)
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
                    json={"specs": collect_runtime_stats()},
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

    p_ui = sub.add_parser("ui", help="localhost Worker 관리 UI 실행")
    p_ui.add_argument("--host", default="127.0.0.1", help="바인딩 주소")
    p_ui.add_argument("--port", default=8765, type=int, help="포트")
    p_ui.set_defaults(func=lambda a: __import__("agent.webui", fromlist=["serve"]).serve(a.host, a.port))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
