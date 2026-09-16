from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services.credentials import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/settings", tags=["settings"])
PROVIDERS = {"openai", "anthropic", "gemini"}
PROVIDER_MODELS = {
    "openai": ["gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4.1"],
    "anthropic": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-3-5"],
    "gemini": ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-pro"],
}
DEFAULT_MODELS = {provider: choices[0] for provider, choices in PROVIDER_MODELS.items()}


def _credential(db: Session, user_id: int, provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(404, "지원하지 않는 LLM 공급자입니다.")
    return db.query(models.LLMCredential).filter_by(user_id=user_id, provider=provider).first()


def _out(provider: str, row) -> schemas.ProviderCredentialOut:
    return schemas.ProviderCredentialOut(
        provider=provider,
        configured=row is not None,
        masked_key=f"••••••{row.key_last4}" if row else "",
        has_admin_key=bool(row and row.encrypted_admin_key),
        default_model=row.default_model if row else DEFAULT_MODELS[provider],
        monthly_budget_usd=row.monthly_budget_usd if row else None,
        status=row.status if row else "unconfigured",
        last_verified_at=row.last_verified_at if row else None,
    )


@router.get("/llm-providers", response_model=list[schemas.ProviderCredentialOut])
def list_providers(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = {r.provider: r for r in db.query(models.LLMCredential).filter_by(user_id=user.id).all()}
    return [_out(provider, rows.get(provider)) for provider in sorted(PROVIDERS)]


@router.get("/llm-models")
def list_llm_models(user: models.User = Depends(get_current_user)):
    """Return the cloud model choices supported by the M.A.R.S executor."""
    return PROVIDER_MODELS


@router.put("/llm-providers/{provider}", response_model=schemas.ProviderCredentialOut)
def save_provider(provider: str, body: schemas.ProviderCredentialUpdate, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _credential(db, user.id, provider)
    if row is None and not body.api_key:
        raise HTTPException(422, "API 키를 입력해 주세요.")
    if row is None:
        row = models.LLMCredential(user_id=user.id, provider=provider, encrypted_api_key="")
        db.add(row)
    if body.api_key:
        row.encrypted_api_key = encrypt_secret(body.api_key.strip())
        row.key_last4 = body.api_key.strip()[-4:]
        row.status = "unverified"
    if body.admin_key:
        row.encrypted_admin_key = encrypt_secret(body.admin_key.strip())
    row.default_model = body.default_model.strip() or DEFAULT_MODELS[provider]
    row.monthly_budget_usd = body.monthly_budget_usd
    db.commit()
    db.refresh(row)
    return _out(provider, row)


@router.delete("/llm-providers/{provider}", status_code=204)
def delete_provider(provider: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _credential(db, user.id, provider)
    if row:
        db.delete(row)
        db.commit()


@router.post("/llm-providers/{provider}/verify", response_model=schemas.ProviderCredentialOut)
def verify_provider(provider: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _credential(db, user.id, provider)
    if row is None:
        raise HTTPException(404, "저장된 API 키가 없습니다.")
    key = decrypt_secret(row.encrypted_api_key)
    try:
        with httpx.Client(timeout=10) as client:
            if provider == "openai":
                response = client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
            elif provider == "anthropic":
                response = client.get("https://api.anthropic.com/v1/models", headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
            else:
                response = client.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        row.status = "error"
        db.commit()
        raise HTTPException(400, "API 키를 확인할 수 없습니다.") from exc
    row.status = "connected"
    row.last_verified_at = models.utcnow()
    db.commit()
    db.refresh(row)
    return _out(provider, row)


@router.get("/llm-usage", response_model=list[schemas.UsageSummaryOut])
def usage(days: int = 30, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 366)))
    rows = db.query(
        models.LLMUsage.provider,
        func.sum(models.LLMUsage.input_tokens),
        func.sum(models.LLMUsage.output_tokens),
        func.sum(models.LLMUsage.cached_tokens),
        func.count(models.LLMUsage.id),
    ).filter(models.LLMUsage.user_id == user.id, models.LLMUsage.created_at >= since).group_by(models.LLMUsage.provider).all()
    return [schemas.UsageSummaryOut(provider=p, input_tokens=i or 0, output_tokens=o or 0, cached_tokens=c or 0, requests=n) for p, i, o, c, n in rows]
