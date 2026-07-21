import pytest

from app.services import directory_access, orchestrator
from tests.conftest import graph_of


def graph_with_directory(directory, *, device_id=None):
    graph = graph_of(["a"], [])
    graph["nodes"].append(
        {
            "id": "dir_1",
            "type": "directory",
            "directory_id": directory.id,
            "name": directory.alias,
            "device_id": device_id if device_id is not None else directory.device_id,
        }
    )
    graph["edges"].append(
        {"source": "a", "target": "dir_1", "relation": "directory"}
    )
    return graph


def test_resolves_owned_active_directory(db, make_user, make_device, make_directory):
    user = make_user()
    device = make_device(user)
    directory = make_directory(user, device)
    result = directory_access.resolve_directories_by_agent(
        db, user.id, graph_with_directory(directory)
    )
    assert result["a"] == [directory]


def test_rejects_other_users_directory(db, make_user, make_device, make_directory):
    owner = make_user(email="owner@example.com", username="owner")
    intruder = make_user(email="intruder@example.com", username="intruder")
    device = make_device(owner)
    directory = make_directory(owner, device)
    with pytest.raises(directory_access.DirectoryAccessError):
        directory_access.resolve_directories_by_agent(
            db, intruder.id, graph_with_directory(directory)
        )


def test_rejects_spoofed_device_id(db, make_user, make_device, make_directory):
    user = make_user()
    device = make_device(user)
    other = make_device(user, name="다른 기기")
    directory = make_directory(user, device)
    with pytest.raises(directory_access.DirectoryAccessError):
        directory_access.resolve_directories_by_agent(
            db, user.id, graph_with_directory(directory, device_id=other.id)
        )


def test_task_paths_are_converted_and_device_is_restricted(
    db, make_user, make_device, make_directory, make_execution
):
    user = make_user()
    target = make_device(user, name="대상", last_heartbeat=None)
    other = make_device(user, name="다른 기기", last_heartbeat=None)
    directory = make_directory(user, target, local_path="/srv/private")
    execution = make_execution(user, graph_with_directory(directory))

    orchestrator.create_tasks_for_execution(db, execution)
    task = execution.tasks[0]
    assert task.allowed_folders == ["/srv/private"]
    assert orchestrator.claim_next_task(db, other) is None
    claimed = orchestrator.claim_next_task(db, target)
    assert claimed is not None
    db.expire_all()
    assert claimed.assigned_device_id == target.id
