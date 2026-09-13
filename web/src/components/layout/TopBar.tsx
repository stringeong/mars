import { ReactNode } from 'react';
import { Bell } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useData } from '@/context/DataContext';

interface TopBarProps {
  title: string;
  breadcrumb?: string[];
  actions?: ReactNode;
}

export function TopBar({ title, breadcrumb, actions }: TopBarProps) {
  const { user } = useAuth();
  const { devices } = useData();
  const onlineCount = devices.filter((d) => d.status !== 'offline').length;

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-brand-100/60 bg-white/70 px-6 backdrop-blur">
      <div>
        {breadcrumb && (
          <p className="text-[11px] text-ink-500">
            {breadcrumb.join('  ›  ')}
          </p>
        )}
        <h1 className="text-[17px] font-bold tracking-tight text-ink-900">{title}</h1>
      </div>

      <div className="flex items-center gap-3">
        {actions}

        <div className="hidden items-center gap-1.5 rounded-full border border-brand-100 bg-white px-3 py-1.5 text-[12px] font-medium text-ink-700 sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 pulse-dot" />
          {onlineCount} Devices Online
        </div>

        <button className="flex h-9 w-9 items-center justify-center rounded-full border border-brand-100 bg-white text-ink-500 hover:bg-brand-50">
          <Bell size={16} />
        </button>

        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-[12px] font-bold text-white">
          {user?.avatarInitials ?? 'U'}
        </div>
      </div>
    </header>
  );
}
