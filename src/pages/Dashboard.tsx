import { useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  Target,
  Calendar,
  ClipboardList,
  Brain,
  Plane,
  Sparkles,
  MoreVertical,
  Clock,
  Cpu,
  Users,
} from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useData } from '@/context/DataContext';
import { useState } from 'react';

const categoryIcon: Record<string, typeof Target> = {
  research: Search,
  career: Target,
  planning: ClipboardList,
  meeting: Calendar,
  knowledge: Brain,
  travel: Plane,
  custom: Sparkles,
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { workflows, executions, devices } = useData();
  const [query, setQuery] = useState('');

  const filtered = workflows.filter((w) => w.name.toLowerCase().includes(query.toLowerCase()));
  const onlineDevices = devices.filter((d) => d.status === 'online').length;
  const runningExecutions = executions.filter((e) => e.status === 'running').length;

  return (
    <>
      <TopBar
        title="대시보드"
        actions={
          <button
            onClick={() => navigate('/workflows/new')}
            className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-2 text-[12.5px] font-semibold text-white shadow-soft hover:bg-brand-700"
          >
            <Plus size={15} /> 새 워크플로우
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="전체 워크플로우" value={workflows.length} sub="services" />
          <StatCard label="온라인 기기" value={`${onlineDevices}/${devices.length}`} sub="devices" />
          <StatCard label="실행 중" value={runningExecutions} sub="running now" accent={runningExecutions > 0} />
          <StatCard label="이번 달 실행" value={executions.length} sub="total runs" />
        </div>

        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-[14px] font-bold text-ink-900">내 워크플로우</h2>
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

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <button
            onClick={() => navigate('/workflows/new')}
            className="flex min-h-[176px] flex-col items-center justify-center gap-2 rounded-xl2 border-2 border-dashed border-brand-200 bg-brand-50/40 text-brand-600 transition hover:border-brand-400 hover:bg-brand-50"
          >
            <Plus size={22} />
            <span className="text-[13px] font-semibold">새 워크플로우 만들기</span>
          </button>

          {filtered.map((wf) => {
            const Icon = categoryIcon[wf.category] ?? Sparkles;
            return (
              <Card
                key={wf.id}
                className="group flex cursor-pointer flex-col p-5 transition hover:-translate-y-0.5 hover:shadow-lg"
                onClick={() => navigate(`/workflows/${wf.id}`)}
              >
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                    <Icon size={18} />
                  </div>
                  <button
                    onClick={(e) => e.stopPropagation()}
                    className="rounded-md p-1 text-ink-300 opacity-0 hover:bg-brand-50 group-hover:opacity-100"
                  >
                    <MoreVertical size={16} />
                  </button>
                </div>

                <h3 className="text-[14px] font-bold leading-snug text-ink-900">{wf.name}</h3>
                <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-ink-500">{wf.description}</p>

                <div className="mt-4 flex items-center gap-3 text-[11px] text-ink-500">
                  <span className="flex items-center gap-1">
                    <Users size={12} /> {wf.agentCount} agents
                  </span>
                  <span className="flex items-center gap-1">
                    <Cpu size={12} /> {wf.deviceCount} devices
                  </span>
                  {wf.lastRunDurationSec && (
                    <span className="flex items-center gap-1">
                      <Clock size={12} /> {wf.lastRunDurationSec}s
                    </span>
                  )}
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-brand-100/60 pt-3">
                  <StatusBadge status={wf.status} />
                  <span className="text-[11px] text-ink-300">Updated {wf.updatedAt}</span>
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub: string;
  accent?: boolean;
}) {
  return (
    <Card className="p-4">
      <p className="text-[11.5px] font-medium text-ink-500">{label}</p>
      <div className="mt-1.5 flex items-baseline gap-1.5">
        <span className={`text-2xl font-bold tracking-tight ${accent ? 'text-brand-600' : 'text-ink-900'}`}>
          {value}
        </span>
        <span className="text-[11px] text-ink-300">{sub}</span>
      </div>
    </Card>
  );
}
