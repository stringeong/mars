"""generator의 순수 함수 검증 — LLM 출력 파싱과 규칙 기반 폴백.

실제 Ollama HTTP 호출은 모킹하고, 파싱·폴백·재시도 정책을 검증한다.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx

import pytest

from app.services import dag
from app.services.generator import _extract_json, _fallback_graph, generate_workflow


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


class TestGenerateWorkflow:
    def test_network_failure_falls_back_immediately_with_canonical_graph(self):
        with patch(
            "app.services.generator._generate_once",
            new=AsyncMock(side_effect=httpx.ConnectError("Ollama unavailable")),
        ) as generate:
            graph, source = asyncio.run(
                generate_workflow("문서를 분석해 보고서를 작성해줘")
            )

        assert source == "fallback"
        assert generate.await_count == 1
        assert all(node["type"] == "agent" for node in graph["nodes"])
        assert all(edge["relation"] == "workflow" for edge in graph["edges"])
        assert dag.validate_graph(graph) == ["collector", "analyzer", "writer"]

    def test_invalid_model_output_is_retried_once(self):
        with patch(
            "app.services.generator._generate_once",
            new=AsyncMock(side_effect=ValueError("invalid model JSON")),
        ) as generate:
            graph, source = asyncio.run(generate_workflow("여행 계획을 만들어줘"))

        assert source == "fallback"
        assert generate.await_count == 2
        assert graph["nodes"][0]["type"] == "agent"
