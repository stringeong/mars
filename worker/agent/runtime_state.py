"""Small process-safe status snapshot consumed by the localhost Worker UI."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .paths import runtime_directory


def state_path():
    return runtime_directory() / "worker_state.json"


def read() -> dict:
    try:
        value = json.loads(state_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def write(*, status: str, task: dict | None = None) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    payload = {
        "status": status,
        "task": task,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def clear() -> None:
    try:
        state_path().unlink()
    except FileNotFoundError:
        pass
