// ---------- Auth ----------
export interface User {
  id: string;
  name: string;
  email: string;
  plan: 'Free' | 'Pro' | 'Team';
  avatarInitials: string;
}

// ---------- Devices ----------
export type DeviceType = 'Windows Laptop' | 'Desktop PC' | 'Android Phone' | 'NAS Server' | 'iPhone';
export type DeviceStatus = 'online' | 'idle' | 'offline';

export interface DeviceResource {
  cpu: number; // percent
  ram: number; // percent
  ramTotalGb?: number;
}

export interface Device {
  id: string;
  name: string;
  type: DeviceType;
  status: DeviceStatus;
  cpuModel?: string;
  ramGb?: number;
  storage?: string;
  gpu?: string;
  network?: string;
  resources: DeviceResource;
  folders: string[];
  fileAccessMode: 'read-only' | 'read-write';
  agentAccessScope: 'local-only' | 'selected-workflows' | 'all-workflows';
  securityScore: 'High' | 'Medium' | 'Low';
  registeredAt: string;
  runningAgent?: string;
}

// ---------- Cloud models ----------
export interface CloudModel {
  id: string;
  name: string;
  provider: 'OpenAI' | 'Anthropic' | 'Google';
  modelId: string;
  status: 'online' | 'offline';
  latencyMs?: number;
  tokensToday?: number;
  costToday?: number;
}

// ---------- Workflow / Agents ----------
export type NodeKind = 'start' | 'agent' | 'tool' | 'data' | 'merge' | 'output';

export type AgentRole =
  | 'Planner Agent'
  | 'Research Agent'
  | 'Summarizer Agent'
  | 'Decision Agent'
  | 'Writer Agent';

export type ModelChoice =
  | 'Local LLM (Llama 3.1 8B)'
  | 'Local LLM (Gemma 2 9B)'
  | 'Local LLM (Qwen3 8B)'
  | 'GPT-4o (Cloud)'
  | 'Claude Sonnet 4.6 (Cloud)'
  | 'Gemini 1.5 Pro (Cloud)';

export interface WorkflowNodeData {
  label: string;
  kind: NodeKind;
  device?: string; // assigned device id or 'cloud'
  model?: ModelChoice;
  systemPrompt?: string;
  temperature?: number;
  inputVariables?: string[];
  outputVariables?: string[];
  toolName?: string;
  status?: 'idle' | 'running' | 'success' | 'error';
  durationSec?: number;
  subtitle?: string;
}

export interface WorkflowNode {
  id: string;
  type: 'marsNode';
  position: { x: number; y: number };
  data: WorkflowNodeData;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  animated?: boolean;
}

export type WorkflowStatus = 'draft' | 'ready' | 'running' | 'completed' | 'failed';

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  status: WorkflowStatus;
  updatedAt: string;
  agentCount: number;
  deviceCount: number;
  lastRunDurationSec?: number;
  category: 'research' | 'career' | 'planning' | 'meeting' | 'knowledge' | 'travel' | 'custom';
  icon: string;
}

export interface Workflow extends WorkflowSummary {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

// ---------- Execution ----------
export type ExecutionStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface ExecutionLogEntry {
  id: string;
  timestamp: string;
  nodeId?: string;
  actor: string;
  message: string;
  level: 'info' | 'success' | 'warning' | 'error';
  device?: string;
}

export interface AgentCollabStep {
  id: string;
  agentName: string;
  device: string;
  modelBadge: string;
  summary: string;
  findingsCount?: number;
  durationSec: number;
  tokens?: number;
}

export interface ExecutionOutputSection {
  id: string;
  title: string;
  meta: string;
  detail: string;
}

export interface GeneratedFile {
  id: string;
  name: string;
  sizeLabel: string;
  kind: 'pdf' | 'docx' | 'pptx' | 'xlsx';
}

export interface Execution {
  id: string;
  workflowId: string;
  workflowName: string;
  status: ExecutionStatus;
  startedAt: string;
  completedAt?: string;
  durationSec?: number;
  devicesUsed: string[];
  cloudModelsUsed: string[];
  totalTokens?: number;
  estimatedCost?: number;
  taskDescription: string;
  outputs: ExecutionOutputSection[];
  files: GeneratedFile[];
  agentSteps: AgentCollabStep[];
  logs: ExecutionLogEntry[];
}

// ---------- Event log ----------
export interface EventLogEntry {
  id: string;
  timestamp: string;
  category: 'auth' | 'device' | 'workflow' | 'execution' | 'security' | 'billing';
  message: string;
  severity: 'info' | 'warning' | 'critical';
}
