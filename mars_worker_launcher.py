"""Cross-platform Tkinter launcher for the Docker-based M.A.R.S Worker.

Windows executable:
    python -m pip install -r requirements-launcher.txt
    pyinstaller --onefile --windowed --name MARS-Worker-Launcher mars_worker_launcher.py
Place the resulting executable next to docker-compose.yml and
 docker-compose.nvidia.yml.
"""

from __future__ import annotations

import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DOCKER_DESKTOP_URL = "https://www.docker.com/products/docker-desktop/"
WORKER_UI_URL = "http://127.0.0.1:8765"
DEFAULT_MODELS = ("qwen3:4b", "gemma3:4b", "llama3.2:3b", "mistral:7b")


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class LauncherError(RuntimeError):
    pass


class MarsWorkerLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("M.A.R.S Worker Launcher")
        self.geometry("920x760")
        self.minsize(760, 650)
        self.base_dir = application_dir()
        self.settings_path = self.base_dir / ".mars-launcher.json"
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.running = False
        self._build_ui()
        self._load_settings()
        self.after(100, self._drain_events)
        self.after(600, self.check_updates)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="M.A.R.S Worker", font=("TkDefaultFont", 18, "bold")).grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar(value="준비")
        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

        form = ttk.LabelFrame(self, text="Worker 설정", padding=14)
        form.grid(row=1, column=0, padx=16, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self.server_var = tk.StringVar(value="http://localhost:8000")
        self.name_var = tk.StringVar(value=platform.node() or "MARS Worker")
        self.user_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="auto")
        self.model_var = tk.StringVar(value=DEFAULT_MODELS[0])

        fields = [
            ("Server URL", self.server_var, 0, 0),
            ("Worker 이름", self.name_var, 0, 2),
            ("사용자명", self.user_var, 1, 0),
            ("비밀번호", self.password_var, 1, 2),
        ]
        for label, variable, row, col in fields:
            ttk.Label(form, text=label).grid(row=row, column=col, padx=(0, 8), pady=6, sticky="w")
            entry = ttk.Entry(form, textvariable=variable, show="*" if label == "비밀번호" else "")
            entry.grid(row=row, column=col + 1, padx=(0, 16), pady=6, sticky="ew")

        ttk.Label(form, text="공유 폴더").grid(row=2, column=0, padx=(0, 8), pady=6, sticky="w")
        ttk.Entry(form, textvariable=self.folder_var).grid(row=2, column=1, columnspan=2, padx=(0, 8), pady=6, sticky="ew")
        ttk.Button(form, text="찾아보기", command=self.choose_folder).grid(row=2, column=3, pady=6, sticky="w")

        ttk.Label(form, text="실행 모드").grid(row=3, column=0, padx=(0, 8), pady=6, sticky="w")
        modes = ttk.Frame(form)
        modes.grid(row=3, column=1, pady=6, sticky="w")
        for text, value in (("자동", "auto"), ("GPU", "gpu"), ("CPU", "cpu")):
            ttk.Radiobutton(modes, text=text, value=value, variable=self.mode_var).pack(side="left", padx=(0, 12))

        ttk.Label(form, text="Ollama 모델").grid(row=3, column=2, padx=(0, 8), pady=6, sticky="w")
        model_box = ttk.Combobox(form, textvariable=self.model_var, values=DEFAULT_MODELS)
        model_box.grid(row=3, column=3, pady=6, sticky="ew")

        actions = ttk.Frame(form)
        actions.grid(row=4, column=0, columnspan=4, pady=(12, 0), sticky="ew")
        self.start_button = ttk.Button(actions, text="Worker 시작", command=self.start_worker)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(actions, text="Worker 중지", command=self.stop_worker)
        self.stop_button.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="모델 다운로드", command=self.download_model).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="관리 화면 열기", command=lambda: webbrowser.open(WORKER_UI_URL)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="업데이트 확인", command=self.check_updates).pack(side="right")

        log_frame = ttk.LabelFrame(self, text="로그", padding=10)
        log_frame.grid(row=2, column=0, padx=16, pady=16, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", bg="#101827", fg="#e5edf7")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(self, padding=(16, 0, 16, 14))
        footer.grid(row=3, column=0, sticky="ew")
        self.update_var = tk.StringVar(value="업데이트 상태: 확인 전")
        ttk.Label(footer, textvariable=self.update_var).pack(side="left")
        if platform.system() == "Windows":
            ttk.Button(footer, text="Docker Desktop 다운로드", command=lambda: webbrowser.open(DOCKER_DESKTOP_URL)).pack(side="right")

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Worker가 읽을 공유 폴더 선택")
        if selected:
            self.folder_var.set(selected)

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _emit(self, kind: str, value: object) -> None:
        self.events.put((kind, value))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log(str(value))
            elif kind == "status":
                self.status_var.set(str(value))
            elif kind == "update":
                self.update_var.set(str(value))
            elif kind == "error":
                self.status_var.set("오류")
                self.log(str(value))
                messagebox.showerror("M.A.R.S Worker", str(value))
            elif kind == "done":
                self.busy = False
                self.start_button.configure(state="normal")
        self.after(100, self._drain_events)

    def _background(self, target) -> None:
        if self.busy:
            messagebox.showinfo("M.A.R.S Worker", "현재 작업이 끝날 때까지 기다려 주세요.")
            return
        self.busy = True
        self.start_button.configure(state="disabled")

        def run() -> None:
            try:
                target()
            except Exception as exc:
                self._emit("error", str(exc))
            finally:
                self._emit("done", None)

        threading.Thread(target=run, daemon=True).start()

    def _command(self, args: list[str], env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        self._emit("log", "$ " + " ".join(args))
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        process = subprocess.Popen(
            args,
            cwd=self.base_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            creationflags=creationflags,
        )
        output: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            clean = line.rstrip()
            output.append(clean)
            self._emit("log", clean)
        code = process.wait()
        result = subprocess.CompletedProcess(args, code, "\n".join(output), "")
        if check and code:
            raise LauncherError(f"명령 실행 실패 ({code}): {' '.join(args)}")
        return result

    def _capture(self, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            return subprocess.run(
                args, cwd=self.base_dir, env=env, capture_output=True, text=True,
                errors="replace", timeout=timeout, creationflags=creationflags,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "timeout")

    def _check_prerequisites(self) -> None:
        if not (self.base_dir / "docker-compose.yml").exists():
            raise LauncherError("MARS-Worker-Launcher를 docker-compose.yml과 같은 폴더에 놓아 주세요.")
        if not shutil.which("docker"):
            raise LauncherError("Docker를 찾을 수 없습니다. Docker Desktop을 설치해 주세요.")
        result = self._command(["docker", "info"], check=False)
        if result.returncode:
            raise LauncherError("Docker 엔진이 실행 중이 아닙니다. Docker Desktop을 먼저 실행해 주세요.")
        compose = self._command(["docker", "compose", "version"], check=False)
        if compose.returncode:
            raise LauncherError("Docker Compose v2를 사용할 수 없습니다.")

    def _gpu_available(self) -> bool:
        if not shutil.which("nvidia-smi"):
            self._emit("log", "NVIDIA GPU 도구를 찾지 못했습니다.")
            return False
        gpu = self._command(["nvidia-smi", "-L"], check=False)
        if gpu.returncode:
            return False
        info = self._command(["docker", "info", "--format", "{{json .Runtimes}}"], check=False)
        runtime_visible = info.returncode == 0 and "nvidia" in info.stdout.lower()
        self._emit("log", "Docker NVIDIA 런타임 표시: " + ("확인" if runtime_visible else "미표시 · 실제 시작으로 검증"))
        return True

    def _compose(self, gpu: bool) -> list[str]:
        command = ["docker", "compose", "-f", "docker-compose.yml"]
        if gpu:
            override = self.base_dir / "docker-compose.nvidia.yml"
            if not override.exists():
                raise LauncherError("docker-compose.nvidia.yml 파일이 없습니다.")
            command.extend(["-f", override.name])
        command.extend(["--profile", "worker-ui"])
        return command


    @staticmethod
    def _container_server_url(url: str) -> str:
        from urllib.parse import urlsplit, urlunsplit
        parsed = urlsplit(url)
        if parsed.hostname not in {"localhost", "127.0.0.1"}:
            return url
        host = "host.docker.internal"
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme or "http", host, parsed.path, parsed.query, parsed.fragment))

    def _environment(self, folder_value: str, model: str) -> dict[str, str]:
        folder = Path(folder_value).expanduser()
        if not folder.is_dir():
            raise LauncherError("존재하는 공유 폴더를 선택해 주세요.")
        if not model:
            raise LauncherError("사용할 Ollama 모델을 입력해 주세요.")
        env = os.environ.copy()
        env["MARS_WORKER_SHARED_DIR"] = str(folder.resolve())
        env["MARS_WORKER_MODEL"] = model
        return env

    def _wait_for_ui(self, timeout: int = 90) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self._http("GET", WORKER_UI_URL + "/api/status")
                return
            except Exception:
                time.sleep(2)
        raise LauncherError("Worker UI가 제한 시간 안에 시작되지 않았습니다. 로그를 확인해 주세요.")

    @staticmethod
    def _http(method: str, url: str, data: dict | None = None, timeout: int = 30) -> dict:
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise LauncherError(detail or str(exc)) from exc
        return json.loads(payload or b"{}")

    def start_worker(self) -> None:
        self._save_settings()
        settings = {
            "server_url": self.server_var.get().strip().rstrip("/"),
            "worker_name": self.name_var.get().strip(),
            "username": self.user_var.get().strip(),
            "password": self.password_var.get(),
            "folder": self.folder_var.get().strip(),
            "mode": self.mode_var.get(),
            "model": self.model_var.get().strip(),
        }

        def task() -> None:
            if bool(settings["username"]) != bool(settings["password"]):
                raise LauncherError("사용자명과 비밀번호를 모두 입력하거나 모두 비워 주세요.")
            if settings["username"] and (not settings["server_url"] or not settings["worker_name"]):
                raise LauncherError("Server URL과 Worker 이름을 입력해 주세요.")
            self._emit("status", "Docker 확인 중")
            self._check_prerequisites()
            env = self._environment(settings["folder"], settings["model"])
            requested = settings["mode"]
            use_gpu = requested == "gpu" or (requested == "auto" and self._gpu_available())
            self._emit("log", "선택된 실행 모드: " + ("GPU" if use_gpu else "CPU"))

            command = self._compose(use_gpu) + ["up", "--build", "-d", "worker-ui"]
            result = self._command(command, env=env, check=False)
            if result.returncode and use_gpu:
                self._emit("log", "GPU 시작에 실패했습니다. CPU 모드로 자동 재시도합니다.")
                self._command(self._compose(True) + ["stop", "worker-ui", "ollama"], env=env, check=False)
                self._command(self._compose(False) + ["up", "--build", "-d", "--force-recreate", "worker-ui"], env=env)
                use_gpu = False
            elif result.returncode:
                raise LauncherError("CPU 모드 Worker 컨테이너를 시작하지 못했습니다.")

            self._wait_for_ui()
            username = settings["username"]
            password = settings["password"]
            if username and password:
                self._emit("status", "Worker 등록 중")
                self._http("POST", WORKER_UI_URL + "/api/register", {
                    "server_url": self._container_server_url(settings["server_url"]),
                    "username": username,
                    "password": password,
                    "device_name": settings["worker_name"],
                })
            else:
                self._emit("log", "계정 정보가 비어 있어 기존 Worker 등록 정보를 사용합니다.")
            self._http("POST", WORKER_UI_URL + "/api/folders", {"folders": ["/shared"]})
            self._http("POST", WORKER_UI_URL + "/api/worker/start", {})
            self.running = True
            self._emit("status", "실행 중 · " + ("GPU" if use_gpu else "CPU"))
            self._emit("log", "Worker가 시작되었습니다: " + WORKER_UI_URL)

        self._background(task)

    def stop_worker(self) -> None:
        folder_value = self.folder_var.get().strip()

        def task() -> None:
            self._emit("status", "중지 중")
            try:
                self._http("POST", WORKER_UI_URL + "/api/worker/stop", {}, timeout=10)
            except Exception:
                pass
            env = os.environ.copy()
            if folder_value:
                env["MARS_WORKER_SHARED_DIR"] = folder_value
            self._command(self._compose(False) + ["stop", "worker-ui", "ollama"], env=env, check=False)
            self.running = False
            self._emit("status", "중지됨")

        self._background(task)

    def download_model(self) -> None:
        model = self.model_var.get().strip()
        if not model:
            messagebox.showwarning("M.A.R.S Worker", "모델 이름을 입력해 주세요.")
            return

        def task() -> None:
            self._emit("status", "모델 다운로드 중")
            request = urllib.request.Request(
                "http://127.0.0.1:11434/api/pull",
                data=json.dumps({"model": model, "stream": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=3600) as response:
                for raw in response:
                    event = json.loads(raw)
                    total = event.get("total") or 0
                    completed = event.get("completed") or 0
                    percent = round(completed * 100 / total) if total else 0
                    self._emit("log", f"{event.get('status', '다운로드 중')} {percent}%")
            self._emit("status", "모델 준비 완료")
            self._emit("log", f"모델 다운로드 완료: {model}")

        self._background(task)

    def check_updates(self) -> None:
        def task() -> None:
            if not (self.base_dir / ".git").exists() or not shutil.which("git"):
                self._emit("update", "업데이트 상태: Git 설치본이 아니어서 자동 확인 불가")
                return
            origin = self._capture(["git", "remote", "get-url", "origin"])
            if origin.returncode:
                self._emit("update", "업데이트 상태: origin 저장소 없음")
                return
            local = self._capture(["git", "rev-parse", "HEAD"])
            remote = self._capture(["git", "ls-remote", "origin", "HEAD"])
            if local.returncode or remote.returncode or not remote.stdout.strip():
                self._emit("update", "업데이트 상태: 확인 실패")
                return
            remote_sha = remote.stdout.split()[0]
            if local.stdout.strip().splitlines()[-1] == remote_sha:
                self._emit("update", "업데이트 상태: 최신 버전")
            else:
                self._emit("update", "업데이트 상태: 새 버전 사용 가능")

        self._background(task)

    def _load_settings(self) -> None:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.server_var.set(data.get("server_url", self.server_var.get()))
        self.name_var.set(data.get("worker_name", self.name_var.get()))
        self.folder_var.set(data.get("shared_folder", ""))
        self.mode_var.set(data.get("mode", "auto"))
        self.model_var.set(data.get("model", DEFAULT_MODELS[0]))

    def _save_settings(self) -> None:
        data = {
            "server_url": self.server_var.get().strip(),
            "worker_name": self.name_var.get().strip(),
            "shared_folder": self.folder_var.get().strip(),
            "mode": self.mode_var.get(),
            "model": self.model_var.get().strip(),
        }
        try:
            self.settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.log(f"설정 저장 실패: {exc}")


if __name__ == "__main__":
    MarsWorkerLauncher().mainloop()
