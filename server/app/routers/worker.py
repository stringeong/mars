"""Worker Agent 통신 프로토콜.

Worker는 기기 api_key(X-Device-Key 헤더)로 인증한다.
- POST /worker/heartbeat : 상태 보고 (사양 갱신 포함)
- POST /worker/tasks/next : ready 작업 하나 할당받기 (없으면 204)
- POST /worker/tasks/{id}/result : 작업 결과 제출
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import directory_access, orchestrator

router = APIRouter(prefix="/worker", tags=["worker"])


def get_device(
    x_device_key: str = Header(...), db: Session = Depends(get_db)
) -> models.Device:
    device = (
        db.query(models.Device).filter(models.Device.api_key == x_device_key).first()
    )
    if device is None:
        raise HTTPException(401, "기기 인증에 실패했습니다.")
    return device


@router.post("/heartbeat")
def heartbeat(
    body: dict | None = None,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    device.last_heartbeat = models.utcnow()
    if body and isinstance(body.get("specs"), dict):
        device.specs = {**(device.specs or {}), **body["specs"]}
    db.commit()
    return {"ok": True, "device_id": device.id}


@router.post("/tasks/next", response_model=schemas.WorkerTaskOut | None)
def next_task(
    response: Response,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    device.last_heartbeat = models.utcnow()
    task = orchestrator.claim_next_task(db, device)
    if task is None:
        db.commit()
        response.status_code = 204
        return None
    execution = db.get(models.Execution, task.execution_id)
    directory_ids = directory_access.task_directory_ids(task.allowed_folders)
    directory_paths = directory_access.local_paths_for_device(
        db, device.id, directory_ids
    )
    if directory_paths is None:
        # A path mapping may have been removed between claim and payload creation.
        task.status = "ready"
        task.assigned_device_id = None
        task.started_at = None
        db.commit()
        response.status_code = 204
        return None
    payload = schemas.WorkerTaskOut(
        task_id=task.id,
        execution_id=task.execution_id,
        agent_name=task.agent_name,
        role_prompt=task.role_prompt,
        model=task.model or "",
        directory_paths=directory_paths if directory_ids else task.allowed_folders or [],
        input_context=task.input_context,
        run_prompt=execution.run_prompt if execution else "",
    )
    db.commit()
    return payload


@router.post("/tasks/{task_id}/result")
def submit_result(
    task_id: int,
    body: schemas.WorkerTaskResult,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    task = db.get(models.TaskRecord, task_id)
    if task is None or task.assigned_device_id != device.id:
        raise HTTPException(404, "할당된 작업이 아닙니다.")
    if task.status != "running":
        raise HTTPException(409, "이미 종료된 작업입니다.")
    device.last_heartbeat = models.utcnow()
    orchestrator.complete_task(db, task, body.status, body.output, body.error)
    db.commit()
    return {"ok": True}
