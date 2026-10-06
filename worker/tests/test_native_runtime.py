from agent import config, paths, runtime_state, webui


def test_data_directory_honors_environment_override(tmp_path, monkeypatch):
    target = tmp_path / "mars-worker-data"
    monkeypatch.setenv("MARS_DATA_DIR", str(target))

    assert paths.data_directory() == target
    assert paths.runtime_directory() == target / "run"
    assert paths.log_directory() == target / "logs"


def test_config_path_override_takes_precedence(tmp_path, monkeypatch):
    target = tmp_path / "custom.json"
    monkeypatch.setenv("MARS_CONFIG_PATH", str(target))

    assert paths.config_path() == target


def test_load_applies_runtime_server_and_ollama_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("MARS_SERVER_URL", "https://worker.example/api")
    monkeypatch.setenv("MARS_OLLAMA_URL", "http://127.0.0.1:9999")

    loaded = config.load()

    assert loaded["server_url"] == "https://worker.example/api"
    assert loaded["ollama_url"] == "http://127.0.0.1:9999"


def test_worker_ui_uses_shared_mars_visual_language():
    assert "https://marsflowlab.com/api" in webui.HTML
    assert "grid-template-columns:224px" in webui.HTML
    assert "WORKER CONSOLE" in webui.HTML
    assert ".worker-auth:not(.shell-hidden)+#appShell{display:none}" in webui.HTML


def test_runtime_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_DATA_DIR", str(tmp_path))

    task = {"task_id": 7, "execution_id": 3, "agent_name": "분석", "model": "qwen3:4b"}
    runtime_state.write(status="running", task=task)

    saved = runtime_state.read()
    assert saved["status"] == "running"
    assert saved["task"] == task
    assert saved["updated_at"]

    runtime_state.clear()
    assert runtime_state.read() == {}


def test_worker_ui_exposes_device_controls_and_current_task():
    assert 'id="homeDeviceName"' in webui.HTML
    assert 'id="homeTask"' in webui.HTML
    assert "/api/settings/name" in webui.HTML
    assert "/api/logout" in webui.HTML
    assert "/api/unregister" in webui.HTML
