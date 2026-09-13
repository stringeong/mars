import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import clsx from 'clsx';
import {
  Play,
  Bot,
  Wrench,
  Mail,
  Calendar,
  FileSearch,
  GitMerge,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Globe,
} from 'lucide-react';
import type { WorkflowNodeData } from '@/types';

const kindStyle: Record<string, { border: string; bg: string; icon: string; ring: string }> = {
  start: { border: 'border-ink-900/15', bg: 'bg-white', icon: 'text-ink-700', ring: 'ring-ink-900/10' },
  data: { border: 'border-amber-300', bg: 'bg-amber-50', icon: 'text-amber-600', ring: 'ring-amber-200' },
  tool: { border: 'border-emerald-300', bg: 'bg-emerald-50', icon: 'text-emerald-600', ring: 'ring-emerald-200' },
  agent: { border: 'border-brand-300', bg: 'bg-brand-50', icon: 'text-brand-600', ring: 'ring-brand-200' },
  merge: { border: 'border-ink-900/15', bg: 'bg-white', icon: 'text-ink-500', ring: 'ring-ink-900/10' },
  output: { border: 'border-blue-300', bg: 'bg-blue-50', icon: 'text-blue-600', ring: 'ring-blue-200' },
};

function pickIcon(label: string, kind: string) {
  const l = label.toLowerCase();
  if (kind === 'start') return Play;
  if (kind === 'output') return CheckCircle2;
  if (kind === 'merge') return GitMerge;
  if (l.includes('email') || l.includes('gmail')) return Mail;
  if (l.includes('calendar')) return Calendar;
  if (l.includes('nas') || l.includes('doc')) return FileSearch;
  if (l.includes('web') || l.includes('search')) return Globe;
  if (kind === 'tool') return Wrench;
  return Bot;
}

function StatusIcon({ status }: { status?: WorkflowNodeData['status'] }) {
  if (status === 'running') return <Loader2 size={13} className="animate-spin text-brand-600" />;
  if (status === 'success') return <CheckCircle2 size={13} className="text-emerald-500" />;
  if (status === 'error') return <AlertCircle size={13} className="text-rose-500" />;
  return null;
}

type MarsFlowNode = Node<WorkflowNodeData>;

export const MarsNode = memo(({ data, selected }: NodeProps<MarsFlowNode>) => {
  const style = kindStyle[data.kind] ?? kindStyle.data;
  const Icon = pickIcon(data.label, data.kind);
  const isStart = data.kind === 'start';

  return (
    <div
      className={clsx(
        'w-[168px] rounded-xl border-2 bg-white px-3 py-2.5 shadow-soft transition-all',
        style.border,
        selected && 'ring-4',
        selected && style.ring
      )}
    >
      {!isStart && <Handle type="target" position={Position.Left} />}
      <div className="flex items-center gap-2">
        <div className={clsx('flex h-6 w-6 shrink-0 items-center justify-center rounded-md', style.bg)}>
          <Icon size={13} className={style.icon} strokeWidth={2.25} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-bold leading-tight text-ink-900">{data.label}</p>
          {data.subtitle && <p className="truncate text-[10px] leading-tight text-ink-500">{data.subtitle}</p>}
        </div>
        <StatusIcon status={data.status} />
      </div>
      {data.kind === 'agent' && (
        <div className="mt-2 flex items-center justify-between border-t border-ink-900/5 pt-1.5">
          <span className="truncate text-[9.5px] font-medium text-brand-600">{data.model?.split(' (')[0]}</span>
          {data.durationSec !== undefined && (
            <span className="text-[9.5px] text-ink-500">{data.durationSec.toFixed(1)}s</span>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
});

MarsNode.displayName = 'MarsNode';

export const nodeTypes = { marsNode: MarsNode };
