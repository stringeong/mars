"""커뮤니티: 내 워크플로우를 활용 예시로 공유하고, 다른 사람이 공유한 구성을 가져온다."""

import copy

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import community, dag

router = APIRouter(tags=["community"])


def _get_owned_service(service_id: int, user: models.User, db: Session) -> models.Service:
    service = db.get(models.Service, service_id)
    if service is None or service.user_id != user.id:
        raise HTTPException(404, "서비스를 찾을 수 없습니다.")
    return service


def _entry_for(service: models.Service, db: Session) -> models.CommunityWorkflow | None:
    return db.query(models.CommunityWorkflow).filter(models.CommunityWorkflow.service_id == service.id).first()


@router.get("/community/workflows", response_model=list[schemas.CommunityWorkflowOut])
def list_community_workflows(db: Session = Depends(get_db)):
    """로그인 없이 보는 공유 워크플로우 목록. 많이 가져간 것부터."""
    entries = (
        db.query(models.CommunityWorkflow)
        .order_by(models.CommunityWorkflow.import_count.desc(), models.CommunityWorkflow.updated_at.desc())
        .limit(100)
        .all()
    )
    return [community.to_out(entry) for entry in entries]


@router.post("/community/workflows/{entry_id}/import", response_model=schemas.ServiceOut, status_code=201)
def import_community_workflow(
    entry_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """공유된 구성을 내 워크플로우로 복사한다. 워커·파일은 비어 있으니 가져온 뒤 내 환경에 맞게 채운다."""
    entry = db.get(models.CommunityWorkflow, entry_id)
    if entry is None:
        raise HTTPException(404, "공유된 워크플로우를 찾을 수 없습니다.")
    service = models.Service(
        user_id=user.id,
        name=entry.title,
        description=entry.description,
        graph=copy.deepcopy(entry.graph),
        generation_info={
            "source": "community", "location": None, "provider": None, "model": None,
            "community_id": entry.id, "author": entry.author.username,
        },
    )
    entry.import_count = (entry.import_count or 0) + 1
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.get("/services/{service_id}/publication", response_model=schemas.CommunityWorkflowOut | None)
def get_publication(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _entry_for(_get_owned_service(service_id, user, db), db)
    return community.to_out(entry) if entry else None


@router.put("/services/{service_id}/publication", response_model=schemas.CommunityWorkflowOut)
def publish_service(
    service_id: int,
    body: schemas.CommunityPublish,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """지금 저장된 구성을 공유한다. 이미 공유했으면 최신 구성으로 바꾼다."""
    service = _get_owned_service(service_id, user, db)
    graph = community.public_graph(service.graph or {})
    try:
        dag.validate_graph(graph)
    except dag.DagError as e:
        raise HTTPException(422, f"실행할 수 없는 구성은 공유할 수 없습니다: {e}")
    entry = _entry_for(service, db)
    if entry is None:
        entry = models.CommunityWorkflow(service_id=service.id, user_id=user.id, import_count=0)
        db.add(entry)
    entry.title = body.title.strip()
    entry.description = body.description.strip()
    entry.graph = graph
    db.commit()
    db.refresh(entry)
    return community.to_out(entry)


@router.delete("/services/{service_id}/publication", status_code=204)
def unpublish_service(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _entry_for(_get_owned_service(service_id, user, db), db)
    if entry is not None:
        db.delete(entry)
        db.commit()
