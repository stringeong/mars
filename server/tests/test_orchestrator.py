"""orchestrator 실행 생명주기 검증.

작업 생성 → 할당(선점) → 완료/실패 전파 → 결과 통합 / 취소 / 진행률.
"""

from datetime import timedelta

from app import models
from app.config import HEARTBEAT_TIMEOUT_SEC
from app.services import orchestrator
from tests.conftest import DIAMOND, LINEAR, graph_of


def tasks_by_node(db, execution):
    return {
        t.node_id: t
        for t in db.query(models.TaskRecord)
        .filter(models.TaskRecord.execution_id == execution.id)
        .all()
    }


class TestCreateTasks:
    def test_roots_ready_others_blocked(self, db, make_user, make_execution):
        execution = make_execution(make_user(), DIAMOND)
        orchestrator.create_tasks_for_execution(db, execution)

        tasks = tasks_by_node(db, execution)
        assert tasks["a"].status == "ready"
        assert tasks["b"].status == "blocked"
        assert tasks["c"].status == "blocked"
        assert tasks["d"].status == "blocked"
        assert execution.status == "running"

    def test_task_fields_copied_from_node(self, db, make_user, make_execution):
        graph = graph_of(["a"], [])
        graph["nodes"][0]["model"] = "gemma3:4b"
        graph["nodes"][0]["allowed_folders"] = ["/tmp/docs"]
        execution = make_execution(make_user(), graph)
        orchestrator.create_tasks_for_execution(db, execution)

        task = tasks_by_node(db, execution)["a"]
        assert task.agent_name == "에이전트 a"
        assert task.role_prompt == "a 역할"
        assert task.model == "gemma3:4b"
        assert task.allowed_folders == ["/tmp/docs"]


class TestDeviceOnline:
    def test_no_heartbeat_is_offline(self, make_user, make_device, db):
        device = make_device(make_user(), last_heartbeat=None)
        assert not orchestrator.device_is_online(device)

    def test_recent_heartbeat_is_online(self, make_user, make_device, db):
        device = make_device(make_user(), last_heartbeat=models.utcnow())
        assert orchestrator.device_is_online(device)

    def test_stale_heartbeat_is_offline(self, make_user, make_device, db):
        stale = models.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT_SEC + 1)
        device = make_device(make_user(), last_heartbeat=stale)
        assert not orchestrator.device_is_online(device)


class TestReclaimStaleTasks:
    def test_stale_device_task_returns_to_ready(
        self, db, make_user, make_device, make_execution
    ):
        user = make_user()
        stale = models.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT_SEC + 1)
        device = make_device(user, last_heartbeat=stale)
        execution = make_execution(user, LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)

        task = tasks_by_node(db, execution)["a"]
        task.status = "running"
        task.assigned_device_id = device.id
        task.started_at = models.utcnow()
        db.flush()

        orchestrator.reclaim_stale_tasks(db, user.id)

        assert task.status == "ready"
        assert task.assigned_device_id is None
        assert task.started_at is None

    def test_online_device_task_untouched(
        self, db, make_user, make_device, make_execution
    ):
        user = make_user()
        device = make_device(user, last_heartbeat=models.utcnow())
        execution = make_execution(user, LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)

        task = tasks_by_node(db, execution)["a"]
        task.status = "running"
        task.assigned_device_id = device.id
        db.flush()

        orchestrator.reclaim_stale_tasks(db, user.id)

        assert task.status == "running"
        assert task.assigned_device_id == device.id


