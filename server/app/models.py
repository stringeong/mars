import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,

)


from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    devices: Mapped[list["Device"]] = relationship(back_populates="owner")
    services: Mapped[list["Service"]] = relationship(back_populates="owner")

    shared_directories: Mapped[list["SharedDirectory"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Device(Base):
    """사용자가 등록한 Worker Node."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    # Worker가 자동 수집한 사양 (os, cpu, ram_gb, hostname ...)
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    # 이 기기에서 에이전트가 접근을 허용받은 폴더 목록 (절대경로)
    allowed_folders: Mapped[list] = mapped_column(JSON, default=list)
    # Worker Agent 인증용 키
    api_key: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_hex(24), unique=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship(back_populates="devices")
    
    shared_directories: Mapped[list["SharedDirectory"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
    )
    

class SharedDirectory(Base):

    __tablename__ = "shared_directories"

    __table_args__ = (
    UniqueConstraint(
        "user_id",
        "alias",
        name="uq_shared_directory_user_alias",
    ),
    UniqueConstraint(
        "device_id",
        "local_path",
        name="uq_shared_directory_device_path",
    ),
)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id"),
        index=True,
    )

    # 화면과 워크플로우에서 사용하는 이름
    alias: Mapped[str] = mapped_column(String(128))

    # 해당 기기 내부의 실제 절대경로
    local_path: Mapped[str] = mapped_column(Text)

    # 향후 폴더별 읽기/쓰기 제어
    permission: Mapped[str] = mapped_column(
        String(16),
        default="read",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )

    owner: Mapped["User"] = relationship(
        back_populates="shared_directories",
    )

    device: Mapped["Device"] = relationship(
        back_populates="shared_directories",
    )
    


class Service(Base):
    """사용자가 생성한 MAS 구성(워크플로우). graph 는 DAG JSON."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    # {"nodes": [{"id","name","role_prompt","model","allowed_folders",...}],
    #  "edges": [{"source","target"}]}
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="services")
    executions: Mapped[list["Execution"]] = relationship(back_populates="service")


class Execution(Base):
    """서비스 1회 실행."""

    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    run_prompt: Mapped[str] = mapped_column(Text, default="")
    # pending -> running -> completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # 실행 시점의 그래프 스냅샷 (이후 서비스가 수정돼도 이력은 보존)
    graph_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    service: Mapped[Service] = relationship(back_populates="executions")
    tasks: Mapped[list["TaskRecord"]] = relationship(back_populates="execution")


class TaskRecord(Base):
    """실행 내 개별 에이전트 작업 (DAG 노드 1개)."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(64))
    agent_name: Mapped[str] = mapped_column(String(128))
    role_prompt: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    allowed_folders: Mapped[list] = mapped_column(JSON, default=list)
    # blocked(선행 대기) -> ready(할당 대기) -> running -> done | failed
    status: Mapped[str] = mapped_column(String(16), default="blocked", index=True)
    assigned_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    # 선행 작업 출력이 합쳐진 입력 컨텍스트
    input_context: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    execution: Mapped[Execution] = relationship(back_populates="tasks")
