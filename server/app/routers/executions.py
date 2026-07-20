"""UC-203/204 서비스 실행, UC-205 결과 확인, UC-206 이력 조회."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import dag, orchestrator, directory_access

router = APIRouter(tags=["executions"])


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
    if not body.run_prompt.strip():
        raise HTTPException(422, "실행 프롬프트가 비어 있습니다.")  # UC-203 e301
    try:
        dag.validate_graph(service.graph)
    except dag.DagError as e:
        raise HTTPException(422, f"실행 불가능한 구성입니다: {e}")
    try:
        directory_access.resolve_directories_by_agent(db, user.id, service.graph)
    except directory_access.DirectoryAccessError as e:
        raise HTTPException(422, f"디렉토리 접근 설정이 올바르지 않습니다: {e}")

    # F2-403: 실행 전 사용 가능한 기기 확인
    devices = db.query(models.Device).filter(models.Device.user_id == user.id).all()
    if not any(orchestrator.device_is_online(d) for d in devices):
        raise HTTPException(409, "사용 가능한(온라인) 기기가 없습니다. Worker Agent를 실행해 주세요.")

    execution = models.Execution(
        service_id=service.id,
        user_id=user.id,
        run_prompt=body.run_prompt.strip(),
        graph_snapshot=service.graph,
    )
    db.add(execution)
    db.flush()
    orchestrator.create_tasks_for_execution(db, execution)
    db.commit()
    db.refresh(execution)
    return _to_out(execution)


def _to_out(execution: models.Execution) -> schemas.ExecutionOut:
    out = schemas.ExecutionOut.model_validate(execution)
    out.progress = orchestrator.execution_progress(execution)
    return out


@router.get("/executions", response_model=list[schemas.ExecutionListItem])
def list_executions(
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = (
        db.query(models.Execution)
        .filter(models.Execution.user_id == user.id)
        .order_by(models.Execution.created_at.desc())
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
    return _to_out(execution)


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
    return _to_out(execution)
