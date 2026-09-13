import { Laptop, Monitor, Smartphone, HardDrive, Cloud } from 'lucide-react';
import { useData } from '@/context/DataContext';
import { cloudModels } from '@/data/mockData';
import clsx from 'clsx';

const deviceIcon: Record<string, typeof Laptop> = {
  'Desktop PC': Monitor,
  'Windows Laptop': Laptop,
  'Android Phone': Smartphone,
  'NAS Server': HardDrive,
  iPhone: Smartphone,
};

export function ResourceStatusBar() {
  const { devices } = useData();

  return (
    <div className="flex h-11 shrink-0 items-center gap-6 overflow-x-auto border-t border-brand-100/60 bg-white px-4 text-[11px]">
      <div className="flex items-center gap-4">
        {devices.map((d) => {
          const Icon = deviceIcon[d.type] ?? Monitor;
          return (
            <div key={d.id} className="flex items-center gap-1.5 whitespace-nowrap">
              <Icon size={13} className="text-ink-500" />
              <span className="font-medium text-ink-700">{d.name}</span>
              <span
                className={clsx(
                  'h-1.5 w-1.5 rounded-full',
                  d.status === 'online' ? 'bg-emerald-500' : d.status === 'idle' ? 'bg-amber-500' : 'bg-ink-300'
                )}
              />
              <span className="text-ink-500">CPU {d.resources.cpu}%</span>
            </div>
          );
        })}
      </div>
      <div className="h-4 w-px bg-brand-100" />
      <div className="flex items-center gap-4">
        {cloudModels.map((m) => (
          <div key={m.id} className="flex items-center gap-1.5 whitespace-nowrap">
            <Cloud size={13} className="text-ink-500" />
            <span className="font-medium text-ink-700">{m.name}</span>
            <span className={clsx('h-1.5 w-1.5 rounded-full', m.status === 'online' ? 'bg-emerald-500' : 'bg-ink-300')} />
            <span className="text-ink-500">{m.latencyMs ?? '–'}ms</span>
          </div>
        ))}
      </div>
    </div>
  );
}
