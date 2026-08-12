"""Background downloads and the official Ollama library catalog."""
from __future__ import annotations

import json
import platform
import re
import threading
import uuid
from datetime import datetime
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def ollama_install_info() -> dict:
    system = platform.system().lower()
    instructions = {
        "windows": "공식 설치 프로그램을 내려받아 실행하세요.",
        "darwin": "공식 macOS 앱을 내려받아 Applications에 설치하세요.",
        "linux": "공식 Linux 설치 안내의 명령 또는 수동 설치 절차를 사용하세요.",
    }
    return {"download_url": OLLAMA_DOWNLOAD_URL, "platform": system, "instructions": instructions.get(system, "공식 다운로드 페이지에서 운영체제를 선택하세요.")}


def search_library(query: str) -> list[dict]:
    """Parse server-rendered cards from Ollama's official model library."""
    query = query.strip()
    url = f"https://ollama.com/library?q={quote_plus(query)}&sort=featured"
    response = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "MARS-Worker/1.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results, seen = [], set()
    for anchor in soup.select('a[href^="/library/"]'):
        href = anchor.get("href", "").split("?")[0].rstrip("/")
        name = href.removeprefix("/library/")
        if not name or "/" in name or name in seen:
            continue
        text = " ".join(anchor.stripped_strings)
        if not text:
            continue
        seen.add(name)
        description = text
        if description.lower().startswith(name.lower()):
            description = description[len(name):].strip()
        size_text = text
        if " Pulls" in size_text:
            size_text = size_text.rsplit(" Pulls", 1)[0].rsplit(" ", 1)[0]
        sizes = re.findall(r"(?<![\w.])(?:\d+(?:\.\d+)?(?:m|b)|\d+x\d+b)(?!\w)", size_text, re.I)
        tags = [tag for tag in ("tools", "vision", "thinking", "embedding", "cloud") if re.search(rf"\b{tag}\b", text, re.I)]
        unique_sizes = list(dict.fromkeys(sizes))
        results.append({"name": name, "description": description[:500] or "Ollama 모델", "sizes": unique_sizes, "performance": "모델 크기: " + (" · ".join(unique_sizes) if unique_sizes else "상세 페이지 참조"), "tags": tags, "url": "https://ollama.com" + href})
        if len(results) >= 30:
            break
    return results


def create_job(kind: str, label: str, target) -> dict:
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "kind": kind, "label": label, "status": "queued", "message": "대기 중", "percent": 0, "completed": 0, "total": 0, "error": "", "created_at": datetime.now().isoformat(timespec="seconds")}
    with _lock:
        _jobs[job_id] = job
    def runner():
        update_job(job_id, status="running", message="시작 중")
        try:
            target(job_id)
            update_job(job_id, status="done", message="완료", percent=100)
        except Exception as exc:
            update_job(job_id, status="failed", message="실패", error=str(exc))
    threading.Thread(target=runner, name=f"mars-{kind}-{job_id[:8]}", daemon=True).start()
    return dict(job)


def update_job(job_id: str, **values) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)


def get_jobs() -> list[dict]:
    with _lock:
        return [dict(item) for item in reversed(list(_jobs.values()))]


def pull_model(ollama_url: str, name: str, job_id: str) -> None:
    with httpx.stream("POST", ollama_url.rstrip("/") + "/api/pull", json={"model": name, "stream": True}, timeout=None) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            total, completed = int(data.get("total") or 0), int(data.get("completed") or 0)
            percent = round(completed * 100 / total, 1) if total else 0
            update_job(job_id, message=data.get("status", "다운로드 중"), total=total, completed=completed, percent=percent)
