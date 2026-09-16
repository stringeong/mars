"""Device registration and reconnection behavior."""

from fastapi import FastAPI, Response, status
from fastapi.testclient import TestClient

from app import schemas
from app.database import get_db
from app.security import get_current_user
from app.routers import devices


def test_register_device_creates_new_worker(db, make_user):
    user = make_user()

    result = devices.register_device(
        schemas.DeviceRegister(name="worker-a", specs={"cpu_count": 8}),
        Response(),
        user,
        db,
    )

    assert result["name"] == "worker-a"
    assert result["specs"] == {"cpu_count": 8}
    assert result["api_key"]


def test_reregister_reconnects_existing_worker(db, make_user, make_device):
    user = make_user()
    worker = make_device(user, name="worker-a")
    worker.specs = {
        "cpu_count": 4,
        "resource_limits": {"max_cpu_percent": 80},
    }
    old_id = worker.id
    old_key = worker.api_key
    db.commit()
    response = Response()

    result = devices.register_device(
        schemas.DeviceRegister(
            name="worker-a",
            specs={"cpu_count": 8, "gpu_mode": "nvidia"},
        ),
        response,
        user,
        db,
    )

    assert response.status_code == status.HTTP_200_OK
    assert result["id"] == old_id
    assert result["api_key"] != old_key
    assert result["specs"] == {
        "cpu_count": 8,
        "gpu_mode": "nvidia",
        "resource_limits": {"max_cpu_percent": 80},
    }
    assert db.query(type(worker)).filter_by(user_id=user.id).count() == 1


def test_same_worker_name_is_scoped_to_user(db, make_user):
    first_user = make_user(email="first@example.com", username="first")
    second_user = make_user(email="second@example.com", username="second")
    db.commit()

    first = devices.register_device(
        schemas.DeviceRegister(name="shared-name", specs={}),
        Response(),
        first_user,
        db,
    )
    second = devices.register_device(
        schemas.DeviceRegister(name="shared-name", specs={}),
        Response(),
        second_user,
        db,
    )

    assert first["id"] != second["id"]


def test_reregister_endpoint_returns_200_and_same_device(db, make_user):
    user = make_user()
    db.commit()
    app = FastAPI()
    app.include_router(devices.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as client:
        created = client.post(
            "/devices", json={"name": "worker-http", "specs": {"cpu_count": 4}}
        )
        reconnected = client.post(
            "/devices", json={"name": "worker-http", "specs": {"cpu_count": 8}}
        )

    assert created.status_code == status.HTTP_201_CREATED
    assert reconnected.status_code == status.HTTP_200_OK
    assert reconnected.json()["id"] == created.json()["id"]
    assert reconnected.json()["api_key"] != created.json()["api_key"]


def test_list_device_models_normalizes_worker_report(db, make_user, make_device):
    user = make_user()
    worker = make_device(user, name="model-worker")
    worker.specs = {
        "models": ["qwen3:4b", "", "qwen3:4b", "gemma3:4b", 123],
        "default_model": "qwen3:4b",
    }
    db.commit()

    result = devices.list_device_models(worker.id, user, db)

    assert result["device_id"] == worker.id
    assert result["models"] == ["gemma3:4b", "qwen3:4b"]
    assert result["default_model"] == "qwen3:4b"
    assert result["synced_at"] == worker.last_heartbeat


def test_list_device_models_rejects_other_user(db, make_user, make_device):
    owner = make_user(email="model-owner@example.com", username="model-owner")
    intruder = make_user(email="model-other@example.com", username="model-other")
    worker = make_device(owner)
    db.commit()

    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as exc:
        devices.list_device_models(worker.id, intruder, db)
    assert exc.value.status_code == 404
