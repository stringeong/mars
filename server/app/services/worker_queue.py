"""Worker가 처리할 서로 다른 작업 종류의 선택 정책.

현재 실행 블록은 TaskRecord, 워크플로우 생성은 GenerationJob에 저장한다. 이 모듈은
저장 모델과 무관한 공통 claim/busy 경계를 제공해, 나중에 WorkerTask 모델로 합칠 때
라우터와 Worker 프로토콜을 유지할 수 있게 한다.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from .. import models

WorkKind = Literal["execution", "generation"]


@dataclass(frozen=True)
class ClaimedWork:
    kind: WorkKind
    item: models.TaskRecord | dict


def has_running_work(
    db: Session,
    device: models.Device,
    *,
    exclude_generation_id: int | None = None,
) -> bool:
    """일반 실행 TASK나 워크플로우 생성 중 하나라도 이 Worker에서 실행 중인지."""
    running_task = db.query(models.TaskRecord.id).filter(
        models.TaskRecord.assigned_device_id == device.id,
        models.TaskRecord.status == "running",
    ).first()
    if running_task is not None:
        return True

    generations = db.query(models.GenerationJob.id).filter(
        models.GenerationJob.device_id == device.id,
        models.GenerationJob.status == "running",
    )
    if exclude_generation_id is not None:
        generations = generations.filter(models.GenerationJob.id != exclude_generation_id)
    return generations.first() is not None


def claim_next(db: Session, device: models.Device) -> ClaimedWork | None:
    """서버 정책에 따라 다음 작업 하나를 선점한다.

    기존 Worker의 동작과 같이 생성 요청을 실행 TASK보다 먼저 처리한다. Worker 하나는
    한 번에 한 작업만 실행하며, 서로 다른 저장 모델을 쓰는 동안에도 중복 선점을 막는다.
    """
    if has_running_work(db, device):
        return None

    # 순환 import를 피하고, 향후 공통 WorkerTask 저장소로 교체할 경계를 이 함수에 모은다.
    from . import generation_jobs, orchestrator

    generation = generation_jobs.claim_next(db, device)
    if generation is not None:
        return ClaimedWork("generation", generation)

    task = orchestrator.claim_next_task(db, device)
    return ClaimedWork("execution", task) if task is not None else None
