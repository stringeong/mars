import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Cpu,
  Workflow,
  PlayCircle,
  Database,
  Store,
  Settings,
  ScrollText,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';

const navItems = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/devices', label: '기기 관리', icon: Cpu },
  { to: '/workflows/new', label: '워크플로우 빌더', icon: Workflow },
  { to: '/executions', label: '실행 이력', icon: PlayCircle },
  { to: '/data-sources', label: '데이터 소스', icon: Database },
  { to: '/marketplace', label: '마켓플레이스', icon: Store },
  { to: '/events', label: '이벤트 로그', icon: ScrollText },
  { to: '/settings', label: '설정', icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-brand-100/60 bg-white/70 px-3 py-5 backdrop-blur md:flex">
      <div className="mb-6 flex items-center gap-2 px-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-soft">
          <Zap size={18} strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <p className="text-[15px] font-bold tracking-tight text-ink-900">M.A.R.S</p>
          <p className="text-[11px] text-ink-500">Multi-Agent Resource Sharing</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                'group flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors',
                isActive
                  ? 'bg-brand-500 text-white shadow-soft'
                  : 'text-ink-700 hover:bg-brand-50 hover:text-brand-700'
              )
            }
          >
            <Icon size={17} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-4 rounded-xl bg-surface-sunk px-3 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-600">Pro Plan Active</p>
        <p className="mt-0.5 text-[11px] text-ink-500">10 agents · 5GB NAS</p>
      </div>
    </aside>
  );
}
