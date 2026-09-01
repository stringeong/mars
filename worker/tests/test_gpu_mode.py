import subprocess

from agent import main


def test_collect_specs_reports_configured_gpu_mode(monkeypatch):
    monkeypatch.setenv("MARS_GPU_MODE", "nvidia")
    monkeypatch.setattr(main, "collect_gpu_devices", lambda: [])

    specs = main.collect_specs()

    assert specs["gpu_mode"] == "nvidia"
    assert specs["gpus"] == []


def test_runtime_stats_exposes_ollama_gpu_mode_without_local_device(monkeypatch):
    monkeypatch.setenv("MARS_GPU_MODE", "native-windows")
    monkeypatch.setattr(main, "collect_gpu_devices", lambda: [])
    monkeypatch.setattr(main.Path, "glob", lambda _self, _pattern: [])
    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    stats = main.collect_runtime_stats()

    assert stats["gpu_mode"] == "native-windows"
    assert stats["gpu_devices"] == [
        {
            "vendor": "native-windows",
            "name": "Ollama GPU (native-windows)",
            "id": "native-windows",
        }
    ]
