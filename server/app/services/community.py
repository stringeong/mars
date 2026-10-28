"""커뮤니티 공유용 워크플로우 사본 만들기.

공유한 구성은 로그인하지 않은 사람도 본다. 내 기기·폴더·파일을 가리키는 값과
블록에 직접 적어 둔 텍스트 입력은 지우고, 에이전트 구성과 연결만 남긴다.
"""

import copy


def public_graph(graph: dict) -> dict:
    nodes = []
    for node in graph.get("nodes", []):
        if node.get("type", "agent") != "agent":
            continue
        node = copy.deepcopy(node)
        node.update(worker_id=None, directory_ids=[], uploaded_file_ids=[], text_input="")
        nodes.append(node)
    agent_ids = {node["id"] for node in nodes}
    edges = [
        copy.deepcopy(edge)
        for edge in graph.get("edges", [])
        if (edge.get("relation") or "workflow") == "workflow" and edge.get("source") in agent_ids and edge.get("target") in agent_ids
    ]
    slots = [{**copy.deepcopy(slot), "file_ids": [], "directory_ids": []} for slot in graph.get("input_slots", [])]
    return {"nodes": nodes, "edges": edges, "input_slots": slots, "goal": graph.get("goal", "")}


def to_out(entry) -> dict:
    return {
        "id": entry.id,
        "service_id": entry.service_id,
        "title": entry.title,
        "description": entry.description,
        "author": entry.author.username,
        "graph": entry.graph,
        "import_count": entry.import_count,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }
