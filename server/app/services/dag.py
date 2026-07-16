"""DAG 검증 및 위상 정렬.

요구사항 2.5: 순환 구조나 실행 불가능한 구성은 검증 단계에서 차단한다.
"""

from collections import defaultdict, deque

from asyncio import graph


class DagError(ValueError):
    pass

def _node_type(node: dict) -> str:
    """기존 노드에 type이 없으면 agent로 취급한다."""
    return node.get("type", "agent")


def _edge_relation(edge: dict) -> str:
    """기존 간선에 relation이 없으면 workflow로 취급한다."""
    return edge.get("relation", "workflow")


def validate_graph(graph: dict) -> list[str]:
    """그래프를 검증하고 에이전트 노드의 위상 정렬 결과를 반환한다."""

    all_nodes = graph.get("nodes", [])
    all_edges = graph.get("edges", [])

    if not all_nodes:
        raise DagError("워크플로우에 노드가 하나도 없습니다.")

    all_ids = [node["id"] for node in all_nodes]

    if len(all_ids) != len(set(all_ids)):
        raise DagError("노드 id가 중복되었습니다.")

    all_id_set = set(all_ids)

    agent_nodes = [
        node
        for node in all_nodes
        if _node_type(node) == "agent"
    ]

    directory_nodes = [
        node
        for node in all_nodes
        if _node_type(node) == "directory"
    ]

    if not agent_nodes:
        raise DagError("워크플로우에 에이전트가 하나도 없습니다.")

    agent_ids = [node["id"] for node in agent_nodes]
    agent_id_set = set(agent_ids)

    directory_ids = {
        node["id"]
        for node in directory_nodes
    }

    workflow_edges = [
        edge
        for edge in all_edges
        if _edge_relation(edge) == "workflow"
    ]

    directory_edges = [
        edge
        for edge in all_edges
        if _edge_relation(edge) == "directory"
    ]

    # 모든 간선의 source/target 존재 여부 검사
    for edge in all_edges:
        source = edge["source"]
        target = edge["target"]

        if source not in all_id_set or target not in all_id_set:
            raise DagError(
                "연결이 존재하지 않는 노드를 참조합니다: "
                f"{source} -> {target}"
            )

        if source == target:
            raise DagError(
                f"자기 자신으로의 연결은 허용되지 않습니다: {source}"
            )

    # workflow 간선은 Agent -> Agent만 허용
    for edge in workflow_edges:
        source = edge["source"]
        target = edge["target"]

        if source not in agent_id_set or target not in agent_id_set:
            raise DagError(
                "workflow 연결은 에이전트끼리만 연결할 수 있습니다: "
                f"{source} -> {target}"
            )

    # directory 간선은 Agent -> Directory만 허용
    for edge in directory_edges:
        source = edge["source"]
        target = edge["target"]

        if source not in agent_id_set:
            raise DagError(
                "directory 연결의 source는 에이전트여야 합니다: "
                f"{source} -> {target}"
            )

        if target not in directory_ids:
            raise DagError(
                "directory 연결의 target은 디렉토리여야 합니다: "
                f"{source} -> {target}"
            )

    # workflow 간선만 이용해 위상 정렬
    indegree: dict[str, int] = {
        agent_id: 0
        for agent_id in agent_ids
    }

    adjacency: dict[str, list[str]] = defaultdict(list)
    seen_edges: set[tuple[str, str]] = set()

    for edge in workflow_edges:
        source = edge["source"]
        target = edge["target"]

        key = (source, target)

        if key in seen_edges:
            continue

        seen_edges.add(key)
        adjacency[source].append(target)
        indegree[target] += 1

    queue = deque(
        agent_id
        for agent_id in agent_ids
        if indegree[agent_id] == 0
    )

    order: list[str] = []

    while queue:
        current = queue.popleft()
        order.append(current)

        for next_id in adjacency[current]:
            indegree[next_id] -= 1

            if indegree[next_id] == 0:
                queue.append(next_id)

    if len(order) != len(agent_ids):
        raise DagError(
            "에이전트 실행 흐름에서 순환 구조가 감지되었습니다. "
            "연결을 수정해 주세요."
        )

    return order


def parents_of(graph: dict) -> dict[str, list[str]]:
    agent_ids = {
        node["id"]
        for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent"
    }

    parents: dict[str, list[str]] = {
        agent_id: []
        for agent_id in agent_ids
    }

    for edge in graph.get("edges", []):
        if edge.get("relation", "workflow") != "workflow":
            continue

        source = edge["source"]
        target = edge["target"]

        if (
            source in agent_ids
            and target in parents
            and source not in parents[target]
        ):
            parents[target].append(source)

    return parents


def terminal_nodes(graph: dict) -> list[str]:
    """나가는 workflow 간선이 없는 에이전트 노드."""

    agent_nodes = [
        node
        for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent"
    ]

    workflow_sources = {
        edge["source"]
        for edge in graph.get("edges", [])
        if edge.get("relation", "workflow") == "workflow"
    }

    return [
        node["id"]
        for node in agent_nodes
        if node["id"] not in workflow_sources
    ]
