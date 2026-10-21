from datetime import datetime, timezone
from typing import Annotated, Literal

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


class ResourceLimits(BaseModel):
    """Worker를 새 작업에 배정할 때 사용할 현재 사용률 상한."""

    max_cpu_percent: int | None = Field(default=None, ge=1, le=100)
    max_gpu_percent: int | None = Field(default=None, ge=1, le=100)


class DeviceRegister(BaseModel):
    """Worker CLI가 사용자 인증 후 호출하는 기기 등록 요청."""

    name: str = Field(min_length=1, max_length=128)
    specs: dict = Field(default_factory=dict)


class DeviceOut(BaseModel):
    id: int
    name: str
    specs: dict
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    last_heartbeat: UTCDateTime | None
    online: bool = False

    model_config = {"from_attributes": True}


class DeviceRegisterOut(DeviceOut):
    api_key: str  # 등록 응답에서만 노출


class DeviceUpdate(BaseModel):
    name: str | None = None
    resource_limits: ResourceLimits | None = None


class DeviceModelsOut(BaseModel):
    device_id: int
    device_name: str
    online: bool
    models: list[str] = Field(default_factory=list)
    default_model: str | None = None
    synced_at: UTCDateTime | None = None


#----------- SharedDirectory ----------

class SharedDirectoryCreate(BaseModel):
    alias: str
    local_path: str
    permission: Literal["read"] = "read"


class SharedDirectoryUpdate(BaseModel):
    alias: str | None = None
    local_path: str | None = None
    is_active: bool | None = None


class SharedDirectoryResponse(BaseModel):
    id: int
    user_id: int
    device_id: int
    alias: str
    local_path: str
    permission: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class DirectoryInspectionOut(BaseModel):
    id: int
    directory_id: int
    device_id: int
    status: str
    files: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class UploadedFileOut(BaseModel):
    id: int
    original_name: str
    content_type: str | None = None
    size_bytes: int
    created_at: UTCDateTime

    model_config = {"from_attributes": True}

# ---------- Service / Workflow ----------


class AgentNode(BaseModel):
    id: str
    type: Literal["agent"] = "agent"
    name: str
    role_prompt: str = ""
    model: str = ""
    executor: Literal["local", "cloud"] = "local"
    provider: Literal["ollama", "openai", "anthropic", "gemini"] = "ollama"
    worker_id: int | None = None
    directory_ids: list[int] = Field(default_factory=list)
    uploaded_file_ids: list[int] = Field(default_factory=list)
    # 실행 결과를 내는 블록. 워크플로우에 하나만 둔다.
    final: bool = False
    # 사용자 파일을 직접 읽어야 하는 블록과, 그 파일이 들어갈 슬롯
    needs_file: bool = False
    input_slot_ids: list[str] = Field(default_factory=list)
    # 파일 대신 블록에 직접 전달할 텍스트. 활성화되어 있으면 빈 문자열도 유효한 입력이다.
    text_input_enabled: bool = False
    text_input: str = ""
    # 생성기가 제안한 값과 사용자가 직접 지정했는지. 자동 규칙(dag.apply_auto_flags)은
    # 직접 지정한 값을 덮어쓰지 않는다.
    final_hint: bool = False
    needs_file_hint: bool = False
    final_manual: bool = False
    needs_file_manual: bool = False
    position: dict | None = None


class DirectoryNode(BaseModel):
    id: str
    type: Literal["directory"] = "directory"
    directory_id: int
    name: str
    device_id: int
    position: dict | None = None

    
WorkflowNode = Annotated[
    AgentNode | DirectoryNode,
    Field(discriminator="type"),
]


class Edge(BaseModel):
    source: str
    target: str
    relation: Literal["workflow", "directory"] = "workflow"
    access: Literal["read", "read_write"] | None = None



class InputSlot(BaseModel):
    """사용자가 올릴 파일 하나. 여러 블록이 같은 슬롯을 함께 읽을 수 있다."""

    id: str
    description: str = ""
    format: str = ""
    file_ids: list[int] = Field(default_factory=list)
    directory_ids: list[int] = Field(default_factory=list)


class Graph(BaseModel):
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    input_slots: list[InputSlot] = Field(default_factory=list)
    # 기본 워크플로우의 생성 프롬프트. 시작 블록 컨텍스트로 전달된다.
    goal: str = ""


