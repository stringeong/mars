"""실행 오케스트레이션.

- 실행 시작: 그래프 스냅샷으로 TaskRecord 들을 만들고, 선행이 없는 노드를 ready로 둔다.
- Worker 폴링: ready 작업을 하나 할당(running)한다.
- 작업 완료: 자식 노드의 선행이 모두 done이면 ready로 전환. 전부 done이면 실행 완료.
- 기기 단절: 하트비트가 끊긴 기기의 running 작업을 ready로 되돌린다 (재할당, UC-204 e203).
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import HEARTBEAT_TIMEOUT_SEC
from . import dag, directory_access


def create_tasks_for_execution(db: Session, execution: models.Execution) -> None:
    graph = execution.graph_snapshot
    parents = dag.parents_of(graph)
    directories_by_agent = directory_access.resolve_directories_by_agent(
        db, execution.user_id, graph
    )
    for node in graph.get("nodes", []):

        if node.get("type", "agent") != "agent":
            continue

        status = (
            "ready"
            if not parents[node["id"]]
            else "blocked"
        )
        
        task = models.TaskRecord(
            execution_id=execution.id,
            node_id=node["id"],
            agent_name=node.get("name", node["id"]),
            role_prompt=node.get("role_prompt", ""),
            model=node.get("model", ""),
            allowed_folders=(
                [directory.local_path for directory in directories_by_agent[node["id"]]]
                or node.get("allowed_folders", [])
            ),
            status=status,
            input_context="",
        )
        db.add(task)
    execution.status = "running"
    db.flush()



def device_is_online(device: models.Device) -> bool:
    if device.last_heartbeat is None:
        return False
    return models.utcnow() - device.last_heartbeat < timedelta(seconds=HEARTBEAT_TIMEOUT_SEC)


def reclaim_stale_tasks(db: Session, user_id: int) -> None:
    """하트비트가 끊긴 기기에 할당된 running 작업을 ready로 되돌린다."""
    rows = (
        db.query(models.TaskRecord, models.Device)
        .join(models.Execution, models.TaskRecord.execution_id == models.Execution.id)
        .join(models.Device, models.TaskRecord.assigned_device_id == models.Device.id)
        .filter(
            models.Execution.user_id == user_id,
            models.Execution.status == "running",
            models.TaskRecord.status == "running",
        )
        .all()
    )
    for task, device in rows:
        if not device_is_online(device):
            task.status = "ready"
            task.assigned_device_id = None
            task.started_at = None
    db.flush()


def claim_next_task(db: Session, device: models.Device) -> models.TaskRecord | None:
    """해당 기기(소유 사용자)의 ready 작업 하나를 할당한다.

    여러 기기가 동시에 폴링해도 같은 작업이 중복 할당되지 않도록,
    조회 후 대입이 아니라 'status=ready인 행만 갱신'하는 원자적 UPDATE로 선점한다.
    UPDATE가 0행이면 다른 기기가 먼저 가져간 것이므로 다음 후보로 넘어간다.
    """
    reclaim_stale_tasks(db, device.user_id)
    candidate_rows = (
        db.query(models.TaskRecord.id, models.TaskRecord.node_id, models.Execution.graph_snapshot)
        .join(models.Execution, models.TaskRecord.execution_id == models.Execution.id)
        .filter(
            models.Execution.user_id == device.user_id,
            models.Execution.status == "running",
            models.TaskRecord.status == "ready",
        )
        .order_by(models.TaskRecord.id)
        .limit(20)
        .all()
    )
    candidate_ids = []
    for task_id, node_id, graph_snapshot in candidate_rows:
        required_device = directory_access.required_device_by_agent(
            graph_snapshot or {}
        ).get(node_id)
        if required_device is None or required_device == device.id:
            candidate_ids.append(task_id)

    # 원자적 UPDATE로 실제 선점
    task = None
    for tid in candidate_ids:
        claimed = (
            db.query(models.TaskRecord)
            .filter(
                models.TaskRecord.id == tid,
                models.TaskRecord.status == "ready",
            )
            .update(
                {
                    "status": "running",
                    "assigned_device_id": device.id,
                    "started_at": models.utcnow(),
                },
                synchronize_session=False,
            )
        )
        if claimed:
            db.flush()
            task = db.get(models.TaskRecord, tid)
            break
    if task is None:
        return None
    # 실행 프롬프트 + 선행 출력들을 입력 컨텍스트로 구성
    execution = db.get(models.Execution, task.execution_id)
    parents = dag.parents_of(execution.graph_snapshot).get(task.node_id, [])
    parts: list[str] = []
    if execution.run_prompt:
        parts.append(f"[사용자 실행 요청]\n{execution.run_prompt}")
    if parents:
        parent_tasks = {
            t.node_id: t
            for t in db.query(models.TaskRecord)
            .filter(
                models.TaskRecord.execution_id == execution.id,
                models.TaskRecord.node_id.in_(parents),
            )
            .all()
        }
        for pid in parents:
            pt = parent_tasks.get(pid)
            if pt and pt.output:
                parts.append(f"[이전 단계: {pt.agent_name}의 결과]\n{pt.output}")
    task.input_context = "\n\n".join(parts)
    db.flush()
    return task

def complete_task(
    db: Session, task: models.TaskRecord, status: str, output: str, error: str
) -> None:
    task.status = status
    task.output = output or None
    task.error = error or None
    task.finished_at = models.utcnow()

    execution = db.get(models.Execution, task.execution_id)
    graph = execution.graph_snapshot
    tasks = {
        t.node_id: t
        for t in db.query(models.TaskRecord)
        .filter(models.TaskRecord.execution_id == execution.id)
        .all()
    }

    if status == "failed":
        # MAS 내부 오류 -> 실행 실패 처리 (UC-204 e202)
        execution.status = "failed"
        execution.error = f"{task.agent_name} 작업 실패: {error or '알 수 없는 오류'}"
        execution.finished_at = models.utcnow()
        for t in tasks.values():
            if t.status in ("blocked", "ready"):
                t.status = "failed"
                t.error = "선행 작업 실패로 취소됨"
        db.flush()
        return

    # 자식 노드 해제
    parents = dag.parents_of(graph)
    for node_id, plist in parents.items():
        t = tasks.get(node_id)
        if t and t.status == "blocked" and all(
            tasks[p].status == "done" for p in plist if p in tasks
        ):
            t.status = "ready"

    # 전부 완료되면 결과 통합 (UC-205)
    if all(t.status == "done" for t in tasks.values()):
        terminals = dag.terminal_nodes(graph)
        outputs = [
            f"## {tasks[nid].agent_name}\n\n{tasks[nid].output or ''}"
            for nid in terminals
            if nid in tasks
        ]
        execution.result = "\n\n---\n\n".join(outputs) if outputs else ""
        execution.status = "completed"
        execution.finished_at = models.utcnow()
    db.flush()


def cancel_execution(db: Session, execution: models.Execution) -> None:
    execution.status = "cancelled"
    execution.finished_at = models.utcnow()
    for t in execution.tasks:
        if t.status in ("blocked", "ready", "running"):
            t.status = "failed"
            t.error = "사용자가 실행을 중단함"
    db.flush()


def execution_progress(execution: models.Execution) -> float:
    total = len(execution.tasks)
    if total == 0:
        return 0.0
    done = sum(1 for t in execution.tasks if t.status in ("done", "failed"))
    return round(done / total * 100, 1)
