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


def test_direct_cloud_file_is_explicit_in_preview():
    graph = {
        "nodes": [{"id": "cloud", "type": "agent", "name": "Claude", "executor": "cloud", "provider": "anthropic", "uploaded_file_ids": [4, 9]}],
        "edges": [],
    }
    items = transfers.describe_transfers(graph)
    original = next(item for item in items if item["type"] == "original_file")
    assert original["file_ids"] == [4, 9]


def test_consent_digest_changes_with_prompt_or_graph():
    graph = {"nodes": [], "edges": []}
    first = transfers.request_digest(graph, "first")
    assert first != transfers.request_digest(graph, "second")
    assert first != transfers.request_digest({"nodes": [{"id": "x"}], "edges": []}, "first")
