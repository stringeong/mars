import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { executions as seedExecutions } from '@/data/mockData';
import { apiFetch } from '@/lib/api';
import { computeSecurityScore } from '@/lib/security';
import { useAuth } from './AuthContext';

let idCounter = 1000;
const nextId = (prefix) => `${prefix}-${idCounter++}`;

function normalizeDevice(raw) {
  const specs = raw.specs ?? {};
  const fileAccessMode = specs.fileAccessMode ?? 'read-only';
  const agentAccessScope = specs.agentAccessScope ?? 'selected-workflows';
  return {
    id: String(raw.id),
    name: raw.name ?? '기기',
    type: specs.type ?? 'Desktop PC',
    status: raw.online ? 'online' : 'offline',
    cpuModel: specs.cpuModel,
    ramGb: specs.ramGb,
    storage: specs.storage,
    gpu: specs.gpu,
    network: specs.network,
    resources: { cpu: 0, ram: 0, ramTotalGb: specs.ramGb },
    folders: raw.allowed_folders ?? [],
    fileAccessMode,
    agentAccessScope,
    securityScore: computeSecurityScore(fileAccessMode, agentAccessScope),
    registeredAt: raw.last_heartbeat ?? new Date().toISOString().slice(0, 10),
    runningAgent: undefined,
  };
}

function denormalizeDevice(device) {
  return {
    name: device.name,
    specs: {
      type: device.type,
      fileAccessMode: device.fileAccessMode,
      agentAccessScope: device.agentAccessScope,
      cpuModel: device.cpuModel,
      ramGb: device.ramGb,
      storage: device.storage,
      gpu: device.gpu,
      network: device.network,
    },
    allowed_folders: device.folders,
  };
}

function normalizeService(raw) {
  const graph = raw.graph ?? {};
  const rawNodes = graph.nodes ?? [];
  const rawEdges = graph.edges ?? [];

  const nodes = rawNodes.map((n, i) => ({
    id: n.id,
    type: 'marsNode',
    position: { x: 80 + i * 260, y: 260 },
    data: {
      label: n.name ?? n.id,
      kind: 'agent',
      subtitle: n.model ? n.model : 'Local LLM',
      device: n.model ? 'cloud' : undefined,
      model: n.model || 'Local LLM (Llama 3.1 8B)',
      systemPrompt: n.role_prompt ?? '',
      temperature: 0.7,
      inputVariables: [],
      outputVariables: [],
      status: 'idle',
    },
  }));

  const edges = rawEdges.map((e, i) => ({
    id: `e-${e.source}-${e.target}-${i}`,
    source: e.source,
    target: e.target,
  }));

  const updatedAt = (raw.updated_at ?? raw.created_at ?? new Date().toISOString()).slice(0, 10);

  return {
    id: String(raw.id),
    name: raw.name ?? '워크플로우',
    description: raw.description ?? '',
    status: 'draft',
    updatedAt,
    agentCount: nodes.length,
    deviceCount: new Set(nodes.map((n) => n.data.device).filter(Boolean)).size,
    category: 'custom',
    icon: 'sparkles',
    nodes,
    edges,
  };
}

function denormalizeService(workflow) {
  return {
    name: workflow.name,
    description: workflow.description,
    graph: {
      nodes: workflow.nodes
        .filter((n) => n.data.kind === 'agent')
        .map((n) => ({
          id: n.id,
          name: n.data.label,
          role_prompt: n.data.systemPrompt ?? '',
          model: n.data.device === 'cloud' ? n.data.model ?? '' : '',
          allowed_folders: [],
        })),
      edges: workflow.edges.map((e) => ({ source: e.source, target: e.target })),
    },
  };
}

const DataContext = createContext(undefined);

