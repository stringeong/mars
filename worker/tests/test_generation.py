"""서버가 맡긴 워크플로우 생성 요청 처리 — 서버 GPU 대신 이 기기의 Ollama로 생성한다.

서버·Ollama 호출(httpx.post)은 monkeypatch로 대체한다.
"""

from contextlib import nullcontext

import httpx

from agent import executor, main

SERVER = "http://server.test"
JOB = {"job_id": 7, "model": "qwen3:4b", "system": "MAS 설계", "prompt": "문서 요약", "temperature": 0.1}


def _fake_server(monkeypatch, next_response: httpx.Response):
    posts = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posts.append((url, json))
        if url.endswith("/worker/generations/next"):
            return next_response
        return httpx.Response(200, json={"ok": True})

    states = []
    monkeypatch.setattr(main.httpx, "post", fake_post)
    monkeypatch.setattr(main, "heartbeat_while_running", lambda server, headers: nullcontext())
    monkeypatch.setattr(main.runtime_state, "write", lambda **state: states.append(state))
    return posts, states


def test_generates_with_local_ollama_and_reports_reply(monkeypatch):
    posts, states = _fake_server(monkeypatch, httpx.Response(200, json=JOB))
    seen = {}

    def fake_generate(config, job):
        seen["job"] = job
        return '{"nodes": []}'

    monkeypatch.setattr(main.executor, "generate_workflow_reply", fake_generate)

    assert main.process_generation_job(SERVER, {"X-Device-Key": "k"}, {"default_model": "gemma3:4b"}) is True
    assert seen["job"] == JOB
    assert posts[-1] == (f"{SERVER}/worker/generations/7/result", {"content": '{"nodes": []}', "error": ""})
    # Worker UI에는 생성 중으로 보였다가 대기로 돌아간다
    assert states[0]["status"] == "running" and states[0]["task"]["label"] == "워크플로우 생성"
    assert states[-1] == {"status": "idle"}


def test_reports_ollama_failure_to_server(monkeypatch):
    posts, _ = _fake_server(monkeypatch, httpx.Response(200, json=JOB))

    def broken(config, job):
        raise httpx.ConnectError("Ollama가 꺼져 있음")

    monkeypatch.setattr(main.executor, "generate_workflow_reply", broken)

    assert main.process_generation_job(SERVER, {}, {}) is True
    assert posts[-1] == (f"{SERVER}/worker/generations/7/result", {"content": "", "error": "Ollama가 꺼져 있음"})


def test_moves_on_when_nothing_is_queued_or_server_is_older(monkeypatch):
    for response in (httpx.Response(204), httpx.Response(404, json={"detail": "Not Found"})):
        posts, _ = _fake_server(monkeypatch, response)
        assert main.process_generation_job(SERVER, {}, {}) is False
        assert len(posts) == 1


def test_unified_work_endpoint_dispatches_generation(monkeypatch):
    response = httpx.Response(200, json={"kind": "generation", "payload": JOB})
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: response)
    seen = {}
    monkeypatch.setattr(
        main,
        "process_generation_job",
        lambda server, headers, config, job=None: seen.setdefault("job", job) is not None,
    )

    assert main.process_next_work(SERVER, {}, {}) is True
    assert seen["job"] == JOB


def test_unified_work_endpoint_signals_legacy_server(monkeypatch):
    monkeypatch.setattr(
        main.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(404, json={"detail": "Not Found"}),
    )
    assert main.process_next_work(SERVER, {}, {}) is None


def test_generation_asks_ollama_for_json(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, payload=json)
        return httpx.Response(
            200, json={"message": {"content": '<think>…</think>{"nodes": []}'}}, request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(executor.httpx, "post", fake_post)
    reply = executor.generate_workflow_reply({"ollama_url": "http://ollama.test", "default_model": "gemma3:4b"}, {**JOB, "model": ""})

    assert reply == '{"nodes": []}'
    assert sent["url"] == "http://ollama.test/api/chat"
    payload = sent["payload"]
    assert (payload["model"], payload["format"], payload["options"]["temperature"]) == ("gemma3:4b", "json", 0.1)
    assert payload["messages"] == [{"role": "system", "content": "MAS 설계"}, {"role": "user", "content": "문서 요약"}]
