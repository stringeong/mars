"""실행 오케스트레이션.

- 실행 시작: 그래프 스냅샷으로 TaskRecord 들을 만들고, 선행이 없는 노드를 ready로 둔다.
- Worker 폴링: ready 작업을 하나 할당(running)한다.
- 작업 완료: 자식 노드의 선행이 모두 done이면 ready로 전환. 전부 done이면 실행 완료.
- 기기 단절: 하트비트가 끊긴 기기의 running 작업을 ready로 되돌린다 (재할당, UC-204 e203).
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import HEARTBEAT_TIMEOUT_SEC, RELEASE_PAUSE_SEC
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
            directory_ids=[
                directory.id for directory in directories_by_agent[node["id"]]
            ],
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


def _number(value) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def paused_until(device: models.Device):
    """작업을 다른 기기로 넘긴 뒤 새 작업을 받지 않는 시각(지났거나 없으면 None)."""
    raw = (device.specs or {}).get("paused_until")
    if not isinstance(raw, str):
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return until if until > models.utcnow() else None


def capacity_block(device: models.Device) -> tuple[str, str] | None:
    """이 기기에 지금 새 작업을 주지 않는 이유 (코드, 설명). 줄 수 있으면 None.

    CPU는 기기 전체 사용률이 아니라 M.A.R.S.(Worker·Ollama)를 뺀 '다른 프로그램' 사용률로
    판단한다. 전체 사용률로 보면 방금 끝낸 자기 작업의 부하 때문에 다음 작업을 못 받는다.
    분리 측정값을 보내지 않는 구버전 Worker는 기존처럼 전체 사용률로 본다.
    """
    specs = device.specs or {}
    limits = specs.get("resource_limits") or {}

    until = paused_until(device)
    if until is not None:
        minutes = max(1, round((until - models.utcnow()).total_seconds() / 60))
        return "paused", f"작업을 다른 기기로 넘겨 {minutes}분 동안 새 작업을 받지 않습니다."

    min_idle = _number(limits.get("min_user_idle_min"))
    idle = _number(specs.get("user_idle_sec"))
    if min_idle is not None and idle is not None and idle < min_idle * 60:
        return "user_active", f"사용자가 기기를 쓰고 있습니다. 입력이 {int(min_idle)}분 동안 없으면 작업을 받습니다."

    other_cpu = _number(specs.get("other_cpu_percent"))
    cpu = other_cpu if other_cpu is not None else _number(specs.get("cpu_percent"))
    cpu_limit = _number(limits.get("max_cpu_percent"))
    if cpu is not None and cpu_limit is not None and cpu >= cpu_limit:
        label = "다른 프로그램 CPU" if other_cpu is not None else "CPU"
        return "busy", f"{label} {round(cpu)}%가 상한 {round(cpu_limit)}% 이상입니다."

    gpu = _number(specs.get("gpu_percent"))
    gpu_limit = _number(limits.get("max_gpu_percent"))
    if gpu is not None and gpu_limit is not None and gpu >= gpu_limit:
        return "busy", f"GPU {round(gpu)}%가 상한 {round(gpu_limit)}% 이상입니다."
    return None


def device_has_capacity(device: models.Device) -> bool:
    """지금 새 작업을 줄 수 있는 기기인지(사용률 상한, 자리 비움 기준, 넘김 뒤 일시 중지)."""
    return capacity_block(device) is None


def device_state(device: models.Device, running: bool) -> tuple[str, str]:
    """기기 목록에 보여줄 상태와 이유."""
    if not device_is_online(device):
        return "offline", "Worker 프로그램이 꺼져 있거나 서버에 연결되지 않았습니다."
    if running:
        return "running", "작업을 실행하고 있습니다."
    return capacity_block(device) or ("available", "새 작업을 받을 수 있습니다.")


def release_task(db: Session, task: models.TaskRecord, device: models.Device) -> None:
    """실행 중이던 작업을 내려놓아 다른 Worker가 이어받게 하고, 넘긴 기기는 잠시 쉬게 한다.

    하트비트가 끊긴 기기의 작업을 회수할 때(reclaim_stale_tasks)와 같은 처리다.
    """
    task.status = "ready"
    task.assigned_device_id = None
    task.started_at = None
    until = models.utcnow() + timedelta(seconds=RELEASE_PAUSE_SEC)
    device.specs = {**(device.specs or {}), "paused_until": until.isoformat()}
    db.flush()


def device_has_model(device: models.Device, model: str) -> bool:
    """An empty model uses the Worker default; named models must be installed."""
    if not model:
        return True
    available = (device.specs or {}).get("models")
    return True if not isinstance(available, list) else model in available


def inspect_graph_for_user(db: Session, user_id: int, graph: dict, run_prompt: str = "", split_plans=None) -> dict:
    """dag.inspect_graph에 사용자의 Worker 모델 정보와 파일 분할 계획을 더해 구성 검사를 한다.

    결과의 splits는 분할 블록별 예상 조각(Worker 수, 조각 수, 조각별 줄 수)이다.
    실행처럼 이미 계획을 세운 곳에서는 split_plans로 넘겨 파일을 두 번 읽지 않는다.
    """
    from . import split_inputs
    from .transfers import is_cloud_node

    # 저장 이후 자동 규칙이 바뀌었거나 이전 버전 그래프여도 실행할 때와 같은 기준으로 검사한다
    graph = dag.apply_auto_flags(graph)

    devices = {
        device.id: device
        for device in db.query(models.Device).filter(models.Device.user_id == user_id).all()
    }

    def has_model(node: dict) -> bool | None:
        device = devices.get(node.get("worker_id"))
        if device is None or is_cloud_node(node):
            return None
        return device_has_model(device, node.get("model") or "")

    if split_plans is None:
        split_plans = split_inputs.plan_graph(db, user_id, graph)
    result = dag.inspect_graph(graph, run_prompt=run_prompt, has_model=has_model, split_problem=split_plans.problem)
    result["splits"] = split_plans.summaries()
    return result


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
        db.query(
            models.TaskRecord.id,
            models.TaskRecord.node_id,
            models.TaskRecord.directory_ids,
            models.TaskRecord.model,
            models.Execution.graph_snapshot,
        )
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
    for task_id, node_id, directory_ids, model, graph_snapshot in candidate_rows:
        from .transfers import is_cloud_node
        node = next((n for n in (graph_snapshot or {}).get("nodes", []) if n.get("id") == node_id), {})
        if is_cloud_node(node):
            continue
        required_device = directory_access.required_device_by_agent(
            graph_snapshot or {}
        ).get(node_id)
        local_paths = directory_access.local_paths_for_device(
            db, device.id, directory_ids or []
        )
        if (
            (required_device is None or required_device == device.id)
            and device_has_capacity(device)
            and device_has_model(device, model or "")
            and local_paths is not None
        ):
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
    populate_task_context(db, task)
    return task


def populate_task_context(db: Session, task: models.TaskRecord) -> None:
    """Build prompt context from the run prompt and completed parent outputs."""
    execution = db.get(models.Execution, task.execution_id)
    parents = dag.parents_of(execution.graph_snapshot).get(task.node_id, [])
    parts: list[str] = []
    goal = (execution.graph_snapshot or {}).get("goal")
    if goal and not parents:
        parts.append(f"[서비스 목표]\n{goal}")
    node = next(
        (item for item in (execution.graph_snapshot or {}).get("nodes", []) if item.get("id") == task.node_id),
        {},
    )
    text_input = node.get("text_input")
    if node.get("text_input_enabled") and isinstance(text_input, str) and text_input:
        parts.append(f"[텍스트 데이터 입력]\n{text_input}")
    if execution.run_prompt:
        parts.append(f"[사용자 실행 요청]\n{execution.run_prompt}")
    part_note = _split_part_note(node)
    if part_note:
        parts.append(part_note)
    if parents:
        nodes = {item.get("id"): item for item in (execution.graph_snapshot or {}).get("nodes", [])}
        parent_tasks = {t.node_id: t for t in db.query(models.TaskRecord).filter(models.TaskRecord.execution_id == execution.id, models.TaskRecord.node_id.in_(parents)).all()}
        for parent_id in parents:
            parent = parent_tasks.get(parent_id)
            if parent and parent.output:
                # 나눠서 실행한 조각의 결과에는 원본에서 맡은 범위를 함께 적는다
                label = (nodes.get(parent_id, {}).get("split_part") or {}).get("label")
                suffix = f" · {label}" if label else ""
                parts.append(f"[이전 단계: {parent.agent_name}의 결과{suffix}]\n{parent.output}")
    task.input_context = "\n\n".join(parts)
    db.flush()


def _split_part_note(node: dict) -> str:
    """조각 블록에게 자신이 원본의 어느 부분을 맡았는지 알려준다."""
    part = node.get("split_part")
    if not isinstance(part, dict) or part.get("unit") not in ("line", "csv"):
        return ""
    note = (
        f"[나눠 받은 자료]\n첨부 파일은 원본 '{part.get('source_name')}'의 {part.get('label')}입니다 "
        f"(전체 {part.get('total')}조각 중 {part.get('index')}번째). 이 범위만 처리하세요. "
        "나머지 범위는 다른 조각이 같은 방식으로 처리합니다."
    )
    if part.get("context_start"):
        note += " 파일 앞의 '참고 문맥'은 직전 조각의 끝부분이므로 이해에만 쓰고 결과에는 넣지 마세요."
    return note


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
        terminals = dag.result_node_ids(graph)
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


ACTIVE_EXECUTION = ("pending", "running")


def delete_execution(db: Session, execution: models.Execution) -> None:
    """실행 이력 하나를 지운다. 작업(TaskRecord)도 함께 지우고, 외부 LLM 사용량 기록은
    비용 집계를 위해 남기되 실행·작업 연결만 끊는다. 업로드 파일은 다른 실행이 쓸 수 있으므로 지우지 않는다."""
    task_ids = [task_id for (task_id,) in db.query(models.TaskRecord.id).filter(models.TaskRecord.execution_id == execution.id)]
    usage = db.query(models.LLMUsage).filter(models.LLMUsage.execution_id == execution.id)
    if task_ids:
        usage = db.query(models.LLMUsage).filter(
            (models.LLMUsage.execution_id == execution.id) | (models.LLMUsage.task_id.in_(task_ids))
        )
    usage.update({"execution_id": None, "task_id": None}, synchronize_session=False)
    db.query(models.TaskRecord).filter(models.TaskRecord.execution_id == execution.id).delete(synchronize_session=False)
    # 파일을 나눠 실행하며 만든 조각 파일은 이 실행에서만 쓰므로 함께 지운다
    from . import split_inputs

    split_inputs.delete_piece_files(db, execution.graph_snapshot)
    db.delete(execution)
