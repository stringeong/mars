"""작업 실행 중 하트비트 검증 — 오래 걸리는 작업이 서버에 회수되지 않아야 한다.

서버 호출(send_heartbeat)은 monkeypatch로 대체한다.
"""

import threading
import time

import httpx

from agent import main


def test_sends_heartbeats_until_task_finishes(monkeypatch):
    beats = []
    enough = threading.Event()

    def fake_send(server, headers):
        beats.append((server, headers))
        if len(beats) >= 2:
            enough.set()

    monkeypatch.setattr(main, "send_heartbeat", fake_send)
    with main.heartbeat_while_running("http://server.test", {"X-Device-Key": "k"}, interval=0.01):
        assert enough.wait(2)
    sent = len(beats)
    time.sleep(0.05)

    assert beats[0] == ("http://server.test", {"X-Device-Key": "k"})
    assert len(beats) == sent  # 작업이 끝나면 더 보내지 않는다


def test_keeps_beating_after_a_failed_heartbeat(monkeypatch):
    calls = []
    recovered = threading.Event()

    def flaky_send(server, headers):
        calls.append(server)
        if len(calls) == 1:
            raise httpx.ConnectError("server down")
        recovered.set()

    monkeypatch.setattr(main, "send_heartbeat", flaky_send)
    with main.heartbeat_while_running("http://server.test", {}, interval=0.01):
        assert recovered.wait(2)
