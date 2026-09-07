"""API 통합 테스트 — 회원가입부터 실행 완료까지 전 구간 + 인증/격리 가드.

워크플로우 생성 LLM은 mock으로 대체한다 (LLM 파싱 자체는 test_generator.py에서 검증).
"""

import copy

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.conftest import LINEAR


@pytest.fixture()
def client(db, monkeypatch):
    async def fake_generate(prompt):
        graph = copy.deepcopy(LINEAR)
        graph["name"] = "테스트 서비스"
        graph["description"] = prompt
        return graph, "llm"

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
        assert r.json() == {"valid": True, "order": ["a", "b", "c"]}

    def test_duplicate_device_name_rejected(self, client):
        auth = signup_and_login(client)
        register_device(client, auth, name="노트북")
        r = client.post("/devices", json={"name": "노트북"}, headers=auth)
        assert r.status_code == 409


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
