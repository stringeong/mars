"""Worker Agent 통신 프로토콜.

Worker는 기기 api_key(X-Device-Key 헤더)로 인증한다.
- POST /worker/heartbeat : 상태 보고 (사양 갱신 포함)
- POST /worker/tasks/next : ready 작업 하나 할당받기 (없으면 204)
- POST /worker/tasks/{id}/result : 작업 결과 제출
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..config import UPLOAD_DIR
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
    agent = next(
        (node for node in (execution.graph_snapshot or {}).get("nodes", []) if node.get("id") == task.node_id),
        {},
    )
    uploaded_file_ids = [
        file_id for file_id in agent.get("uploaded_file_ids", []) if isinstance(file_id, int)
    ]
    uploaded_files = (
        db.query(models.UploadedFile)
        .filter(
            models.UploadedFile.user_id == device.user_id,
            models.UploadedFile.id.in_(uploaded_file_ids),
        )
        .all()
        if uploaded_file_ids else []
    )
    payload = schemas.WorkerTaskOut(
        task_id=task.id,
        execution_id=task.execution_id,
        agent_name=task.agent_name,
        role_prompt=task.role_prompt,
        model=task.model or "",
        directory_paths=directory_paths if directory_ids else task.allowed_folders or [],
        uploaded_files=[
            {"id": uploaded.id, "original_name": uploaded.original_name}
            for uploaded in uploaded_files
        ],
        input_context=task.input_context,
        run_prompt=execution.run_prompt if execution else "",
    )
    db.commit()
    return payload


@router.get("/files/{file_id}")
def download_uploaded_file(
    file_id: int,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    uploaded = db.get(models.UploadedFile, file_id)
    if uploaded is None or uploaded.user_id != device.user_id:
        raise HTTPException(404, "File not found.")
    path = UPLOAD_DIR / uploaded.stored_name
    if not path.is_file():
        raise HTTPException(404, "Stored file not found.")
    return FileResponse(path, filename=uploaded.original_name)


@router.post("/directory-inspections/next")
def next_directory_inspection(
    response: Response,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    inspection_id = (
        db.query(models.DirectoryInspection.id)
        .filter(
            models.DirectoryInspection.device_id == device.id,
            models.DirectoryInspection.status == "pending",
        )
        .order_by(models.DirectoryInspection.id)
        .scalar()
    )
    if inspection_id is None:
        response.status_code = 204
        return None
    claimed = (
        db.query(models.DirectoryInspection)
        .filter(
            models.DirectoryInspection.id == inspection_id,
            models.DirectoryInspection.status == "pending",
        )
        .update({"status": "running"}, synchronize_session=False)
    )
    if not claimed:
        db.commit()
        response.status_code = 204
        return None
    inspection = db.get(models.DirectoryInspection, inspection_id)
    device.last_heartbeat = models.utcnow()
    db.commit()
    return {"inspection_id": inspection.id, "local_path": inspection.local_path}


@router.post("/directory-inspections/{inspection_id}/result")
def submit_directory_inspection(
    inspection_id: int,
    body: dict,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    inspection = db.get(models.DirectoryInspection, inspection_id)
    if inspection is None or inspection.device_id != device.id:
        raise HTTPException(404, "할당된 디렉터리 검사가 아닙니다.")
    if inspection.status != "running":
        raise HTTPException(409, "이미 종료된 디렉터리 검사입니다.")
    files = body.get("files")
    inspection.files = files if isinstance(files, list) else []
    inspection.error = str(body.get("error") or "") or None
    inspection.status = "failed" if inspection.error else "done"
    inspection.finished_at = models.utcnow()
    device.last_heartbeat = models.utcnow()
    db.commit()
    return {"ok": True}


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
