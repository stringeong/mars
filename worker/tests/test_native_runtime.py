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
    # 웹(styles.css)과 같은 토큰·사이드바 폭·글꼴을 쓰고, 영어 머리말 대신 한국어로 통일한다
    assert "--primary:#1f1f1f" in webui.HTML
    assert ".side{width:224px" in webui.HTML
    assert "'Pretendard Variable','Pretendard'" in webui.HTML
    assert "WORKER CONSOLE" not in webui.HTML
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


def test_runtime_state_update_keeps_other_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_DATA_DIR", str(tmp_path))

    runtime_state.update(account={"username": "hyunjeong"}, limits={"max_cpu_percent": 70})
    runtime_state.write(status="running", task={"task_id": 1})
    runtime_state.update(overload={"reason": "x"})

    saved = runtime_state.read()
    assert saved["account"] == {"username": "hyunjeong"}
    assert saved["limits"] == {"max_cpu_percent": 70}
    assert saved["status"] == "running" and saved["overload"] == {"reason": "x"}


def test_worker_ui_shows_state_account_and_overload_controls():
    for element in ('id="badge"', 'id="reason"', 'id="accountName"', 'id="switchAccount"', 'id="cpuOtherText"',
                    'id="idle"', 'id="overloadBanner"', 'id="webLink"', "/api/overload", "/api/resume"):
        assert element in webui.HTML


def test_web_settings_link_follows_server_address():
    assert webui.web_devices_url("https://marsflowlab.com/api") == "https://marsflowlab.com/devices"
    assert webui.web_devices_url("http://localhost:8000/") == "http://localhost:5173/devices"
    assert webui.web_devices_url("http://10.0.0.5:8000") == ""


def test_status_returns_to_login_when_registration_was_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "agent_config.json")
    monkeypatch.setattr(webui, "collect_specs", lambda: {})
    monkeypatch.setattr(webui, "collect_runtime_stats", lambda: {})
    config.save({**config.DEFAULTS, "api_key": "key", "device_name": "연구실 PC", "device_id": 3})
    runtime_state.update(account={"username": "hyunjeong", "email": "h***@gmail.com"})

    assert webui.status_payload(config.load())["account"]["username"] == "hyunjeong"

    runtime_state.write(status="unregistered")
    payload = webui.status_payload(config.load())
    assert payload["registered"] is False and payload["account"] is None
    assert "다시 로그인" in payload["notice"]
    assert config.load()["api_key"] == ""
