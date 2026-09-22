"""Platform-specific writable paths for the Worker runtime."""

from __future__ import annotations

import os
from pathlib import Path


APP_DIRECTORY = Path("MarsFlowLab") / "Worker"


def data_directory() -> Path:
    """Return a user-writable directory that survives source updates."""
    configured = os.getenv("MARS_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_DIRECTORY
        return Path.home() / "AppData" / "Local" / APP_DIRECTORY
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    configured = os.getenv("MARS_CONFIG_PATH")
    if configured:
        return Path(configured).expanduser()
    return data_directory() / "agent_config.json"


def runtime_directory() -> Path:
    return data_directory() / "run"


def log_directory() -> Path:
    return data_directory() / "logs"
