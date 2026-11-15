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
from ..security import hash_device_key
from ..services import directory_access, generation_jobs, orchestrator, worker_queue

router = APIRouter(prefix="/worker", tags=["worker"])

_SERVER_OWNED_SPECS = {"resource_limits", "paused_until"}


def _masked_email(email: str) -> str:
    """앞 한 글자만 남긴다: hyunjeong@gmail.com -> h***@gmail.com"""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else f"{email[:1]}***"


def get_device(
    x_device_key: str = Header(...), db: Session = Depends(get_db)
) -> models.Device:
    device = (
        db.query(models.Device)
        .filter(models.Device.api_key_hash == hash_device_key(x_device_key))
        .first()
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
        # 서버가 관리하는 값(상한 설정, 넘김 뒤 일시 중지)은 Worker가 덮어쓰지 못한다
        reported = {k: v for k, v in body["specs"].items() if k not in _SERVER_OWNED_SPECS}
        device.specs = {**(device.specs or {}), **reported}
    db.commit()
    owner = db.get(models.User, device.user_id)
    until = orchestrator.paused_until(device)
    return {
        "ok": True,
        "device_id": device.id,
        "device_name": device.name,
        # Worker 화면이 어느 계정에 연결됐는지, 지금 왜 작업을 안 받는지 보여줄 수 있게 한다
        "account": {"username": owner.username, "email": _masked_email(owner.email)} if owner else None,
        "resource_limits": (device.specs or {}).get("resource_limits") or {},
        "paused_until": until.isoformat() + "Z" if until else None,
    }


@router.post("/resume")
def resume(device: models.Device = Depends(get_device), db: Session = Depends(get_db)):
    """넘김 뒤 일시 중지를 사용자가 Worker 화면에서 바로 푼다."""
    specs = dict(device.specs or {})
    specs.pop("paused_until", None)
    device.specs = specs
    device.last_heartbeat = models.utcnow()
    db.commit()
    return {"ok": True}


@router.patch("/device", response_model=schemas.DeviceOut)
def update_own_device(
    body: schemas.DeviceUpdate,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    """Allow a Worker key to rename only the device it authenticates."""
    if body.name is None:
        raise HTTPException(422, "변경할 기기 이름을 입력하세요.")
    name = body.name.strip()
    if not name or len(name) > 128:
        raise HTTPException(422, "기기 이름은 1~128자로 입력하세요.")
    duplicate = (
        db.query(models.Device)
        .filter(
            models.Device.user_id == device.user_id,
            models.Device.name == name,
            models.Device.id != device.id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(409, "같은 이름의 기기가 이미 등록되어 있습니다.")
    device.name = name
    db.commit()
    db.refresh(device)
    specs = device.specs or {}
    return {
        "id": device.id,
        "name": device.name,
        "specs": specs,
        "resource_limits": specs.get("resource_limits") or {},
        "last_heartbeat": device.last_heartbeat,
        "online": orchestrator.device_is_online(device),
    }


@router.delete("/device", status_code=204)
def delete_own_device(
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    """Remove the authenticated Worker registration from its workspace."""
    running = (
        db.query(models.TaskRecord)
        .filter(
            models.TaskRecord.assigned_device_id == device.id,
            models.TaskRecord.status == "running",
        )
        .first()
    )
    if running:
        raise HTTPException(409, "실행 중인 작업이 있어 등록을 해제할 수 없습니다.")
    db.query(models.TaskRecord).filter(
        models.TaskRecord.assigned_device_id == device.id
    ).update({"assigned_device_id": None}, synchronize_session=False)
    db.delete(device)
    db.commit()


def _execution_payload(
    db: Session, device: models.Device, task: models.TaskRecord,
) -> schemas.WorkerTaskOut | None:
    """기존 실행 TASK를 Worker 프로토콜 payload로 변환한다."""
    execution = db.get(models.Execution, task.execution_id)
    directory_ids = task.directory_ids or []
    directory_paths = directory_access.local_paths_for_device(
        db, device.id, directory_ids
    )
    if directory_paths is None:
        # A path mapping may have been removed between claim and payload creation.
        task.status = "ready"
        task.assigned_device_id = None
        task.started_at = None
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
    return schemas.WorkerTaskOut(
        task_id=task.id,
        execution_id=task.execution_id,
        agent_name=task.agent_name,
        role_prompt=task.role_prompt,
        model=task.model or "",
        directory_paths=directory_paths,
        uploaded_files=[
            {"id": uploaded.id, "original_name": uploaded.original_name}
            for uploaded in uploaded_files
        ],
        input_context=task.input_context,
        run_prompt=execution.run_prompt if execution else "",
    )


@router.post("/work/next", response_model=schemas.WorkerWorkOut | None)
def next_work(
    response: Response,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    """일반 실행과 워크플로우 생성 중 서버 정책으로 선택한 작업 하나를 반환한다."""
    device.last_heartbeat = models.utcnow()
    claimed = worker_queue.claim_next(db, device)
    if claimed is None:
        db.commit()
        response.status_code = 204
        return None
    if claimed.kind == "generation":
        result = schemas.WorkerWorkOut(kind="generation", payload=claimed.item)
    else:
        payload = _execution_payload(db, device, claimed.item)
        if payload is None:
            db.commit()
            response.status_code = 204
            return None
        result = schemas.WorkerWorkOut(kind="execution", payload=payload.model_dump())
    db.commit()
    return result


@router.post("/tasks/next", response_model=schemas.WorkerTaskOut | None)
def next_task(
    response: Response,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    """구버전 Worker 호환용 실행 TASK endpoint."""
    device.last_heartbeat = models.utcnow()
    task = orchestrator.claim_next_task(db, device)
    if task is None:
        db.commit()
        response.status_code = 204
        return None
    payload = _execution_payload(db, device, task)
    if payload is None:
        db.commit()
        response.status_code = 204
        return None
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


@router.post("/generations/next")
def next_generation(
    response: Response,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    """사용자가 이 Worker에 맡긴 워크플로우 생성 요청 (서버 GPU 대신 Worker의 Ollama 사용)."""
    job = generation_jobs.claim_next(db, device)
    device.last_heartbeat = models.utcnow()
    db.commit()
    if job is None:
        response.status_code = 204
        return None
    return job


@router.post("/generations/{job_id}/result")
def submit_generation(
    job_id: int,
    body: dict,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    job = db.get(models.GenerationJob, job_id)
    if job is None or job.device_id != device.id:
        raise HTTPException(404, "할당된 생성 요청이 아닙니다.")
    if job.status != "running":
        # 사용자가 취소했거나 시간이 지나 실패로 정리된 요청
        raise HTTPException(409, "이미 종료된 생성 요청입니다.")
    generation_jobs.submit_result(
        db, job, device, str(body.get("content") or ""), str(body.get("error") or ""),
    )
    device.last_heartbeat = models.utcnow()
    db.commit()
    return {"ok": True, "status": job.status}


@router.post("/tasks/{task_id}/release")
def release_task(
    task_id: int,
    device: models.Device = Depends(get_device),
    db: Session = Depends(get_db),
):
    """실행 중 과부하일 때 Worker가 작업을 내려놓는다. 다른 Worker가 이어서 가져간다.

    이 기기가 나중에 보내는 결과는 할당 기기가 달라져 submit_result가 거부한다.
    """
    task = db.get(models.TaskRecord, task_id)
    if task is None or task.assigned_device_id != device.id:
        raise HTTPException(404, "할당된 작업이 아닙니다.")
    if task.status != "running":
        raise HTTPException(409, "이미 종료된 작업입니다.")
    device.last_heartbeat = models.utcnow()
    orchestrator.release_task(db, task, device)
    db.commit()
    until = orchestrator.paused_until(device)
    return {"ok": True, "paused_until": until.isoformat() + "Z" if until else None}


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
    orchestrator.complete_task(db, task, body.status, body.output, body.error, notice=body.notice)
    db.commit()
    return {"ok": True}
