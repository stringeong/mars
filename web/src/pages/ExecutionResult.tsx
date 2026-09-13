import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ReactFlow, Background, BackgroundVariant, ReactFlowProvider, type Node, type Edge } from '@xyflow/react';
import {
  RotateCcw,
  Download,
  Clock,
  ChevronRight,
  ChevronDown,
  FileText,
  FileSpreadsheet,
  Presentation as PresentationIcon,
  Sparkles,
  Terminal,
} from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { nodeTypes } from '@/components/workflow/MarsNode';
import { useData } from '@/context/DataContext';
import type { WorkflowNodeData } from '@/types';

const fileIcon: Record<string, typeof FileText> = {
  pdf: FileText,
  docx: FileText,
  pptx: PresentationIcon,
  xlsx: FileSpreadsheet,
};

export default function ExecutionResult() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { getExecution, getWorkflow } = useData();
  const execution = id ? getExecution(id) : undefined;
  const workflow = execution ? getWorkflow(execution.workflowId) : undefined;
  const [openOutput, setOpenOutput] = useState<string | null>(execution?.outputs[0]?.id ?? null);
  const [showLogs, setShowLogs] = useState(false);

  const flowNodes: Node<WorkflowNodeData>[] = useMemo(
    () =>
      (workflow?.nodes ?? []).map((n) => ({
        ...n,
        data: { ...n.data, status: execution?.status === 'failed' ? n.data.status : 'success' },
      })) as Node<WorkflowNodeData>[],
    [workflow, execution]
  );
  const flowEdges: Edge[] = useMemo(() => (workflow?.edges as unknown as Edge[]) ?? [], [workflow]);

  if (!execution) {
    return <div className="flex flex-1 items-center justify-center text-ink-500">실행 결과를 찾을 수 없습니다.</div>;
  }

  return (
    <>
      <TopBar
        title={execution.workflowName}
        breadcrumb={['M.A.R.S', 'Executions', execution.workflowName]}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={execution.status} label={execution.status === 'completed' ? 'Completed Successfully' : undefined} />
            <span className="flex items-center gap-1 rounded-full border border-brand-100 bg-white px-2.5 py-1 text-[11px] font-medium text-ink-700">
              <Clock size={12} /> {execution.durationSec?.toFixed(1) ?? '—'} sec
            </span>
            <button
              onClick={() => navigate(`/workflows/${execution.workflowId}/run`)}
              className="flex items-center gap-1.5 rounded-lg border border-brand-100 bg-white px-3 py-2 text-[12.5px] font-semibold text-ink-700 hover:bg-brand-50"
            >
              <RotateCcw size={13} /> Run Again
            </button>
            <button className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-2 text-[12.5px] font-bold text-white shadow-soft hover:bg-brand-700">
              <Download size={13} /> Export Report
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-5 rounded-xl2 border border-brand-100 bg-white p-4 shadow-soft">
          <p className="mb-2 text-[12.5px] font-semibold text-ink-500">"{execution.taskDescription}"</p>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_320px]">
          <div className="space-y-5">
            <Card className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="flex items-center gap-1.5 text-[12.5px] font-bold text-ink-900">
                  <Sparkles size={14} className="text-brand-600" /> Workflow Visualization
                </p>
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-600">
                  All nodes completed
                </span>
              </div>
              <div className="h-72 overflow-hidden rounded-xl border border-brand-100/60 bg-surface-sunk">
                <ReactFlowProvider>
                  <ReactFlow
                    nodes={flowNodes}
                    edges={flowEdges}
                    nodeTypes={nodeTypes}
                    fitView
                    nodesDraggable={false}
                    nodesConnectable={false}
                    zoomOnScroll={false}
                    panOnDrag
                    proOptions={{ hideAttribution: true }}
                  >
                    <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#dfe2f7" />
                  </ReactFlow>
                </ReactFlowProvider>
              </div>
            </Card>

            <Card className="p-4">
              <p className="mb-3 text-[12.5px] font-bold text-ink-900">Agent Collaboration Summary</p>
              <div className="space-y-0">
                {execution.agentSteps.map((step, i) => (
                  <div key={step.id}>
                    <div className="rounded-xl border border-brand-100 bg-surface-sunk p-3.5">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-[10px] font-bold text-white">
                          {i + 1}
                        </span>
                        <p className="text-[13px] font-bold text-ink-900">{step.agentName}</p>
                        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-ink-500 ring-1 ring-brand-100">
                          {step.device}
                        </span>
                      </div>
                      <p className="mt-2 text-[12.5px] leading-relaxed text-ink-700">{step.summary}</p>
                      <div className="mt-2 flex items-center gap-3 text-[11px] text-emerald-600">
                        {step.findingsCount && <span>✓ {step.findingsCount} findings generated</span>}
                        <span className="text-ink-400">· {step.durationSec.toFixed(1)}s</span>
                        {step.tokens && <span className="text-ink-400">· {step.tokens.toLocaleString()} tokens</span>}
                      </div>
                    </div>
                    {i < execution.agentSteps.length - 1 && (
                      <div className="my-1 flex items-center justify-center gap-2 py-1 text-[10.5px] text-ink-400">
                        <span className="h-px flex-1 bg-brand-100" /> Agent Handoff <span className="h-px flex-1 bg-brand-100" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4">
              <button onClick={() => setShowLogs((s) => !s)} className="flex w-full items-center justify-between">
                <span className="flex items-center gap-1.5 text-[12.5px] font-bold text-ink-900">
                  <Terminal size={14} /> Agent Thinking Process
                </span>
                <ChevronDown size={15} className={`text-ink-400 transition-transform ${showLogs ? 'rotate-180' : ''}`} />
              </button>
              {showLogs && (
                <div className="mt-3 space-y-1.5 rounded-xl bg-ink-900 p-3 font-mono text-[11px] leading-relaxed text-emerald-300">
                  {execution.logs.map((log) => (
                    <p key={log.id}>
                      <span className="text-ink-300">[{log.timestamp}]</span>{' '}
                      <span className="text-brand-300">{log.actor}</span>{' '}
                      <span className={log.level === 'error' ? 'text-rose-400' : log.level === 'warning' ? 'text-amber-300' : 'text-emerald-300'}>
                        {log.message}
                      </span>
                    </p>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="space-y-4">
            <Card className="p-4">
              <p className="mb-3 text-[12.5px] font-bold text-ink-900">Final Output</p>
              <div className="space-y-1.5">
                {execution.outputs.map((o) => (
                  <div key={o.id} className="rounded-lg border border-brand-100/70">
                    <button
                      onClick={() => setOpenOutput(openOutput === o.id ? null : o.id)}
                      className="flex w-full items-center justify-between px-3 py-2.5"
                    >
                      <span className="text-left">
                        <p className="text-[12.5px] font-semibold text-ink-900">{o.title}</p>
                        <p className="text-[10.5px] text-ink-500">{o.meta}</p>
                      </span>
                      <ChevronRight size={14} className={`text-ink-400 transition-transform ${openOutput === o.id ? 'rotate-90' : ''}`} />
                    </button>
                    {openOutput === o.id && (
                      <p className="border-t border-brand-100/70 px-3 py-2.5 text-[12px] leading-relaxed text-ink-600">{o.detail}</p>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            {execution.files.length > 0 && (
              <Card className="p-4">
                <p className="mb-3 text-[12.5px] font-bold text-ink-900">Generated Files</p>
                <div className="space-y-2">
                  {execution.files.map((f) => {
                    const Icon = fileIcon[f.kind] ?? FileText;
                    return (
                      <div key={f.id} className="flex items-center justify-between rounded-lg border border-brand-100 px-3 py-2">
                        <span className="flex items-center gap-2 text-[12px] font-medium text-ink-700">
                          <Icon size={14} className="text-brand-500" /> {f.name}
                        </span>
                        <span className="text-[10.5px] text-ink-400">{f.sizeLabel}</span>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            <Card className="p-4">
              <p className="mb-3 text-[12.5px] font-bold text-ink-900">Execution Metadata</p>
              <dl className="space-y-2 text-[12px]">
                <Row label="Devices Used" value={execution.devicesUsed.join(', ') || '—'} />
                <Row label="Cloud Models" value={execution.cloudModelsUsed.join(', ') || '—'} />
                <Row label="Total Tokens" value={execution.totalTokens?.toLocaleString() ?? '—'} />
                <Row label="Estimated Cost" value={execution.estimatedCost ? `$${execution.estimatedCost}` : '—'} />
                <Row label="Started" value={execution.startedAt} />
              </dl>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-ink-500">{label}</dt>
      <dd className="max-w-[60%] text-right font-medium text-ink-900">{value}</dd>
    </div>
  );
}
