import pytest

from app.services import transfers
from app.services.credentials import decrypt_secret, encrypt_secret


def test_credentials_round_trip_without_exposing_plaintext():
    encrypted = encrypt_secret("sk-test-secret-value")
    assert "sk-test-secret-value" not in encrypted
    assert decrypt_secret(encrypted) == "sk-test-secret-value"


def test_cloud_transfer_preview_marks_user_input_and_derived_file_text():
    graph = {
        "nodes": [
            {"id": "local", "type": "agent", "name": "Local reader", "provider": "ollama", "directory_ids": [1]},
            {"id": "cloud", "type": "agent", "name": "Cloud writer", "executor": "cloud", "provider": "openai"},
        ],
        "edges": [{"source": "local", "target": "cloud", "relation": "workflow"}],
    }
    items = transfers.describe_transfers(graph)
    assert {item["type"] for item in items} == {"user_input", "derived_text"}
    assert items[0]["provider"] == "openai"
    assert items[1]["sources"] == ["Local reader"]


def test_direct_cloud_file_text_is_explicit_in_preview():
    graph = {
        "nodes": [{"id": "cloud", "type": "agent", "name": "Claude", "executor": "cloud", "provider": "anthropic", "uploaded_file_ids": [4, 9]}],
        "edges": [],
    }
    items = transfers.describe_transfers(graph)
    file_text = next(item for item in items if item["type"] == "file_text")
    assert file_text["file_ids"] == [4, 9]


def test_consent_digest_changes_with_prompt_or_graph():
    graph = {"nodes": [], "edges": []}
    first = transfers.request_digest(graph, "first")
    assert first != transfers.request_digest(graph, "second")
    assert first != transfers.request_digest({"nodes": [{"id": "x"}], "edges": []}, "first")


def test_cloud_task_is_claimed_without_running_inline(db, make_user, make_execution):
    from app import models
    from app.services import cloud_executor, orchestrator

    user = make_user()
    graph = {
        "nodes": [{"id": "cloud", "type": "agent", "name": "Cloud", "executor": "cloud", "provider": "openai"}],
        "edges": [],
    }
    execution = make_execution(user, graph)
    orchestrator.create_tasks_for_execution(db, execution)
    db.commit()

    task = cloud_executor.claim_next_cloud_task(db)

    assert task is not None
    assert task.status == "running"
    assert task.assigned_device_id is None
    assert db.query(models.TaskRecord).filter_by(status="ready").count() == 0


def test_cloud_file_context_contains_extracted_text(db, make_user, tmp_path, monkeypatch):
    from app import models
    from app.services import file_context

    monkeypatch.setattr(file_context, "UPLOAD_DIR", tmp_path)
    user = make_user()
    path = tmp_path / "stored.txt"
    path.write_text("private attachment contents", encoding="utf-8")
    uploaded = models.UploadedFile(
        user_id=user.id,
        original_name="notes.txt",
        stored_name=path.name,
        content_type="text/plain",
        size_bytes=path.stat().st_size,
    )
    db.add(uploaded)
    db.flush()

    context = file_context.cloud_file_context(
        db, user.id, {"uploaded_file_ids": [uploaded.id]}
    )

    assert "notes.txt" in context
    assert "private attachment contents" in context


def test_cloud_file_longer_than_the_limit_is_marked_and_noted(db, make_user, tmp_path, monkeypatch):
    from app import models
    from app.services import file_context

    monkeypatch.setattr(file_context, "UPLOAD_DIR", tmp_path)
    user = make_user()
    path = tmp_path / "stored-long.txt"
    path.write_text("가" * 40_000, encoding="utf-8")
    uploaded = models.UploadedFile(
        user_id=user.id, original_name="회의록.txt", stored_name=path.name,
        content_type="text/plain", size_bytes=path.stat().st_size,
    )
    db.add(uploaded)
    db.flush()

    notes: list[str] = []
    context = file_context.cloud_file_context(db, user.id, {"uploaded_file_ids": [uploaded.id]}, notes)

    # 바이트가 아니라 글자 수로 자른다: 한글도 30,000자까지 들어간다
    assert context.count("가") == 30_000
    assert context.endswith("[여기까지만 포함됨: 전체 40,000자 중 앞 30,000자. 이후 10,000자는 생략됨]")
    assert notes == ["회의록.txt: 전체 40,000자 중 앞 30,000자만 읽었어요. 뒤 10,000자는 빠졌어요."]


