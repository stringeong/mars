"""Small process-safe status snapshot consumed by the localhost Worker UI.

Worker 프로세스(`agent run`)와 관리 화면(`agent ui`)은 서로 다른 프로세스라 이 파일로 상태를 주고받는다.
- status, task: 지금 실행 중인 작업
- account, limits, paused_until: 하트비트 응답으로 받은 서버 쪽 정보
- overload: 실행 중 과부하 경고와 사용자의 선택
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from .paths import runtime_directory

_LOCK = threading.Lock()


def state_path():
    return runtime_directory() / "worker_state.json"


def read() -> dict:
    try:
        value = json.loads(state_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def update(**fields) -> None:
    """주어진 항목만 바꾸고 나머지는 그대로 둔다."""
    with _LOCK:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        payload = {**read(), **fields, "updated_at": datetime.now(timezone.utc).isoformat()}
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)


def write(*, status: str, task: dict | None = None) -> None:
    update(status=status, task=task)


def clear() -> None:
    try:
        state_path().unlink()
    except FileNotFoundError:
        pass
