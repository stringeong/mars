import pytest
from fastapi import HTTPException

from app import models, schemas
from app.routers import devices, services
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
    directory = make_directory(user, source, local_path="/srv/private")
    db.add(models.DirectoryMount(
        directory_id=directory.id,
        device_id=worker.id,
        local_path="D:/team/private",
    ))
    db.flush()
    execution = make_execution(user, graph_with_directory(directory))

    orchestrator.create_tasks_for_execution(db, execution)
    task = execution.tasks[0]
    assert task.allowed_folders == [{"directory_id": directory.id}]

    claimed = orchestrator.claim_next_task(db, worker)
    assert claimed is not None
    db.expire_all()
    assert claimed.assigned_device_id == worker.id
    assert directory_access.local_paths_for_device(
        db, worker.id, [directory.id]
    ) == ["D:/team/private"]


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


def test_directory_update_rejects_another_users_device(
    db, make_user, make_device, make_directory
):
    owner = make_user(email="owner@example.com", username="owner")
    other = make_user(email="other@example.com", username="other")
    directory = make_directory(owner, make_device(owner))
    other_device = make_device(other)

    with pytest.raises(HTTPException) as exc:
        devices.update_directory(
            other_device.id,
            directory.id,
            schemas.SharedDirectoryUpdate(local_path="/foreign/path"),
            db,
            owner,
        )

    assert exc.value.status_code == 404
    assert not db.query(models.DirectoryMount).all()


def test_deleting_secondary_mount_keeps_logical_directory_active(
    db, make_user, make_device, make_directory
):
    user = make_user()
    source = make_device(user, name="source")
    secondary = make_device(user, name="secondary")
    directory = make_directory(user, source, local_path="/source/docs")
    mount = models.DirectoryMount(
        directory_id=directory.id,
        device_id=secondary.id,
        local_path="/secondary/docs",
    )
    db.add(mount)
    db.flush()

    devices.delete_directory(secondary.id, directory.id, db, user)

    assert directory.is_active
    assert directory.device_id == source.id
    assert db.get(models.DirectoryMount, mount.id) is None


def test_deleting_source_promotes_an_existing_mount(
    db, make_user, make_device, make_directory
):
    from app.routers import devices

    user = make_user()
    source = make_device(user, name="source")
    secondary = make_device(user, name="secondary")
    directory = make_directory(user, source, local_path="/source/docs")
    mount = models.DirectoryMount(
        directory_id=directory.id,
        device_id=secondary.id,
        local_path="/secondary/docs",
    )
    db.add(mount)
    db.flush()

    devices.delete_directory(source.id, directory.id, db, user)

    assert directory.is_active
    assert directory.device_id == secondary.id
    assert directory.local_path == "/secondary/docs"
    assert db.get(models.DirectoryMount, mount.id) is None


def test_service_with_execution_history_cannot_be_deleted(
    db, make_user, make_execution
):
    user = make_user()
    execution = make_execution(user, {"nodes": [], "edges": []})

    with pytest.raises(HTTPException) as exc:
        services.delete_service(execution.service_id, user, db)

    assert exc.value.status_code == 409
    assert db.get(models.Service, execution.service_id) is not None
