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
        {"source": "dir_1", "target": "a", "relation": "directory"}
    )
    return graph


def test_resolves_owned_active_directory(db, make_user, make_device, make_directory):
    user = make_user()
    directory = make_directory(user, make_device(user))

    result = directory_access.resolve_directories_by_agent(
        db, user.id, graph_with_directory(directory)
    )

    assert result["a"] == [directory]


def test_rejects_other_users_directory(db, make_user, make_device, make_directory):
    owner = make_user(email="owner@example.com", username="owner")
    intruder = make_user(email="intruder@example.com", username="intruder")
    directory = make_directory(owner, make_device(owner))

    with pytest.raises(directory_access.DirectoryAccessError):
        directory_access.resolve_directories_by_agent(
            db, intruder.id, graph_with_directory(directory)
        )


def test_directory_node_device_is_metadata_only(
    db, make_user, make_device, make_directory
):
    user = make_user()
    source = make_device(user, name="source")
    worker = make_device(user, name="worker")
    directory = make_directory(user, source)

    result = directory_access.resolve_directories_by_agent(
        db, user.id, graph_with_directory(directory, device_id=worker.id)
    )

    assert result["a"] == [directory]


def test_shared_directory_task_can_be_claimed_by_any_user_device(
    db, make_user, make_device, make_directory, make_execution
):
    user = make_user()
    source = make_device(user, name="source")
    worker = make_device(user, name="worker")
    directory = make_directory(user, source, local_path="/shared/private")
    execution = make_execution(user, graph_with_directory(directory))

    orchestrator.create_tasks_for_execution(db, execution)
    task = execution.tasks[0]
    assert task.allowed_folders == ["/shared/private"]

    claimed = orchestrator.claim_next_task(db, worker)
    assert claimed is not None
    db.expire_all()
    assert claimed.assigned_device_id == worker.id


def test_nested_resources_resolve_and_pin_the_selected_worker(
    db, make_user, make_device, make_directory, make_execution
):
    user = make_user()
    selected_worker = make_device(user, name="selected")
    other_worker = make_device(user, name="other")
    directory = make_directory(user, selected_worker, local_path="/shared/docs")
    graph = graph_of(["a"], [])
    graph["nodes"][0].update(
        worker_id=selected_worker.id,
        directory_ids=[directory.id],
    )
    execution = make_execution(user, graph)

    resolved = directory_access.resolve_directories_by_agent(db, user.id, graph)
    assert resolved["a"] == [directory]

    orchestrator.create_tasks_for_execution(db, execution)
    assert orchestrator.claim_next_task(db, other_worker) is None
    assert orchestrator.claim_next_task(db, selected_worker) is not None
