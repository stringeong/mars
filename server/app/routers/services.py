"""UC-201 서비스 생성, UC-202 서비스 수정."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import dag
from ..services.generator import generate_workflow

router = APIRouter(prefix="/services", tags=["services"])


@router.post("/generate", response_model=schemas.ServiceOut, status_code=201)
async def generate_service(
    body: schemas.ServiceGenerate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.prompt.strip():
        raise HTTPException(422, "프롬프트가 비어 있습니다.")  # UC-201 e201
    graph, source = await generate_workflow(body.prompt.strip())
    try:
        dag.validate_graph(graph)
    except dag.DagError as e:
        raise HTTPException(422, f"유효한 서비스를 생성하지 못했습니다: {e}")  # e401
    service = models.Service(
        user_id=user.id,
        name=graph.pop("name", "새 서비스"),
        description=graph.pop("description", body.prompt.strip()),
        graph=graph,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.get("", response_model=list[schemas.ServiceOut])
def list_services(
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.query(models.Service)
        .filter(models.Service.user_id == user.id)
        .order_by(models.Service.updated_at.desc())
        .all()
    )


def _get_owned(service_id: int, user: models.User, db: Session) -> models.Service:
    service = db.get(models.Service, service_id)
    if service is None or service.user_id != user.id:
        raise HTTPException(404, "서비스를 찾을 수 없습니다.")
    return service


@router.get("/{service_id}", response_model=schemas.ServiceOut)
def get_service(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_owned(service_id, user, db)


@router.put("/{service_id}", response_model=schemas.ServiceOut)
def update_service(
    service_id: int,
    body: schemas.ServiceUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = _get_owned(service_id, user, db)
    if body.graph is not None:
        graph = body.graph.model_dump()
        try:
            dag.validate_graph(graph)  # UC-202 e301 실행 불가 구성 차단
        except dag.DagError as e:
            raise HTTPException(422, f"실행 불가능한 구성입니다: {e}")
        service.graph = graph
    if body.name is not None:
        service.name = body.name
    if body.description is not None:
        service.description = body.description
    db.commit()
    db.refresh(service)
    return service


@router.post("/{service_id}/validate")
def validate_service(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = _get_owned(service_id, user, db)
    try:
        order = dag.validate_graph(service.graph)
    except dag.DagError as e:
        return {"valid": False, "reason": str(e)}
    return {"valid": True, "order": order}


@router.delete("/{service_id}", status_code=204)
def delete_service(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = _get_owned(service_id, user, db)
    db.delete(service)
    db.commit()