def test_stale_cloud_task_returns_to_ready(db, make_user, make_execution, monkeypatch):
    from datetime import timedelta
    from app import models
    from app.services import cloud_executor, orchestrator

    user = make_user()
    graph = {
        "nodes": [{"id": "cloud", "type": "agent", "name": "Cloud", "executor": "cloud", "provider": "openai"}],
        "edges": [],
    }
    execution = make_execution(user, graph)
    orchestrator.create_tasks_for_execution(db, execution)
    task = execution.tasks[0]
    task.status = "running"
    task.started_at = models.utcnow() - timedelta(seconds=301)
    db.commit()
    monkeypatch.setattr(cloud_executor, "CLOUD_TASK_TIMEOUT_SECONDS", 300)

    cloud_executor.reclaim_stale_cloud_tasks(db)

    db.refresh(task)
    assert task.status == "ready"
    assert task.started_at is None


class _CloudResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _CloudClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, headers, json):
        self.requests.append({"url": url, "headers": headers, "json": json})
        provider = "openai" if "openai.com" in url else "anthropic" if "anthropic.com" in url else "gemini"
        return _CloudResponse(self.responses[provider])


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        ("openai", "gpt-5-mini", 128_000),
        ("openai", "gpt-4.1", 32_768),
        ("anthropic", "claude-sonnet-4-5", 65_536),
        ("anthropic", "claude-opus-4-1", 32_768),
        ("anthropic", "claude-haiku-3-5", 8_192),
        ("gemini", "gemini-3.8-flash", 65_536),
    ],
)
def test_cloud_output_tokens_follow_model_native_limit(provider, model, expected, monkeypatch):
    from app.services import cloud_executor

    monkeypatch.setattr(cloud_executor, "CLOUD_MAX_OUTPUT_TOKENS", 128_000)
    assert cloud_executor.cloud_output_tokens(provider, model) == expected


def test_cloud_requests_send_each_model_native_output_limit(monkeypatch):
    from app.services import cloud_executor

    client = _CloudClient({
        "openai": {"status": "completed", "output_text": "ok", "usage": {}},
        "anthropic": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}], "usage": {}},
        "gemini": {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]},
    })
    monkeypatch.setattr(cloud_executor.httpx, "Client", lambda timeout: client)

    cloud_executor._call("openai", "key", "gpt-5-mini", "system", "user")
    assert client.requests[-1]["json"]["max_output_tokens"] == 128_000
    cloud_executor._call("anthropic", "key", "claude-sonnet-4-5", "system", "user")
    assert client.requests[-1]["json"]["max_tokens"] == 65_536
    cloud_executor._call("gemini", "key", "gemini-3.8-flash", "system", "user")
    assert client.requests[-1]["json"]["generationConfig"]["maxOutputTokens"] == 65_536


@pytest.mark.parametrize(
    ("provider", "model", "response"),
    [
        ("openai", "gpt-5-mini", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}),
        ("anthropic", "claude-sonnet-4-5", {"stop_reason": "max_tokens", "content": []}),
        ("gemini", "gemini-3.8-flash", {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
    ],
)
def test_cloud_requests_reject_silently_truncated_output(provider, model, response, monkeypatch):
    from app.services import cloud_executor

    normal = {
        "openai": {"status": "completed", "output_text": "ok", "usage": {}},
        "anthropic": {"stop_reason": "end_turn", "content": [], "usage": {}},
        "gemini": {"candidates": []},
    }
    normal[provider] = response
    client = _CloudClient(normal)
    monkeypatch.setattr(cloud_executor.httpx, "Client", lambda timeout: client)

    with pytest.raises(cloud_executor.CloudOutputTruncated):
        cloud_executor._call(provider, "key", model, "system", "user")
