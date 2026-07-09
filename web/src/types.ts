export interface AgentNode {
  id: string
  name: string
  role_prompt: string
  model: string
  allowed_folders: string[]
  position?: { x: number; y: number } | null
}

export interface GraphEdge {
  source: string
  target: string
}

export interface Graph {
  nodes: AgentNode[]
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
  allowed_folders: string[]
  last_heartbeat: string | null
  online: boolean
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
