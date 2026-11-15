"""실행 오케스트레이션.

- 실행 시작: 그래프 스냅샷으로 TaskRecord 들을 만들고, 선행이 없는 노드를 ready로 둔다.
- Worker 폴링: ready 작업을 하나 할당(running)한다.
- 작업 완료: 자식 노드의 선행이 모두 done이면 ready로 전환. 전부 done이면 실행 완료.
- 기기 단절: 하트비트가 끊긴 기기의 running 작업을 ready로 되돌린다 (재할당, UC-204 e203).
"""

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..config import HEARTBEAT_TIMEOUT_SEC, RELEASE_PAUSE_SEC
from . import dag, directory_access


def _node_for(graph: dict, node_id: str) -> dict:
    return next((node for node in graph.get("nodes", []) if node.get("id") == node_id), {})


def _is_approval_node(node: dict) -> bool:
    return node.get("type") == "approval"


def create_tasks_for_execution(db: Session, execution: models.Execution) -> None:
    graph = execution.graph_snapshot
    parents = dag.parents_of(graph)
    directories_by_agent = directory_access.resolve_directories_by_agent(
        db, execution.user_id, graph
    )
    for node in graph.get("nodes", []):
        if node.get("type", "agent") not in {"agent", "approval"}:
            continue
        node_id = node["id"]
        status = "ready" if not parents[node_id] else "blocked"
        if _is_approval_node(node) and status == "ready":
            status = "waiting_approval"
        task = models.TaskRecord(
            execution_id=execution.id,
            node_id=node_id,
            agent_name=node.get("name", node_id),
            role_prompt=node.get("role_prompt", node.get("message", "")),
            model=node.get("model", ""),
            directory_ids=[directory.id for directory in directories_by_agent.get(node_id, [])],
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
    result["warnings"] += _cut_input_warnings(db, user_id, graph, split_plans)
    result["splits"] = split_plans.summaries()
    return result


def _cut_input_warnings(db: Session, user_id: int, graph: dict, split_plans) -> list[dict]:
    """블록이 읽을 업로드 파일이 한 번에 읽는 상한보다 길면, 실행 전에 뒷부분이 빠진다고 알린다.

    Worker와 클라우드 블록 모두 파일 하나에서 file_context.MAX_FILE_CHARS자까지만 읽는다.
    줄·행 단위로 나눠 실행하는 블록은 조각이 상한 안에 들어오게 나누므로 해당하지 않는다.
    """
    from . import file_context, splitter
    from .transfers import is_cloud_node

    targets = []
    for node in dag._agent_nodes(graph):
        plan = split_plans.plans.get(node["id"])
        if node["id"] in split_plans.errors or (plan and plan.unit != "file"):
            continue
        file_ids = dag.input_sources(graph, node)[0]
        if file_ids:
            targets.append((node, file_ids))
    if not targets:
        return []
    wanted = {file_id for _, file_ids in targets for file_id in file_ids}
    uploads = {
        uploaded.id: uploaded
        for uploaded in db.query(models.UploadedFile)
        .filter(models.UploadedFile.user_id == user_id, models.UploadedFile.id.in_(wanted))
        .all()
    }
    warnings = []
    for node, file_ids in targets:
        for uploaded in (uploads[file_id] for file_id in file_ids if file_id in uploads):
            splittable = Path(uploaded.original_name).suffix.lower() in splitter.TEXT_SUFFIXES
            # 텍스트 파일은 글자 수가 바이트 수를 넘지 못하므로 작은 파일은 읽어 보지 않아도 된다
            if splittable and uploaded.size_bytes <= file_context.MAX_FILE_CHARS:
                continue
            text = file_context.measure_upload(uploaded)
            if text is None or not text.cut:
                continue
            size = f"{text.total:,}자" if text.exact else f"{text.total:,}자가 넘는 길이"
            rest = f" 뒤 {text.total - len(text.text):,}자는 빠져요." if text.exact else " 나머지는 빠져요."
            hint = (
                " 끝까지 읽게 하려면 '파일 나눠서 병렬 실행'을 켜세요."
                if splittable and len(file_ids) == 1 and not is_cloud_node(node) else ""
            )
            warnings.append({
                "code": "input_cut",
                "severity": "warning",
                "message": (
                    f"'{node.get('name') or node['id']}' 블록의 '{uploaded.original_name}' 파일은 {size}라서 "
                    f"앞 {len(text.text):,}자만 읽어요.{rest}{hint}"
                ),
                "node_ids": [node["id"]],
            })
    return warnings


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
        if _is_approval_node(node) or is_cloud_node(node):
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
    if not isinstance(part, dict) or part.get("unit") not in ("line", "csv", "json"):
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
    db: Session, task: models.TaskRecord, status: str, output: str, error: str, notice: str = ""
) -> None:
    task.status = status
    task.output = output or None
    task.error = error or None
    task.notice = notice.strip() or None
    task.finished_at = models.utcnow()

    execution = db.get(models.Execution, task.execution_id)
    graph = execution.graph_snapshot
    tasks = {
        item.node_id: item
        for item in db.query(models.TaskRecord)
        .filter(models.TaskRecord.execution_id == execution.id)
        .all()
    }

    if status == "failed":
        execution.status = "failed"
        execution.error = f"{task.agent_name} 작업 실패: {error or '알 수 없는 오류'}"
        execution.finished_at = models.utcnow()
        for item in tasks.values():
            if item.status in ("blocked", "ready", "waiting_approval"):
                item.status = "failed"
                item.error = "선행 작업 실패로 취소됨"
        db.flush()
        return

    parents = dag.parents_of(graph)
    for node_id, parent_ids in parents.items():
        child = tasks.get(node_id)
        if child and child.status == "blocked" and all(
            tasks[parent_id].status == "done" for parent_id in parent_ids if parent_id in tasks
        ):
            child_node = _node_for(graph, node_id)
            child.status = "waiting_approval" if _is_approval_node(child_node) else "ready"

    if all(item.status == "done" for item in tasks.values()):
        terminals = dag.result_node_ids(graph)
        outputs = [
            f"## {tasks[node_id].agent_name}\n\n{tasks[node_id].output or ''}"
            for node_id in terminals
            if node_id in tasks
        ]
        execution.result = "\n\n---\n\n".join(outputs) if outputs else ""
        execution.status = "completed"
        execution.finished_at = models.utcnow()
    db.flush()


