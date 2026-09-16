import hashlib
import json
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import models
from . import dag


def is_cloud_node(node: dict) -> bool:
    return node.get("executor") == "cloud" or node.get("provider") in {"openai", "anthropic", "gemini"}


def provider_for(node: dict) -> str:
    provider = node.get("provider")
    if provider in {"openai", "anthropic", "gemini"}:
        return provider
    model = str(node.get("model") or "")
    return model.split(":", 1)[0] if ":" in model and model.split(":", 1)[0] in {"openai", "anthropic", "gemini"} else "ollama"


def request_digest(graph: dict, run_prompt: str) -> str:
    payload = json.dumps({"graph": graph, "run_prompt": run_prompt.strip()}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def describe_transfers(graph: dict) -> list[dict]:
    nodes = {n["id"]: n for n in graph.get("nodes", []) if n.get("type", "agent") == "agent"}
    parents = dag.parents_of(graph)
    transfers = []
    for node_id, node in nodes.items():
        if not is_cloud_node(node):
            continue
        provider = provider_for(node)
        transfers.append({"node_id": node_id, "node_name": node.get("name", node_id), "provider": provider, "type": "user_input"})
        file_ids = [v for v in node.get("uploaded_file_ids", []) if isinstance(v, int)]
        if file_ids:
            transfers.append({"node_id": node_id, "node_name": node.get("name", node_id), "provider": provider, "type": "original_file", "file_ids": file_ids})
        derived = []
        for parent_id in parents.get(node_id, []):
            parent = nodes.get(parent_id, {})
            if parent.get("directory_ids") or parent.get("uploaded_file_ids"):
                derived.append(parent.get("name", parent_id))
        if derived:
            transfers.append({"node_id": node_id, "node_name": node.get("name", node_id), "provider": provider, "type": "derived_text", "sources": derived})
    return transfers


def issue_consent(db: Session, user_id: int, service_id: int, graph: dict, run_prompt: str, transfers: list[dict]) -> str:
    token = secrets.token_urlsafe(32)
    db.add(models.ExternalTransferConsent(token=token, user_id=user_id, service_id=service_id, request_digest=request_digest(graph, run_prompt), transfers=transfers, expires_at=models.utcnow() + timedelta(minutes=10)))
    db.commit()
    return token


def consume_consent(db: Session, token: str | None, user_id: int, service_id: int, graph: dict, run_prompt: str) -> bool:
    row = db.query(models.ExternalTransferConsent).filter_by(token=token or "", user_id=user_id, service_id=service_id).first()
    if row is None or row.used_at is not None or row.expires_at <= models.utcnow() or row.request_digest != request_digest(graph, run_prompt):
        return False
    row.used_at = models.utcnow()
    return True
