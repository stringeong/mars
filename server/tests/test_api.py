"""API 통합 테스트 — 회원가입부터 실행 완료까지 전 구간 + 인증/격리 가드.

워크플로우 생성 LLM은 mock으로 대체한다 (LLM 파싱 자체는 test_generator.py에서 검증).
"""

import copy
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app
from tests.conftest import LINEAR
from tests.test_generator import CYCLIC_LLM_REPLY, VALID_LLM_REPLY


GENERATE_CALLS: list = []


@pytest.fixture()
def client(db, monkeypatch):
    async def fake_generate(prompt, choice=None):
        graph = copy.deepcopy(LINEAR)
        graph["name"] = "테스트 서비스"
        graph["description"] = prompt
        # 시작 블록 a는 사용자가 '파일 필요'를 해제해 실행 프롬프트만으로 실행하는 블록이다
        graph["nodes"][0].update(needs_file=False, needs_file_manual=True)
        GENERATE_CALLS.append(choice)
        return graph, {
            "source": "llm",
            "location": choice.location if choice else "local",
            "provider": choice.provider if choice else "ollama",
            "model": "test-model",
            "generated_at": "2026-10-21T00:00:00+00:00",
        }

    GENERATE_CALLS.clear()
    monkeypatch.setattr("app.routers.services.generate_workflow", fake_generate)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signup_and_login(client, username="user1", email="u1@example.com"):
    r = client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": "secret1"},
    )
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": username, "password": "secret1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register_device(client, auth, name="노트북"):
    r = client.post("/devices", json={"name": name}, headers=auth)
    assert r.status_code == 201, r.text
    return {"X-Device-Key": r.json()["api_key"]}


def editable_graph(service):
    """웹 편집기가 저장할 때처럼 노드 type을 채운 그래프 복사본."""
    graph = copy.deepcopy(service["graph"])
    for n in graph["nodes"]:
        n.setdefault("type", "agent")
    return graph


def upload(client, auth, name="input.csv", content=b"id,amount\n1,100\n"):
    r = client.post("/files", files={"file": (name, content, "text/plain")}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def create_service(client, auth):
    r = client.post(
        "/services/generate", json={"prompt": "문서 요약 서비스 만들기"}, headers=auth
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestHappyPath:
    def test_signup_to_completed_execution(self, client):
        """회원가입 → 기기 등록 → 하트비트 → 서비스 생성 → 실행 → 워커 루프 → 결과."""
        auth = signup_and_login(client)

        # 기기 등록 + 하트비트 → 온라인 (UC-103/104)
        key = register_device(client, auth)
        r = client.post("/worker/heartbeat", json={"specs": {"os": "mac"}}, headers=key)
        assert r.status_code == 200
        devices = client.get("/devices", headers=auth).json()
        assert devices[0]["online"] is True
        assert devices[0]["specs"] == {"os": "mac"}

        # 서비스 생성 (UC-201) — a -> b -> c
        service = create_service(client, auth)
        assert service["name"] == "테스트 서비스"
        assert len(service["graph"]["nodes"]) == 3

        # 실행 시작 (UC-203)
        r = client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "보고서 작성"},
            headers=auth,
        )
        assert r.status_code == 201, r.text
        execution = r.json()
        assert execution["status"] == "running"
        assert len(execution["tasks"]) == 3
        # 실행 이력에 생성 모델 정보가 복사된다
        assert execution["generation_info"]["model"] == "test-model"

        # 워커 프로토콜 루프: a → b → c 순서로 할당·완료 (UC-204)
        for node, output in [("a", "a 결과"), ("b", "b 결과"), ("c", "c 결과")]:
            r = client.post("/worker/tasks/next", headers=key)
            assert r.status_code == 200
            task = r.json()
            assert task["agent_name"] == f"에이전트 {node}"
            assert task["run_prompt"] == "보고서 작성"
            if node == "b":  # 선행 출력이 컨텍스트로 전달된다
                assert "a 결과" in task["input_context"]
            r = client.post(
                f"/worker/tasks/{task['task_id']}/result",
                json={"status": "done", "output": output},
                headers=key,
            )
            assert r.status_code == 200

        # 타임라인: 단계·연결선·배정 워커 이름이 함께 온다 (4번 개선)
        body = client.get(f"/executions/{execution['id']}", headers=auth).json()
        assert body["stages"] == [["a"], ["b"], ["c"]]
        assert body["final_node_ids"] == ["c"]
        assert sorted((e["source"], e["target"]) for e in body["edges"]) == [("a", "b"), ("b", "c")]
        assert [(t["node_id"], t["depth"], t["assigned_device_name"], t["executor"]) for t in body["tasks"]] == [
            ("a", 0, "노트북", "local"), ("b", 1, "노트북", "local"), ("c", 2, "노트북", "local"),
        ]

        # 더 줄 작업이 없으면 204
        assert client.post("/worker/tasks/next", headers=key).status_code == 204

        # 결과 확인 (UC-205): 말단 노드 c의 출력만 통합된다
        r = client.get(f"/executions/{execution['id']}", headers=auth)
        body = r.json()
        assert body["status"] == "completed"
        assert body["progress"] == 100.0
        assert body["result"] == "## 에이전트 c\n\nc 결과"

        # 이력 조회 (UC-206)
        items = client.get("/executions", headers=auth).json()
        assert len(items) == 1
        assert items[0]["service_name"] == "테스트 서비스"
        assert items[0]["status"] == "completed"


class TestAutoFlags:
    """최종 블록·파일 필요는 자동으로 정하고, 사용자가 직접 지정한 값은 덮어쓰지 않는다."""

    def test_save_recomputes_flags_from_connections(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        graph = editable_graph(service)
        # a -> b -> c 에 a -> x 를 더하면 끝나는 블록이 c, x 두 개가 된다
        graph["nodes"].append({"id": "x", "type": "agent", "name": "요약"})
        graph["edges"].append({"source": "a", "target": "x"})
        r = client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth)
        assert r.status_code == 200, r.text
        nodes = {n["id"]: n for n in r.json()["graph"]["nodes"]}
        # 가장 뒤 단계의 끝 블록 c가 최종 블록, x는 최종 블록에 닿지 않는다는 경고
        assert [i for i, n in nodes.items() if n["final"]] == ["c"]
        assert [w["node_ids"] for w in r.json()["validation"]["warnings"]] == [["x"]]
        # a는 직접 해제한 값이 유지되고, 들어오는 연결이 있는 b·c·x는 파일이 필요 없다
        assert {i: n["needs_file"] for i, n in nodes.items()} == {"a": False, "b": False, "c": False, "x": False}

    def test_manual_values_survive_connection_changes(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["nodes"][1].update(final=True, final_manual=True)      # b를 직접 최종 블록으로
        graph["nodes"][0].update(needs_file_manual=False)             # a는 다시 자동으로
        r = client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth)
        nodes = {n["id"]: n for n in r.json()["graph"]["nodes"]}
        assert [i for i, n in nodes.items() if n["final"]] == ["b"]
        # 들어오는 연결이 없는 a는 자동으로 파일 필요 → 파일 누락 오류
        assert nodes["a"]["needs_file"] is True
        assert {e["code"] for e in r.json()["validation"]["errors"]} == {"missing_file"}


