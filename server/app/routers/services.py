"""UC-202 서비스 생성, UC-203 서비스 수정."""

import copy

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import dag, directory_access, generation_jobs, orchestrator
from ..services.credentials import decrypt_secret
from ..services.generator import (
    GenerationError,
    GeneratorChoice,
    fallback_workflow,
    generate_workflow,
    list_local_models,
    revise_workflow,
)
from .settings import DEFAULT_MODELS, PROVIDER_MODELS


router = APIRouter(prefix="/services", tags=["services"])


@router.get("/generator-models")
async def generator_models(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """워크플로우 생성에 쓸 수 있는 모델. 외부 LLM은 API 키를 등록한 제공자만, Worker는 온라인일 때만 고를 수 있다."""
    rows = {row.provider: row for row in db.query(models.LLMCredential).filter_by(user_id=user.id).all()}
    devices = db.query(models.Device).filter_by(user_id=user.id).order_by(models.Device.id).all()
    return {
        "local": await list_local_models(),
        # 서버 GPU 대신 사용자의 Worker에서 생성할 수 있다. 온라인이고 모델이 있는 Worker를 앞에 둔다.
        "workers": sorted(
            (_worker_generator(device) for device in devices),
            key=lambda item: not (item["online"] and item["models"]),
        ),
        "cloud": [
            {
                "provider": provider,
                "configured": provider in rows,
                "status": rows[provider].status if provider in rows else "unconfigured",
                "default_model": (rows[provider].default_model if provider in rows else "") or DEFAULT_MODELS[provider],
                "models": choices,
            }
            for provider, choices in PROVIDER_MODELS.items()
        ],
    }


def _worker_generator(device: models.Device) -> dict:
    specs = device.specs or {}
    names = sorted({str(m).strip() for m in specs.get("models") or [] if isinstance(m, str) and m.strip()})
    default = specs.get("default_model") if isinstance(specs.get("default_model"), str) else ""
    return {
        "device_id": device.id,
        "name": device.name,
        "online": orchestrator.device_is_online(device),
        "models": names,
        # 기본 모델이 설치되어 있지 않으면 설치된 첫 모델을 기본으로 보여준다
        "default_model": default if default in names else (names[0] if names else ""),
    }


def _generator_choice(body: schemas.ServiceGenerate, user: models.User, db: Session) -> GeneratorChoice:
    if body.location == "local":
        return GeneratorChoice(model=body.model.strip())
    if body.provider == "ollama":
        raise HTTPException(422, "외부 LLM 제공자를 선택해 주세요.")
    credential = db.query(models.LLMCredential).filter_by(user_id=user.id, provider=body.provider).first()
    if credential is None:
        raise HTTPException(422, f"{body.provider} API 키가 등록되어 있지 않습니다. 설정에서 먼저 등록해 주세요.")
    if not body.external_transfer_ack:
        raise HTTPException(428, "생성 프롬프트가 외부 LLM으로 전송된다는 안내를 확인해 주세요.")
    try:
        api_key = decrypt_secret(credential.encrypted_api_key)
    except RuntimeError:
        raise HTTPException(422, "저장된 API 키를 읽을 수 없습니다. 설정에서 다시 등록해 주세요.")
    return GeneratorChoice(
        location="cloud",
        provider=body.provider,
        model=body.model.strip() or credential.default_model,
        api_key=api_key,
    )


@router.post("/generate", response_model=schemas.ServiceOut, status_code=201)
async def generate_service(
    body: schemas.ServiceGenerate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(422, "프롬프트가 비어 있습니다.")  # UC-202 e201
    if body.use_fallback:
        graph, info = fallback_workflow(prompt, body.fallback_reason)
    else:
        choice = _generator_choice(body, user, db)
        try:
            graph, info = await generate_workflow(prompt, choice)
        except GenerationError as e:
            # 기본 워크플로우로 바로 대체하지 않고, 원인을 보여준 뒤 사용자가 고르게 한다
            raise HTTPException(502, {"message": e.message, "generation_error": e.detail()})
        usage = info.pop("usage", None)
        if usage and choice.location == "cloud":
            db.add(models.LLMUsage(
                user_id=user.id,
                provider=choice.provider,
                model=choice.resolved_model,
                input_tokens=usage.get("input_tokens", 0) or 0,
                output_tokens=usage.get("output_tokens", 0) or 0,
                cached_tokens=usage.get("cached_tokens", 0) or 0,
            ))
    try:
        service = generation_jobs.save_service(db, user.id, prompt, graph, info)
    except dag.DagError as e:
        raise HTTPException(422, f"유효한 서비스를 생성하지 못했습니다: {e}")  # e401
    db.commit()
    db.refresh(service)
    return service


@router.post("/generation-jobs", response_model=schemas.GenerationJobOut, status_code=202)
def queue_worker_generation(
    body: schemas.GenerationJobCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """서버 GPU 대신 사용자의 Worker로 생성한다. 웹은 GET으로 상태를 확인하다가 완료되면 워크플로우로 이동한다."""
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(422, "프롬프트가 비어 있습니다.")
    device = db.get(models.Device, body.device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(404, "워커를 찾을 수 없습니다.")
    if not orchestrator.device_is_online(device):
        raise HTTPException(409, f"워커 '{device.name}'가 오프라인입니다. 워커를 실행한 뒤 다시 시도해 주세요.")
    worker = _worker_generator(device)
    model = body.model.strip() or worker["default_model"]
    if not model:
        raise HTTPException(422, f"워커 '{device.name}'에 설치된 Ollama 모델이 없습니다. 워커 화면에서 모델을 받아 주세요.")
    if worker["models"] and model not in worker["models"]:
        raise HTTPException(422, f"워커 '{device.name}'에 {model} 모델이 설치되어 있지 않습니다.")
    job = models.GenerationJob(user_id=user.id, device_id=device.id, prompt=prompt, model=model)
    db.add(job)
    db.commit()
    db.refresh(job)
    return generation_jobs.to_out(db, job)


def _get_job(job_id: int, user: models.User, db: Session) -> models.GenerationJob:
    job = db.get(models.GenerationJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "생성 요청을 찾을 수 없습니다.")
    return job


@router.get("/generation-jobs/{job_id}", response_model=schemas.GenerationJobOut)
def get_worker_generation(
    job_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_job(job_id, user, db)
    generation_jobs.expire(db, job)
    db.commit()
    return generation_jobs.to_out(db, job)


@router.post("/generation-jobs/{job_id}/cancel", response_model=schemas.GenerationJobOut)
def cancel_worker_generation(
    job_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = _get_job(job_id, user, db)
    if job.status in generation_jobs.ACTIVE:
        job.status = "canceled"
        job.finished_at = models.utcnow()
        db.commit()
    return generation_jobs.to_out(db, job)


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
        # 연결이 바뀌었을 수 있으므로 직접 지정하지 않은 최종 블록·파일 필요 값을 다시 계산한다
        graph = dag.apply_auto_flags(body.graph.model_dump())
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


@router.post("/{service_id}/duplicate", response_model=schemas.ServiceOut, status_code=201)
def duplicate_service(
    service_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 워크플로우를 그대로 복제한다. 실행 이력은 복사하지 않는다."""
    source = _get_owned(service_id, user, db)
    duplicate = models.Service(
        user_id=user.id,
        name=f"{source.name} (복사본)"[:255],
        description=source.description,
        graph=copy.deepcopy(source.graph),
        generation_info=copy.deepcopy(source.generation_info),
    )
    db.add(duplicate)
    db.commit()
    db.refresh(duplicate)
    return duplicate


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