class TestClaimNextTask:
    def test_claims_ready_task(self, db, make_user, make_device, make_execution):
        user = make_user()
        device = make_device(user, last_heartbeat=models.utcnow())
        execution = make_execution(user, LINEAR, run_prompt="보고서 작성")
        orchestrator.create_tasks_for_execution(db, execution)

        task = orchestrator.claim_next_task(db, device)

        assert task is not None
        assert task.node_id == "a"
        assert task.status == "running"
        assert task.assigned_device_id == device.id
        assert task.started_at is not None
        assert "[사용자 실행 요청]\n보고서 작성" in task.input_context

    def test_returns_none_when_nothing_ready(
        self, db, make_user, make_device, make_execution
    ):
        user = make_user()
        device = make_device(user, last_heartbeat=models.utcnow())
        execution = make_execution(user, LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)

        assert orchestrator.claim_next_task(db, device) is not None  # a 선점
        # b, c 는 blocked 이므로 더 줄 작업이 없어야 한다
        assert orchestrator.claim_next_task(db, device) is None

    def test_two_devices_never_get_same_task(
        self, db, make_user, make_device, make_execution
    ):
        user = make_user()
        d1 = make_device(user, name="기기1", last_heartbeat=models.utcnow())
        d2 = make_device(user, name="기기2", last_heartbeat=models.utcnow())
        # 루트가 둘인 그래프 → ready 2개
        execution = make_execution(user, graph_of(["a", "b", "c"], [("a", "c"), ("b", "c")]))
        orchestrator.create_tasks_for_execution(db, execution)

        t1 = orchestrator.claim_next_task(db, d1)
        t2 = orchestrator.claim_next_task(db, d2)

        assert t1 is not None and t2 is not None
        assert t1.id != t2.id
        assert {t1.assigned_device_id, t2.assigned_device_id} == {d1.id, d2.id}
        assert orchestrator.claim_next_task(db, d1) is None

    def test_does_not_claim_other_users_tasks(
        self, db, make_user, make_device, make_execution
    ):
        owner = make_user(email="owner@example.com", username="owner")
        intruder = make_user(email="other@example.com", username="other")
        execution = make_execution(owner, LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)
        other_device = make_device(intruder, last_heartbeat=models.utcnow())

        assert orchestrator.claim_next_task(db, other_device) is None

    def test_input_context_includes_parent_outputs(
        self, db, make_user, make_device, make_execution
    ):
        user = make_user()
        device = make_device(user, last_heartbeat=models.utcnow())
        execution = make_execution(user, DIAMOND, run_prompt="실행 요청")
        orchestrator.create_tasks_for_execution(db, execution)

        tasks = tasks_by_node(db, execution)
        tasks["a"].status = "done"
        tasks["a"].output = "a의 출력"
        tasks["b"].status = "done"
        tasks["b"].output = "b의 출력"
        tasks["c"].status = "done"
        tasks["c"].output = ""  # 출력 없는 부모는 건너뛴다
        tasks["d"].status = "ready"
        db.flush()

        task = orchestrator.claim_next_task(db, device)

        assert task.node_id == "d"
        assert "[사용자 실행 요청]\n실행 요청" in task.input_context
        assert "[이전 단계: 에이전트 b의 결과]\nb의 출력" in task.input_context
        assert "에이전트 c의 결과" not in task.input_context

    def test_reclaims_stale_tasks_before_claiming(
        self, db, make_user, make_device, make_execution
    ):
        """끊긴 기기의 running 작업이 다른 기기로 재할당되는지 (UC-204 e203)."""
        user = make_user()
        stale = models.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT_SEC + 1)
        dead = make_device(user, name="죽은 기기", last_heartbeat=stale)
        alive = make_device(user, name="산 기기", last_heartbeat=models.utcnow())
        execution = make_execution(user, LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)

        first = orchestrator.claim_next_task(db, dead)
        assert first.node_id == "a"

        task = orchestrator.claim_next_task(db, alive)

        assert task is not None
        assert task.node_id == "a"
        # 선점 UPDATE는 synchronize_session=False라 세션에 이미 로드된
        # 인스턴스에는 반영되지 않는다 — DB 값을 다시 읽어 확인한다
        db.expire_all()
        assert task.status == "running"
        assert task.assigned_device_id == alive.id