class TestGenerationChoice:
    def test_generator_models_lists_local_and_registered_cloud(self, client, monkeypatch):
        async def fake_local():
            return {"available": True, "models": ["gemma3:4b", "qwen3:4b"], "default_model": "gemma3:4b", "error": None}

        monkeypatch.setattr("app.routers.services.list_local_models", fake_local)
        auth = signup_and_login(client)
        client.put("/settings/llm-providers/openai", json={"api_key": "sk-test-12345678"}, headers=auth)

        body = client.get("/services/generator-models", headers=auth).json()
        assert body["local"]["models"] == ["gemma3:4b", "qwen3:4b"]
        configured = {item["provider"]: item["configured"] for item in body["cloud"]}
        assert configured == {"openai": True, "anthropic": False, "gemini": False}

    def test_failure_returns_cause_without_creating_service(self, client, monkeypatch):
        from app.services.generator import GenerationError, GeneratorChoice

        async def failing_generate(prompt, choice=None):
            raise GenerationError("parse", "모델 응답을 워크플로우로 해석하지 못했습니다", choice or GeneratorChoice())

        monkeypatch.setattr("app.routers.services.generate_workflow", failing_generate)
        auth = signup_and_login(client)
        r = client.post("/services/generate", json={"prompt": "문서 요약 서비스", "model": "qwen3:4b"}, headers=auth)

        assert r.status_code == 502
        error = r.json()["detail"]["generation_error"]
        assert error["stage"] == "parse" and error["model"] == "qwen3:4b"
        assert client.get("/services", headers=auth).json() == []

    def test_user_can_choose_default_workflow_after_failure(self, client):
        auth = signup_and_login(client)
        r = client.post(
            "/services/generate",
            json={"prompt": "문서 요약 서비스", "use_fallback": True, "fallback_reason": "연결 실패"},
            headers=auth,
        )
        assert r.status_code == 201, r.text
        service = r.json()
        assert service["generation_info"]["source"] == "fallback"
        assert service["generation_info"]["fallback_reason"] == "연결 실패"
        assert service["graph"]["goal"] == "문서 요약 서비스"
        assert GENERATE_CALLS == []

    def test_cloud_generation_requires_key_and_transfer_ack(self, client):
        auth = signup_and_login(client)
        body = {"prompt": "문서 요약 서비스", "location": "cloud", "provider": "openai"}
        assert client.post("/services/generate", json=body, headers=auth).status_code == 422

        client.put("/settings/llm-providers/openai", json={"api_key": "sk-test-12345678"}, headers=auth)
        assert client.post("/services/generate", json=body, headers=auth).status_code == 428

        r = client.post("/services/generate", json={**body, "external_transfer_ack": True}, headers=auth)
        assert r.status_code == 201, r.text
        choice = GENERATE_CALLS[-1]
        assert choice.location == "cloud" and choice.provider == "openai"
        assert choice.model == "gpt-5-mini"  # 등록된 기본 모델
        assert choice.api_key == "sk-test-12345678"
        assert r.json()["generation_info"]["provider"] == "openai"


