import { Calendar, Mail, Users, StickyNote, HardDrive, Check, Plug } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';

const sources = [
  { id: 'calendar', label: 'Calendar Data', icon: Calendar, connected: true, detail: 'Home PC · read-only', count: '128 events synced' },
  { id: 'email', label: 'Email Data', icon: Mail, connected: true, detail: 'Home PC · read-only', count: '3,204 messages indexed' },
  { id: 'nas', label: 'NAS Documents', icon: HardDrive, connected: true, detail: 'NAS Server · read-write', count: '14 documents in RAG index' },
  { id: 'contacts', label: 'Contacts', icon: Users, connected: false, detail: 'Not linked', count: '—' },
  { id: 'notes', label: 'Notes', icon: StickyNote, connected: false, detail: 'Not linked', count: '—' },
];

export default function DataSources() {
  return (
    <>
      <TopBar title="데이터 소스" breadcrumb={['M.A.R.S', 'Data Sources']} />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <p className="mb-5 max-w-2xl text-[12.5px] leading-relaxed text-ink-500">
          워크플로우가 참조할 수 있는 개인 데이터 소스입니다. 연결된 데이터는 지정된 기기에서만 읽어오며, 외부로
          전송되지 않습니다.
        </p>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {sources.map((s) => {
            const Icon = s.icon;
            return (
              <Card key={s.id} className="p-5">
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                    <Icon size={18} />
                  </div>
                  {s.connected ? (
                    <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[10.5px] font-semibold text-emerald-600">
                      <Check size={11} /> Connected
                    </span>
                  ) : (
                    <button className="flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-[10.5px] font-semibold text-brand-600 hover:bg-brand-100">
                      <Plug size={11} /> Connect
                    </button>
                  )}
                </div>
                <p className="text-[13.5px] font-bold text-ink-900">{s.label}</p>
                <p className="mt-0.5 text-[11.5px] text-ink-500">{s.detail}</p>
                <p className="mt-3 rounded-lg bg-surface-sunk px-2.5 py-1.5 text-[11px] font-medium text-ink-600">{s.count}</p>
              </Card>
            );
          })}
        </div>
      </div>
    </>
  );
}