class TestCompleteTask:
    def _start(self, db, make_user, make_execution, graph, run_prompt=""):
        execution = make_execution(make_user(), graph, run_prompt=run_prompt)
        orchestrator.create_tasks_for_execution(db, execution)
        return execution, tasks_by_node(db, execution)

    def _finish(self, db, task, output="출력"):
        task.status = "running"
        db.flush()
        orchestrator.complete_task(db, task, "done", output, "")

    def test_done_unlocks_child(self, db, make_user, make_execution):
        execution, tasks = self._start(db, make_user, make_execution, LINEAR)
        self._finish(db, tasks["a"])

        assert tasks["a"].status == "done"
        assert tasks["b"].status == "ready"
        assert tasks["c"].status == "blocked"
        assert execution.status == "running"

    def test_diamond_child_waits_for_all_parents(self, db, make_user, make_execution):
        execution, tasks = self._start(db, make_user, make_execution, DIAMOND)
        self._finish(db, tasks["a"])
        self._finish(db, tasks["b"])

        # c(a의 다른 자식)가 아직 done이 아니므로 d는 blocked 유지
        assert tasks["d"].status == "blocked"

        self._finish(db, tasks["c"])
        assert tasks["d"].status == "ready"

    def test_all_done_completes_execution_with_terminal_outputs(
        self, db, make_user, make_execution
    ):
        execution, tasks = self._start(db, make_user, make_execution, DIAMOND)
        for nid in ("a", "b", "c", "d"):
            self._finish(db, tasks[nid], output=f"{nid} 결과")

        assert execution.status == "completed"
        assert execution.finished_at is not None
        # 결과는 말단 노드(d)의 출력만으로 구성된다
        assert execution.result == "## 에이전트 d\n\nd 결과"

    def test_multiple_terminals_joined_with_separator(
        self, db, make_user, make_execution
    ):
        graph = graph_of(["a", "b", "c"], [("a", "b"), ("a", "c")])
        execution, tasks = self._start(db, make_user, make_execution, graph)
        for nid in ("a", "b", "c"):
            self._finish(db, tasks[nid], output=f"{nid} 결과")

        assert execution.status == "completed"
        assert execution.result == (
            "## 에이전트 b\n\nb 결과\n\n---\n\n## 에이전트 c\n\nc 결과"
        )

    def test_failure_fails_execution_and_cancels_pending(
        self, db, make_user, make_execution
    ):
        """UC-204 e202: 작업 실패 시 실행 실패 + 대기 작업 취소."""
        execution, tasks = self._start(db, make_user, make_execution, LINEAR)
        tasks["a"].status = "running"
        db.flush()

        orchestrator.complete_task(db, tasks["a"], "failed", "", "모델 오류")

        assert execution.status == "failed"
        assert "에이전트 a" in execution.error
        assert "모델 오류" in execution.error
        assert execution.finished_at is not None
        assert tasks["b"].status == "failed"
        assert tasks["b"].error == "선행 작업 실패로 취소됨"
        assert tasks["c"].status == "failed"

    def test_failure_leaves_running_sibling_untouched(
        self, db, make_user, make_execution
    ):
        """현재 동작 고정: 실패 시 blocked/ready만 취소되고 running 형제는 그대로 남는다.

        해당 워커는 이미 failed 처리된 실행에 결과를 제출하게 된다 —
        동작을 바꾸기로 하면 이 테스트도 함께 갱신할 것.
        """
        graph = graph_of(["a", "b", "c"], [("a", "c"), ("b", "c")])
        execution, tasks = self._start(db, make_user, make_execution, graph)
        tasks["a"].status = "running"
        tasks["b"].status = "running"
        db.flush()

        orchestrator.complete_task(db, tasks["a"], "failed", "", "오류")

        assert execution.status == "failed"
        assert tasks["b"].status == "running"
        assert tasks["c"].status == "failed"

    def test_failure_without_error_message_uses_default(
        self, db, make_user, make_execution
    ):
        execution, tasks = self._start(db, make_user, make_execution, LINEAR)
        tasks["a"].status = "running"
        db.flush()

        orchestrator.complete_task(db, tasks["a"], "failed", "", "")

        assert "알 수 없는 오류" in execution.error


class TestCancelExecution:
    def test_cancel_marks_pending_tasks_failed(self, db, make_user, make_execution):
        execution = make_execution(make_user(), LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)
        tasks = tasks_by_node(db, execution)
        tasks["a"].status = "running"
        db.flush()

        orchestrator.cancel_execution(db, execution)

        assert execution.status == "cancelled"
        assert execution.finished_at is not None
        for nid in ("a", "b", "c"):
            assert tasks[nid].status == "failed"
            assert tasks[nid].error == "사용자가 실행을 중단함"

    def test_cancel_preserves_finished_tasks(self, db, make_user, make_execution):
        execution = make_execution(make_user(), LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)
        tasks = tasks_by_node(db, execution)
        tasks["a"].status = "done"
        tasks["a"].output = "완료된 출력"
        db.flush()

        orchestrator.cancel_execution(db, execution)

        assert tasks["a"].status == "done"
        assert tasks["a"].output == "완료된 출력"


class TestExecutionProgress:
    def test_no_tasks_is_zero(self, db, make_user, make_execution):
        execution = make_execution(make_user(), LINEAR)
        assert orchestrator.execution_progress(execution) == 0.0

    def test_counts_done_and_failed(self, db, make_user, make_execution):
        execution = make_execution(make_user(), LINEAR)
        orchestrator.create_tasks_for_execution(db, execution)
        tasks = tasks_by_node(db, execution)
        tasks["a"].status = "done"
        tasks["b"].status = "failed"  # 실패도 '끝난 작업'으로 진행률에 포함된다
        db.flush()
        db.refresh(execution)

        assert orchestrator.execution_progress(execution) == 66.7
