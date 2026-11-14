"""Localhost-only web management screen for M.A.R.S Worker."""
import os, importlib.util, json, platform, shutil, subprocess, sys, threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import httpx
from . import config as cfg
from . import runtime_state
from .main import collect_runtime_stats, collect_specs
from .overload import worker_badge
from .webui_page import HTML
from .downloads import create_job, get_jobs, ollama_install_info, pull_model, search_library

PROCESS = None
LOGS = deque(maxlen=200)
# 로그인 화면에 한 번 보여줄 안내(등록이 해제됐을 때 등)
NOTICE = ""


def web_devices_url(server_url: str) -> str:
    """웹의 워커 설정 화면 주소. 배포 서버는 /api 앞이 웹이고, 로컬 개발은 Vite(5173)다."""
    base = server_url.rstrip("/")
    if base.endswith("/api"):
        return base[:-4] + "/devices"
    host = urlparse(base).hostname
    return "http://localhost:5173/devices" if host in {"localhost", "127.0.0.1", "::1"} else ""


def status_payload(c: dict) -> dict:
    """화면이 2초마다 읽는 상태. 등록 해제를 감지하면 인증 정보를 지워 로그인 화면으로 돌린다."""
    global NOTICE
    state = runtime_state.read()
    if state.get("status") == "unregistered" and c.get("api_key"):
        c.update(device_id=None, device_name="", api_key="")
        cfg.save(c)
        runtime_state.clear()
        state = {}
        NOTICE = "서버에서 이 워커의 등록이 해제되었습니다. 다시 로그인하세요."
        LOGS.append(NOTICE)
    registered = bool(c.get("api_key"))
    if registered:
        NOTICE = ""
    running = bool(PROCESS and PROCESS.poll() is None)
    stats = collect_runtime_stats()
    task = state.get("task") if state.get("status") == "running" else None
    return {
        "registered": registered,
        "running": running,
        "server_url": c["server_url"],
        "web_url": web_devices_url(c["server_url"]),
        "device_id": c.get("device_id"),
        "device_name": c["device_name"],
        "current_task": task,
        "badge": worker_badge(running=running, state=state, stats=stats),
        "account": state.get("account") if registered else None,
        "limits": state.get("limits") or {},
        "overload": state.get("overload") if task else None,
        "notice": NOTICE,
        "shared_folders": c.get("shared_folders", []),
        "specs": collect_specs(),
        "stats": stats,
        "logs": list(LOGS),
    }
TOOLS = ({"id":"pdf-ocr","name":"PDF & OCR","packages":["pypdf","PyMuPDF","pytesseract","Pillow"],"modules":["pypdf","fitz","pytesseract","PIL"],"binary":"tesseract"},{"id":"office","name":"Office 문서","packages":["python-docx","openpyxl","python-pptx"],"modules":["docx","openpyxl","pptx"]})

def tool_states():
    return [{**t,"installed":all(importlib.util.find_spec(m) for m in t["modules"]) and (not t.get("binary") or bool(shutil.which(t["binary"])))} for t in TOOLS]
def watch(p):
    for line in p.stdout: LOGS.append(line.rstrip())

