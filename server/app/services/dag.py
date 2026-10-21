"""DAG 검증 및 위상 정렬.

요구사항 2.5: 순환 구조나 실행 불가능한 구성은 검증 단계에서 차단한다.
"""

import copy
from collections import defaultdict, deque


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

    # directory 간선은 Directory -> Agent만 허용
    for edge in directory_edges:
        source = edge["source"]
        target = edge["target"]

        if source not in directory_ids:
            raise DagError(
                "directory 연결의 source는 디렉토리여야 합니다: "
                f"{source} -> {target}"
            )

        if target not in agent_id_set:
            raise DagError(
                "directory 연결의 target은 에이전트여야 합니다: "
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


# directory_ids_by_agent : 각 에이전트에 연결된 SharedDirectory ID 목록을 반환
def directory_ids_by_agent(graph: dict) -> dict[str, list[int]]:

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    directory_node_map = {
        node["id"]: node
        for node in nodes
        if node.get("type") == "directory"
    }

    result: dict[str, list[int]] = {
        node["id"]: []
        for node in nodes
        if node.get("type", "agent") == "agent"
    }

    for edge in edges:
        if edge.get("relation") != "directory":
            continue

        directory_node_id = edge["source"]
        agent_node_id = edge["target"]

        directory_node = directory_node_map.get(directory_node_id)

        if directory_node is None:
            continue

        directory_id = directory_node.get("directory_id")

        if directory_id is None:
            continue

        if directory_id not in result[agent_node_id]:
            result[agent_node_id].append(directory_id)

    return result

# ---------- 구성 검사 (블록 단위 오류·경고, 실행 단계) ----------

def _agent_nodes(graph: dict) -> list[dict]:
    return [node for node in graph.get("nodes", []) if _node_type(node) == "agent"]


def _workflow_pairs(graph: dict) -> set[tuple[str, str]]:
    """에이전트끼리의 workflow 간선. 자기 자신으로의 연결도 순환으로 보기 위해 남긴다."""
    agent_ids = {node["id"] for node in _agent_nodes(graph)}
    return {
        (edge["source"], edge["target"])
        for edge in graph.get("edges", [])
        if _edge_relation(edge) == "workflow"
        and edge.get("source") in agent_ids
        and edge.get("target") in agent_ids
    }


def _levels(graph: dict) -> dict[str, int]:
    """순환에 걸리지 않은 에이전트의 깊이(가장 긴 선행 경로의 길이)."""
    agent_ids = [node["id"] for node in _agent_nodes(graph)]
    indegree = {agent_id: 0 for agent_id in agent_ids}
    children: dict[str, list[str]] = defaultdict(list)
    for source, target in _workflow_pairs(graph):
        children[source].append(target)
        indegree[target] += 1

    depth = {agent_id: 0 for agent_id in agent_ids}
    queue = deque(agent_id for agent_id in agent_ids if indegree[agent_id] == 0)
    done: dict[str, int] = {}
    while queue:
        current = queue.popleft()
        done[current] = depth[current]
        for child in children[current]:
            depth[child] = max(depth[child], depth[current] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return done


def stages(graph: dict) -> list[list[str]]:
    """DAG 깊이별 에이전트 묶음. 같은 단계의 블록은 동시에 실행될 수 있다."""
    levels = _levels(graph)
    grouped: dict[int, list[str]] = defaultdict(list)
    for node in _agent_nodes(graph):
        if node["id"] in levels:
            grouped[levels[node["id"]]].append(node["id"])
    return [grouped[level] for level in sorted(grouped)]


def cycle_node_ids(graph: dict) -> list[str]:
    """순환에 걸린 에이전트. 순환 뒤에만 있는 블록은 제외한다."""
    levels = _levels(graph)
    remaining = {node["id"] for node in _agent_nodes(graph)} - set(levels)
    pairs = {(s, t) for s, t in _workflow_pairs(graph) if s in remaining and t in remaining}
    # 남은 부분 그래프에서 나가는 간선이 없는 블록을 반복해서 걷어내면 순환만 남는다
    while True:
        sinks = {n for n in remaining if not any(s == n for s, _ in pairs)}
        if not sinks:
            break
        remaining -= sinks
        pairs = {(s, t) for s, t in pairs if t not in sinks}
    return [node["id"] for node in _agent_nodes(graph) if node["id"] in remaining]


def final_node_ids(graph: dict) -> list[str]:
    """최종 블록. final 표시가 있으면 그 블록들, 없으면 말단이 하나일 때만 그 말단(기존 워크플로우 호환)."""
    marked = [node["id"] for node in _agent_nodes(graph) if node.get("final")]
    if marked:
        return marked
    sinks = terminal_nodes(graph)
    return sinks if len(sinks) == 1 else []


def result_node_ids(graph: dict) -> list[str]:
    """실행 결과로 모을 블록. final 표시가 없으면 기존처럼 모든 말단을 모은다."""
    marked = [node["id"] for node in _agent_nodes(graph) if node.get("final")]
    return marked or terminal_nodes(graph)


def apply_auto_flags(graph: dict) -> dict:
    """최종 블록과 '사용자 파일 필요'를 규칙으로 정한 복사본. 직접 지정한 값(*_manual)은 바꾸지 않는다.

    - 파일 필요: 생성기가 필요하다고 했거나(needs_file_hint) 들어오는 연결이 없는 블록
    - 최종 블록: 직접 지정한 최종 블록이 있으면 그 블록만. 없으면 끝나는 블록 중 생성기가 고른
      블록(final_hint), 그것도 없으면 가장 뒤 단계(같으면 블록 순서상 뒤)의 끝나는 블록 하나
    """
    result = copy.deepcopy(graph)
    agents = _agent_nodes(result)
    parents = parents_of(result)
    for node in agents:
        if not node.get("needs_file_manual"):
            node["needs_file"] = bool(node.get("needs_file_hint")) or not parents.get(node["id"])
        if not node.get("final_manual"):
            node["final"] = False
    if any(node.get("final_manual") and node.get("final") for node in agents):
        return result
    # 직접 최종 블록에서 뺀 블록은 후보에서 제외한다
    excluded = {node["id"] for node in agents if node.get("final_manual")}
    sinks = [node_id for node_id in terminal_nodes(result) if node_id not in excluded]
    if not sinks:
        return result
    levels = _levels(result)
    order = {node["id"]: index for index, node in enumerate(agents)}
    hinted = {node["id"] for node in agents if node.get("final_hint")}
    candidates = [node_id for node_id in sinks if node_id in hinted] or sinks
    chosen = max(candidates, key=lambda node_id: (levels.get(node_id, -1), order[node_id]))
    next(node for node in agents if node["id"] == chosen)["final"] = True
    return result


def input_sources(graph: dict, node: dict) -> tuple[list[int], list[int]]:
    """블록이 직접 읽는 (업로드 파일 id, 공유 디렉터리 id). 파일 슬롯과 디렉터리 간선을 포함한다."""
    file_ids = [v for v in node.get("uploaded_file_ids") or [] if isinstance(v, int)]
    directory_ids = [v for v in node.get("directory_ids") or [] if isinstance(v, int)]
    slots = {slot.get("id"): slot for slot in graph.get("input_slots") or []}
    for slot_id in node.get("input_slot_ids") or []:
        slot = slots.get(slot_id) or {}
        file_ids += [v for v in slot.get("file_ids") or [] if isinstance(v, int)]
        directory_ids += [v for v in slot.get("directory_ids") or [] if isinstance(v, int)]
    directory_ids += directory_ids_by_agent(graph).get(node["id"], [])
    return list(dict.fromkeys(file_ids)), list(dict.fromkeys(directory_ids))


def apply_run_inputs(
    graph: dict,
    slots: dict[str, list[int]] | None = None,
    nodes: dict[str, list[int]] | None = None,
) -> dict:
    """이번 실행에만 쓰는 입력 파일을 반영한 그래프 복사본. 저장된 워크플로우는 바뀌지 않는다.

    slots는 슬롯별, nodes는 슬롯 없이 블록에 직접 붙은 파일(이전 버전 워크플로우)을 덮어쓴다.
    """
    applied = copy.deepcopy(graph)
    slot_map = {slot.get("id"): slot for slot in applied.get("input_slots") or []}
    agent_map = {node["id"]: node for node in _agent_nodes(applied)}
    for slot_id, file_ids in (slots or {}).items():
        if slot_id not in slot_map:
            raise DagError(f"존재하지 않는 파일 슬롯입니다: {slot_id}")
        slot_map[slot_id]["file_ids"] = list(dict.fromkeys(file_ids))
    for node_id, file_ids in (nodes or {}).items():
        if node_id not in agent_map:
            raise DagError(f"존재하지 않는 블록입니다: {node_id}")
        agent_map[node_id]["uploaded_file_ids"] = list(dict.fromkeys(file_ids))
    return applied


def expand_input_slots(graph: dict) -> dict:
    """슬롯에 연결된 파일·디렉터리를 각 블록의 uploaded_file_ids/directory_ids로 펼친 복사본.

    Worker·클라우드 실행·외부 전송 동의 로직은 블록 필드만 읽으므로 실행 스냅샷에 이 결과를 쓴다.
    """
    expanded = copy.deepcopy(graph)
    slots = {slot.get("id"): slot for slot in expanded.get("input_slots") or []}
    for node in _agent_nodes(expanded):
        for slot_id in node.get("input_slot_ids") or []:
            slot = slots.get(slot_id) or {}
            node["uploaded_file_ids"] = list(dict.fromkeys([*(node.get("uploaded_file_ids") or []), *(slot.get("file_ids") or [])]))
            node["directory_ids"] = list(dict.fromkeys([*(node.get("directory_ids") or []), *(slot.get("directory_ids") or [])]))
    return expanded


def _ancestors(graph: dict, node_id: str) -> set[str]:
    parents: dict[str, list[str]] = defaultdict(list)
    for source, target in _workflow_pairs(graph):
        parents[target].append(source)
    seen = {node_id}
    queue = deque([node_id])
    while queue:
        for parent in parents[queue.popleft()]:
            if parent not in seen:
                seen.add(parent)
                queue.append(parent)
    return seen


def inspect_graph(graph: dict, *, run_prompt: str = "", has_model=None) -> dict:
    """저장·실행 전 구성 검사. 오류는 실행을 막고, 경고는 사용자 확인 후 진행할 수 있다.

    has_model(node)는 지정 워커에 모델이 설치되어 있으면 True, 아니면 False,
    판단할 수 없으면(클라우드 블록, 워커 미지정 등) None을 반환한다.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    def add(severity: str, code: str, message: str, node_ids=(), **extra) -> None:
        issue = {"code": code, "severity": severity, "message": message, "node_ids": list(node_ids), **extra}
        (errors if severity == "error" else warnings).append(issue)

    order: list[str] = []
    try:
        order = validate_graph(graph)
    except DagError as exc:
        cyclic = cycle_node_ids(graph)
        add("error", "cycle" if cyclic else "invalid_graph", str(exc), cyclic)
        if not cyclic:
            # 잘못된 연결·중복 id 등은 블록 단위 검사를 신뢰할 수 없으므로 여기서 멈춘다
            return {"valid": False, "order": [], "errors": errors, "warnings": warnings, "stages": [], "final_node_ids": []}

    agents = _agent_nodes(graph)
    names = {node["id"]: node.get("name") or node["id"] for node in agents}
    parents = parents_of(graph)
    for node in agents:
        node_id = node["id"]
        file_ids, directory_ids = input_sources(graph, node)
        # 텍스트 입력은 사용자가 명시적으로 활성화한 것 자체를 입력으로 본다.
        # 따라서 내용이 빈 문자열이어도 시작 블록을 실행할 수 있다.
        has_input = bool(file_ids or directory_ids or node.get("text_input_enabled"))
        if node.get("needs_file") and not has_input:
            add("error", "missing_file", f"'{names[node_id]}' 블록에 필요한 파일이 비어 있습니다.", [node_id])
        elif not has_input and not parents.get(node_id) and not run_prompt.strip():
            add(
                "error",
                "no_input",
                f"'{names[node_id]}' 블록에 입력이 없습니다. 파일·공유 디렉터리를 연결하거나 "
                "실행할 때 실행 프롬프트를 입력하세요.",
                [node_id],
                resolvable_by_run_prompt=True,
            )

    finals = final_node_ids(graph)
    if not finals:
        sinks = terminal_nodes(graph)
        add(
            "error",
            "final_missing",
            f"끝나는 블록이 {len(sinks)}개라 최종 블록을 정할 수 없습니다. 결과를 낼 블록 하나를 최종 블록으로 지정하세요."
            if len(sinks) > 1 else "최종 블록이 없습니다. 결과를 낼 블록 하나를 최종 블록으로 지정하세요.",
            sinks,
        )
    elif len(finals) > 1:
        add("error", "final_multiple", f"최종 블록이 {len(finals)}개입니다. 하나만 지정하세요.", finals)
    else:
        reachable = _ancestors(graph, finals[0])
        for node in agents:
            if node["id"] not in reachable:
                add(
                    "warning",
                    "unreachable",
                    f"'{names[node['id']]}' 블록의 결과는 최종 블록에 전달되지 않습니다.",
                    [node["id"]],
                )

    if has_model is not None:
        for node in agents:
            if node.get("model") and has_model(node) is False:
                add(
                    "warning",
                    "model_not_installed",
                    f"'{names[node['id']]}' 블록의 모델 {node['model']}이(가) 지정한 워커에 설치되어 있지 않습니다.",
                    [node["id"]],
                )

    return {
        "valid": not errors,
        "order": order,
        "errors": errors,
        "warnings": warnings,
        "stages": stages(graph),
        "final_node_ids": finals,
    }
