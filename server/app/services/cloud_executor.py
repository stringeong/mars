import os
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from .. import models
from ..config import CLOUD_MAX_OUTPUT_TOKENS, CLOUD_REQUEST_TIMEOUT_SEC
from .credentials import decrypt_secret
from .transfers import is_cloud_node, provider_for

TIMEOUT = httpx.Timeout(float(CLOUD_REQUEST_TIMEOUT_SEC), connect=10.0)


class CloudOutputTruncated(RuntimeError):
    """Raised instead of silently storing a response cut at its token limit."""


def cloud_output_tokens(provider: str, model: str) -> int:
    """Use the selected cloud model's native output ceiling, up to the deployment cap."""
    name = model.lower()
    if provider == "openai":
        native_limit = 32_768 if name.startswith("gpt-4.1") else 128_000
    elif provider == "anthropic":
        if "haiku-3-5" in name or "3-5-haiku" in name or "3.5-haiku" in name:
            native_limit = 8_192
        elif "opus-4-1" in name or "opus-4.1" in name:
            native_limit = 32_768
        elif "sonnet-4-5" in name or "sonnet-4.5" in name:
            native_limit = 65_536
        else:
            native_limit = 128_000
    else:
        native_limit = 65_536
    return min(CLOUD_MAX_OUTPUT_TOKENS, native_limit)


def _node_for(execution: models.Execution, node_id: str) -> dict:
    return next((n for n in execution.graph_snapshot.get("nodes", []) if n.get("id") == node_id), {})


def _call(provider: str, key: str, model: str, system: str, user: str, timeout: httpx.Timeout = TIMEOUT) -> tuple[str, dict]:
    max_output_tokens = cloud_output_tokens(provider, model)
    with httpx.Client(timeout=timeout) as client:
        if provider == "openai":
            response = client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}"}, json={"model": model, "instructions": system, "input": user, "max_output_tokens": max_output_tokens})
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "incomplete" and (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
                raise CloudOutputTruncated("OpenAI 응답이 모델의 최대 출력 토큰에서 끝났습니다.")
            text = data.get("output_text") or "".join(item.get("text", "") for output in data.get("output", []) for item in output.get("content", []) if item.get("type") == "output_text")
            usage = data.get("usage") or {}
            usage["cached_tokens"] = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
            return text, usage
        if provider == "anthropic":
            response = client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json={"model": model, "max_tokens": max_output_tokens, "system": system, "messages": [{"role": "user", "content": user}]})
            response.raise_for_status()
            data = response.json()
            if data.get("stop_reason") == "max_tokens":
                raise CloudOutputTruncated("Anthropic 응답이 모델의 최대 출력 토큰에서 끝났습니다.")
            text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
            usage = data.get("usage") or {}
            usage["cached_tokens"] = usage.get("cache_read_input_tokens", 0)
            return text, usage
        response = client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": max_output_tokens},
            },
        )
        response.raise_for_status()
        data = response.json()
        if any(candidate.get("finishReason") == "MAX_TOKENS" for candidate in data.get("candidates", [])):
            raise CloudOutputTruncated("Gemini 응답이 모델의 최대 출력 토큰에서 끝났습니다.")
        text = "".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in (candidate.get("content") or {}).get("parts", [])
        )
        metadata = data.get("usageMetadata") or {}
        return text, {
            "input_tokens": metadata.get("promptTokenCount", 0),
            "output_tokens": metadata.get("candidatesTokenCount", 0),
            "cached_tokens": metadata.get("cachedContentTokenCount", 0),
        }

CLOUD_TASK_TIMEOUT_SECONDS = max(
    CLOUD_REQUEST_TIMEOUT_SEC + 60,
    int(os.getenv("MARS_CLOUD_TASK_TIMEOUT", str(CLOUD_REQUEST_TIMEOUT_SEC + 60))),
)


def reclaim_stale_cloud_tasks(db: Session) -> None:
    cutoff = models.utcnow() - timedelta(seconds=CLOUD_TASK_TIMEOUT_SECONDS)
    stale = (
        db.query(models.TaskRecord)
        .join(models.Execution)
        .filter(
            models.TaskRecord.status == "running",
            models.TaskRecord.assigned_device_id.is_(None),
            models.TaskRecord.started_at < cutoff,
            models.Execution.status == "running",
        )
        .all()
    )
    for task in stale:
        if is_cloud_node(_node_for(task.execution, task.node_id)):
            task.status = "ready"
            task.started_at = None
    db.commit()



def claim_next_cloud_task(db: Session) -> models.TaskRecord | None:
    """Atomically claim one ready cloud task across cloud-worker processes."""
    reclaim_stale_cloud_tasks(db)
    candidates = (
        db.query(models.TaskRecord)
        .join(models.Execution)
        .filter(
            models.TaskRecord.status == "ready",
            models.Execution.status == "running",
        )
        .order_by(models.TaskRecord.id)
        .limit(50)
        .all()
    )
    for candidate in candidates:
        if not is_cloud_node(_node_for(candidate.execution, candidate.node_id)):
            continue
        claimed = (
            db.query(models.TaskRecord)
            .filter(
                models.TaskRecord.id == candidate.id,
                models.TaskRecord.status == "ready",
            )
            .update(
                {"status": "running", "started_at": models.utcnow()},
                synchronize_session=False,
            )
        )
        if claimed:
            db.commit()
            return db.get(models.TaskRecord, candidate.id)
        db.rollback()
    return None


def process_one_ready_cloud_task(db: Session) -> bool:
    from . import orchestrator
    from .file_context import cloud_file_context

    task = claim_next_cloud_task(db)
    if task is None:
        return False
    execution = task.execution
    node = _node_for(execution, task.node_id)
    provider = provider_for(node)
    credential = db.query(models.LLMCredential).filter_by(
        user_id=execution.user_id, provider=provider
    ).first()
    if credential is None:
        orchestrator.complete_task(
            db, task, "failed", "", f"{provider} API 키가 설정되지 않았습니다."
        )
        db.commit()
        return True

    orchestrator.populate_task_context(db, task)
    # 재실행에서 사용자가 고른 모델은 TaskRecord에 보관된다. 그래프 스냅샷보다
    # 작업 값을 우선해야 실제 클라우드 호출에도 변경이 반영된다.
    model = str(task.model or node.get("model") or credential.default_model)
    if model.startswith(provider + ":"):
        model = model.split(":", 1)[1]
    user_message = task.input_context or execution.run_prompt
    notes: list[str] = []
    try:
        attached = cloud_file_context(db, execution.user_id, node, notes)
        if attached:
            user_message = f"{user_message}\n\n{attached}"
        output, usage = _call(
            provider,
            decrypt_secret(credential.encrypted_api_key),
            model,
            task.role_prompt or "You are a helpful assistant.",
            user_message,
        )
        db.add(models.LLMUsage(
            user_id=execution.user_id,
            execution_id=execution.id,
            task_id=task.id,
            provider=provider,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
        ))
        orchestrator.complete_task(db, task, "done", output, "", notice="\n".join(notes))
    except Exception as exc:
        orchestrator.complete_task(
            db, task, "failed", "", f"클라우드 LLM 호출 실패: {type(exc).__name__}"
        )
    db.commit()
    return True