def start_worker_process():
    global PROCESS
    if PROCESS and PROCESS.poll() is None:
        return False
    PROCESS = subprocess.Popen(
        [sys.executable, "-m", "agent", "run"],
        cwd=str(Path(__file__).parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    threading.Thread(target=watch, args=(PROCESS,), daemon=True).start()
    return True

def stop_worker_process():
    global PROCESS
    if not PROCESS or PROCESS.poll() is not None:
        return False
    PROCESS.terminate()
    try:
        PROCESS.wait(timeout=8)
    except subprocess.TimeoutExpired:
        PROCESS.kill()
        PROCESS.wait(timeout=3)
    PROCESS = None
    runtime_state.clear()
    return True

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body)
    def body(self): return json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))) or b"{}")
    def do_GET(self):
        try:
            if self.path=="/":
                b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Content-Security-Policy","default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'");self.end_headers();self.wfile.write(b);return
            c=cfg.load()
            if self.path=="/api/status":
                self.reply(status_payload(c));return
            if self.path=="/api/models": r=httpx.get(c["ollama_url"].rstrip('/')+'/api/tags',timeout=5);r.raise_for_status();self.reply(r.json());return
            if self.path=="/api/ollama/install": self.reply(ollama_install_info());return
            if self.path=="/api/jobs": self.reply({"jobs":get_jobs()});return
            if self.path.startswith("/api/models/search"):
                from urllib.parse import parse_qs
                query=parse_qs(urlparse(self.path).query).get("q",[""])[0];self.reply({"models":search_library(query)});return
            if self.path=="/api/tools": self.reply({"tools":tool_states()});return
            self.reply({"error":"Not found"},404)
        except Exception as e:self.reply({"error":str(e)},503)
    def do_POST(self):
        global PROCESS
        origin=self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in {"127.0.0.1","localhost","::1"}:self.reply({"error":"localhost만 허용됩니다."},403);return
        try:
            d=self.body();c=cfg.load()
            if self.path=="/api/register":
                server = str(d.get("server_url", "")).rstrip("/")
                user = str(d.get("username", "")).strip()
                password = str(d.get("password", "")).strip()
                if not all((server, user, password)):
                    raise ValueError("서버 주소, 아이디, 비밀번호를 입력하세요.")
                login = httpx.post(
                    server + "/auth/login",
                    data={"username": user, "password": password},
                    timeout=15,
                )
                login.raise_for_status()
                name = str(d.get("device_name", "")).strip() or platform.node() or "내 기기"
                registration = httpx.post(
                    server + "/devices",
                    json={"name": name, "specs": collect_specs()},
                    headers={"Authorization": "Bearer " + login.json()["access_token"]},
                    timeout=15,
                )
                registration.raise_for_status()
                registered = registration.json()
                was_running = bool(PROCESS and PROCESS.poll() is None)
                if was_running:
                    stop_worker_process()
                c.update(
                    server_url=server,
                    device_id=registered["id"],
                    device_name=registered["name"],
                    api_key=registered["api_key"],
                )
                cfg.save(c)
                if was_running:
                    start_worker_process()
                    LOGS.append("새 인증 키로 Worker 재시작")
                LOGS.append("기기 등록 완료: " + registered["name"])
                self.reply({"ok": True})
                return
            if self.path=="/api/settings/name":
                name=str(d.get("name","")).strip()
                if not name:raise ValueError("기기 이름을 입력하세요.")
                r=httpx.patch(c["server_url"].rstrip("/")+"/worker/device",json={"name":name},headers={"X-Device-Key":c["api_key"]},timeout=15)
                r.raise_for_status();c["device_name"]=r.json()["name"];cfg.save(c);LOGS.append("기기 이름 변경: "+c["device_name"]);self.reply({"name":c["device_name"]});return
            if self.path=="/api/logout":
                if runtime_state.read().get("status")=="running":raise ValueError("실행 중인 작업을 마친 뒤 로그아웃하세요.")
                stop_worker_process();c.update(device_id=None,device_name="",api_key="");cfg.save(c);LOGS.append("Worker 로그아웃");self.reply({"ok":True});return
            if self.path=="/api/unregister":
                if runtime_state.read().get("status")=="running":raise ValueError("실행 중인 작업을 마친 뒤 등록을 해제하세요.")
                stop_worker_process()
                r=httpx.delete(c["server_url"].rstrip("/")+"/worker/device",headers={"X-Device-Key":c["api_key"]},timeout=15)
                r.raise_for_status();c.update(device_id=None,device_name="",api_key="");cfg.save(c);LOGS.append("기기 등록 해제");self.reply({"ok":True});return
            if self.path=="/api/folders":
                folders=[]
                for raw in d.get("folders",[]):
                    p=Path(raw).expanduser().resolve()
                    if not p.is_dir():raise ValueError('존재하지 않는 디렉터리: '+str(raw))
                    if str(p) not in folders:folders.append(str(p))
                c["shared_folders"]=folders;cfg.save(c);self.reply({"folders":folders});return
            if self.path=="/api/overload":
                # 과부하 경고에 대한 선택을 Worker 프로세스가 읽어 가도록 남긴다
                decision=d.get("decision")
                if decision not in {"continue","release"}:raise ValueError("선택 값이 올바르지 않습니다.")
                overload=runtime_state.read().get("overload")
                if not isinstance(overload,dict):raise ValueError("진행 중인 과부하 경고가 없습니다.")
                runtime_state.update(overload={**overload,"decision":decision})
                LOGS.append("과부하 경고 선택: "+("다른 기기로 넘기기" if decision=="release" else "계속 실행"));self.reply({"ok":True});return
            if self.path=="/api/resume":
                r=httpx.post(c["server_url"].rstrip("/")+"/worker/resume",headers={"X-Device-Key":c["api_key"]},timeout=15)
                r.raise_for_status();runtime_state.update(paused_until=None);LOGS.append("일시 중지 해제: 다시 작업을 받습니다");self.reply({"ok":True});return
            if self.path=="/api/worker/start":
                if not c.get("api_key"):raise ValueError("먼저 Worker를 등록하세요.")
                start_worker_process()
                self.reply({"ok":True});return
            if self.path=="/api/worker/stop":
                if stop_worker_process(): LOGS.append("Worker 중지")
                self.reply({"ok":True});return
            if self.path in {"/api/models/pull","/api/models/delete"}:
                name=str(d.get("name","")).strip()
                if not name:raise ValueError("모델 이름을 입력하세요.")
                if self.path.endswith("pull"):
                    job=create_job("model",name,lambda job_id:pull_model(c["ollama_url"],name,job_id));self.reply({"job":job},202);return
                r=httpx.request("DELETE",c["ollama_url"].rstrip("/")+"/api/delete",json={"name":name},timeout=30);r.raise_for_status();self.reply({"ok":True});return
            if self.path=="/api/tools/install":
                t=next((x for x in TOOLS if x["id"]==d.get("id")),None)
                if not t:raise ValueError("승인되지 않은 Tool입니다.")
                reinstall=bool(d.get("reinstall"))
                def install(job_id):
                    if t["packages"]:
                        command=[sys.executable,"-m","pip","install"]
                        if reinstall:command.extend(["--upgrade","--force-reinstall"])
                        command.extend(t["packages"])
                        p=subprocess.run(command,capture_output=True,text=True,timeout=600)
                        if p.returncode:raise RuntimeError((p.stderr or p.stdout)[-2000:] or "패키지 설치 실패")
                    if t.get("binary") and not shutil.which(t["binary"]):raise RuntimeError(t["binary"]+" 실행 파일이 필요합니다. Docker Worker를 사용하거나 운영체제에 직접 설치하세요.")
                label=t["name"]+(" 재설치" if reinstall else " 설치")
                job=create_job("tool",label,install,tool_id=t["id"],reinstall=reinstall);self.reply({"job":job},202);return
            self.reply({"error":"Not found"},404)
        except httpx.HTTPStatusError as e:self.reply({"error":e.response.text or str(e)},400)
        except Exception as e:self.reply({"error":str(e)},400)

def serve(host='127.0.0.1',port=8765):
    if host not in {'127.0.0.1','localhost','::1'} and os.getenv('MARS_ALLOW_CONTAINER_BIND') != '1':raise ValueError('관리 UI는 localhost에만 바인딩할 수 있습니다.')
    server=ThreadingHTTPServer((host,port),Handler);print(f'M.A.R.S Worker UI: http://{host}:{port}')
    try:server.serve_forever()
    except KeyboardInterrupt:print('\n관리 UI 종료')
    finally:
        if PROCESS and PROCESS.poll() is None:PROCESS.terminate()
        server.server_close()
