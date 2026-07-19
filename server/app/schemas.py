from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, PlainSerializer

# DB에는 UTC를 tz 정보 없이 저장하므로, 응답 직렬화 시 UTC임을 명시해야
# 브라우저가 사용자 로컬 시간대로 올바르게 변환한다.
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(
        lambda v: v.replace(tzinfo=timezone.utc).isoformat(), return_type=str
    ),
]

# ---------- Auth ----------


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    username: str

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Device ----------


class DeviceRegister(BaseModel):
    """Worker CLI가 사용자 인증 후 호출하는 기기 등록 요청."""

    name: str = Field(min_length=1, max_length=128)
    specs: dict = Field(default_factory=dict)
    allowed_folders: list[str] = Field(default_factory=list)


class DeviceOut(BaseModel):
    id: int
    name: str
    specs: dict
    allowed_folders: list
    last_heartbeat: UTCDateTime | None
    online: bool = False

    model_config = {"from_attributes": True}


class DeviceRegisterOut(DeviceOut):
    api_key: str  # 등록 응답에서만 노출


class DeviceUpdate(BaseModel):
    name: str | None = None
    allowed_folders: list[str] | None = None


# ---------- Service / Workflow ----------


class AgentNode(BaseModel):
    id: str
    name: str
    role_prompt: str = ""
    model: str = ""
    allowed_folders: list[str] = Field(default_factory=list)
    # React Flow 배치용 좌표 (없으면 프론트에서 자동 배치)
    position: dict | None = None


class Edge(BaseModel):
    source: str
    target: str


class Graph(BaseModel):
    nodes: list[AgentNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class ServiceGenerate(BaseModel):
    prompt: str = Field(min_length=5, description="만들고자 하는 서비스를 설명하는 자연어")


class ServiceRevise(BaseModel):
    instruction: str = Field(min_length=2, description="워크플로우를 어떻게 고칠지 설명하는 자연어")


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: Graph | None = None


class ServiceOut(BaseModel):
    id: int
    name: str
    description: str
    graph: dict
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = {"from_attributes": True}


# ---------- Execution ----------


class ExecutionCreate(BaseModel):
    run_prompt: str = Field(min_length=1, description="이번 실행에 대한 지시")


class TaskOut(BaseModel):
    id: int
    node_id: str
    agent_name: str
    status: str
    assigned_device_id: int | None
    output: str | None
    error: str | None
    started_at: UTCDateTime | None
    finished_at: UTCDateTime | None

    model_config = {"from_attributes": True}


class ExecutionOut(BaseModel):
    id: int
    service_id: int
    run_prompt: str
    status: str
    result: str | None
    error: str | None
    created_at: UTCDateTime
    finished_at: UTCDateTime | None
    progress: float = 0.0
    tasks: list[TaskOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ExecutionListItem(BaseModel):
    id: int
    service_id: int
    service_name: str = ""
    run_prompt: str
    status: str
    created_at: UTCDateTime
    finished_at: UTCDateTime | None

    model_config = {"from_attributes": True}


# ---------- Worker protocol ----------


class WorkerTaskOut(BaseModel):
    """Worker가 가져가는 작업 페이로드."""

    task_id: int
    execution_id: int
    agent_name: str
    role_prompt: str
    model: str
    allowed_folders: list[str]
    input_context: str
    run_prompt: str


class WorkerTaskResult(BaseModel):
    status: str = Field(pattern="^(done|failed)$")
    output: str = ""
    error: str = ""


# ---------- 회원정보 수정 / 이벤트 로그 ----------


class UserUpdate(BaseModel):
    """회원정보 수정 — 본인 확인을 위해 현재 비밀번호가 항상 필요하다."""

    current_password: str = Field(min_length=1)
    email: EmailStr | None = None
    new_password: str | None = Field(default=None, min_length=6, max_length=128)


class EventOut(BaseModel):
    id: int
    event_type: str
    detail: str
    created_at: UTCDateTime

    model_config = {"from_attributes": True}
