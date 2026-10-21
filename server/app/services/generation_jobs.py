"""UC-202 서비스 생성을 사용자의 Worker가 대신 처리한다 (서버 GPU가 부족할 때).

서버는 Worker에 먼저 연결할 수 없으므로(pull 방식) 생성 요청을 대기열에 넣고, Worker가
/worker/generations/next로 가져가 자기 Ollama로 응답을 만든 뒤 결과를 보낸다. 응답 해석·구성
검증·온도를 낮춘 재시도와 워크플로우 저장은 서버 생성과 같은 규칙을 쓴다.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import models
from . import dag, worker_queue
from .generator import (
    GENERATION_TEMPERATURES,
    SYSTEM_PROMPT,
    GenerationError,
    GeneratorChoice,
    graph_from_reply,
    reply_error,
)
from .orchestrator import device_is_online

# Worker는 3초마다 대기열을 확인하므로 이 시간 안에 가져가지 않으면 꺼져 있거나 이전 버전이다.
# 다른 작업을 실행 중인 Worker는 그 작업을 마친 뒤 가져가므로 RUNNING_TIMEOUT까지 기다린다.
PENDING_TIMEOUT = timedelta(seconds=30)
RUNNING_TIMEOUT = timedelta(minutes=5)
ACTIVE = ("pending", "running")


def save_service(db: Session, user_id: int, prompt: str, graph: dict, info: dict) -> models.Service:
    """생성된 그래프를 워크플로우로 저장한다. 실행할 수 없는 구성이면 dag.DagError."""
    dag.validate_graph(graph)
    graph = dag.apply_auto_flags(graph)
    service = models.Service(
        user_id=user_id,
        name=graph.pop("name", "새 서비스"),
        description=graph.pop("description", prompt),
        graph=graph,
        generation_info=info,
    )
    db.add(service)
    db.flush()
    return service


def _choice(job: models.GenerationJob, device: models.Device | None) -> GeneratorChoice:
    return GeneratorChoice(location="worker", model=job.model, device_name=device.name if device else "")


def _fail(job: models.GenerationJob, error: GenerationError) -> None:
    job.status = "failed"
    job.error = {**error.detail(), "device_id": job.device_id, "device_name": error.choice.device_name}
    job.finished_at = models.utcnow()


def worker_busy(
    db: Session,
    device: models.Device | None,
    *,
    exclude_generation_id: int | None = None,
) -> bool:
    """Worker가 일반 실행 TASK 또는 다른 생성 작업을 처리 중인지."""
    return bool(
        device is not None
        and device_is_online(device)
        and worker_queue.has_running_work(
            db, device, exclude_generation_id=exclude_generation_id,
        )
    )


def expire(db: Session, job: models.GenerationJob) -> None:
    """가져가지 않거나 끝나지 않는 요청을 실패로 정리한다. 상태를 조회할 때 부른다."""
    if job.status not in ACTIVE:
        return
    device = db.get(models.Device, job.device_id)
    choice = _choice(job, device)
    name = choice.device_name or f"#{job.device_id}"
    now = models.utcnow()
    busy = job.status == "pending" and worker_busy(db, device)
    if job.status == "pending" and busy and now - job.queued_at > RUNNING_TIMEOUT:
        _fail(job, GenerationError(
            "connection",
            f"워커 '{name}'가 다른 작업을 실행하느라 {int(RUNNING_TIMEOUT.total_seconds() // 60)}분 안에 생성 요청을 가져가지 않았습니다.",
            choice,
        ))
    elif job.status == "pending" and not busy and now - job.queued_at > PENDING_TIMEOUT:
        _fail(job, GenerationError(
            "connection",
            f"워커 '{name}'가 {int(PENDING_TIMEOUT.total_seconds())}초 안에 생성 요청을 가져가지 않았습니다. "
            "워커가 꺼져 있거나 이 기능이 없는 이전 버전일 수 있습니다.",
            choice,
        ))
    elif job.status == "running" and (device is None or not device_is_online(device)):
        _fail(job, GenerationError("connection", f"생성 중에 워커 '{name}'의 연결이 끊겼습니다.", choice))
    elif job.status == "running" and now - job.claimed_at > RUNNING_TIMEOUT:
        _fail(job, GenerationError(
            "connection", f"워커 '{name}'의 생성 시간이 {int(RUNNING_TIMEOUT.total_seconds() // 60)}분을 넘었습니다.", choice,
        ))


def claim_next(db: Session, device: models.Device) -> dict | None:
    """이 Worker에 쌓인 생성 요청 하나를 가져간다."""
    # 사용자가 화면을 닫아 아무도 확인하지 않은 오래된 요청은 가져가지 않고 실패로 정리한다
    stale = (
        db.query(models.GenerationJob)
        .filter(
            models.GenerationJob.device_id == device.id,
            models.GenerationJob.status == "pending",
            models.GenerationJob.queued_at < models.utcnow() - RUNNING_TIMEOUT,
        )
        .all()
    )
    for job in stale:
        _fail(job, GenerationError("connection", "오래 기다린 생성 요청이라 처리하지 않았습니다.", _choice(job, device)))
    job_id = (
        db.query(models.GenerationJob.id)
        .filter(models.GenerationJob.device_id == device.id, models.GenerationJob.status == "pending")
        .order_by(models.GenerationJob.id)
        .limit(1)
        .scalar()
    )
    if job_id is None:
        return None
    claimed = (
        db.query(models.GenerationJob)
        .filter(models.GenerationJob.id == job_id, models.GenerationJob.status == "pending")
        .update({"status": "running", "claimed_at": models.utcnow()}, synchronize_session=False)
    )
    if not claimed:
        return None
    job = db.get(models.GenerationJob, job_id)
    db.refresh(job)
    return {
        "job_id": job.id,
        "model": job.model,
        "system": SYSTEM_PROMPT,
        "prompt": job.prompt,
        "temperature": GENERATION_TEMPERATURES[job.attempt - 1],
    }


def submit_result(db: Session, job: models.GenerationJob, device: models.Device, content: str, error: str) -> None:
    """Worker가 만든 응답을 해석해 워크플로우를 저장하거나, 1회 더 묻거나, 실패로 남긴다."""
    choice = _choice(job, device)
    if error:
        _fail(job, GenerationError(
            "connection", f"워커 '{device.name}'에서 모델을 실행하지 못했습니다: {error[:200]}", choice,
        ))
        return
    try:
        graph = graph_from_reply(content, job.prompt)
    except (dag.DagError, KeyError, TypeError, ValueError) as exc:
        if job.attempt < len(GENERATION_TEMPERATURES):
            job.attempt += 1
            job.status = "pending"
            job.queued_at = models.utcnow()
            job.claimed_at = None
            return
        _fail(job, reply_error(exc, choice))
        return
    info = {
        "source": "llm",
        "location": "worker",
        "provider": "ollama",
        "model": job.model,
        "device_id": device.id,
        "device_name": device.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    service = save_service(db, job.user_id, job.prompt, graph, info)
    job.status = "done"
    job.service_id = service.id
    job.finished_at = models.utcnow()


def to_out(db: Session, job: models.GenerationJob) -> dict:
    device = db.get(models.Device, job.device_id)
    return {
        "id": job.id,
        "status": job.status,
        "attempt": job.attempt,
        "device_id": job.device_id,
        "device_name": device.name if device else None,
        "model": job.model,
        "created_at": job.created_at,
        "claimed_at": job.claimed_at,
        "finished_at": job.finished_at,
        "service_id": job.service_id,
        "generation_error": job.error,
        # 다른 작업을 마친 뒤에 가져가는 중인지 (화면에 '다른 작업을 마치면 시작' 안내)
        "worker_busy": job.status == "pending" and worker_busy(
            db, device, exclude_generation_id=job.id,
        ),
    }