export function DataProvider({ children }) {
  const { isAuthenticated } = useAuth();
  const [workflows, setWorkflows] = useState({});
  const [summaries, setSummaries] = useState([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(false);
  const [executionList, setExecutionList] = useState(seedExecutions);
  const [devices, setDevices] = useState([]);
  const [devicesLoading, setDevicesLoading] = useState(false);

  const getWorkflow = useCallback((id) => workflows[id], [workflows]);
  const getExecution = useCallback((id) => executionList.find((e) => e.id === id), [executionList]);

  useEffect(() => {
    if (!isAuthenticated) {
      setDevices([]);
      return;
    }
    setDevicesLoading(true);
    apiFetch('/devices')
      .then((raw) => setDevices(raw.map(normalizeDevice)))
      .catch(() => setDevices([]))
      .finally(() => setDevicesLoading(false));
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setWorkflows({});
      setSummaries([]);
      return;
    }
    setWorkflowsLoading(true);
    apiFetch('/services')
      .then((raw) => {
        const normalized = raw.map(normalizeService);
        setWorkflows(Object.fromEntries(normalized.map((w) => [w.id, w])));
        setSummaries(normalized);
      })
      .catch(() => {
        setWorkflows({});
        setSummaries([]);
      })
      .finally(() => setWorkflowsLoading(false));
  }, [isAuthenticated]);

  const registerDevice = useCallback(async (device) => {
    const created = await apiFetch('/devices', {
      method: 'POST',
      body: JSON.stringify(denormalizeDevice(device)),
    });
    setDevices((prev) => [...prev, normalizeDevice(created)]);
  }, []);

  const removeDevice = useCallback(async (deviceId) => {
    await apiFetch(`/devices/${deviceId}`, { method: 'DELETE' });
    setDevices((prev) => prev.filter((d) => d.id !== deviceId));
  }, []);

  const createWorkflowFromPrompt = useCallback(async (prompt, _deviceIds) => {
    const raw = await apiFetch('/services/generate', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
    const workflow = normalizeService(raw);
    setWorkflows((prev) => ({ ...prev, [workflow.id]: workflow }));
    setSummaries((prev) => [workflow, ...prev]);
    return workflow;
  }, []);

  const saveWorkflow = useCallback(async (workflow) => {
    const raw = await apiFetch(`/services/${workflow.id}`, {
      method: 'PUT',
      body: JSON.stringify(denormalizeService(workflow)),
    });
    const updated = normalizeService(raw);
    setWorkflows((prev) => ({ ...prev, [updated.id]: updated }));
    setSummaries((prev) => {
      const idx = prev.findIndex((s) => s.id === updated.id);
      if (idx === -1) return [updated, ...prev];
      const copy = [...prev];
      copy[idx] = updated;
      return copy;
    });
  }, []);

  const runExecution = useCallback(
    (workflowId, taskDescription) => {
      const wf = workflows[workflowId];
      const id = nextId('ex');
      const agentNodes = wf?.nodes.filter((n) => n.data.kind === 'agent') ?? [];
      const execution = {
        id,
        workflowId,
        workflowName: wf?.name ?? 'Workflow',
        status: 'completed',
        startedAt: new Date().toLocaleString('ko-KR'),
        completedAt: new Date().toLocaleString('ko-KR'),
        durationSec: 12 + agentNodes.length * 4.3,
        devicesUsed: Array.from(new Set(wf?.nodes.map((n) => n.data.device).filter((d) => !!d && d !== 'cloud'))),
        cloudModelsUsed: wf?.nodes.some((n) => n.data.device === 'cloud') ? ['GPT-4o'] : [],
        totalTokens: 3000 + agentNodes.length * 2100,
        estimatedCost: Number((0.01 + agentNodes.length * 0.015).toFixed(2)),
        taskDescription,
        outputs: [
          { id: nextId('o'), title: 'Summary', meta: 'generated', detail: `"${taskDescription}" 요청에 대한 결과를 생성했습니다.` },
          { id: nextId('o'), title: 'Key Findings', meta: `${Math.max(agentNodes.length, 1) * 4} items`, detail: '에이전트가 도출한 핵심 인사이트입니다.' },
        ],
        files: [{ id: nextId('f'), name: 'Result_Report.pdf', sizeLabel: '1.2 MB', kind: 'pdf' }],
        agentSteps: agentNodes.map((n, i) => ({
          id: nextId('a'),
          agentName: n.data.label,
          device: n.data.device === 'cloud' ? `Cloud · ${n.data.model ?? ''}` : `${n.data.device ?? 'Home PC'} · ${n.data.model ?? 'Local LLM'}`,
          modelBadge: n.data.model?.split(' ')[0] ?? 'LLM',
          summary: `${n.data.label}가 입력 데이터를 분석하고 결과를 다음 단계로 전달했습니다.`,
          findingsCount: i === 0 ? 8 + agentNodes.length : undefined,
          durationSec: 5 + i * 3.1,
          tokens: 1500 + i * 900,
        })),
        logs: [
          { id: nextId('l'), timestamp: new Date().toLocaleTimeString('ko-KR'), actor: 'System', message: 'Workflow execution started', level: 'info' },
          ...agentNodes.map((n) => ({
            id: nextId('l'),
            timestamp: new Date().toLocaleTimeString('ko-KR'),
            actor: n.data.label,
            message: `${n.data.label} completed its task`,
            level: 'success',
            device: n.data.device,
          })),
          { id: nextId('l'), timestamp: new Date().toLocaleTimeString('ko-KR'), actor: 'System', message: 'Execution completed successfully', level: 'success' },
        ],
      };
      setExecutionList((prev) => [execution, ...prev]);
      return execution;
    },
    [workflows]
  );

  return (
    <DataContext.Provider
      value={{
        workflows: summaries,
        workflowsLoading,
        getWorkflow,
        devices,
        devicesLoading,
        registerDevice,
        removeDevice,
        executions: executionList,
        createWorkflowFromPrompt,
        saveWorkflow,
        runExecution,
        getExecution,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useData must be used within DataProvider');
  return ctx;
}
