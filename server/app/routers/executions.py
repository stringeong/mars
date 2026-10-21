"""UC-204 실행 입력, UC-205 서비스 실행, UC-206 실행 결과 확인, UC-207 실행 이력 조회."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import dag, orchestrator, directory_access, transfers

router = APIRouter(tags=["executions"])


def _validate_uploaded_files(db: Session, user_id: int, graph: dict) -> None:
    file_ids = {
        file_id
        for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent"
        for file_id in node.get("uploaded_file_ids", [])
        if isinstance(file_id, int)
    }
    if not file_ids:
        return
    owned_ids = {
        file_id
        for (file_id,) in db.query(models.UploadedFile.id)
        .filter(
            models.UploadedFile.user_id == user_id,
            models.UploadedFile.id.in_(file_ids),
        )
        .all()
    }
    if owned_ids != file_ids:
        raise HTTPException(422, "A selected uploaded file is unavailable.")


def _run_graph(service: models.Service, inputs: schemas.RunInputs) -> dict:
    """이번 실행의 입력 파일과 최종 블록·파일 필요 자동 규칙을 반영한 그래프(슬롯은 아직 펼치지 않음)."""
    try:
        return dag.apply_auto_flags(dag.apply_run_inputs(service.graph, inputs.slots, inputs.nodes))
    except dag.DagError as e:
        raise HTTPException(422, f"실행 입력이 올바르지 않습니다: {e}")


def input_record(db: Session, user_id: int, graph: dict) -> list[dict]:
    """실행 이력에 남길 입력 파일. 파일이 나중에 삭제돼도 볼 수 있게 이름까지 저장한다."""
    agents = [n for n in graph.get("nodes", []) if n.get("type", "agent") == "agent"]
    slots = graph.get("input_slots") or []
    file_ids = {v for s in slots for v in s.get("file_ids") or []} | {v for n in agents for v in n.get("uploaded_file_ids") or []}
    directory_ids = {v for s in slots for v in s.get("directory_ids") or []}
    names = dict(
        db.query(models.UploadedFile.id, models.UploadedFile.original_name)
        .filter(models.UploadedFile.user_id == user_id, models.UploadedFile.id.in_(file_ids))
        .all()
    ) if file_ids else {}
    aliases = dict(
        db.query(models.SharedDirectory.id, models.SharedDirectory.alias)
        .filter(models.SharedDirectory.user_id == user_id, models.SharedDirectory.id.in_(directory_ids))
        .all()
    ) if directory_ids else {}

    def files(ids):
        return [{"id": v, "name": names.get(v, f"파일 #{v}")} for v in ids or [] if isinstance(v, int)]

    record = [
        {
            "kind": "slot",
            "id": slot["id"],
            "label": slot.get("description") or "사용자 파일",
            "node_ids": [n["id"] for n in agents if slot["id"] in (n.get("input_slot_ids") or [])],
            "files": files(slot.get("file_ids")),
            "directories": [{"id": v, "alias": aliases.get(v, f"디렉터리 #{v}")} for v in slot.get("directory_ids") or []],
        }
        for slot in slots
    ]
    record += [
        {
            "kind": "node",
            "id": n["id"],
            "label": n.get("name") or n["id"],
            "node_ids": [n["id"]],
            "files": files(n.get("uploaded_file_ids")),
            "directories": [],
        }
        for n in agents
        if n.get("uploaded_file_ids")
    ]
    return record


@router.post("/services/{service_id}/executions/preview")
def preview_execution(
    service_id: int,
    body: schemas.ExecutionPreview,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.get(models.Service, service_id)
    if service is None or service.user_id != user.id:
        raise HTTPException(404, "서비스를 찾을 수 없습니다.")
    graph = dag.expand_input_slots(_run_graph(service, body.input_files))
    validation = orchestrator.inspect_graph_for_user(db, user.id, graph, run_prompt=body.run_prompt)
    items = transfers.describe_transfers(graph)
    # 오류가 있으면 실행할 수 없으므로 외부 전송 동의 토큰을 발급하지 않는다
    token = (
        transfers.issue_consent(db, user.id, service.id, graph, body.run_prompt, items)
        if items and validation["valid"] else None
    )
    return {"requires_consent": bool(items), "consent_token": token, "transfers": items, "validation": validation}


@router.post(
    "/services/{service_id}/executions",
    response_model=schemas.ExecutionOut,
    status_code=201,
)
def start_execution(
    service_id: int,
    body: schemas.ExecutionCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.get(models.Service, service_id)
    if service is None or service.user_id != user.id:
        raise HTTPException(404, "서비스를 찾을 수 없습니다.")
    # 실행 프롬프트는 선택 사항이다. 입력이 전혀 없는 시작 블록은 구성 검사(no_input)가 막는다.
    # 이번 실행의 입력 파일을 반영하고 파일 슬롯을 블록 필드로 펼친 그래프로 검사·동의·스냅샷을 처리한다
    run_graph = _run_graph(service, body.input_files)
    graph = dag.expand_input_slots(run_graph)
    validation = orchestrator.inspect_graph_for_user(db, user.id, graph, run_prompt=body.run_prompt)
    if validation["errors"]:
        raise HTTPException(
            422,
            {"message": f"실행 불가능한 구성입니다: {validation['errors'][0]['message']}", "validation": validation},
        )
    if validation["warnings"] and not body.acknowledge_warnings:
        raise HTTPException(409, {"message": "구성 경고를 확인한 뒤 실행해 주세요.", "validation": validation})
    try:
        directory_access.resolve_directories_by_agent(db, user.id, graph)
    except directory_access.DirectoryAccessError as e:
        raise HTTPException(422, f"디렉토리 접근 설정이 올바르지 않습니다: {e}")

    # F2-403: 실행 전 사용 가능한 기기 확인
    _validate_uploaded_files(db, user.id, graph)
    transfer_items = transfers.describe_transfers(graph)
    if transfer_items and not transfers.consume_consent(db, body.consent_token, user.id, service.id, graph, body.run_prompt):
        raise HTTPException(428, "외부 전송 내용을 확인하고 동의해 주세요.")
    devices = db.query(models.Device).filter(models.Device.user_id == user.id).all()
    has_local_nodes = any(n.get("type", "agent") == "agent" and not transfers.is_cloud_node(n) for n in graph.get("nodes", []))
    if has_local_nodes and not any(orchestrator.device_is_online(d) for d in devices):
        raise HTTPException(409, "사용 가능한(온라인) 기기가 없습니다. Worker Agent를 실행해 주세요.")

    execution = models.Execution(
        service_id=service.id,
        user_id=user.id,
        run_prompt=body.run_prompt.strip(),
        graph_snapshot=graph,
        generation_info=service.generation_info,
        input_files=input_record(db, user.id, run_graph),
    )
    db.add(execution)
    db.flush()
    orchestrator.create_tasks_for_execution(db, execution)
    db.commit()
    db.refresh(execution)
    return _to_out(db, execution)


def _to_out(db: Session, execution: models.Execution) -> schemas.ExecutionOut:
    out = schemas.ExecutionOut.model_validate(execution)
    out.progress = orchestrator.execution_progress(execution)
    # 타임라인을 단계(열)와 의존선으로 그릴 수 있게 실행 당시 그래프에서 계산한다
    graph = execution.graph_snapshot or {}
    out.stages = dag.stages(graph)
    out.edges = [
        {"source": parent, "target": child}
        for child, parents in dag.parents_of(graph).items()
        for parent in parents
    ]
    out.final_node_ids = dag.result_node_ids(graph)
    depth = {node_id: index for index, node_ids in enumerate(out.stages) for node_id in node_ids}
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    device_ids = {task.assigned_device_id for task in out.tasks if task.assigned_device_id}
    names = dict(
        db.query(models.Device.id, models.Device.name).filter(models.Device.id.in_(device_ids)).all()
    ) if device_ids else {}
    for task in out.tasks:
        node = nodes.get(task.node_id, {})
        cloud = transfers.is_cloud_node(node)
        task.depth = depth.get(task.node_id)
        task.assigned_device_name = names.get(task.assigned_device_id)
        task.executor = "cloud" if cloud else "local"
        task.provider = transfers.provider_for(node) if cloud else None
    return out


@router.get("/executions", response_model=list[schemas.ExecutionListItem])
def list_executions(
    service_id: int | None = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Execution).filter(models.Execution.user_id == user.id)
    if service_id is not None:
        query = query.filter(models.Execution.service_id == service_id)
    rows = (
        query
        .order_by(models.Execution.created_at.desc(), models.Execution.id.desc())
        .limit(100)
        .all()
    )
    items = []
    for e in rows:
        item = schemas.ExecutionListItem.model_validate(e)
        item.service_name = e.service.name if e.service else ""
        items.append(item)
    return items


@router.get("/executions/{execution_id}", response_model=schemas.ExecutionOut)
def get_execution(
    execution_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    execution = db.get(models.Execution, execution_id)
    if execution is None or execution.user_id != user.id:
        raise HTTPException(404, "실행 이력을 찾을 수 없습니다.")  # UC-206 e401
    # 조회 시점에 끊긴 기기 작업 재할당 처리
    orchestrator.reclaim_stale_tasks(db, user.id)
    db.commit()
    db.refresh(execution)
    return _to_out(db, execution)


@router.post("/executions/{execution_id}/cancel", response_model=schemas.ExecutionOut)
def cancel_execution(
    execution_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    execution = db.get(models.Execution, execution_id)
    if execution is None or execution.user_id != user.id:
        raise HTTPException(404, "실행 이력을 찾을 수 없습니다.")
    if execution.status not in ("pending", "running"):
        raise HTTPException(409, "이미 종료된 실행입니다.")
    orchestrator.cancel_execution(db, execution)  # UC-204 s201
    db.commit()
    db.refresh(execution)
    return _to_out(db, execution)
