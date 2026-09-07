"""generator 검증 — LLM 출력 파싱, 규칙 기반 폴백, 재시도/폴백 사다리.

Ollama HTTP 호출은 httpx.MockTransport로 대체한다.
"""

import asyncio
import json

import httpx
import pytest

from app.services import dag, generator
from app.services.generator import _extract_json, _fallback_graph


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"name": "svc"}') == {"name": "svc"}

    def test_json_wrapped_in_prose(self):
        text = '다음은 결과입니다:\n{"name": "svc"}\n이상입니다.'
        assert _extract_json(text) == {"name": "svc"}

    def test_think_block_removed(self):
        text = '<think>{"name": "가짜"}\n생각 중...</think>{"name": "진짜"}'
        assert _extract_json(text) == {"name": "진짜"}

    def test_multiline_nested_json(self):
        data = {"nodes": [{"id": "a"}], "edges": []}
        assert _extract_json("```json\n" + json.dumps(data, indent=2) + "\n```") == data

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            _extract_json("JSON이 없는 답변입니다.")

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("{name: 따옴표 없는 키}")


class TestFallbackGraph:
    def test_fallback_is_always_valid_dag(self):
        graph = _fallback_graph("여행 계획 서비스")
        # 폴백은 '항상 유효한 그래프 보장'이 계약이므로 DAG 검증을 통과해야 한다
        assert dag.validate_graph(graph) == ["collector", "analyzer", "writer"]

    def test_fallback_embeds_prompt(self):
        graph = _fallback_graph("이력서 첨삭")
        assert graph["description"] == "이력서 첨삭"
        assert "이력서 첨삭" in graph["nodes"][0]["role_prompt"]

    def test_fallback_name_truncates_long_prompt(self):
        graph = _fallback_graph("긴 프롬프트 " * 50)
        assert len(graph["name"]) <= 40 + len(" 서비스")


@pytest.fixture()
def fake_ollama(monkeypatch):
    """Ollama /api/chat 을 가짜 응답으로 대체하고 호출 페이로드를 기록한다.

    replies에 담긴 항목을 호출 순서대로 돌려준다. 문자열이면 그대로 content로,
    예외 인스턴스면 해당 호출에서 raise한다.
    """
    calls: list[dict] = []
    replies: list = []
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json={"message": {"content": reply}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        generator.httpx, "AsyncClient", lambda **kw: real_client(transport=transport)
    )
    return calls, replies


VALID_LLM_REPLY = json.dumps({
    "name": "요약 서비스",
    "description": "문서를 요약한다",
    "nodes": [
        {"id": "reader", "name": "읽기", "role_prompt": "문서를 읽어라"},
        {"name": "요약", "role_prompt": "요약하라"},  # id 없음 -> agent1 부여
    ],
    "edges": [
        {"source": "reader", "target": "agent1"},
        {"source": "", "target": "agent1"},  # source 없음 -> 제거
    ],
}, ensure_ascii=False)

