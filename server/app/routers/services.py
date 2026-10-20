"""UC-201 서비스 생성, UC-202 서비스 수정."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import dag, directory_access, orchestrator
from ..services.generator import generate_workflow, revise_workflow


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
        try:
            directory_access.resolve_directories_by_agent(db, user.id, graph)
        except directory_access.DirectoryAccessError as e:
            raise HTTPException(422, f"디렉토리 접근 설정이 올바르지 않습니다: {e}")
        service.graph = graph
    if body.name is not None:
        service.name = body.name
    if body.description is not None:
        service.description = body.description
    db.commit()
    db.refresh(service)
    out = schemas.ServiceOut.model_validate(service)
    # 구조 오류만 저장을 막고, 나머지 문제는 저장 결과와 함께 알려 실행 전에 고치게 한다
    out.validation = orchestrator.inspect_graph_for_user(db, user.id, service.graph)
    return out


@router.post("/{service_id}/revise")
async def revise_service(
    service_id: int,
    body: schemas.ServiceRevise,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """자연어 지시로 워크플로우 수정안을 생성한다. 저장하지 않고 수정안만 반환 —
    사용자가 캔버스에서 확인 후 직접 저장한다."""
    service = _get_owned(service_id, user, db)
    try:
        revised = await revise_workflow(service.graph, body.instruction.strip())
    except Exception:
        raise HTTPException(
            503, "AI 수정에 실패했습니다. 로컬 LLM(Ollama)이 실행 중인지 확인해 주세요."
        )
    graph = {"nodes": revised["nodes"], "edges": revised["edges"]}
    try:
        dag.validate_graph(graph)
    except dag.DagError as e:
        raise HTTPException(422, f"AI가 실행 불가능한 구성을 제안했습니다. 다시 시도해 주세요: {e}")
    return {"graph": graph, "name": revised.get("name"), "description": revised.get("description")}


@router.post("/{service_id}/validate")
def validate_service(
    service_id: int,
    body: schemas.ServiceValidate | None = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 그래프 또는 편집 중인 그래프를 검사해 블록 단위 오류·경고와 실행 단계를 돌려준다."""
    service = _get_owned(service_id, user, db)
    graph = body.graph.model_dump() if body and body.graph else service.graph
    result = orchestrator.inspect_graph_for_user(
        db, user.id, graph, run_prompt=body.run_prompt if body else ""
    )
    return {**result, "reason": result["errors"][0]["message"] if result["errors"] else None}


@router.delete("/{service_id}", status_code=204)
def delete_service(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = _get_owned(service_id, user, db)
    has_history = (
        db.query(models.Execution.id)
        .filter(models.Execution.service_id == service.id)
        .first()
        is not None
    )
    if has_history:
        raise HTTPException(
            409,
            "실행 이력이 있는 서비스는 삭제할 수 없습니다. 실행 이력을 보존해 주세요.",
        )
    db.delete(service)
    db.commit()
