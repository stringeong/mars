import os

from agent import config


def test_save_uses_private_permissions(tmp_path, monkeypatch):
    target = tmp_path / "agent_config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", target)

    config.save({"api_key": "secret"})

    assert target.exists()
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    assert not target.with_name(target.name + ".tmp").exists()