CYCLIC_LLM_REPLY = json.dumps({
    "name": "순환", "description": "d",
    "nodes": [{"id": "a", "name": "a"}, {"id": "b", "name": "b"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
})


class TestGenerateWorkflow:
    def test_valid_llm_reply_normalized(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(VALID_LLM_REPLY)

        graph, source = asyncio.run(generator.generate_workflow("문서 요약"))

        assert source == "llm"
        assert len(calls) == 1
        assert calls[0]["options"]["temperature"] == 0.3
        assert calls[0]["messages"][1]["content"] == "문서 요약"
        # id 없는 노드에 agent{i} 부여, model/allowed_folders 필드 보강
        assert [n["id"] for n in graph["nodes"]] == ["reader", "agent1"]
        for n in graph["nodes"]:
            assert n["model"] == ""
            assert n["allowed_folders"] == []
        # source가 빈 간선은 제거된다
        assert graph["edges"] == [{"source": "reader", "target": "agent1"}]

    def test_cyclic_reply_retries_then_falls_back(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(CYCLIC_LLM_REPLY)

        graph, source = asyncio.run(generator.generate_workflow("무한 루프"))

        assert source == "fallback"
        # 온도를 낮춰 1회 재시도한 뒤 폴백
        assert [c["options"]["temperature"] for c in calls] == [0.3, 0.1]
        assert dag.validate_graph(graph)  # 폴백은 항상 유효한 DAG
        for n in graph["nodes"]:
            assert "model" in n and "allowed_folders" in n

    def test_garbage_reply_falls_back(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append("JSON이 아닌 잡담입니다.")

        graph, source = asyncio.run(generator.generate_workflow("요청"))

        assert source == "fallback"
        assert dag.validate_graph(graph)

    def test_recovers_on_second_attempt(self, fake_ollama):
        calls, replies = fake_ollama
        replies.extend(["잡담", VALID_LLM_REPLY])

        graph, source = asyncio.run(generator.generate_workflow("요청"))

        assert source == "llm"
        assert len(calls) == 2
        assert calls[1]["options"]["temperature"] == 0.1

    def test_connection_error_falls_back(self, fake_ollama):
        """Ollama가 아예 실행 중이 아니어도 생성은 항상 성공해야 한다."""
        calls, replies = fake_ollama
        replies.append(httpx.ConnectError("Ollama 없음"))

        graph, source = asyncio.run(generator.generate_workflow("요청"))

        assert source == "fallback"
        assert dag.validate_graph(graph)


CURRENT_GRAPH = {
    "nodes": [
        {
            "id": "agent1", "name": "수집", "role_prompt": "수집하라",
            "model": "gemma3:4b", "allowed_folders": ["/docs"],
            "position": {"x": 10, "y": 20},
        },
    ],
    "edges": [],
}


class TestReviseWorkflow:
    def test_kept_node_preserves_local_settings(self, fake_ollama):
        """수정 지시와 무관한 설정(모델·허용 폴더·좌표)은 id 기준으로 보존된다."""
        calls, replies = fake_ollama
        replies.append(json.dumps({
            "name": "새 이름", "description": "새 설명",
            "nodes": [
                {"id": "agent1", "name": "수집", "role_prompt": "더 꼼꼼히 수집하라"},
                {"id": "agent2", "name": "검토", "role_prompt": "검토하라"},
            ],
            "edges": [{"source": "agent1", "target": "agent2"}],
        }, ensure_ascii=False))

        revised = asyncio.run(generator.revise_workflow(CURRENT_GRAPH, "검토 단계 추가"))

        kept = revised["nodes"][0]
        assert kept["role_prompt"] == "더 꼼꼼히 수집하라"  # 지시 반영
        assert kept["model"] == "gemma3:4b"
        assert kept["allowed_folders"] == ["/docs"]
        assert kept["position"] == {"x": 10, "y": 20}
        new = revised["nodes"][1]
        assert new["model"] == "" and new["allowed_folders"] == []
        assert revised["edges"] == [{"source": "agent1", "target": "agent2"}]

    def test_empty_role_prompt_falls_back_to_previous(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(json.dumps({
            "nodes": [{"id": "agent1", "name": "", "role_prompt": ""}],
            "edges": [],
        }))

        revised = asyncio.run(generator.revise_workflow(CURRENT_GRAPH, "이름만 바꿔"))

        assert revised["nodes"][0]["name"] == "수집"
        assert revised["nodes"][0]["role_prompt"] == "수집하라"

    def test_garbage_reply_raises_without_fallback(self, fake_ollama):
        """수정은 폴백이 없어야 한다 — 실패 시 기존 그래프를 보존하도록 예외."""
        calls, replies = fake_ollama
        replies.append("잡담뿐인 응답")

        with pytest.raises(ValueError):
            asyncio.run(generator.revise_workflow(CURRENT_GRAPH, "수정해"))

    def test_empty_nodes_raises(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(json.dumps({"nodes": [], "edges": []}))

        with pytest.raises(ValueError):
            asyncio.run(generator.revise_workflow(CURRENT_GRAPH, "전부 지워"))
