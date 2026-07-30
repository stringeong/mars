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
