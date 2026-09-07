import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Clock, Cpu, Coins } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useData } from '@/context/DataContext';
import clsx from 'clsx';

const filters = [
  { id: 'all', label: 'All' },
  { id: 'completed', label: 'Completed' },
  { id: 'running', label: 'Running' },
  { id: 'failed', label: 'Failed' },
] as const;

export default function Executions() {
  const { executions } = useData();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<(typeof filters)[number]['id']>('all');
  const [query, setQuery] = useState('');

  const filtered = useMemo(
    () =>
      executions.filter((e) => {
        const matchesFilter = filter === 'all' || e.status === filter;
        const matchesQuery = e.workflowName.toLowerCase().includes(query.toLowerCase());
        return matchesFilter && matchesQuery;
      }),
    [executions, filter, query]
  );

  return (
    <>
      <TopBar title="실행 이력" breadcrumb={['M.A.R.S', 'Executions']} />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 rounded-lg border border-brand-100 bg-white p-1">
            {filters.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={clsx(
                  'rounded-md px-3 py-1.5 text-[12px] font-semibold transition',
                  filter === f.id ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-brand-50'
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-white px-3 py-1.5">
            <Search size={13} className="text-ink-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="워크플로우 검색"
              className="w-48 bg-transparent text-[12.5px] outline-none placeholder:text-ink-300"
            />
          </div>
        </div>

        <div className="space-y-2.5">
          {filtered.map((ex) => (
            <Card
              key={ex.id}
              className="flex cursor-pointer flex-col gap-2 p-4 transition hover:border-brand-300 sm:flex-row sm:items-center sm:justify-between"
              onClick={() => navigate(`/executions/${ex.id}`)}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate text-[13px] font-bold text-ink-900">{ex.workflowName}</p>
                  <StatusBadge status={ex.status} />
                </div>
                <p className="mt-1 line-clamp-1 text-[12px] text-ink-500">{ex.taskDescription}</p>
              </div>

              <div className="flex shrink-0 items-center gap-4 text-[11.5px] text-ink-500">
                <span className="flex items-center gap-1">
                  <Clock size={12} /> {ex.durationSec ? `${ex.durationSec.toFixed(0)}s` : '진행 중'}
                </span>
                <span className="flex items-center gap-1">
                  <Cpu size={12} /> {ex.devicesUsed.length} devices
                </span>
                {ex.estimatedCost !== undefined && (
                  <span className="flex items-center gap-1">
                    <Coins size={12} /> ${ex.estimatedCost}
                  </span>
                )}
                <span className="hidden text-ink-300 sm:block">{ex.startedAt}</span>
              </div>
            </Card>
          ))}

          {filtered.length === 0 && (
            <div className="rounded-xl2 border border-dashed border-brand-200 bg-brand-50/30 py-14 text-center text-[13px] text-ink-500">
              조건에 맞는 실행 이력이 없습니다.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
