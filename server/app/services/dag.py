"""DAG 검증 및 위상 정렬.

요구사항 2.5: 순환 구조나 실행 불가능한 구성은 검증 단계에서 차단한다.
"""

from collections import defaultdict, deque


class DagError(ValueError):
    pass


def validate_graph(graph: dict) -> list[str]:
    """그래프를 검증하고 위상 정렬된 노드 id 목록을 반환한다.

    실패 시 DagError(사유) 를 던진다.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        raise DagError("워크플로우에 에이전트가 하나도 없습니다.")

    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        raise DagError("에이전트 id가 중복되었습니다.")
    id_set = set(ids)

    for e in edges:
        if e["source"] not in id_set or e["target"] not in id_set:
            raise DagError(f"연결이 존재하지 않는 에이전트를 참조합니다: {e['source']} -> {e['target']}")
        if e["source"] == e["target"]:
            raise DagError(f"자기 자신으로의 연결은 허용되지 않습니다: {e['source']}")

    # Kahn 알고리즘으로 위상 정렬 — 남는 노드가 있으면 순환
    indegree: dict[str, int] = {i: 0 for i in ids}
    adj: dict[str, list[str]] = defaultdict(list)
    seen_edges = set()
    for e in edges:
        key = (e["source"], e["target"])
        if key in seen_edges:
            continue  # 중복 간선은 무시
        seen_edges.add(key)
        adj[e["source"]].append(e["target"])
        indegree[e["target"]] += 1

    queue = deque([i for i in ids if indegree[i] == 0])
    order: list[str] = []
    while queue:
        cur = queue.popleft()
        order.append(cur)
        for nxt in adj[cur]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(ids):
        raise DagError("순환 구조가 감지되었습니다. 연결을 수정해 주세요.")

    return order


def parents_of(graph: dict) -> dict[str, list[str]]:
    parents: dict[str, list[str]] = {n["id"]: [] for n in graph.get("nodes", [])}
    for e in graph.get("edges", []):
        if e["target"] in parents and e["source"] not in parents[e["target"]]:
            parents[e["target"]].append(e["source"])
    return parents


def terminal_nodes(graph: dict) -> list[str]:
    """나가는 간선이 없는 노드들 (최종 결과 수집 대상)."""
    sources = {e["source"] for e in graph.get("edges", [])}
    return [n["id"] for n in graph.get("nodes", []) if n["id"] not in sources]