class TestAuthGuards:
    def test_me_requires_token(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_duplicate_username_rejected(self, client):
        signup_and_login(client)
        r = client.post(
            "/auth/register",
            json={"email": "new@example.com", "username": "user1", "password": "secret1"},
        )
        assert r.status_code == 409

    def test_duplicate_email_rejected(self, client):
        signup_and_login(client)
        r = client.post(
            "/auth/register",
            json={"email": "u1@example.com", "username": "user2", "password": "secret1"},
        )
        assert r.status_code == 409

    def test_wrong_password_rejected(self, client):
        signup_and_login(client)
        r = client.post("/auth/login", data={"username": "user1", "password": "wrong!"})
        assert r.status_code == 401

    def test_unknown_user_rejected(self, client):
        r = client.post("/auth/login", data={"username": "ghost", "password": "secret1"})
        assert r.status_code == 401

    def test_bad_device_key_rejected(self, client):
        r = client.post("/worker/heartbeat", headers={"X-Device-Key": "wrong-key"})
        assert r.status_code == 401


    def test_worker_key_can_rename_own_device(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth, name="기존 이름")

        r = client.patch("/worker/device", json={"name": "새 이름"}, headers=key)

        assert r.status_code == 200
        assert r.json()["name"] == "새 이름"
        assert client.get("/devices", headers=auth).json()[0]["name"] == "새 이름"

    def test_worker_key_can_unregister_own_device(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)

        r = client.delete("/worker/device", headers=key)

        assert r.status_code == 204
        assert client.get("/devices", headers=auth).json() == []
        assert client.post("/worker/heartbeat", headers=key).status_code == 401


class TestServiceEndpoints:
    def test_blank_prompt_rejected(self, client):
        auth = signup_and_login(client)
        r = client.post("/services/generate", json={"prompt": "     "}, headers=auth)
        assert r.status_code == 422

    def test_update_with_cyclic_graph_rejected(self, client):
        """UC-202 e301: 실행 불가능한 구성은 저장 단계에서 차단."""
        auth = signup_and_login(client)
        service = create_service(client, auth)
        cyclic = {
            "nodes": [{"id": "a", "name": "a"}, {"id": "b", "name": "b"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        }
        r = client.put(f"/services/{service['id']}", json={"graph": cyclic}, headers=auth)
        assert r.status_code == 422
        # 기존 그래프는 보존된다
        saved = client.get(f"/services/{service['id']}", headers=auth).json()
        assert len(saved["graph"]["nodes"]) == 3

    def test_validate_endpoint(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        r = client.post(f"/services/{service['id']}/validate", headers=auth)
        body = r.json()
        # 시작 블록 a에 파일이 없으므로 실행 프롬프트 없이는 오류다
        assert body["valid"] is False
        assert [e["code"] for e in body["errors"]] == ["no_input"]
        assert body["order"] == ["a", "b", "c"]
        assert body["stages"] == [["a"], ["b"], ["c"]]

        r = client.post(
            f"/services/{service['id']}/validate", json={"run_prompt": "요약"}, headers=auth
        )
        assert r.json()["valid"] is True

    def test_validate_draft_graph_and_save_reports_issues(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        draft = editable_graph(service)
        draft["edges"].append({"source": "a", "target": "c"})
        draft["nodes"][1].update(needs_file=True, needs_file_manual=True)
        r = client.post(f"/services/{service['id']}/validate", json={"graph": draft}, headers=auth)
        assert {e["code"] for e in r.json()["errors"]} == {"no_input", "missing_file"}

        # 저장은 구조 오류만 막고, 나머지 문제는 저장 응답에 함께 돌려준다
        r = client.put(f"/services/{service['id']}", json={"graph": draft}, headers=auth)
        assert r.status_code == 200, r.text
        assert {e["code"] for e in r.json()["validation"]["errors"]} == {"no_input", "missing_file"}

    def test_duplicate_device_name_reconnects_and_rotates_key(self, client):
        auth = signup_and_login(client)
        first_key = register_device(client, auth, name="노트북")["X-Device-Key"]
        r = client.post("/devices", json={"name": "노트북"}, headers=auth)
        assert r.status_code == 200
        assert r.json()["api_key"] != first_key
        assert client.post("/worker/heartbeat", headers={"X-Device-Key": first_key}).status_code == 401


class TestExecutionGuards:
    def test_no_online_device_rejected(self, client):
        """F2-403: 온라인 기기가 없으면 실행을 시작할 수 없다."""
        auth = signup_and_login(client)
        service = create_service(client, auth)
        r = client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        )
        assert r.status_code == 409

    def test_blank_run_prompt_rejected_only_when_start_block_has_no_input(self, client):
        """실행 프롬프트는 선택 사항이다. 시작 블록에 파일도 프롬프트도 없을 때만 막는다."""
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = create_service(client, auth)
        r = client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "   "},
            headers=auth,
        )
        assert r.status_code == 422
        assert r.json()["detail"]["validation"]["errors"][0]["code"] == "no_input"

        uploaded = upload(client, auth, "memo.txt")
        r = client.post(
            f"/services/{service['id']}/executions",
            json={"input_files": {"nodes": {"a": [uploaded["id"]]}}},
            headers=auth,
        )
        assert r.status_code == 201, r.text
        assert r.json()["run_prompt"] == ""

    def test_cancel_then_cancel_again_conflicts(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = create_service(client, auth)
        execution = client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        ).json()

        r = client.post(f"/executions/{execution['id']}/cancel", headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"
        # 취소된 실행의 작업은 워커에게 배포되지 않는다
        assert client.post("/worker/tasks/next", headers=key).status_code == 204
        # 이미 종료된 실행은 다시 취소할 수 없다
        r = client.post(f"/executions/{execution['id']}/cancel", headers=auth)
        assert r.status_code == 409


    def test_validation_errors_block_execution(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["nodes"][1].update(needs_file=True, needs_file_manual=True)
        assert client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth).status_code == 200

        r = client.post(
            f"/services/{service['id']}/executions", json={"run_prompt": "실행"}, headers=auth
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["validation"]["errors"][0]["code"] == "missing_file"
        assert detail["validation"]["errors"][0]["node_ids"] == ["b"]

    def test_warnings_need_acknowledgement(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["nodes"].append({"id": "x", "type": "agent", "name": "고립", "needs_file_manual": True})
        graph["nodes"][2]["final"] = True
        assert client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth).status_code == 200

        preview = client.post(
            f"/services/{service['id']}/executions/preview", json={"run_prompt": "실행"}, headers=auth
        ).json()
        assert [w["code"] for w in preview["validation"]["warnings"]] == ["unreachable"]

        url = f"/services/{service['id']}/executions"
        r = client.post(url, json={"run_prompt": "실행"}, headers=auth)
        assert r.status_code == 409
        assert r.json()["detail"]["validation"]["warnings"][0]["node_ids"] == ["x"]
        r = client.post(url, json={"run_prompt": "실행", "acknowledge_warnings": True}, headers=auth)
        assert r.status_code == 201, r.text


    def test_slot_files_reach_every_block_that_shares_the_slot(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = create_service(client, auth)
        uploaded = client.post(
            "/files", files={"file": ("card.csv", b"id,amount\n1,100\n", "text/csv")}, headers=auth
        ).json()
        graph = editable_graph(service)
        graph["input_slots"] = [{"id": "slot1", "description": "신용카드 사용 내역", "file_ids": [uploaded["id"]]}]
        graph["nodes"][0].update(needs_file=True, input_slot_ids=["slot1"])
        graph["nodes"][1].update(needs_file=True, input_slot_ids=["slot1"])
        assert client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth).status_code == 200

        execution = client.post(f"/services/{service['id']}/executions", json={"run_prompt": "분석"}, headers=auth)
        assert execution.status_code == 201, execution.text
        task = client.post("/worker/tasks/next", headers=key).json()
        assert task["uploaded_files"] == [{"id": uploaded["id"], "original_name": "card.csv"}]
        client.post(f"/worker/tasks/{task['task_id']}/result", json={"status": "done", "output": "a"}, headers=key)
        task = client.post("/worker/tasks/next", headers=key).json()
        assert [f["id"] for f in task["uploaded_files"]] == [uploaded["id"]]


class TestRunInputsAndReuse:
    def _slot_service(self, client, auth, file_id):
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["input_slots"] = [{"id": "slot1", "description": "신용카드 사용 내역", "file_ids": [file_id]}]
        graph["nodes"][0].update(needs_file=True, input_slot_ids=["slot1"])
        assert client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth).status_code == 200
        return service

    def test_run_files_override_defaults_without_changing_workflow(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        october = upload(client, auth, "10월.csv")
        november = upload(client, auth, "11월.csv")
        service = self._slot_service(client, auth, october["id"])

        r = client.post(
            f"/services/{service['id']}/executions",
            json={"input_files": {"slots": {"slot1": [november["id"]]}}},
            headers=auth,
        )
        assert r.status_code == 201, r.text
        # 실행 이력에 이번 실행의 입력 파일이 이름과 함께 남는다
        assert r.json()["input_files"] == [{
            "kind": "slot", "id": "slot1", "label": "신용카드 사용 내역", "node_ids": ["a"],
            "files": [{"id": november["id"], "name": "11월.csv"}], "directories": [],
        }]
        task = client.post("/worker/tasks/next", headers=key).json()
        assert [f["original_name"] for f in task["uploaded_files"]] == ["11월.csv"]
        # 저장된 워크플로우의 기본 파일은 그대로다
        saved = client.get(f"/services/{service['id']}", headers=auth).json()
        assert saved["graph"]["input_slots"][0]["file_ids"] == [october["id"]]

    def test_unknown_slot_is_rejected(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = self._slot_service(client, auth, upload(client, auth)["id"])
        r = client.post(
            f"/services/{service['id']}/executions",
            json={"input_files": {"slots": {"ghost": [1]}}},
            headers=auth,
        )
        assert r.status_code == 422

    def test_history_filter_by_service_returns_input_files(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        file = upload(client, auth, "카드.csv")
        first = self._slot_service(client, auth, file["id"])
        other = create_service(client, auth)
        client.post(f"/services/{first['id']}/executions", json={}, headers=auth)
        client.post(f"/services/{other['id']}/executions", json={"run_prompt": "요약"}, headers=auth)

        items = client.get(f"/executions?service_id={first['id']}", headers=auth).json()
        assert [item["service_id"] for item in items] == [first["id"]]
        assert items[0]["input_files"][0]["files"] == [{"id": file["id"], "name": "카드.csv"}]

    def test_consent_is_bound_to_the_run_files(self, client):
        """외부 전송 동의는 이번 실행 파일까지 포함한 그래프에 묶인다."""
        auth = signup_and_login(client)
        client.put("/settings/llm-providers/openai", json={"api_key": "sk-test-12345678"}, headers=auth)
        first, second = upload(client, auth, "a.csv"), upload(client, auth, "b.csv")
        service = self._slot_service(client, auth, first["id"])
        graph = client.get(f"/services/{service['id']}", headers=auth).json()["graph"]
        for n in graph["nodes"]:
            n.update(provider="openai", executor="cloud")
        client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth)

        inputs = {"slots": {"slot1": [second["id"]]}}
        preview = client.post(
            f"/services/{service['id']}/executions/preview", json={"input_files": inputs}, headers=auth
        ).json()
        assert any(t["type"] == "file_text" and t["file_ids"] == [second["id"]] for t in preview["transfers"])
        url = f"/services/{service['id']}/executions"
        token = preview["consent_token"]
        # 다른 파일로 바꾸면 이전 동의로는 실행할 수 없다
        r = client.post(url, json={"consent_token": token, "input_files": {"slots": {"slot1": [first["id"]]}}}, headers=auth)
        assert r.status_code == 428
        r = client.post(url, json={"consent_token": token, "input_files": inputs}, headers=auth)
        assert r.status_code == 201, r.text

    def test_duplicate_copies_workflow_but_not_history(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        r = client.post(f"/services/{service['id']}/duplicate", headers=auth)
        assert r.status_code == 201, r.text
        copy_ = r.json()
        assert copy_["id"] != service["id"]
        assert copy_["name"] == "테스트 서비스 (복사본)"
        assert copy_["graph"] == service["graph"]
        assert copy_["generation_info"] == service["generation_info"]
        intruder = signup_and_login(client, username="user2", email="u2@example.com")
        assert client.post(f"/services/{service['id']}/duplicate", headers=intruder).status_code == 404


class TestWorkerGeneration:
    """서버 GPU 대신 사용자의 Worker(그 기기의 Ollama)로 워크플로우를 생성한다."""

    def _worker(self, client, auth, name="맥북", installed=("qwen3:4b", "gemma3:4b")):
        key = register_device(client, auth, name)
        specs = {"models": list(installed), "default_model": "qwen3:4b"}
        assert client.post("/worker/heartbeat", json={"specs": specs}, headers=key).status_code == 200
        return key

    def _device_id(self, client, auth, name="맥북"):
        return next(d["id"] for d in client.get("/devices", headers=auth).json() if d["name"] == name)

    def _queue(self, client, auth, device_id, **extra):
        body = {"prompt": "문서 요약 서비스 만들기", "device_id": device_id, **extra}
        return client.post("/services/generation-jobs", json=body, headers=auth)

    def _claim(self, client, key):
        r = client.post("/worker/generations/next", headers=key)
        assert r.status_code == 200, r.text
        return r.json()

    def test_generator_models_lists_online_workers_first(self, client, monkeypatch):
        async def fake_local():
            return {"available": False, "models": [], "default_model": "gemma3:4b", "error": "없음"}

        monkeypatch.setattr("app.routers.services.list_local_models", fake_local)
        auth = signup_and_login(client)
        register_device(client, auth, "꺼진 PC")
        self._worker(client, auth)
        workers = client.get("/services/generator-models", headers=auth).json()["workers"]
        assert [(w["name"], w["online"]) for w in workers] == [("맥북", True), ("꺼진 PC", False)]
        assert workers[0]["models"] == ["gemma3:4b", "qwen3:4b"] and workers[0]["default_model"] == "qwen3:4b"

    def test_worker_generates_and_workflow_is_saved(self, client):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        r = self._queue(client, auth, self._device_id(client, auth))
        assert r.status_code == 202, r.text
        queued = r.json()
        assert (queued["status"], queued["model"], queued["device_name"]) == ("pending", "qwen3:4b", "맥북")

        job = self._claim(client, key)
        assert (job["job_id"], job["model"], job["prompt"], job["temperature"]) == (queued["id"], "qwen3:4b", "문서 요약 서비스 만들기", 0.3)
        assert "DAG" in job["system"]
        assert client.get(f"/services/generation-jobs/{queued['id']}", headers=auth).json()["status"] == "running"

        r = client.post(f"/worker/generations/{job['job_id']}/result", json={"content": VALID_LLM_REPLY}, headers=key)
        assert r.json() == {"ok": True, "status": "done"}
        done = client.get(f"/services/generation-jobs/{queued['id']}", headers=auth).json()
        assert done["status"] == "done" and done["generation_error"] is None
        service = client.get(f"/services/{done['service_id']}", headers=auth).json()
        assert service["name"] == "요약 서비스"
        info = service["generation_info"]
        assert (info["location"], info["provider"], info["model"], info["device_name"]) == ("worker", "ollama", "qwen3:4b", "맥북")
        # 처리한 요청은 다시 가져가지 않는다
        assert client.post("/worker/generations/next", headers=key).status_code == 204

    def test_unreadable_reply_is_asked_again_then_reported(self, client):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        job_id = self._queue(client, auth, self._device_id(client, auth), model="gemma3:4b").json()["id"]

        first = self._claim(client, key)
        assert client.post(f"/worker/generations/{job_id}/result", json={"content": "JSON 아님"}, headers=key).json()["status"] == "pending"
        second = self._claim(client, key)
        assert (first["temperature"], second["temperature"], second["model"]) == (0.3, 0.1, "gemma3:4b")
        client.post(f"/worker/generations/{job_id}/result", json={"content": CYCLIC_LLM_REPLY}, headers=key)

        failed = client.get(f"/services/generation-jobs/{job_id}", headers=auth).json()
        assert (failed["status"], failed["attempt"]) == ("failed", 2)
        error = failed["generation_error"]
        assert (error["stage"], error["location"], error["model"], error["device_name"]) == ("validation", "worker", "gemma3:4b", "맥북")
        assert client.get("/services", headers=auth).json() == []

    def test_worker_model_error_is_reported(self, client):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        job_id = self._queue(client, auth, self._device_id(client, auth)).json()["id"]
        self._claim(client, key)
        client.post(f"/worker/generations/{job_id}/result", json={"error": "Ollama에 연결할 수 없음"}, headers=key)
        error = client.get(f"/services/generation-jobs/{job_id}", headers=auth).json()["generation_error"]
        assert error["stage"] == "connection" and "맥북" in error["message"] and "Ollama에 연결할 수 없음" in error["message"]

    def test_only_own_online_worker_with_the_model(self, client):
        auth = signup_and_login(client)
        self._worker(client, auth)
        register_device(client, auth, "꺼진 PC")
        assert self._queue(client, auth, self._device_id(client, auth, "꺼진 PC")).status_code == 409
        assert self._queue(client, auth, self._device_id(client, auth), model="llama3:70b").status_code == 422
        intruder = signup_and_login(client, username="user2", email="u2@example.com")
        assert self._queue(client, intruder, self._device_id(client, auth)).status_code == 404
        job_id = self._queue(client, auth, self._device_id(client, auth)).json()["id"]
        assert client.get(f"/services/generation-jobs/{job_id}", headers=intruder).status_code == 404
        # 다른 사용자의 Worker는 이 요청을 가져가지 못한다
        other_key = self._worker(client, intruder, "남의 PC")
        assert client.post("/worker/generations/next", headers=other_key).status_code == 204

    def test_unclaimed_request_times_out(self, client, db):
        auth = signup_and_login(client)
        self._worker(client, auth)
        job_id = self._queue(client, auth, self._device_id(client, auth)).json()["id"]
        db.get(models.GenerationJob, job_id).queued_at -= timedelta(seconds=31)
        db.commit()
        failed = client.get(f"/services/generation-jobs/{job_id}", headers=auth).json()
        assert failed["status"] == "failed"
        assert failed["generation_error"]["stage"] == "connection" and "30초" in failed["generation_error"]["message"]

    def test_busy_worker_gets_time_to_finish_its_task(self, client, db):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        service = create_service(client, auth)
        assert client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        ).status_code == 201
        assert client.post("/worker/tasks/next", headers=key).json()["agent_name"]  # 작업 실행 중

        job_id = self._queue(client, auth, self._device_id(client, auth)).json()["id"]
        db.get(models.GenerationJob, job_id).queued_at -= timedelta(minutes=2)
        db.commit()
        waiting = client.get(f"/services/generation-jobs/{job_id}", headers=auth).json()
        assert (waiting["status"], waiting["worker_busy"]) == ("pending", True)
        db.get(models.GenerationJob, job_id).queued_at -= timedelta(minutes=4)
        db.commit()
        failed = client.get(f"/services/generation-jobs/{job_id}", headers=auth).json()
        assert failed["status"] == "failed" and "다른 작업" in failed["generation_error"]["message"]

    def test_unified_queue_prefers_generation_and_labels_kind(self, client):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        service = create_service(client, auth)
        assert client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        ).status_code == 201
        generation_id = self._queue(
            client, auth, self._device_id(client, auth),
        ).json()["id"]

        work = client.post("/worker/work/next", headers=key).json()
        assert work["kind"] == "generation"
        assert work["payload"]["job_id"] == generation_id
        # 하나를 실행 중이면 같은 Worker에 다음 작업을 중복 할당하지 않는다.
        assert client.post("/worker/work/next", headers=key).status_code == 204

    def test_unified_queue_returns_execution_task(self, client):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        service = create_service(client, auth)
        assert client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        ).status_code == 201

        work = client.post("/worker/work/next", headers=key).json()
        assert work["kind"] == "execution"
        assert work["payload"]["agent_name"] == "에이전트 a"
        assert work["payload"]["run_prompt"] == "실행"

    def test_pending_generation_waits_for_running_generation(self, client, db):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        device_id = self._device_id(client, auth)
        first_id = self._queue(client, auth, device_id).json()["id"]
        second_id = self._queue(client, auth, device_id).json()["id"]

        first = client.post("/worker/work/next", headers=key).json()
        assert first["kind"] == "generation" and first["payload"]["job_id"] == first_id
        db.get(models.GenerationJob, second_id).queued_at -= timedelta(minutes=2)
        db.commit()

        waiting = client.get(f"/services/generation-jobs/{second_id}", headers=auth).json()
        assert (waiting["status"], waiting["worker_busy"]) == ("pending", True)

    def test_cancel_ignores_late_reply(self, client):
        auth = signup_and_login(client)
        key = self._worker(client, auth)
        job_id = self._queue(client, auth, self._device_id(client, auth)).json()["id"]
        self._claim(client, key)
        assert client.post(f"/services/generation-jobs/{job_id}/cancel", headers=auth).json()["status"] == "canceled"
        r = client.post(f"/worker/generations/{job_id}/result", json={"content": VALID_LLM_REPLY}, headers=key)
        assert r.status_code == 409
        assert client.get("/services", headers=auth).json() == []


class TestFolders:
    """내 워크플로우 폴더. 남의 폴더로는 옮길 수 없고, 폴더를 지우면 워크플로우는 미분류로 남는다."""

    def test_create_move_and_delete_folder(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        r = client.post("/folders", json={"name": " 업무 "}, headers=auth)
        assert r.status_code == 201, r.text
        folder = r.json()
        assert folder["name"] == "업무"
        assert client.post("/folders", json={"name": "업무"}, headers=auth).status_code == 409

        moved = client.put(f"/services/{service['id']}/folder", json={"folder_id": folder["id"]}, headers=auth)
        assert moved.status_code == 200 and moved.json()["folder_id"] == folder["id"]
        copied = client.post(f"/services/{service['id']}/duplicate", headers=auth).json()
        assert copied["folder_id"] == folder["id"]

        assert client.put(f"/folders/{folder['id']}", json={"name": "회사 일"}, headers=auth).json()["name"] == "회사 일"
        assert client.delete(f"/folders/{folder['id']}", headers=auth).status_code == 204
        assert client.get("/folders", headers=auth).json() == []
        assert {item["folder_id"] for item in client.get("/services", headers=auth).json()} == {None}

    def test_cannot_use_other_users_folder(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        other = signup_and_login(client, username="user2", email="u2@example.com")
        folder = client.post("/folders", json={"name": "남의 폴더"}, headers=other).json()
        assert client.put(f"/services/{service['id']}/folder", json={"folder_id": folder["id"]}, headers=auth).status_code == 404
        assert client.delete(f"/folders/{folder['id']}", headers=auth).status_code == 404


class TestCommunity:
    """공유한 구성은 로그인 없이 보이고, 내 기기·파일·텍스트 입력은 빠진 채로 공유된다."""

    def _published(self, client, db):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        row = db.get(models.Service, service["id"])
        graph = copy.deepcopy(row.graph)
        graph["nodes"][0].update(worker_id=7, directory_ids=[3], uploaded_file_ids=[9], text_input="내 계좌 메모")
        graph["input_slots"] = [{"id": "card", "description": "카드 내역", "format": "CSV", "file_ids": [9], "directory_ids": [3]}]
        row.graph = graph
        db.commit()
        r = client.put(f"/services/{service['id']}/publication", json={"title": "카드 지출 정리", "description": "월말에 쓰는 구성"}, headers=auth)
        assert r.status_code == 200, r.text
        return auth, service, r.json()

    def test_publish_strips_private_values_and_is_public(self, client, db):
        _, _, entry = self._published(client, db)
        node = entry["graph"]["nodes"][0]
        assert (node["worker_id"], node["directory_ids"], node["uploaded_file_ids"], node["text_input"]) == (None, [], [], "")
        assert entry["graph"]["input_slots"][0]["file_ids"] == [] and entry["graph"]["input_slots"][0]["description"] == "카드 내역"
        listed = client.get("/community/workflows").json()
        assert [(item["title"], item["author"]) for item in listed] == [("카드 지출 정리", "user1")]

    def test_republish_updates_one_entry_and_unpublish_removes_it(self, client, db):
        auth, service, entry = self._published(client, db)
        again = client.put(f"/services/{service['id']}/publication", json={"title": "카드 지출 리포트"}, headers=auth).json()
        assert again["id"] == entry["id"]
        assert client.get(f"/services/{service['id']}/publication", headers=auth).json()["title"] == "카드 지출 리포트"
        assert client.delete(f"/services/{service['id']}/publication", headers=auth).status_code == 204
        assert client.get(f"/services/{service['id']}/publication", headers=auth).json() is None
        assert client.get("/community/workflows").json() == []

    def test_import_copies_to_my_workflows(self, client, db):
        _, _, entry = self._published(client, db)
        other = signup_and_login(client, username="user2", email="u2@example.com")
        r = client.post(f"/community/workflows/{entry['id']}/import", headers=other)
        assert r.status_code == 201, r.text
        imported = r.json()
        assert imported["name"] == "카드 지출 정리"
        assert imported["generation_info"]["source"] == "community" and imported["generation_info"]["author"] == "user1"
        assert [item["id"] for item in client.get("/services", headers=other).json()] == [imported["id"]]
        assert client.get("/community/workflows").json()[0]["import_count"] == 1

    def test_only_owner_can_publish_and_deleting_workflow_unpublishes(self, client, db):
        auth, service, _ = self._published(client, db)
        other = signup_and_login(client, username="user2", email="u2@example.com")
        assert client.put(f"/services/{service['id']}/publication", json={"title": "가로채기"}, headers=other).status_code == 404
        assert client.delete(f"/services/{service['id']}", headers=auth).status_code == 204
        assert client.get("/community/workflows").json() == []


class TestDeletion:
    """실행 이력·워크플로우 삭제. 실행 중인 것은 막고, 업로드 파일과 비용 집계는 남긴다."""

    def _setup(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        return auth, create_service(client, auth)

    def _run(self, client, auth, service):
        r = client.post(f"/services/{service['id']}/executions", json={"run_prompt": "이번 달 정리"}, headers=auth)
        assert r.status_code == 201, r.text
        return r.json()

    def _finished(self, client, auth, service):
        execution = self._run(client, auth, service)
        assert client.post(f"/executions/{execution['id']}/cancel", headers=auth).status_code == 200
        return execution

    def test_finished_execution_is_deleted_with_tasks_but_files_and_usage_kept(self, client, db):
        auth, service = self._setup(client)
        uploaded = upload(client, auth, "카드.csv")
        execution = self._finished(client, auth, service)
        owner = db.get(models.Execution, execution["id"]).user_id
        db.add(models.LLMUsage(user_id=owner, execution_id=execution["id"], provider="openai", model="gpt-5-mini"))
        db.commit()

        assert client.delete(f"/executions/{execution['id']}", headers=auth).status_code == 204
        assert client.get(f"/executions/{execution['id']}", headers=auth).status_code == 404
        assert client.get("/executions", headers=auth).json() == []
        assert db.query(models.TaskRecord).filter_by(execution_id=execution["id"]).count() == 0
        usage = db.query(models.LLMUsage).one()
        assert (usage.execution_id, usage.task_id) == (None, None)
        assert [f["id"] for f in client.get("/files", headers=auth).json()] == [uploaded["id"]]

    def test_running_execution_cannot_be_deleted(self, client):
        auth, service = self._setup(client)
        execution = self._run(client, auth, service)
        assert client.delete(f"/executions/{execution['id']}", headers=auth).status_code == 409
        assert client.get(f"/executions/{execution['id']}", headers=auth).status_code == 200

    def test_other_users_execution_is_not_found(self, client):
        auth, service = self._setup(client)
        execution = self._finished(client, auth, service)
        intruder = signup_and_login(client, username="user2", email="u2@example.com")
        assert client.delete(f"/executions/{execution['id']}", headers=intruder).status_code == 404

    def test_workflow_with_history_needs_confirmation(self, client):
        auth, service = self._setup(client)
        self._finished(client, auth, service)
        r = client.delete(f"/services/{service['id']}", headers=auth)
        assert r.status_code == 409 and r.json()["detail"]["history_count"] == 1
        assert client.delete(f"/services/{service['id']}?with_history=true", headers=auth).status_code == 204
        assert client.get(f"/services/{service['id']}", headers=auth).status_code == 404
        assert client.get("/executions", headers=auth).json() == []

    def test_workflow_with_running_execution_cannot_be_deleted(self, client):
        auth, service = self._setup(client)
        self._run(client, auth, service)
        r = client.delete(f"/services/{service['id']}?with_history=true", headers=auth)
        assert r.status_code == 409 and r.json()["detail"]["active"] is True

    def test_workflow_without_history_is_deleted(self, client):
        auth, service = self._setup(client)
        assert client.delete(f"/services/{service['id']}", headers=auth).status_code == 204
        assert client.get("/services", headers=auth).json() == []


class TestWorkerResultGuards:
    def _running_task(self, client, auth, key):
        service = create_service(client, auth)
        client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        )
        r = client.post("/worker/tasks/next", headers=key)
        assert r.status_code == 200
        return r.json()

    def test_result_from_unassigned_device_rejected(self, client):
        auth = signup_and_login(client)
        key1 = register_device(client, auth, name="기기1")
        key2 = register_device(client, auth, name="기기2")
        client.post("/worker/heartbeat", headers=key1)
        client.post("/worker/heartbeat", headers=key2)
        task = self._running_task(client, auth, key1)

        r = client.post(
            f"/worker/tasks/{task['task_id']}/result",
            json={"status": "done", "output": "가로챈 결과"},
            headers=key2,
        )
        assert r.status_code == 404

    def test_double_submit_conflicts(self, client):
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        task = self._running_task(client, auth, key)

        body = {"status": "done", "output": "결과"}
        assert (
            client.post(f"/worker/tasks/{task['task_id']}/result", json=body, headers=key)
            .status_code == 200
        )
        r = client.post(f"/worker/tasks/{task['task_id']}/result", json=body, headers=key)
        assert r.status_code == 409

    def test_failed_result_fails_execution(self, client):
        """UC-204 e202: 작업 실패 보고 → 실행 실패."""
        auth = signup_and_login(client)
        key = register_device(client, auth)
        client.post("/worker/heartbeat", headers=key)
        service = create_service(client, auth)
        execution = client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=auth,
        ).json()
        task = client.post("/worker/tasks/next", headers=key).json()

        r = client.post(
            f"/worker/tasks/{task['task_id']}/result",
            json={"status": "failed", "error": "모델 응답 없음"},
            headers=key,
        )
        assert r.status_code == 200

        body = client.get(f"/executions/{execution['id']}", headers=auth).json()
        assert body["status"] == "failed"
        assert "모델 응답 없음" in body["error"]


class TestUserIsolation:
    def test_users_cannot_see_each_others_resources(self, client):
        owner = signup_and_login(client)
        service = create_service(client, owner)
        intruder = signup_and_login(client, username="user2", email="u2@example.com")

        assert client.get(f"/services/{service['id']}", headers=intruder).status_code == 404
        assert client.get("/services", headers=intruder).json() == []
        r = client.put(
            f"/services/{service['id']}", json={"name": "탈취"}, headers=intruder
        )
        assert r.status_code == 404

    def test_other_users_device_gets_no_tasks(self, client):
        owner = signup_and_login(client)
        owner_key = register_device(client, owner)
        client.post("/worker/heartbeat", headers=owner_key)
        service = create_service(client, owner)
        execution = client.post(
            f"/services/{service['id']}/executions",
            json={"run_prompt": "실행"},
            headers=owner,
        ).json()

        intruder = signup_and_login(client, username="user2", email="u2@example.com")
        intruder_key = register_device(client, intruder, name="침입자 기기")
        client.post("/worker/heartbeat", headers=intruder_key)

        # 다른 사용자의 기기는 작업을 받지 못하고, 실행 이력도 볼 수 없다
        assert client.post("/worker/tasks/next", headers=intruder_key).status_code == 204
        assert (
            client.get(f"/executions/{execution['id']}", headers=intruder).status_code
            == 404
        )


def test_device_registration_persists_only_key_digest(client, db):
    from app import models

    auth = signup_and_login(client, username="digest-user", email="digest@example.com")
    response = client.post("/devices", json={"name": "secure-worker"}, headers=auth)
    assert response.status_code == 201
    raw_key = response.json()["api_key"]
    device = db.query(models.Device).filter_by(name="secure-worker").one()
    assert raw_key != device.api_key
    assert raw_key != device.api_key_hash
    assert device.api_key == device.api_key_hash
    assert client.post(
        "/worker/heartbeat", headers={"X-Device-Key": raw_key}
    ).status_code == 200


class TestFileSplit:
    """파일 나눠서 병렬 실행: 실행할 때 파일을 나누고 블록을 조각 수만큼 펼친다."""

    @pytest.fixture(autouse=True)
    def uploads(self, tmp_path, monkeypatch):
        for module in ("app.routers.files", "app.routers.worker", "app.services.split_inputs"):
            monkeypatch.setattr(f"{module}.UPLOAD_DIR", tmp_path)
        return tmp_path

    def _workers(self, client, auth, count):
        keys = [register_device(client, auth, name=f"워커{index}") for index in range(1, count + 1)]
        for key in keys:
            client.post("/worker/heartbeat", headers=key)
        return keys

    def _split_service(self, client, auth, file_ids, **split):
        """a(분할) -> b -> c. a에 파일을 직접 연결한다."""
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["nodes"][0].update(uploaded_file_ids=file_ids, split={"enabled": True, **split})
        r = client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth)
        assert r.status_code == 200, r.text
        return r.json()

    def _start(self, client, auth, service, **body):
        r = client.post(f"/services/{service['id']}/executions", json={"run_prompt": "이상 징후 찾기", **body}, headers=auth)
        assert r.status_code == 201, r.text
        return r.json()

    def _finish(self, client, key, task, output):
        r = client.post(f"/worker/tasks/{task['task_id']}/result", json={"status": "done", "output": output}, headers=key)
        assert r.status_code == 200, r.text

    def test_log_is_split_across_two_workers_and_merged_in_order(self, client, uploads):
        auth = signup_and_login(client)
        first, second = self._workers(client, auth, 2)
        log = "".join(f"line {index}\n" for index in range(1, 2001)).encode()
        source = upload(client, auth, "BGL_2k.log", log)
        service = self._split_service(client, auth, [source["id"]], max_chars=30_000)

        # 저장·미리보기: 지금 Worker 수로 예상 조각을 알려준다
        assert service["validation"]["splits"] == [{
            "node_id": "a", "unit": "line", "unit_label": "줄", "workers": 2, "parts": 2, "auto": True,
            "sizes": [1000, 1000], "overlap_lines": 0, "source_name": "BGL_2k.log",
        }]
        preview = client.post(f"/services/{service['id']}/executions/preview", json={"run_prompt": "x"}, headers=auth).json()
        assert preview["validation"]["splits"][0]["sizes"] == [1000, 1000]
        # 미리보기는 조각 파일을 만들지 않는다
        assert len(list(uploads.iterdir())) == 1

        execution = self._start(client, auth, service)
        assert execution["stages"] == [["a__p01", "a__p02"], ["b"], ["c"]]
        assert [t["agent_name"] for t in execution["tasks"]] == ["에이전트 a #1", "에이전트 a #2", "에이전트 b", "에이전트 c"]
        record = execution["input_files"][-1]
        assert record["kind"] == "split" and record["files"] == [{"id": source["id"], "name": "BGL_2k.log"}]
        assert [(p["label"], p["name"]) for p in record["pieces"]] == [
            ("1~1000줄", "BGL_2k.part01of02.log"), ("1001~2000줄", "BGL_2k.part02of02.log"),
        ]
        # 저장된 워크플로우는 펼쳐지지 않는다
        saved = client.get(f"/services/{service['id']}", headers=auth).json()
        assert [n["id"] for n in saved["graph"]["nodes"]] == ["a", "b", "c"]

        # 두 Worker가 조각을 하나씩 동시에 가져간다
        task1 = client.post("/worker/tasks/next", headers=first).json()
        task2 = client.post("/worker/tasks/next", headers=second).json()
        assert [task1["agent_name"], task2["agent_name"]] == ["에이전트 a #1", "에이전트 a #2"]
        assert task1["role_prompt"] == task2["role_prompt"] == "a 역할"
        assert "원본 'BGL_2k.log'의 1001~2000줄" in task2["input_context"]
        piece = task2["uploaded_files"][0]
        assert piece["original_name"] == "BGL_2k.part02of02.log"
        content = client.get(f"/worker/files/{piece['id']}", headers=second).content
        assert content == "".join(f"line {index}\n" for index in range(1001, 2001)).encode()
        body = client.get(f"/executions/{execution['id']}", headers=auth).json()
        assert sorted(t["assigned_device_name"] for t in body["tasks"] if t["status"] == "running") == ["워커1", "워커2"]

        # 뒤 조각이 먼저 끝나도 다음 블록은 조각 순서대로 받는다
        self._finish(client, second, task2, "뒤쪽 결과")
        assert client.post("/worker/tasks/next", headers=second).status_code == 204
        self._finish(client, first, task1, "앞쪽 결과")
        merged = client.post("/worker/tasks/next", headers=first).json()
        assert merged["agent_name"] == "에이전트 b"
        context = merged["input_context"]
        assert "[이전 단계: 에이전트 a #1의 결과 · 1~1000줄]\n앞쪽 결과" in context
        assert context.index("앞쪽 결과") < context.index("[이전 단계: 에이전트 a #2의 결과 · 1001~2000줄]\n뒤쪽 결과")

        # 조각 파일은 보관함에 보이지 않고, 실행 이력을 지우면 함께 지워진다
        assert [f["id"] for f in client.get("/files", headers=auth).json()] == [source["id"]]
        assert len(list(uploads.iterdir())) == 3
        client.post(f"/executions/{execution['id']}/cancel", headers=auth)
        assert client.delete(f"/executions/{execution['id']}", headers=auth).status_code == 204
        assert len(list(uploads.iterdir())) == 1
        assert [f["id"] for f in client.get("/files", headers=auth).json()] == [source["id"]]

    def test_csv_rows_keep_header_and_overlap_marks_context(self, client):
        auth = signup_and_login(client)
        (key,) = self._workers(client, auth, 1)
        rows = "id,answer\n" + "".join(f"{index},답안 {index}\n" for index in range(1, 61))
        answers = upload(client, auth, "answers.csv", rows.encode())
        service = self._split_service(client, auth, [answers["id"]], parts=4)
        assert service["validation"]["splits"][0] | {"sizes": None} == {
            "node_id": "a", "unit": "csv", "unit_label": "행", "workers": 1, "parts": 4, "auto": False,
            "sizes": None, "overlap_lines": 0, "source_name": "answers.csv",
        }
        execution = self._start(client, auth, service)
        assert execution["stages"][0] == ["a__p01", "a__p02", "a__p03", "a__p04"]
        seen: list[str] = []
        for index in range(1, 5):
            task = client.post("/worker/tasks/next", headers=key).json()
            lines = client.get(f"/worker/files/{task['uploaded_files'][0]['id']}", headers=key).text.splitlines()
            assert lines[0] == "id,answer"
            seen += lines[1:]
            self._finish(client, key, task, f"채점 {index}")
        assert seen == [f"{index},답안 {index}" for index in range(1, 61)]
        context = client.post("/worker/tasks/next", headers=key).json()["input_context"]
        assert [context.index(f"채점 {index}") for index in range(1, 5)] == sorted(context.index(f"채점 {index}") for index in range(1, 5))
        assert "의 결과 · 16~30행]" in context

        # 줄 단위 + 겹침: 직전 조각의 끝부분이 참고 문맥으로만 붙는다
        log = upload(client, auth, "chat.txt", "".join(f"msg {index}\n" for index in range(1, 41)).encode())
        service = self._split_service(client, auth, [log["id"]], parts=2, overlap_lines=5)
        self._start(client, auth, service)
        client.post("/worker/tasks/next", headers=key)
        task = client.post("/worker/tasks/next", headers=key).json()
        text = client.get(f"/worker/files/{task['uploaded_files'][0]['id']}", headers=key).text
        assert text.startswith("[참고 문맥: 16~20줄. 이해에만 쓰고 판정하지 마세요]\nmsg 16\n")
        assert "\n[처리 대상: 21~40줄]\nmsg 21\n" in text
        assert "참고 문맥" in task["input_context"]

    def test_several_files_are_dealt_out_without_new_files(self, client, uploads):
        auth = signup_and_login(client)
        self._workers(client, auth, 2)
        ids = [upload(client, auth, name, b"text\n")["id"] for name in ("a.pdf", "b.txt", "c.md")]
        service = self._split_service(client, auth, ids)
        assert service["validation"]["splits"][0]["unit"] == "file"
        assert service["validation"]["splits"][0]["sizes"] == [2, 1]
        execution = self._start(client, auth, service)
        assert execution["stages"][0] == ["a__p01", "a__p02"]
        assert [p["file_ids"] for p in execution["input_files"][-1]["pieces"]] == [[ids[0], ids[2]], [ids[1]]]
        assert len(list(uploads.iterdir())) == 3

    def test_small_file_with_one_worker_runs_unsplit(self, client, uploads):
        auth = signup_and_login(client)
        self._workers(client, auth, 1)
        source = upload(client, auth, "note.txt", b"one\ntwo\n")
        service = self._split_service(client, auth, [source["id"]])
        assert service["validation"]["splits"][0]["parts"] == 1
        execution = self._start(client, auth, service, acknowledge_warnings=True)
        assert execution["stages"] == [["a"], ["b"], ["c"]]
        assert [r["kind"] for r in execution["input_files"]] == ["node"]
        assert len(list(uploads.iterdir())) == 1

    def test_piece_left_by_a_lost_worker_is_finished_by_another(self, client, db):
        auth = signup_and_login(client)
        first, second = self._workers(client, auth, 2)
        source = upload(client, auth, "run.log", "".join(f"l{index}\n" for index in range(100)).encode())
        service = self._split_service(client, auth, [source["id"]])
        self._start(client, auth, service)
        lost = client.post("/worker/tasks/next", headers=first).json()
        kept = client.post("/worker/tasks/next", headers=second).json()
        # 워커1이 꺼져 하트비트가 끊긴다
        device = db.query(models.Device).filter_by(name="워커1").one()
        device.last_heartbeat = models.utcnow() - timedelta(minutes=5)
        db.commit()
        self._finish(client, second, kept, "둘째 조각")
        again = client.post("/worker/tasks/next", headers=second).json()
        assert again["task_id"] == lost["task_id"] and again["agent_name"] == "에이전트 a #1"

    def test_split_problems_are_reported_before_running(self, client):
        auth = signup_and_login(client)
        pdf = upload(client, auth, "report.pdf", b"%PDF")
        service = self._split_service(client, auth, [pdf["id"]])

        def codes(result, severity="errors"):
            return [issue["code"] for issue in result[severity]]

        def validate(patch):
            graph = editable_graph(service)
            graph["nodes"][0].update(patch)
            return client.post(f"/services/{service['id']}/validate", json={"graph": graph}, headers=auth).json()

        # 온라인 Worker가 없어도 형식 문제를 먼저 알린다
        assert codes(service["validation"]) == ["split_unsupported"]
        log = upload(client, auth, "run.log", b"a\nb\nc\n")
        assert codes(validate({"uploaded_file_ids": [log["id"]]})) == ["split_no_worker"]
        self._workers(client, auth, 1)
        assert codes(validate({"uploaded_file_ids": [log["id"]]})) == []
        assert codes(validate({"uploaded_file_ids": [log["id"], pdf["id"]], "split": {"enabled": True, "unit": "line"}})) == ["split_unsupported"]
        assert codes(validate({"uploaded_file_ids": [log["id"]], "provider": "openai", "executor": "cloud"})) == ["split_cloud"]
        assert codes(validate({"uploaded_file_ids": [], "text_input_enabled": True})) == ["split_no_file"]
        big = upload(client, auth, "big.log", ("x" * 99 + "\n").encode() * 20_000)
        assert codes(validate({"uploaded_file_ids": [big["id"]]})) == ["split_too_large"]

        # 실행도 같은 검사로 막는다
        r = client.post(f"/services/{service['id']}/executions", json={"run_prompt": "x"}, headers=auth)
        assert r.status_code == 422
        assert r.json()["detail"]["validation"]["errors"][0]["code"] == "split_unsupported"

        # 뒤에 모을 블록이 없으면 경고만 한다
        graph = editable_graph(service)
        graph["nodes"] = [graph["nodes"][2]]
        graph["edges"] = []
        graph["nodes"][0].update(uploaded_file_ids=[log["id"]], split={"enabled": True})
        result = client.post(f"/services/{service['id']}/validate", json={"graph": graph}, headers=auth).json()
        assert (codes(result), codes(result, "warnings")) == ([], ["split_no_next"])

    def test_split_settings_are_validated_on_save(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["nodes"][0]["split"] = {"enabled": True, "parts": 500}
        assert client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth).status_code == 422


class TestWorkerLoadAndAccount:
    """Worker 사용률 경고·유휴 판단: 넘김, 일시 중지, 자리 비움, 계정 표시."""

    def _two_workers(self, client):
        auth = signup_and_login(client)
        first = register_device(client, auth, name="A")
        second = register_device(client, auth, name="B")
        for key in (first, second):
            client.post("/worker/heartbeat", headers=key)
        return auth, first, second

    def _device(self, client, auth, name):
        return next(d for d in client.get("/devices", headers=auth).json() if d["name"] == name)

    def test_released_task_is_finished_by_another_worker(self, client):
        auth, first, second = self._two_workers(client)
        service = create_service(client, auth)
        execution = client.post(f"/services/{service['id']}/executions", json={"run_prompt": "실행"}, headers=auth).json()
        task = client.post("/worker/tasks/next", headers=first).json()

        released = client.post(f"/worker/tasks/{task['task_id']}/release", headers=first)
        assert released.status_code == 200 and released.json()["paused_until"]
        # 넘긴 A는 5분 동안 새 작업을 받지 않고, 그 이유가 기기 목록에 보인다
        assert client.post("/worker/tasks/next", headers=first).status_code == 204
        device = self._device(client, auth, "A")
        assert device["state"] == "paused" and "5분" in device["state_reason"]

        # B가 같은 작업을 이어받아 끝낸다
        again = client.post("/worker/tasks/next", headers=second).json()
        assert again["task_id"] == task["task_id"]
        assert self._device(client, auth, "B")["state"] == "running"
        # A가 늦게 보낸 결과는 거부된다
        late = client.post(f"/worker/tasks/{task['task_id']}/result", json={"status": "done", "output": "늦은 결과"}, headers=first)
        assert late.status_code == 404
        done = client.post(f"/worker/tasks/{task['task_id']}/result", json={"status": "done", "output": "B 결과"}, headers=second)
        assert done.status_code == 200
        body = client.get(f"/executions/{execution['id']}", headers=auth).json()
        assert [(t["status"], t["assigned_device_name"]) for t in body["tasks"]][0] == ("done", "B")

        # 다른 기기의 작업은 넘길 수 없고, 끝난 작업도 넘길 수 없다
        assert client.post(f"/worker/tasks/{task['task_id']}/release", headers=first).status_code == 404
        assert client.post(f"/worker/tasks/{task['task_id']}/release", headers=second).status_code == 409

        # Worker 화면에서 일시 중지를 풀면 다시 받는다. Worker가 보낸 값으로 일시 중지를 덮어쓸 수는 없다
        client.post("/worker/heartbeat", json={"specs": {"paused_until": None, "resource_limits": {}}}, headers=first)
        assert self._device(client, auth, "A")["state"] == "paused"
        assert client.post("/worker/resume", headers=first).status_code == 200
        assert self._device(client, auth, "A")["state"] == "available"

    def test_idle_threshold_and_overload_settings(self, client):
        auth, first, _ = self._two_workers(client)
        device = self._device(client, auth, "A")
        r = client.patch(
            f"/devices/{device['id']}",
            json={"resource_limits": {"max_cpu_percent": 70, "min_user_idle_min": 5, "on_overload": "release"}},
            headers=auth,
        )
        assert r.status_code == 200
        assert r.json()["resource_limits"] == {
            "max_cpu_percent": 70, "max_gpu_percent": None, "min_user_idle_min": 5, "on_overload": "release",
        }
        bad = client.patch(f"/devices/{device['id']}", json={"resource_limits": {"on_overload": "explode"}}, headers=auth)
        assert bad.status_code == 422

        service = create_service(client, auth)
        client.post(f"/services/{service['id']}/executions", json={"run_prompt": "실행"}, headers=auth)
        # 사용자가 1분 전에 입력했으면 안 받고, 기준(5분)을 넘기면 받는다
        client.post("/worker/heartbeat", json={"specs": {"user_idle_sec": 60, "other_cpu_percent": 5}}, headers=first)
        assert client.post("/worker/tasks/next", headers=first).status_code == 204
        assert self._device(client, auth, "A")["state"] == "user_active"
        client.post("/worker/heartbeat", json={"specs": {"user_idle_sec": 400, "other_cpu_percent": 5}}, headers=first)
        assert client.post("/worker/tasks/next", headers=first).status_code == 200

    def test_heartbeat_tells_the_worker_its_account_and_limits(self, client):
        auth = signup_and_login(client, username="hyunjeong", email="hyunjeong@example.com")
        key = register_device(client, auth, name="연구실 PC")
        device = self._device(client, auth, "연구실 PC")
        client.patch(f"/devices/{device['id']}", json={"resource_limits": {"max_cpu_percent": 70}}, headers=auth)

        body = client.post("/worker/heartbeat", headers=key).json()
        assert body["ok"] is True and body["device_id"] == device["id"] and body["device_name"] == "연구실 PC"
        assert body["account"] == {"username": "hyunjeong", "email": "h***@example.com"}
        assert body["resource_limits"] == {"max_cpu_percent": 70} and body["paused_until"] is None

        # 웹에서 기기를 지우면 하트비트가 401로 실패해 Worker가 다시 로그인하게 된다
        assert client.delete(f"/devices/{device['id']}", headers=auth).status_code == 204
        assert client.post("/worker/heartbeat", headers=key).status_code == 401


class TestSplitFromRunScreen:
    """실행 화면에서 이번 실행에만 분할을 켜고 끈다. 저장된 워크플로우는 바뀌지 않는다."""

    @pytest.fixture(autouse=True)
    def uploads(self, tmp_path, monkeypatch):
        for module in ("app.routers.files", "app.routers.worker", "app.services.split_inputs"):
            monkeypatch.setattr(f"{module}.UPLOAD_DIR", tmp_path)

    def test_turning_split_on_for_one_run(self, client):
        auth = signup_and_login(client)
        for name in ("A", "B"):
            client.post("/worker/heartbeat", headers=register_device(client, auth, name=name))
        log = upload(client, auth, "big.log", "".join(f"line {i}\n" for i in range(1, 1001)).encode())
        service = create_service(client, auth)
        inputs = {"nodes": {"a": [log["id"]]}, "split": {"a": True}}

        preview = client.post(f"/services/{service['id']}/executions/preview", json={"run_prompt": "x", "input_files": inputs}, headers=auth).json()
        assert [(s["node_id"], s["parts"], s["sizes"]) for s in preview["validation"]["splits"]] == [("a", 2, [500, 500])]

        execution = client.post(f"/services/{service['id']}/executions", json={"run_prompt": "x", "input_files": inputs}, headers=auth)
        assert execution.status_code == 201, execution.text
        assert execution.json()["stages"][0] == ["a__p01", "a__p02"]
        saved = client.get(f"/services/{service['id']}", headers=auth).json()
        assert not (saved["graph"]["nodes"][0].get("split") or {}).get("enabled")

        # 끄면 나누지 않는다
        off = {"nodes": {"a": [log["id"]]}, "split": {"a": False}}
        preview = client.post(f"/services/{service['id']}/executions/preview", json={"run_prompt": "x", "input_files": off}, headers=auth).json()
        assert preview["validation"]["splits"] == []

    def test_turning_off_keeps_saved_split_settings_for_later(self, client):
        auth = signup_and_login(client)
        client.post("/worker/heartbeat", headers=register_device(client, auth))
        log = upload(client, auth, "big.log", b"a\nb\nc\nd\n")
        service = create_service(client, auth)
        graph = editable_graph(service)
        graph["nodes"][0].update(uploaded_file_ids=[log["id"]], split={"enabled": True, "parts": 4})
        client.put(f"/services/{service['id']}", json={"graph": graph}, headers=auth)
        on = client.post(f"/services/{service['id']}/executions/preview", json={"run_prompt": "x", "input_files": {"split": {"a": True}}}, headers=auth).json()
        # 편집 화면에서 정한 조각 수(4)를 그대로 쓴다
        assert on["validation"]["splits"][0]["parts"] == 4
        off = client.post(f"/services/{service['id']}/executions/preview", json={"run_prompt": "x", "input_files": {"split": {"a": False}}}, headers=auth).json()
        assert off["validation"]["splits"] == []

    def test_unknown_block_is_rejected(self, client):
        auth = signup_and_login(client)
        service = create_service(client, auth)
        r = client.post(f"/services/{service['id']}/executions/preview", json={"input_files": {"split": {"ghost": True}}}, headers=auth)
        assert r.status_code == 422
