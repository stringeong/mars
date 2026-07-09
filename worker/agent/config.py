"""Worker Agent 설정 파일 관리 (worker/agent_config.json)."""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "agent_config.json"

DEFAULTS = {
    "server_url": "http://localhost:8000",
    "device_id": None,
    "device_name": "",
    "api_key": "",
    "allowed_folders": [],
    "ollama_url": "http://localhost:11434",
    "default_model": "qwen3:4b",
    "poll_interval_sec": 3,
}


def load() -> dict:
    if CONFIG_PATH.exists():
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    return dict(DEFAULTS)


def save(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
