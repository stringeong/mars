"""실행 중 과부하 감시와 Worker 상태 배지.

작업을 실행하는 동안 '다른 프로그램'의 CPU 사용률이 상한을 넘은 채 이어지면, 기기 설정에 따라
사용자에게 묻거나(ask) 그대로 두거나(continue) 다른 기기로 넘긴다(release).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

# 순간적으로 튀는 사용량은 무시하고 이 시간(초) 동안 이어질 때만 과부하로 본다
SUSTAIN_SECONDS = 30
# 'ask'에서 사용자가 이 시간(초) 안에 고르지 않으면 계속 실행한다
ASK_TIMEOUT_SECONDS = 60


def _number(value) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class OverloadWatch:
    """작업 하나를 실행하는 동안의 과부하 판정. 하트비트 스레드에서 호출한다.

    read_state/update_state는 runtime_state, release는 서버에 작업을 내려놓는 호출이다.
    """

    def __init__(self, task_id, *, read_state, update_state, release, log=print,
                 sustain=SUSTAIN_SECONDS, ask_timeout=ASK_TIMEOUT_SECONDS, clock=time.monotonic):
        self.task_id = task_id
        self.released = False
        self._read_state = read_state
        self._update_state = update_state
        self._release = release
        self._log = log
        self._sustain = sustain
        self._ask_timeout = ask_timeout
        self._clock = clock
        self._over_since: float | None = None
        self._asked_at: float | None = None
        self._settled = False  # 이번 과부하 구간에서 이미 '계속 실행'으로 정했는지

    def observe(self, stats: dict | None) -> None:
        """하트비트 때마다 방금 잰 사용률을 넘겨받는다."""
        if self.released or not isinstance(stats, dict):
            return
        limits = self._read_state().get("limits") or {}
        limit = _number(limits.get("max_cpu_percent"))
        other = _number(stats.get("other_cpu_percent"))
        if limit is None or other is None or other < limit:
            # 상한 아래로 내려오면 경고를 거두고, 다시 넘으면 처음부터 다시 잰다
            self._over_since = None
            self._settled = False
            if self._asked_at is not None:
                self._asked_at = None
                self._update_state(overload=None)
            return
        now = self._clock()
        if self._over_since is None:
            self._over_since = now
        if now - self._over_since < self._sustain or self._settled or self._asked_at is not None:
            return
        reason = f"다른 프로그램 CPU {round(other)}%가 상한 {round(limit)}%를 넘었습니다"
        mode = limits.get("on_overload") or "ask"
        if mode == "continue":
            self._log(f"[WARN] 과부하: {reason}. 설정에 따라 계속 실행합니다.")
            self._settled = True
        elif mode == "release":
            self._do_release(f"{reason}. 설정에 따라 다른 기기로 넘깁니다.")
        else:
            self._asked_at = now
            self._log(f"[WARN] 과부하: {reason}. Worker 화면에서 계속할지 넘길지 고르세요.")
            self._update_state(overload={
                "task_id": self.task_id,
                "reason": reason,
                "deadline": time.time() + self._ask_timeout,
                "decision": None,
            })

    def poll(self) -> None:
        """사용자가 Worker 화면에서 고른 값을 확인한다. 1초마다 호출한다."""
        if self.released or self._asked_at is None:
            return
        decision = (self._read_state().get("overload") or {}).get("decision")
        if decision == "release":
            self._do_release("사용자가 다른 기기로 넘기기를 골랐습니다.")
        elif decision == "continue" or self._clock() - self._asked_at >= self._ask_timeout:
            self._log("[INFO] 과부하 경고: " + ("계속 실행을 골랐습니다." if decision == "continue" else "응답이 없어 계속 실행합니다."))
            self._asked_at = None
            self._settled = True
            self._update_state(overload=None)

    def _do_release(self, message: str) -> None:
        self._asked_at = None
        try:
            paused_until = self._release(self.task_id)
        except Exception as exc:
            self._log(f"[ERROR] 작업을 넘기지 못해 계속 실행합니다: {exc}")
            self._settled = True
            self._update_state(overload=None)
            return
        self.released = True
        self._log(f"[RELEASED] 작업 #{self.task_id}: {message}")
        self._update_state(overload=None, paused_until=paused_until)


def _remaining_minutes(paused_until, now: datetime) -> int | None:
    if not isinstance(paused_until, str):
        return None
    try:
        until = datetime.fromisoformat(paused_until.replace("Z", "+00:00"))
    except ValueError:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    seconds = (until - now).total_seconds()
    return max(1, round(seconds / 60)) if seconds > 0 else None


def worker_badge(*, running: bool, state: dict, stats: dict, now: datetime | None = None) -> dict:
    """Worker 화면에 보여줄 지금 상태와 그 이유. 서버의 작업 받기 조건과 같은 순서로 판단한다."""
    now = now or datetime.now(timezone.utc)
    limits = state.get("limits") or {}
    task = state.get("task") if state.get("status") == "running" else None
    overload = state.get("overload")
    if not running:
        return {"key": "stopped", "label": "중지됨", "reason": "Worker가 꺼져 있습니다. 시작을 누르면 작업을 받습니다."}
    if isinstance(overload, dict) and task:
        return {"key": "overload", "label": "과부하 경고", "reason": overload.get("reason") or "다른 프로그램 사용률이 상한을 넘었습니다"}
    if task:
        return {"key": "running", "label": "실행 중", "reason": f"#{task.get('task_id')} {task.get('agent_name') or '작업'}을(를) 실행하고 있습니다."}
    minutes = _remaining_minutes(state.get("paused_until"), now)
    if minutes is not None:
        return {"key": "paused", "label": f"일시 중지({minutes}분 남음)", "reason": "작업을 다른 기기로 넘겨 잠시 새 작업을 받지 않습니다."}
    min_idle = _number(limits.get("min_user_idle_min"))
    idle = _number(stats.get("user_idle_sec"))
    if min_idle is not None and idle is not None and idle < min_idle * 60:
        return {"key": "user_active", "label": "사용자 사용 중(작업 안 받음)", "reason": f"마지막 입력이 {round(idle)}초 전입니다. {int(min_idle)}분 동안 입력이 없으면 작업을 받습니다."}
    limit = _number(limits.get("max_cpu_percent"))
    other = _number(stats.get("other_cpu_percent"))
    if limit is not None and other is not None and other >= limit:
        return {"key": "busy", "label": "다른 프로그램 사용 중(작업 안 받음)", "reason": f"다른 프로그램 CPU {round(other)}%가 상한 {round(limit)}% 이상입니다."}
    gpu_limit = _number(limits.get("max_gpu_percent"))
    gpu = _number(stats.get("gpu_percent"))
    if gpu_limit is not None and gpu is not None and gpu >= gpu_limit:
        return {"key": "busy", "label": "다른 프로그램 사용 중(작업 안 받음)", "reason": f"GPU {round(gpu)}%가 상한 {round(gpu_limit)}% 이상입니다."}
    return {"key": "available", "label": "작업 가능", "reason": "새 작업을 기다리고 있습니다."}
