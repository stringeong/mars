
from collections import defaultdict

from sqlalchemy.orm import Session

from .. import models
from . import dag

# 사용자의 개인 디렉토리 접근 검사
"""사용자가 보유한 디렉토리만 에이전트에 연결하도록 검증하는 모듈"""

class DirectoryAccessError(ValueError):
    pass


def resolve_directories_by_agent(
    db: Session,
    user_id: int,
    graph: dict,
) -> dict[str, list[models.SharedDirectory]]:
 
    directory_nodes = {
        node["id"]: node
        for node in graph.get("nodes", [])
        if node.get("type") == "directory"
    }

    agent_ids = {
        node["id"]
        for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent"
    }
    result: dict[str, list[models.SharedDirectory]] = {
        agent_id: [] for agent_id in agent_ids
    }

    referenced_ids = {
        node.get("directory_id")
        for node in directory_nodes.values()
        if node.get("directory_id") is not None
    }
    rows = (
        db.query(models.SharedDirectory)
        .filter(models.SharedDirectory.id.in_(referenced_ids))
        .all()
        if referenced_ids
        else []
    )
    by_id = {row.id: row for row in rows}

    for node_id, node in directory_nodes.items():
        directory_id = node.get("directory_id")
        directory = by_id.get(directory_id)
        if directory is None:
            raise DirectoryAccessError(
                f"디렉토리 노드 '{node_id}'가 존재하지 않는 디렉토리를 참조"
            )
        if directory.user_id != user_id:
            raise DirectoryAccessError(
                f"디렉토리 노드 '{node_id}'에 접근할 권한이 없습니다."
            )
        if not directory.is_active:
            raise DirectoryAccessError(
                f"디렉토리 '{directory.alias}'는 비활성화되어 있습니다."
            )
        if node.get("device_id") != directory.device_id:
            raise DirectoryAccessError(
                f"디렉토리 노드 '{node_id}'의 기기 정보가 실제 등록 정보와 다릅니다."
            )

    directory_ids = dag.directory_ids_by_agent(graph)
    for agent_id, ids in directory_ids.items():
        directories = [by_id[directory_id] for directory_id in ids]
        device_ids = {directory.device_id for directory in directories}
        if len(device_ids) > 1:
            raise DirectoryAccessError(
                f"에이전트 '{agent_id}'에는 서로 다른 기기의 디렉토리를 함께 연결할 수 없습니다."
            )
        result[agent_id] = directories

    return result


def required_device_by_agent(graph: dict) -> dict[str, int | None]:
    """검증된 그래프 스냅샷에서 에이전트별 필수 실행 기기를 계산한다."""

    directory_nodes = {
        node["id"]: node
        for node in graph.get("nodes", [])
        if node.get("type") == "directory"
    }
    required: dict[str, int | None] = {
        node["id"]: None
        for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent"
    }
    devices: dict[str, set[int]] = defaultdict(set)

    for edge in graph.get("edges", []):
        if edge.get("relation") != "directory":
            continue
        node = directory_nodes.get(edge.get("target"))
        if node is not None:
            devices[edge["source"]].add(node["device_id"])

    for agent_id, device_ids in devices.items():
        if len(device_ids) == 1:
            required[agent_id] = next(iter(device_ids))

    return required
