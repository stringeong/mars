export interface AgentNode {
  id: string
  type: 'agent'
  name: string
  role_prompt: string
  model: string
  worker_id?: number | null
  directory_ids?: number[]
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

export interface Graph {
  nodes: WorkflowNode[]
  edges: GraphEdge[]
}

export interface Service {
  id: number
  name: string
  description: string
  graph: Graph
  created_at: string
  updated_at: string
}

export interface Device {
  id: number
  name: string
  specs: Record<string, unknown>
  last_heartbeat: string | null
  online: boolean
}


export interface SharedDirectory {
  id: number
  user_id: number
  device_id: number
  alias: string
  local_path: string
  permission: 'read' | 'read_write'
  is_active: boolean
  created_at: string
  updated_at: string
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
  progress: number
  tasks: Task[]
}

export interface ExecutionListItem {
  id: number
  service_id: number
  service_name: string
  run_prompt: string
  status: string
  created_at: string
  finished_at: string | null
}
