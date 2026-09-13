import clsx from 'clsx';

type Tone = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'running';

const toneStyles: Record<Tone, string> = {
  success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  error: 'bg-rose-50 text-rose-700 border-rose-200',
  info: 'bg-blue-50 text-blue-700 border-blue-200',
  neutral: 'bg-ink-900/5 text-ink-500 border-ink-900/10',
  running: 'bg-brand-50 text-brand-700 border-brand-200',
};

const statusMap: Record<string, { label: string; tone: Tone }> = {
  ready: { label: 'Ready', tone: 'info' },
  draft: { label: 'Draft', tone: 'neutral' },
  running: { label: 'Running', tone: 'running' },
  queued: { label: 'Queued', tone: 'neutral' },
  completed: { label: 'Completed', tone: 'success' },
  failed: { label: 'Failed', tone: 'error' },
  online: { label: 'Online', tone: 'success' },
  idle: { label: 'Idle', tone: 'warning' },
  offline: { label: 'Offline', tone: 'neutral' },
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const cfg = statusMap[status] ?? { label: label ?? status, tone: 'neutral' as Tone };
  const isRunning = status === 'running';
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold',
        toneStyles[cfg.tone]
      )}
    >
      {isRunning && <span className="h-1.5 w-1.5 rounded-full bg-brand-600 pulse-dot" />}
      {label ?? cfg.label}
    </span>
  );
}
