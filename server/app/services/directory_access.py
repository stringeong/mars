"""Resolve the resources nested inside agent blocks."""

from collections import defaultdict

from sqlalchemy.orm import Session

from .. import models
from . import dag


class DirectoryAccessError(ValueError):
    pass


def _agent_nodes(graph: dict) -> list[dict]:
    return [
        node for node in graph.get("nodes", [])
        if node.get("type", "agent") == "agent"
    ]


def _directory_ids_by_agent(graph: dict) -> dict[str, list[int]]:
    """Read the current nested shape and legacy directory edges."""
    result = {node["id"]: list(node.get("directory_ids") or []) for node in _agent_nodes(graph)}
    legacy = dag.directory_ids_by_agent(graph)
    for agent_id, directory_ids in legacy.items():
        for directory_id in directory_ids:
            if directory_id not in result[agent_id]:
                result[agent_id].append(directory_id)
    return result


def resolve_directories_by_agent(
    db: Session, user_id: int, graph: dict
) -> dict[str, list[models.SharedDirectory]]:
    """Return active directories selected inside each agent block."""
    directory_ids_by_agent = _directory_ids_by_agent(graph)
    referenced_ids = {
        directory_id
        for ids in directory_ids_by_agent.values()
        for directory_id in ids
    }
    rows = (
        db.query(models.SharedDirectory)
        .filter(models.SharedDirectory.id.in_(referenced_ids))
        .all()
        if referenced_ids
        else []
    )
    by_id = {row.id: row for row in rows}

    for directory_id in referenced_ids:
        directory = by_id.get(directory_id)
        if directory is None:
            raise DirectoryAccessError(f"Directory {directory_id} does not exist.")
        if directory.user_id != user_id:
            raise DirectoryAccessError(f"No access to directory {directory.alias}.")
        if not directory.is_active:
            raise DirectoryAccessError(f"Directory {directory.alias} is inactive.")

    for agent in _agent_nodes(graph):
        worker_id = agent.get("worker_id")
        if worker_id is None:
            continue
        worker = db.get(models.Device, worker_id)
        if worker is None or worker.user_id != user_id:
            raise DirectoryAccessError(f"Worker {worker_id} is unavailable.")

    return {
        agent_id: [by_id[directory_id] for directory_id in directory_ids]
        for agent_id, directory_ids in directory_ids_by_agent.items()
    }


def required_device_by_agent(graph: dict) -> dict[str, int | None]:
    """A nested Worker selection pins that agent's task to the Worker."""
    return {
        node["id"]: node.get("worker_id")
        for node in _agent_nodes(graph)
    }
