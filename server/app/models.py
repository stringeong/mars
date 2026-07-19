import secrets
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
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


class EventLog(Base):
    """주요 이벤트 기록 (NF-205 비정상 접근 기록, NF-207 이벤트 로그).

    로그인 성공/실패, 기기 등록/삭제, 서비스 생성, 실행 시작/완료/실패/중단 등을
    남긴다. 존재하지 않는 아이디로의 로그인 시도는 user_id 없이 기록된다.
    """

    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
