import { useMemo, useState } from 'react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { eventLogs } from '@/data/mockData';
import clsx from 'clsx';
import { Info, AlertTriangle, ShieldAlert } from 'lucide-react';

const categories = ['all', 'auth', 'device', 'workflow', 'execution', 'security', 'billing'] as const;

const severityIcon = { info: Info, warning: AlertTriangle, critical: ShieldAlert } as const;
const severityStyle = {
  info: 'text-ink-500 bg-ink-900/5',
  warning: 'text-amber-600 bg-amber-50',
  critical: 'text-rose-600 bg-rose-50',
} as const;

export default function EventLog() {
  const [category, setCategory] = useState<(typeof categories)[number]>('all');

  const filtered = useMemo(
    () => eventLogs.filter((e) => category === 'all' || e.category === category),
    [category]
  );

  return (
    <>
      <TopBar title="이벤트 로그" breadcrumb={['M.A.R.S', 'Event Log']} />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-4 flex flex-wrap gap-1.5">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={clsx(
                'rounded-full border px-3 py-1.5 text-[11.5px] font-semibold capitalize transition',
                category === c ? 'border-brand-500 bg-brand-600 text-white' : 'border-brand-100 bg-white text-ink-600 hover:bg-brand-50'
              )}
            >
              {c}
            </button>
          ))}
        </div>

        <Card className="divide-y divide-brand-100/60">
          {filtered.map((e) => {
            const Icon = severityIcon[e.severity];
            return (
              <div key={e.id} className="flex items-start gap-3 px-4 py-3">
                <div className={clsx('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full', severityStyle[e.severity])}>
                  <Icon size={13} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[12.5px] text-ink-800">{e.message}</p>
                  <p className="mt-0.5 text-[10.5px] text-ink-400">
                    {e.timestamp} · <span className="capitalize">{e.category}</span>
                  </p>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && <p className="px-4 py-8 text-center text-[12.5px] text-ink-400">이벤트가 없습니다.</p>}
        </Card>
      </div>
    </>
  );
}