def _descendant_node_ids(graph: dict, node_id: str) -> set[str]:
    children: dict[str, list[str]] = {}
    for source, target in dag._workflow_pairs(graph):
        children.setdefault(source, []).append(target)
    affected = {node_id}
    pending = [node_id]
    while pending:
        for child in children.get(pending.pop(), []):
            if child not in affected:
                affected.add(child)
                pending.append(child)
    return affected


def retry_task(
    db: Session, execution: models.Execution, task: models.TaskRecord, *, role_prompt: str | None = None, model: str | None = None
) -> None:
    graph = execution.graph_snapshot
    node = _node_for(graph, task.node_id)
    if _is_approval_node(node):
        raise ValueError("승인 블록은 선행 작업을 다시 실행해 주세요.")
    affected_ids = _descendant_node_ids(graph, task.node_id)
    tasks = {item.node_id: item for item in execution.tasks}
    if any(tasks[node_id].status == "running" for node_id in affected_ids if node_id in tasks):
        raise ValueError("선택한 블록 또는 뒤쪽 블록이 실행 중입니다. 완료된 뒤 다시 시도해 주세요.")
    if any(item.status == "failed" and item.node_id not in affected_ids for item in tasks.values()):
        raise ValueError("다른 분기에 실패한 작업이 있어 이 블록만 다시 실행할 수 없습니다.")

    if role_prompt is not None:
        task.role_prompt = role_prompt
        node["role_prompt"] = role_prompt
    if model is not None:
        task.model = model
        node["model"] = model

    for node_id in affected_ids:
        affected = tasks.get(node_id)
        if affected is None:
            continue
        affected.status = "blocked"
        affected.output = None
        affected.error = None
        affected.notice = None
        affected.input_context = ""
        affected.assigned_device_id = None
        affected.started_at = None
        affected.finished_at = None

    parents = dag.parents_of(graph)
    if all(tasks[parent_id].status == "done" for parent_id in parents.get(task.node_id, []) if parent_id in tasks):
        task.status = "ready"
    execution.status = "running"
    execution.result = None
    execution.error = None
    execution.finished_at = None
    db.flush()


def approve_task(db: Session, execution: models.Execution, task: models.TaskRecord) -> None:
    node = _node_for(execution.graph_snapshot, task.node_id)
    if not _is_approval_node(node) or task.status != "waiting_approval":
        raise ValueError("승인 대기 중인 검토 블록이 아닙니다.")
    complete_task(db, task, "done", "사용자가 결과를 승인했습니다.", "")


def cancel_execution(db: Session, execution: models.Execution) -> None:
    execution.status = "cancelled"
    execution.finished_at = models.utcnow()
    for t in execution.tasks:
        if t.status in ("blocked", "ready", "running", "waiting_approval"):
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
