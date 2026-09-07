import { createContext, useContext, useState, ReactNode, useCallback } from 'react';
import { workflowSummaries, workflowDetails, executions as seedExecutions, devices as seedDevices } from '@/data/mockData';
import type { Workflow, WorkflowSummary, Execution, WorkflowNode, WorkflowEdge, Device } from '@/types';

let idCounter = 1000;
const nextId = (prefix: string) => `${prefix}-${idCounter++}`;

interface GeneratedPlan {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

/** Very small heuristic "workflow generator" that turns a natural-language
 * prompt into a plausible multi-agent graph, mirroring what the M.A.R.S
 * backend would return from an LLM planning step. */
function generateWorkflowFromPrompt(prompt: string, deviceIds: string[]): GeneratedPlan {
  const lower = prompt.toLowerCase();
  const wantsWeb = /검색|search|web|뉴스|news|리서치|research/.test(lower) || true;
  const wantsDocs = /문서|파일|nas|pdf|보고서|document/.test(lower);
  const wantsCalendar = /일정|캘린더|calendar|미팅|회의|meeting/.test(lower);
  const wantsEmail = /메일|이메일|email|gmail/.test(lower);

  const homeDevice = deviceIds[0] ?? 'dev-home-pc';
  const laptop = deviceIds[1] ?? deviceIds[0] ?? 'dev-laptop';
  const nas = deviceIds.find((d) => d === 'dev-nas') ?? deviceIds[0] ?? 'dev-nas';

  const nodes: WorkflowNode[] = [
    { id: 'start', type: 'marsNode', position: { x: 40, y: 260 }, data: { label: 'Start', kind: 'start', status: 'idle' } },
  ];
  const edges: WorkflowEdge[] = [];
  const sourceNodes: string[] = [];
  let col1Y = 40;

  if (wantsEmail) {
    nodes.push({ id: 'email', type: 'marsNode', position: { x: 280, y: col1Y }, data: { label: 'Email Data', kind: 'data', subtitle: 'Personal email history', device: homeDevice, status: 'idle' } });
    edges.push({ id: nextId('e'), source: 'start', target: 'email' });
    sourceNodes.push('email');
    col1Y += 130;
  }
  if (wantsCalendar) {
    nodes.push({ id: 'calendar', type: 'marsNode', position: { x: 280, y: col1Y }, data: { label: 'Calendar Data', kind: 'data', subtitle: 'Personal schedule', device: homeDevice, status: 'idle' } });
    edges.push({ id: nextId('e'), source: 'start', target: 'calendar' });
    sourceNodes.push('calendar');
    col1Y += 130;
  }
  if (wantsWeb) {
    nodes.push({ id: 'websearch', type: 'marsNode', position: { x: 280, y: col1Y }, data: { label: 'Web Search', kind: 'tool', subtitle: 'Local Tool', device: laptop, status: 'idle' } });
    edges.push({ id: nextId('e'), source: 'start', target: 'websearch' });
    sourceNodes.push('websearch');
    col1Y += 130;
  }
  if (wantsDocs) {
    nodes.push({ id: 'nasdocs', type: 'marsNode', position: { x: 280, y: col1Y }, data: { label: 'NAS Docs', kind: 'tool', subtitle: 'RAG Retrieval', device: nas, status: 'idle' } });
    edges.push({ id: nextId('e'), source: 'start', target: 'nasdocs' });
    sourceNodes.push('nasdocs');
    col1Y += 130;
  }

  const researchId = 'research-agent';
  nodes.push({
    id: researchId,
    type: 'marsNode',
    position: { x: 560, y: 260 },
    data: {
      label: 'Research Agent',
      kind: 'agent',
      subtitle: 'Analyze inputs + synthesize findings',
      device: homeDevice,
      model: 'Local LLM (Llama 3.1 8B)',
      systemPrompt: `You are an expert research agent. Given the task "${prompt}", analyze the provided data, search for relevant information, and synthesize findings into a structured report.`,
      temperature: 0.7,
      inputVariables: sourceNodes,
      outputVariables: ['research_summary', 'key_findings'],
      status: 'idle',
    },
  });
  sourceNodes.forEach((s) => edges.push({ id: nextId('e'), source: s, target: researchId }));

  const plannerId = 'planner-agent';
  nodes.push({
    id: plannerId,
    type: 'marsNode',
    position: { x: 860, y: 260 },
    data: {
      label: 'Planner Agent',
      kind: 'agent',
      subtitle: 'Recommendations & action plan',
      device: 'cloud',
      model: 'GPT-4o (Cloud)',
      systemPrompt: 'You are a planning agent. Synthesize the research findings into a clear, actionable final output for the user.',
      temperature: 0.5,
      inputVariables: ['research_summary', 'key_findings'],
      outputVariables: ['final_plan'],
      status: 'idle',
    },
  });
  edges.push({ id: nextId('e'), source: researchId, target: plannerId, label: 'findings passed' });

  nodes.push({ id: 'output', type: 'marsNode', position: { x: 1120, y: 260 }, data: { label: 'Output', kind: 'output', subtitle: 'Final Report', status: 'idle' } });
  edges.push({ id: nextId('e'), source: plannerId, target: 'output' });

  return { nodes, edges };
}

interface DataContextValue {
  workflows: WorkflowSummary[];
  getWorkflow: (id: string) => Workflow | undefined;
  devices: Device[];
  seedDemoDevices: () => void;
  registerDevice: (device: Device) => void;
  removeDevice: (deviceId: string) => void;
  executions: Execution[];
  createWorkflowFromPrompt: (prompt: string, deviceIds: string[]) => Workflow;
  saveWorkflow: (workflow: Workflow) => void;
  runExecution: (workflowId: string, taskDescription: string) => Execution;
  getExecution: (id: string) => Execution | undefined;
}

const DataContext = createContext<DataContextValue | undefined>(undefined);

export function DataProvider({ children }: { children: ReactNode }) {
  const [workflows, setWorkflows] = useState<Record<string, Workflow>>(workflowDetails);
  const [summaries, setSummaries] = useState<WorkflowSummary[]>(workflowSummaries);
  const [executionList, setExecutionList] = useState<Execution[]>(seedExecutions);
  const [devices, setDevices] = useState<Device[]>([]);

  const getWorkflow = useCallback((id: string) => workflows[id], [workflows]);
  const getExecution = useCallback((id: string) => executionList.find((e) => e.id === id), [executionList]);

  // A brand-new account starts with zero connected devices. This lets a demo
  // user quickly populate the same sample hardware a returning user would have.
  const seedDemoDevices = useCallback(() => setDevices(seedDevices), []);
  const registerDevice = useCallback((device: Device) => setDevices((prev) => [...prev, device]), []);
  const removeDevice = useCallback((deviceId: string) => setDevices((prev) => prev.filter((d) => d.id !== deviceId)), []);

  const createWorkflowFromPrompt = useCallback(
    (prompt: string, deviceIds: string[]) => {
      const id = nextId('wf');
      const plan = generateWorkflowFromPrompt(prompt, deviceIds);
      const summary: WorkflowSummary = {
        id,
        name: prompt.length > 32 ? prompt.slice(0, 32) + '…' : prompt || '새 워크플로우',
        description: prompt,
        status: 'draft',
        updatedAt: new Date().toISOString().slice(0, 10),
        agentCount: plan.nodes.filter((n) => n.data.kind === 'agent').length,
        deviceCount: new Set(plan.nodes.map((n) => n.data.device).filter(Boolean)).size,
        category: 'custom',
        icon: 'sparkles',
      };
      const workflow: Workflow = { ...summary, nodes: plan.nodes, edges: plan.edges };
      setWorkflows((prev) => ({ ...prev, [id]: workflow }));
      setSummaries((prev) => [summary, ...prev]);
      return workflow;
    },
    []
  );

  const saveWorkflow = useCallback((workflow: Workflow) => {
    setWorkflows((prev) => ({ ...prev, [workflow.id]: workflow }));
    setSummaries((prev) => {
      const idx = prev.findIndex((s) => s.id === workflow.id);
      const updatedSummary: WorkflowSummary = {
        id: workflow.id,
        name: workflow.name,
        description: workflow.description,
        status: workflow.status,
        updatedAt: new Date().toISOString().slice(0, 10),
        agentCount: workflow.nodes.filter((n) => n.data.kind === 'agent').length,
        deviceCount: new Set(workflow.nodes.map((n) => n.data.device).filter(Boolean)).size,
        lastRunDurationSec: workflow.lastRunDurationSec,
        category: workflow.category,
        icon: workflow.icon,
      };
      if (idx === -1) return [updatedSummary, ...prev];
      const copy = [...prev];
      copy[idx] = updatedSummary;
      return copy;
    });
  }, []);

  const runExecution = useCallback(
    (workflowId: string, taskDescription: string) => {
      const wf = workflows[workflowId];
      const id = nextId('ex');
      const agentNodes = wf?.nodes.filter((n) => n.data.kind === 'agent') ?? [];
      const execution: Execution = {
        id,
        workflowId,
        workflowName: wf?.name ?? 'Workflow',
        status: 'completed',
        startedAt: new Date().toLocaleString('ko-KR'),
        completedAt: new Date().toLocaleString('ko-KR'),
        durationSec: 12 + agentNodes.length * 4.3,
        devicesUsed: Array.from(new Set(wf?.nodes.map((n) => n.data.device).filter((d): d is string => !!d && d !== 'cloud'))),
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
            level: 'success' as const,
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
        getWorkflow,
        devices,
        seedDemoDevices,
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
