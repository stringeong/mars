"""테스트 공용 fixture — 인메모리 SQLite 세션과 모델 팩토리."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def make_user(db):
    def _make(email="u@example.com", username="user1"):
        user = models.User(email=email, username=username, password_hash="x")
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture()
def make_device(db):
    def _make(user, name="기기", last_heartbeat=None, allowed_folders=None):
        device = models.Device(
            user_id=user.id,
            name=name,
            last_heartbeat=last_heartbeat,
            allowed_folders=allowed_folders or [],
        )
        db.add(device)
        db.flush()
        return device

    return _make


@pytest.fixture()
def make_execution(db):
    def _make(user, graph, run_prompt=""):
        service = models.Service(user_id=user.id, name="테스트 서비스", graph=graph)
        db.add(service)
        db.flush()
        execution = models.Execution(
            service_id=service.id,
            user_id=user.id,
            run_prompt=run_prompt,
            graph_snapshot=graph,
        )
        db.add(execution)
        db.flush()
        return execution

    return _make


def node(node_id, **extra):
    return {
        "id": node_id,
        "name": f"에이전트 {node_id}",
        "role_prompt": f"{node_id} 역할",
        "model": "",
        "allowed_folders": [],
        **extra,
    }


def graph_of(node_ids, edge_pairs):
    return {
        "nodes": [node(i) for i in node_ids],
        "edges": [{"source": s, "target": t} for s, t in edge_pairs],
    }


# a -> b -> c
LINEAR = graph_of(["a", "b", "c"], [("a", "b"), ("b", "c")])

# a -> b, a -> c, b -> d, c -> d
DIAMOND = graph_of(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
