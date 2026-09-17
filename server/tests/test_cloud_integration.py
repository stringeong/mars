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
