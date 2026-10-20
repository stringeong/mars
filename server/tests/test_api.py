"""API 통합 테스트 — 회원가입부터 실행 완료까지 전 구간 + 인증/격리 가드.

워크플로우 생성 LLM은 mock으로 대체한다 (LLM 파싱 자체는 test_generator.py에서 검증).
"""

import copy

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.conftest import LINEAR


GENERATE_CALLS: list = []


@pytest.fixture()
def client(db, monkeypatch):
    async def fake_generate(prompt, choice=None):
        graph = copy.deepcopy(LINEAR)
        graph["name"] = "테스트 서비스"
        graph["description"] = prompt
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
        draft["nodes"][1]["needs_file"] = True
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

    def test_blank_run_prompt_rejected(self, client):
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
        graph["nodes"][1]["needs_file"] = True
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
        graph["nodes"].append({"id": "x", "type": "agent", "name": "고립", "uploaded_file_ids": []})
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
