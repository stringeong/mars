"""Worker Agent 설정 파일 관리."""

import json
import os
from .paths import config_path

CONFIG_PATH = config_path()

DEFAULTS = {
    "server_url": "https://marsflowlab.com/api",
    "device_id": None,
    "device_name": "",
    "api_key": "",
    "shared_folders": [],
    "ollama_url": "http://localhost:11434",
    "default_model": "qwen3:4b",
    "poll_interval_sec": 3,
}

def load() -> dict:
    if CONFIG_PATH.exists():
        config = {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    else:
        config = dict(DEFAULTS)
    config["server_url"] = os.getenv("MARS_SERVER_URL", config["server_url"])
    config["ollama_url"] = os.getenv("MARS_OLLAMA_URL", config["ollama_url"])
    return config


def save(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    temporary.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, CONFIG_PATH)
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
