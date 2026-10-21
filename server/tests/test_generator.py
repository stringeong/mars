"""generator 검증 — LLM 출력 파싱, 생성 모델 선택, 재시도와 실패 원인, 사용자가 고르는 기본 워크플로우.

Ollama HTTP 호출은 httpx.MockTransport로 대체한다.
"""

import asyncio
import json

import httpx
import pytest

from app.config import DEFAULT_MODEL
from app.services import dag, generator
from app.services.generator import GenerationError, GeneratorChoice, _extract_json, _fallback_graph


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

    def test_fallback_keeps_prompt_as_goal_not_role_prompt(self):
        graph = _fallback_graph("이력서 첨삭")
        assert graph["description"] == "이력서 첨삭"
        assert graph["goal"] == "이력서 첨삭"
        # 생성 프롬프트 전체가 역할 프롬프트에 그대로 붙지 않는다
        assert all("이력서 첨삭" not in n["role_prompt"] for n in graph["nodes"])

    def test_fallback_workflow_records_reason(self):
        graph, info = generator.fallback_workflow("여행 계획", reason="연결 실패")
        assert info["source"] == "fallback"
        assert info["fallback_reason"] == "연결 실패"
        assert info["model"] is None
        assert [n["id"] for n in graph["nodes"] if n["final"]] == ["writer"]
        assert graph["goal"] == "여행 계획"
        # 기본 워크플로우는 파일을 요구하지 않는다. 시작 블록 입력은 사용자가 정한다
        assert graph["input_slots"] == []

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

        graph, info = asyncio.run(generator.generate_workflow("문서 요약"))

        assert info["source"] == "llm"
        assert info["location"] == "local" and info["model"] == DEFAULT_MODEL
        assert calls[0]["model"] == DEFAULT_MODEL
        assert len(calls) == 1
        assert calls[0]["options"]["temperature"] == 0.3
        assert calls[0]["messages"][1]["content"] == "문서 요약"
        # id 없는 노드에 agent{i} 부여, model/directory_ids 필드 보강
        assert [n["id"] for n in graph["nodes"]] == ["reader", "agent1"]
        for n in graph["nodes"]:
            assert n["model"] == ""
            assert n["directory_ids"] == []
        # source가 빈 간선은 제거된다
        assert graph["edges"] == [{"source": "reader", "target": "agent1", "relation": "workflow"}]

    def test_single_sink_is_marked_final(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(VALID_LLM_REPLY)

        graph, _ = asyncio.run(generator.generate_workflow("문서 요약"))

        assert {n["id"]: n["final"] for n in graph["nodes"]} == {"reader": False, "agent1": True}
        assert dag.inspect_graph(graph, run_prompt="요약")["final_node_ids"] == ["agent1"]

    def test_two_final_marks_are_reduced_to_one_sink(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(json.dumps({
            "name": "s", "description": "d",
            "nodes": [
                {"id": "a", "name": "수집", "final": True},
                {"id": "b", "name": "요약", "final": True},
                {"id": "c", "name": "보고서", "final": True},
            ],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
        }))

        graph, _ = asyncio.run(generator.generate_workflow("요청"))

        # 생성기가 둘 이상 고르면 끝 블록 기준으로 하나만 남긴다
        assert [n["id"] for n in graph["nodes"] if n["final"]] == ["c"]

    def test_start_block_without_file_hint_gets_no_slot(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(VALID_LLM_REPLY)

        graph, _ = asyncio.run(generator.generate_workflow("문서 요약"))

        reader = next(n for n in graph["nodes"] if n["id"] == "reader")
        # 시작 블록이어도 생성기가 파일이 필요하다고 하지 않았으면 슬롯을 만들지 않는다
        assert reader["needs_file_hint"] is False and reader["needs_file"] is False
        assert graph["input_slots"] == []
        assert reader["input_slot_ids"] == []
        assert reader["text_input_enabled"] is False and reader["allow_no_input"] is False

    def test_cyclic_reply_retries_then_reports_validation_error(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(CYCLIC_LLM_REPLY)

        with pytest.raises(GenerationError) as error:
            asyncio.run(generator.generate_workflow("무한 루프"))

        # 온도를 낮춰 1회 재시도한 뒤, 기본 워크플로우로 바꾸지 않고 원인을 알린다
        assert [c["options"]["temperature"] for c in calls] == [0.3, 0.1]
        assert error.value.stage == "validation"
        assert error.value.detail()["model"] == DEFAULT_MODEL

    def test_garbage_reply_reports_parse_error(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append("JSON이 아닌 잡담입니다.")

        with pytest.raises(GenerationError) as error:
            asyncio.run(generator.generate_workflow("요청"))

        assert error.value.stage == "parse"
        assert len(calls) == 2

    def test_recovers_on_second_attempt(self, fake_ollama):
        calls, replies = fake_ollama
        replies.extend(["잡담", VALID_LLM_REPLY])

        graph, info = asyncio.run(generator.generate_workflow("요청"))

        assert info["source"] == "llm"
        assert len(calls) == 2
        assert calls[1]["options"]["temperature"] == 0.1

    def test_connection_error_is_reported_without_retry(self, fake_ollama):
        """Ollama가 실행 중이 아니면 재시도하지 않고 연결 실패로 알린다."""
        calls, replies = fake_ollama
        replies.append(httpx.ConnectError("Ollama 없음"))

        with pytest.raises(GenerationError) as error:
            asyncio.run(generator.generate_workflow("요청"))

        assert error.value.stage == "connection"
        assert "Ollama" in error.value.message
        assert len(calls) == 1

    def test_model_error_status_is_reported(self, fake_ollama):
        calls, replies = fake_ollama
        request = httpx.Request("POST", "http://ollama.test/api/chat")
        replies.append(httpx.HTTPStatusError(
            "404", request=request,
            response=httpx.Response(404, json={"error": "model 'x' not found"}, request=request),
        ))

        with pytest.raises(GenerationError) as error:
            asyncio.run(generator.generate_workflow("요청", GeneratorChoice(model="x")))

        assert error.value.stage == "connection"
        assert "404" in error.value.message and "model 'x' not found" in error.value.message

    def test_selected_local_model_is_used(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(VALID_LLM_REPLY)

        _, info = asyncio.run(generator.generate_workflow("요청", GeneratorChoice(model="qwen3:4b")))

        assert calls[0]["model"] == "qwen3:4b"
        assert info["model"] == "qwen3:4b"

    def test_cloud_choice_calls_provider_with_short_timeout(self, monkeypatch):
        seen = {}

        def fake_call(provider, key, model, system, user, timeout):
            seen.update(provider=provider, key=key, model=model, user=user, timeout=timeout)
            return VALID_LLM_REPLY, {"input_tokens": 12, "output_tokens": 34}

        monkeypatch.setattr("app.services.cloud_executor._call", fake_call)
        choice = GeneratorChoice(location="cloud", provider="openai", model="gpt-5-mini", api_key="sk-test")

        graph, info = asyncio.run(generator.generate_workflow("문서 요약", choice))

        assert seen["provider"] == "openai" and seen["model"] == "gpt-5-mini"
        assert seen["user"] == "문서 요약"
        assert seen["timeout"] == generator.CLOUD_GENERATION_TIMEOUT
        assert info["location"] == "cloud" and info["provider"] == "openai"
        assert info["usage"] == {"input_tokens": 12, "output_tokens": 34}
        assert "sk-test" not in repr(choice)

    def test_file_requirements_become_shared_slots(self, fake_ollama):
        calls, replies = fake_ollama
        replies.append(json.dumps({
            "name": "가계부", "description": "d",
            "nodes": [
                {"id": "classify", "name": "분류", "needs_file": True, "file_key": "card",
                 "file_description": "신용카드 사용 내역", "file_format": "CSV, 열: 거래ID, 금액"},
                {"id": "detect", "name": "탐지", "needs_file": "true", "file_key": "card"},
                {"id": "report", "name": "리포트", "needs_file": False, "final": True},
            ],
            "edges": [{"source": "classify", "target": "report"}, {"source": "detect", "target": "report"}],
        }, ensure_ascii=False))

        graph, _ = asyncio.run(generator.generate_workflow("가계부 분석"))

        assert graph["input_slots"] == [{
            "id": "slot1", "description": "신용카드 사용 내역", "format": "CSV, 열: 거래ID, 금액",
            "file_ids": [], "directory_ids": [],
        }]
        by_id = {n["id"]: n for n in graph["nodes"]}
        assert by_id["classify"]["input_slot_ids"] == by_id["detect"]["input_slot_ids"] == ["slot1"]
        assert by_id["report"]["needs_file"] is False and by_id["report"]["input_slot_ids"] == []
        # 파일이 아직 없으므로 검사에서 두 블록 모두 파일 누락 오류가 된다
        errors = dag.inspect_graph(graph)["errors"]
        assert sorted(e["node_ids"][0] for e in errors if e["code"] == "missing_file") == ["classify", "detect"]


CURRENT_GRAPH = {
    "nodes": [
        {
            "id": "agent1", "name": "수집", "role_prompt": "수집하라",
            "model": "gemma3:4b", "directory_ids": [1],
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
        assert kept["directory_ids"] == [1]
        assert kept["position"] == {"x": 10, "y": 20}
        new = revised["nodes"][1]
        assert new["model"] == "" and new["directory_ids"] == []
        assert revised["edges"] == [{"source": "agent1", "target": "agent2", "relation": "workflow"}]

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
