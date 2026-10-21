export interface AgentNode {
  id: string
  type: 'agent'
  name: string
  role_prompt: string
  model: string
  executor?: 'local' | 'cloud'
  provider?: 'ollama' | 'openai' | 'anthropic' | 'gemini'
  worker_id?: number | null
  directory_ids?: number[]
  uploaded_file_ids?: number[]
  final?: boolean
  needs_file?: boolean
  input_slot_ids?: string[]
  // 생성기가 제안한 값과 사용자가 직접 지정했는지 (자동 규칙은 직접 지정한 값을 덮어쓰지 않는다)
  final_hint?: boolean
  needs_file_hint?: boolean
  final_manual?: boolean
  needs_file_manual?: boolean
  // 블록에 직접 넣는 텍스트 데이터(켜져 있을 때만 쓰임)와 시작 블록의 '입력 없이 실행 허용'
  text_input_enabled?: boolean
  text_input?: string
  allow_no_input?: boolean
  position?: { x: number; y: number } | null
}

export interface DirectoryNode {
  id: string
  type: 'directory'
  directory_id: number
  name: string
  device_id: number
  position?: { x: number; y: number } | null
}

export type WorkflowNode = AgentNode | DirectoryNode

export interface GraphEdge {
  source: string
  target: string
  relation: 'workflow' | 'directory'
}

export interface InputSlot {
  id: string
  description: string
  format: string
  file_ids: number[]
  directory_ids: number[]
}

export interface Graph {
  nodes: WorkflowNode[]
  edges: GraphEdge[]
  input_slots?: InputSlot[]
  goal?: string
}

export type CloudProvider = 'openai' | 'anthropic' | 'gemini'

export interface GenerationInfo {
  source: 'llm' | 'fallback'
  location: 'local' | 'cloud' | null
  provider: string | null
  model: string | null
  generated_at?: string
  fallback_reason?: string
}

export interface GenerationError {
  stage: 'connection' | 'parse' | 'validation'
  message: string
  location: 'local' | 'cloud'
  provider: string
  model: string
}

export interface GeneratorModels {
  local: { available: boolean; models: string[]; default_model: string; error: string | null }
  cloud: { provider: CloudProvider; configured: boolean; status: string; default_model: string; models: string[] }[]
}

export interface ValidationIssue {
  code: string
  severity: 'error' | 'warning'
  message: string
  node_ids: string[]
}

export interface ValidationResult {
  valid: boolean
  order: string[]
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
  stages: string[][]
  final_node_ids: string[]
  reason?: string | null
}

export interface Service {
  id: number
  name: string
  description: string
  graph: Graph
  created_at: string
  updated_at: string
  generation_info?: GenerationInfo | null
  validation?: ValidationResult | null
}

export interface DeviceModels {
  device_id: number
  device_name: string
  online: boolean
  models: string[]
  default_model: string | null
  synced_at: string | null
}

export interface Device {
  id: number
  name: string
  specs: Record<string, unknown>
  resource_limits: ResourceLimits
  last_heartbeat: string | null
  online: boolean
}

export interface ResourceLimits {
  max_cpu_percent?: number
  max_gpu_percent?: number
}


export interface SharedDirectory {
  id: number
  user_id: number
  device_id: number
  alias: string
  local_path: string
  permission: 'read'
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface DirectoryInspection {
  id: number
  directory_id: number
  device_id: number
  status: 'pending' | 'running' | 'done' | 'failed'
  files: string[]
  error: string | null
  created_at: string
  finished_at: string | null
}

export interface UploadedFile {
  id: number
  original_name: string
  content_type: string | null
  size_bytes: number
  created_at: string
}

export interface RunInputRecord {
  kind: 'slot' | 'node' | 'text'
  id: string
  label: string
  node_ids: string[]
  files: { id: number; name: string }[]
  directories: { id: number; alias: string }[]
  text?: string
}

/** 실행 전 확인 창의 블록별 직접 입력 (POST /executions/preview의 review) */
export interface InputReviewBlock {
  node_id: string
  name: string
  is_start: boolean
  executor: 'local' | 'cloud'
  provider: CloudProvider | null
  device_name: string | null
  files: { id: number; name: string; size_bytes: number | null }[]
  directories: { id: number; alias: string; device_name: string | null }[]
  text: string
  allow_no_input: boolean
}

export interface InputReview {
  blocks: InputReviewBlock[]
  totals: { files: number; bytes: number; directories: number; texts: number }
}

export interface Task {
  id: number
  node_id: string
  agent_name: string
  status: string
  assigned_device_id: number | null
  output: string | null
  error: string | null
  started_at: string | null
  finished_at: string | null
  depth?: number | null
  assigned_device_name?: string | null
  executor?: 'local' | 'cloud'
  provider?: string | null
}

export interface Execution {
  id: number
  service_id: number
  run_prompt: string
  status: string
  result: string | null
  error: string | null
  created_at: string
  finished_at: string | null
  generation_info?: GenerationInfo | null
  input_files?: RunInputRecord[] | null
  progress: number
  tasks: Task[]
  stages?: string[][]
  edges?: { source: string; target: string }[]
  final_node_ids?: string[]
}

export interface ExecutionListItem {
  id: number
  service_id: number
  service_name: string
  run_prompt: string
  status: string
  created_at: string
  finished_at: string | null
  generation_info?: GenerationInfo | null
  input_files?: RunInputRecord[] | null
}
