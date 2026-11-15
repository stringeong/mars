"""사용률 분리, 입력 유휴 시간, 실행 중 과부하 판정, 상태 배지."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from agent import idle, main, runtime_state
from agent.overload import OverloadWatch, worker_badge


class TestSplitCpu:
    def test_own_ollama_load_is_not_counted_as_other_programs(self):
        assert main.split_cpu(85.0, 80.0) == {"cpu_percent": 85.0, "mars_cpu_percent": 80.0, "other_cpu_percent": 5.0}

    def test_other_never_goes_below_zero(self):
        # 두 값을 재는 시점이 달라 M.A.R.S. 사용분이 전체보다 크게 나올 수 있다
        assert main.split_cpu(40.0, 55.0) == {"cpu_percent": 40.0, "mars_cpu_percent": 40.0, "other_cpu_percent": 0.0}

    def test_runtime_stats_report_split_and_idle(self, monkeypatch):
        monkeypatch.setattr(main.psutil, "cpu_percent", lambda: 60.0)
        monkeypatch.setattr(main, "mars_cpu_percent", lambda: 45.0)
        monkeypatch.setattr(main.idle, "user_idle_seconds", lambda: 400.0)
        monkeypatch.setattr(main, "collect_ollama_models", lambda url: [])
        stats = main.collect_runtime_stats()
        assert (stats["mars_cpu_percent"], stats["other_cpu_percent"], stats["user_idle_sec"]) == (45.0, 15.0, 400.0)


class TestUserIdle:
    def test_parses_macos_hid_idle_time(self):
        output = '    | |   "HIDIdleTime" = 2500000000\n    | |   "HIDKeyboardModifierMappingSrc" = 0\n'
        assert idle.parse_ioreg(output) == 2.5
        assert idle.parse_ioreg("no such key") is None

    def test_unmeasurable_platform_gives_none(self, monkeypatch):
        monkeypatch.setattr(idle.platform, "system", lambda: "Linux")
        monkeypatch.setattr(idle.shutil, "which", lambda name: None)
        assert idle.user_idle_seconds() is None

    def test_measurement_errors_give_none(self, monkeypatch):
        monkeypatch.setattr(idle.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(idle, "_macos", lambda: (_ for _ in ()).throw(OSError("no ioreg")))
        assert idle.user_idle_seconds() is None


class Harness:
    """시계와 상태 파일을 흉내 내어 OverloadWatch를 돌린다."""

    def __init__(self, **limits):
        self.now = 0.0
        self.state = {"limits": {"max_cpu_percent": 70, **limits}}
        self.released: list = []
        self.logs: list[str] = []
        self.release_error: Exception | None = None
        self.watch = OverloadWatch(
            7, read_state=lambda: self.state, update_state=self.state.update, release=self._release,
            log=self.logs.append, sustain=30, ask_timeout=60, clock=lambda: self.now,
        )

    def _release(self, task_id):
        if self.release_error:
            raise self.release_error
        self.released.append(task_id)
        return "2026-11-15T00:05:00Z"

    def beat(self, other_cpu, seconds=10):
        self.now += seconds
        self.watch.observe({"other_cpu_percent": other_cpu})
        self.watch.poll()


class TestOverloadWatch:
    def test_short_spike_is_ignored(self):
        h = Harness()
        for cpu in (90, 90, 40, 90, 90):  # 30초를 채우기 전에 한 번 내려간다
            h.beat(cpu)
        assert h.state.get("overload") is None and not h.released

    def test_sustained_overload_asks_and_waits_for_the_user(self):
        h = Harness()
        for _ in range(4):
            h.beat(72)
        assert h.state["overload"]["reason"] == "다른 프로그램 CPU 72%가 상한 70%를 넘었습니다"
        assert h.state["overload"]["task_id"] == 7 and not h.watch.released

    def test_user_chooses_release(self):
        h = Harness()
        for _ in range(4):
            h.beat(90)
        h.state["overload"]["decision"] = "release"
        h.now += 1
        h.watch.poll()
        assert h.released == [7] and h.watch.released
        assert h.state["overload"] is None and h.state["paused_until"] == "2026-11-15T00:05:00Z"

    def test_user_chooses_continue_and_is_not_asked_again(self):
        h = Harness()
        for _ in range(4):
            h.beat(90)
        h.state["overload"]["decision"] = "continue"
        h.watch.poll()
        for _ in range(10):
            h.beat(90)
        assert h.state["overload"] is None and not h.released

    def test_no_answer_within_a_minute_keeps_running(self):
        h = Harness()
        for _ in range(4):
            h.beat(90)
        asked = dict(h.state["overload"])
        for _ in range(7):
            h.beat(90)
        assert asked["decision"] is None and h.state["overload"] is None and not h.released
        assert any("응답이 없어" in line for line in h.logs)

    def test_warning_is_withdrawn_when_usage_drops_and_asked_again_later(self):
        h = Harness()
        for _ in range(4):
            h.beat(90)
        h.beat(20)
        assert h.state["overload"] is None
        for _ in range(4):
            h.beat(90)
        assert h.state["overload"]["decision"] is None

    def test_continue_setting_only_logs(self):
        h = Harness(on_overload="continue")
        for _ in range(6):
            h.beat(90)
        assert h.state.get("overload") is None and not h.released
        assert sum("계속 실행" in line for line in h.logs) == 1

    def test_release_setting_hands_over_without_asking(self):
        h = Harness(on_overload="release")
        for _ in range(4):
            h.beat(90)
        assert h.released == [7] and h.watch.released

    def test_failed_release_keeps_running(self):
        h = Harness(on_overload="release")
        h.release_error = httpx.ConnectError("server down")
        for _ in range(6):
            h.beat(90)
        assert not h.watch.released and any("넘기지 못해" in line for line in h.logs)

    def test_without_a_cpu_limit_nothing_happens(self):
        h = Harness()
        h.state["limits"] = {}
        for _ in range(6):
            h.beat(99)
        assert h.state.get("overload") is None and not h.released


class TestWorkerBadge:
    NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)

    def badge(self, state=None, stats=None, running=True):
        return worker_badge(running=running, state=state or {}, stats=stats or {}, now=self.NOW)

    def test_available_by_default(self):
        assert self.badge()["label"] == "작업 가능"

    def test_stopped_process(self):
        assert self.badge(running=False)["key"] == "stopped"

    def test_running_task(self):
        badge = self.badge({"status": "running", "task": {"task_id": 4, "agent_name": "로그 분석 #2"}})
        assert (badge["label"], badge["reason"]) == ("실행 중", "#4 로그 분석 #2을(를) 실행하고 있습니다.")

    def test_overload_warning_while_running(self):
        state = {"status": "running", "task": {"task_id": 4}, "overload": {"reason": "다른 프로그램 CPU 72%가 상한 70%를 넘었습니다"}}
        assert self.badge(state) == {"key": "overload", "label": "과부하 경고", "reason": "다른 프로그램 CPU 72%가 상한 70%를 넘었습니다"}

    def test_paused_after_release_shows_remaining_minutes(self):
        until = (self.NOW + timedelta(minutes=4, seconds=20)).isoformat().replace("+00:00", "Z")
        assert self.badge({"paused_until": until})["label"] == "일시 중지(4분 남음)"
        past = (self.NOW - timedelta(seconds=5)).isoformat()
        assert self.badge({"paused_until": past})["key"] == "available"

    def test_user_is_using_the_machine(self):
        state = {"limits": {"min_user_idle_min": 5}}
        assert self.badge(state, {"user_idle_sec": 60})["label"] == "사용자 사용 중(작업 안 받음)"
        assert self.badge(state, {"user_idle_sec": 400})["key"] == "available"
        assert self.badge(state, {"user_idle_sec": None})["key"] == "available"

    def test_other_programs_over_the_limit(self):
        badge = self.badge({"limits": {"max_cpu_percent": 70}}, {"other_cpu_percent": 72.4, "cpu_percent": 90})
        assert badge["reason"] == "다른 프로그램 CPU 72%가 상한 70% 이상입니다."
        # 자기 부하(Ollama)만 높으면 작업을 계속 받는다
        assert self.badge({"limits": {"max_cpu_percent": 70}}, {"other_cpu_percent": 6, "cpu_percent": 90})["key"] == "available"


class TestHeartbeatAndRelease:
    @pytest.fixture(autouse=True)
    def data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARS_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(main, "collect_runtime_stats", lambda: {"other_cpu_percent": 3.0})

    def _respond(self, monkeypatch, status, body):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(status, json=body, request=httpx.Request("POST", url))

        monkeypatch.setattr(main.httpx, "post", fake_post)
        return calls

    def test_heartbeat_keeps_account_and_limits_for_the_ui(self, monkeypatch):
        self._respond(monkeypatch, 200, {
            "ok": True, "device_id": 3, "device_name": "연구실 PC",
            "account": {"username": "hyunjeong", "email": "h***@gmail.com"},
            "resource_limits": {"max_cpu_percent": 70}, "paused_until": None,
        })
        assert main.send_heartbeat("http://server.test", {}) == {"other_cpu_percent": 3.0}
        state = runtime_state.read()
        assert state["account"]["username"] == "hyunjeong" and state["limits"] == {"max_cpu_percent": 70}

    def test_old_server_reply_is_accepted(self, monkeypatch):
        self._respond(monkeypatch, 200, {"ok": True, "device_id": 3})
        main.send_heartbeat("http://server.test", {})
        assert runtime_state.read()["account"] is None

    def test_removed_registration_raises(self, monkeypatch):
        self._respond(monkeypatch, 401, {"detail": "기기 인증에 실패했습니다."})
        with pytest.raises(main.Unregistered):
            main.send_heartbeat("http://server.test", {})

    def test_released_task_result_is_not_submitted(self, monkeypatch):
        calls = self._respond(monkeypatch, 200, {"ok": True, "paused_until": "2026-11-15T00:05:00Z"})

        def run_and_release(task, config, notes=None):
            # 실행 도중 과부하로 넘긴 상황
            state["watch"].released = True
            return "늦게 나온 결과"

        state = {}
        real_watch = main.OverloadWatch

        def make_watch(*args, **kwargs):
            state["watch"] = real_watch(*args, **kwargs)
            return state["watch"]

        monkeypatch.setattr(main, "OverloadWatch", make_watch)
        monkeypatch.setattr(main.executor, "run_task", run_and_release)
        main.process_execution_task("http://server.test", {}, {}, {"task_id": 9, "execution_id": 1, "agent_name": "분석"})
        assert not any(url.endswith("/result") for url, _ in calls)
        assert runtime_state.read()["status"] == "idle"

    def test_finished_task_reports_what_was_left_out(self, monkeypatch):
        calls = self._respond(monkeypatch, 200, {"ok": True})

        def run_with_cut_input(task, config, notes=None):
            notes.append("big.log: 전체 45,000자 중 앞 30,000자만 읽었어요. 뒤 15,000자는 빠졌어요.")
            return "결과"

        monkeypatch.setattr(main.executor, "run_task", run_with_cut_input)
        main.process_execution_task("http://server.test", {}, {}, {"task_id": 9, "execution_id": 1, "agent_name": "분석"})
        result = next(kwargs["json"] for url, kwargs in calls if url.endswith("/tasks/9/result"))
        assert result["status"] == "done" and result["output"] == "결과"
        assert result["notice"] == "big.log: 전체 45,000자 중 앞 30,000자만 읽었어요. 뒤 15,000자는 빠졌어요."

    def test_release_calls_the_server_and_returns_pause_time(self, monkeypatch):
        calls = self._respond(monkeypatch, 200, {"ok": True, "paused_until": "2026-11-15T00:05:00Z"})
        assert main.release_task("http://server.test", {"X-Device-Key": "k"}, 9) == "2026-11-15T00:05:00Z"
        assert calls[0][0] == "http://server.test/worker/tasks/9/release"