class ServiceGenerate(BaseModel):
    prompt: str = Field(min_length=5, description="만들고자 하는 서비스를 설명하는 자연어")
    # 워크플로우를 생성할 LLM. 기본값은 서버 로컬 LLM(Ollama)의 기본 모델.
    location: Literal["local", "cloud"] = "local"
    provider: Literal["ollama", "openai", "anthropic", "gemini"] = "ollama"
    model: str = Field(default="", max_length=128)
    # 외부 LLM으로 생성 프롬프트가 전송된다는 안내를 사용자가 확인했는지
    external_transfer_ack: bool = False
    # 생성 실패 후 사용자가 규칙 기반 기본 워크플로우를 고른 경우
    use_fallback: bool = False
    fallback_reason: str = Field(default="", max_length=500)


class ServiceRevise(BaseModel):
    instruction: str = Field(min_length=2, description="워크플로우를 어떻게 고칠지 설명하는 자연어")


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: Graph | None = None


class ServiceValidate(BaseModel):
    """저장 전 편집 중인 그래프를 검사할 때 사용한다. graph가 없으면 저장된 그래프를 검사한다."""

    graph: Graph | None = None
    run_prompt: str = ""


class ServiceOut(BaseModel):
    id: int
    name: str
    description: str
    graph: dict
    created_at: UTCDateTime
    updated_at: UTCDateTime
    generation_info: dict | None = None
    validation: dict | None = None

    model_config = {"from_attributes": True}


# ---------- Execution ----------


class RunInputs(BaseModel):
    """이번 실행에만 쓰는 입력 파일. 저장된 워크플로우의 기본값을 덮어쓴다."""

    slots: dict[str, list[int]] = Field(default_factory=dict)
    # 슬롯 없이 블록에 직접 파일을 붙인 이전 버전 워크플로우용
    nodes: dict[str, list[int]] = Field(default_factory=dict)


class ExecutionCreate(BaseModel):
    run_prompt: str = Field(default="", description="이번 실행에 대한 추가 지시(선택)")
    input_files: RunInputs = Field(default_factory=RunInputs)
    consent_token: str | None = None
    # 구성 검사 경고를 사용자가 확인했는지
    acknowledge_warnings: bool = False


class ExecutionPreview(BaseModel):
    run_prompt: str = ""
    input_files: RunInputs = Field(default_factory=RunInputs)


class ProviderCredentialUpdate(BaseModel):
    api_key: str | None = Field(default=None, min_length=8)
    admin_key: str | None = Field(default=None, min_length=8)
    default_model: str = Field(default="", max_length=128)
    monthly_budget_usd: int | None = Field(default=None, ge=1, le=1_000_000)


class ProviderCredentialOut(BaseModel):
    provider: Literal["openai", "anthropic", "gemini"]
    configured: bool
    masked_key: str = ""
    has_admin_key: bool = False
    default_model: str = ""
    monthly_budget_usd: int | None = None
    status: str = "unverified"
    last_verified_at: UTCDateTime | None = None


class UsageSummaryOut(BaseModel):
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    requests: int = 0



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
    # 실행 타임라인용: DAG 깊이(0부터), 배정 워커 이름, 실행 위치
    depth: int | None = None
    assigned_device_name: str | None = None
    executor: str = "local"
    provider: str | None = None

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
    generation_info: dict | None = None
    input_files: list[dict] | None = None
    progress: float = 0.0
    tasks: list[TaskOut] = Field(default_factory=list)
    # 실행 스냅샷의 DAG 단계(같은 단계는 동시에 실행 가능)와 블록 간 연결
    stages: list[list[str]] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    final_node_ids: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ExecutionListItem(BaseModel):
    id: int
    service_id: int
    service_name: str = ""
    run_prompt: str
    status: str
    created_at: UTCDateTime
    finished_at: UTCDateTime | None
    generation_info: dict | None = None
    input_files: list[dict] | None = None

    model_config = {"from_attributes": True}


# ---------- Worker protocol ----------


class WorkerTaskOut(BaseModel):
    """Worker가 가져가는 작업 페이로드."""

    task_id: int
    execution_id: int
    agent_name: str
    role_prompt: str
    model: str
    directory_paths: list[str] = Field(default_factory=list)
    uploaded_files: list[dict] = Field(default_factory=list)
    input_context: str
    run_prompt: str


class WorkerTaskResult(BaseModel):
    status: str = Field(pattern="^(done|failed)$")
    output: str = ""
    error: str = ""
