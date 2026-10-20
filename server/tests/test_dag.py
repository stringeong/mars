"""dag.validate_graph / parents_of / terminal_nodes 검증.

요구사항 2.5: 순환 구조나 실행 불가능한 구성은 검증 단계에서 차단되어야 한다.
"""

import pytest

from app.services import dag
from tests.conftest import DIAMOND, LINEAR, graph_of


def assert_topological(order, edges):
    pos = {nid: i for i, nid in enumerate(order)}
    for s, t in edges:
        assert pos[s] < pos[t], f"{s} 가 {t} 보다 앞에 와야 함: {order}"


class TestValidateGraph:
    def test_linear_graph_returns_topological_order(self):
        assert dag.validate_graph(LINEAR) == ["a", "b", "c"]

    def test_diamond_graph_order_respects_edges(self):
        order = dag.validate_graph(DIAMOND)
        assert sorted(order) == ["a", "b", "c", "d"]
        assert_topological(order, [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])

    def test_single_node_no_edges(self):
        assert dag.validate_graph(graph_of(["only"], [])) == ["only"]

    def test_disconnected_components_are_allowed(self):
        order = dag.validate_graph(graph_of(["a", "b", "x", "y"], [("a", "b"), ("x", "y")]))
        assert_topological(order, [("a", "b"), ("x", "y")])

    def test_empty_graph_rejected(self):
        with pytest.raises(dag.DagError):
            dag.validate_graph({"nodes": [], "edges": []})

    def test_missing_keys_rejected(self):
        with pytest.raises(dag.DagError):
            dag.validate_graph({})

    def test_duplicate_node_ids_rejected(self):
        graph = graph_of(["a", "b"], [])
        graph["nodes"].append(dict(graph["nodes"][0]))
        with pytest.raises(dag.DagError):
            dag.validate_graph(graph)

    def test_edge_referencing_unknown_node_rejected(self):
        with pytest.raises(dag.DagError):
            dag.validate_graph(graph_of(["a"], [("a", "ghost")]))
        with pytest.raises(dag.DagError):
            dag.validate_graph(graph_of(["a"], [("ghost", "a")]))

    def test_self_loop_rejected(self):
        with pytest.raises(dag.DagError):
            dag.validate_graph(graph_of(["a", "b"], [("a", "a")]))

    def test_two_node_cycle_rejected(self):
        with pytest.raises(dag.DagError):
            dag.validate_graph(graph_of(["a", "b"], [("a", "b"), ("b", "a")]))

    def test_longer_cycle_rejected(self):
        with pytest.raises(dag.DagError):
            dag.validate_graph(
                graph_of(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
            )

    def test_cycle_in_one_component_rejected(self):
        # 분리된 컴포넌트 중 하나에만 순환이 있어도 전체가 거부되어야 한다
        with pytest.raises(dag.DagError):
            dag.validate_graph(
                graph_of(["a", "b", "c", "d"], [("a", "b"), ("c", "d"), ("d", "c")])
            )

    def test_duplicate_edges_are_ignored(self):
        order = dag.validate_graph(graph_of(["a", "b"], [("a", "b"), ("a", "b")]))
        assert order == ["a", "b"]


class TestParentsOf:
    def test_diamond_parents(self):
        parents = dag.parents_of(DIAMOND)
        assert parents["a"] == []
        assert parents["b"] == ["a"]
        assert parents["c"] == ["a"]
        assert sorted(parents["d"]) == ["b", "c"]

    def test_duplicate_edges_deduplicated(self):
        parents = dag.parents_of(graph_of(["a", "b"], [("a", "b"), ("a", "b")]))
        assert parents["b"] == ["a"]

    def test_edge_to_unknown_target_ignored(self):
        parents = dag.parents_of(graph_of(["a"], [("a", "ghost")]))
        assert parents == {"a": []}


class TestTerminalNodes:
    def test_linear_terminal_is_last(self):
        assert dag.terminal_nodes(LINEAR) == ["c"]

    def test_diamond_terminal_is_sink(self):
        assert dag.terminal_nodes(DIAMOND) == ["d"]

    def test_no_edges_all_terminal(self):
        assert dag.terminal_nodes(graph_of(["a", "b"], [])) == ["a", "b"]

    def test_multiple_sinks(self):
        graph = graph_of(["a", "b", "c"], [("a", "b"), ("a", "c")])
        assert dag.terminal_nodes(graph) == ["b", "c"]



def test_one_directory_can_connect_to_multiple_agents():
    graph = {
        "nodes": [
            {
                "id": "dir_1",
                "type": "directory",
                "directory_id": 1,
                "name": "docs",
                "device_id": 1,
            },
            {
                "id": "a",
                "type": "agent",
                "name": "A",
            },
            {
                "id": "b",
                "type": "agent",
                "name": "B",
            },
        ],
        "edges": [
            {
                "source": "dir_1",
                "target": "a",
                "relation": "directory",
            },
            {
                "source": "dir_1",
                "target": "b",
                "relation": "directory",
            },
        ],
    }

    assert dag.validate_graph(graph) == ["a", "b"]
    assert dag.directory_ids_by_agent(graph) == {
        "a": [1],
        "b": [1],
    }


def test_shared_directory_does_not_change_workflow_order():
    graph = {
        "nodes": [
            {
                "id": "dir",
                "type": "directory",
                "directory_id": 1,
                "name": "docs",
                "device_id": 1,
            },
            {
                "id": "a",
                "type": "agent",
                "name": "A",
            },
            {
                "id": "b",
                "type": "agent",
                "name": "B",
            },
            {
                "id": "c",
                "type": "agent",
                "name": "C",
            },
        ],
        "edges": [
            {
                "source": "dir",
                "target": "a",
                "relation": "directory",
            },
            {
                "source": "dir",
                "target": "b",
                "relation": "directory",
            },
            {
                "source": "a",
                "target": "c",
                "relation": "workflow",
            },
            {
                "source": "b",
                "target": "c",
                "relation": "workflow",
            },
        ],
    }

    order = dag.validate_graph(graph)

    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("c")

def _with_file(graph, *node_ids, file_id=1):
    for n in graph["nodes"]:
        if n["id"] in node_ids:
            n["uploaded_file_ids"] = [file_id]
    return graph


def _codes(result, severity="errors"):
    return [(issue["code"], tuple(issue["node_ids"])) for issue in result[severity]]


class TestInspectGraph:
    """1번 개선: 실행 전·저장 시 블록 단위 오류/경고와 실행 단계 미리보기."""

    def test_valid_graph_reports_stages_and_implicit_final(self):
        graph = _with_file(graph_of(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]), "a")
        result = dag.inspect_graph(graph)
        assert result["valid"] is True
        assert result["errors"] == [] and result["warnings"] == []
        assert result["stages"] == [["a"], ["b", "c"], ["d"]]
        # final 표시가 없는 기존 워크플로우는 말단이 하나면 그 말단을 최종 블록으로 본다
        assert result["final_node_ids"] == ["d"]

    def test_stage_uses_longest_path_depth(self):
        # a -> b -> d, a -> d : d는 b 뒤에 와야 하므로 3단계
        graph = _with_file(graph_of(["a", "b", "d"], [("a", "b"), ("b", "d"), ("a", "d")]), "a")
        assert dag.inspect_graph(graph)["stages"] == [["a"], ["b"], ["d"]]

    def test_cycle_reports_only_cycle_blocks(self):
        graph = _with_file(graph_of(["a", "b", "c", "d"], [("a", "b"), ("b", "c"), ("c", "b"), ("c", "d")]), "a")
        result = dag.inspect_graph(graph)
        assert ("cycle", ("b", "c")) in _codes(result)
        assert result["valid"] is False

    def test_needs_file_without_file_is_error(self):
        graph = _with_file(graph_of(["a", "b"], [("a", "b")]), "a")
        graph["nodes"][1]["needs_file"] = True
        assert ("missing_file", ("b",)) in _codes(dag.inspect_graph(graph))

    def test_needs_file_satisfied_by_input_slot_or_directory(self):
        graph = graph_of(["a", "b"], [("a", "b")])
        graph["input_slots"] = [{"id": "s1", "file_ids": [7]}]
        graph["nodes"][0].update(needs_file=True, input_slot_ids=["s1"])
        graph["nodes"][1].update(needs_file=True, directory_ids=[3])
        assert dag.inspect_graph(graph)["errors"] == []

    def test_root_without_input_is_error_until_run_prompt_given(self):
        graph = graph_of(["a", "b"], [("a", "b")])
        result = dag.inspect_graph(graph)
        assert _codes(result) == [("no_input", ("a",))]
        assert result["errors"][0]["resolvable_by_run_prompt"] is True
        assert dag.inspect_graph(graph, run_prompt="이번 달 분석")["valid"] is True

    def test_multiple_sinks_without_final_is_error(self):
        graph = _with_file(graph_of(["a", "b", "c"], [("a", "b"), ("a", "c")]), "a")
        assert ("final_missing", ("b", "c")) in _codes(dag.inspect_graph(graph))

    def test_two_final_marks_are_error(self):
        graph = _with_file(graph_of(["a", "b", "c"], [("a", "b"), ("a", "c")]), "a")
        graph["nodes"][1]["final"] = graph["nodes"][2]["final"] = True
        assert ("final_multiple", ("b", "c")) in _codes(dag.inspect_graph(graph))

    def test_isolated_block_is_warning_when_final_is_marked(self):
        graph = _with_file(graph_of(["a", "b", "x"], [("a", "b")]), "a", "x")
        graph["nodes"][1]["final"] = True
        result = dag.inspect_graph(graph)
        assert result["valid"] is True
        assert _codes(result, "warnings") == [("unreachable", ("x",))]

    def test_model_missing_on_worker_is_warning(self):
        graph = _with_file(graph_of(["a"], []), "a")
        graph["nodes"][0].update(worker_id=1, model="qwen3:4b")
        result = dag.inspect_graph(graph, has_model=lambda node: False)
        assert _codes(result, "warnings") == [("model_not_installed", ("a",))]
        assert dag.inspect_graph(graph, has_model=lambda node: None)["warnings"] == []

    def test_invalid_reference_stops_block_checks(self):
        result = dag.inspect_graph(graph_of(["a"], [("a", "ghost")]))
        assert _codes(result) == [("invalid_graph", ())]

    def test_result_nodes_prefer_final_mark(self):
        graph = graph_of(["a", "b", "c"], [("a", "b"), ("a", "c")])
        assert dag.result_node_ids(graph) == ["b", "c"]
        graph["nodes"][2]["final"] = True
        assert dag.result_node_ids(graph) == ["c"]


def test_expand_input_slots_copies_slot_sources_into_blocks():
    graph = graph_of(["a", "b"], [("a", "b")])
    graph["input_slots"] = [{"id": "s1", "file_ids": [7], "directory_ids": [3]}]
    graph["nodes"][0].update(input_slot_ids=["s1"], uploaded_file_ids=[5])
    expanded = dag.expand_input_slots(graph)
    assert expanded["nodes"][0]["uploaded_file_ids"] == [5, 7]
    assert expanded["nodes"][0]["directory_ids"] == [3]
    assert expanded["nodes"][1].get("uploaded_file_ids", []) == []
    # 원본 그래프는 바뀌지 않는다
    assert graph["nodes"][0]["uploaded_file_ids"] == [5]
