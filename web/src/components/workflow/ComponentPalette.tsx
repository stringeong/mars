import { useState } from 'react';
import { Search, Bot, Wrench, Database, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import type { NodeKind } from '@/types';

export interface PaletteItem {
  label: string;
  kind: NodeKind;
  subtitle: string;
}

const agentItems: PaletteItem[] = [
  { label: 'Planner Agent', kind: 'agent', subtitle: 'Builds action plans' },
  { label: 'Research Agent', kind: 'agent', subtitle: 'Searches & synthesizes' },
  { label: 'Summarizer Agent', kind: 'agent', subtitle: 'Condenses long content' },
  { label: 'Decision Agent', kind: 'agent', subtitle: 'Weighs trade-offs' },
  { label: 'Writer Agent', kind: 'agent', subtitle: 'Drafts final copy' },
];

const toolItems: PaletteItem[] = [
  { label: 'Web Search', kind: 'tool', subtitle: 'Search the open web' },
  { label: 'Browser', kind: 'tool', subtitle: 'Navigate & extract pages' },
  { label: 'Gmail', kind: 'tool', subtitle: 'Read personal email' },
  { label: 'Calendar', kind: 'tool', subtitle: 'Read schedule & events' },
  { label: 'File Reader', kind: 'tool', subtitle: 'Parse local documents' },
  { label: 'API Request', kind: 'tool', subtitle: 'Call an external API' },
];

const dataItems: PaletteItem[] = [
  { label: 'Calendar Data', kind: 'data', subtitle: 'Personal schedule' },
  { label: 'Email Data', kind: 'data', subtitle: 'Personal email history' },
  { label: 'NAS Docs', kind: 'data', subtitle: 'Documents on NAS' },
  { label: 'Contacts', kind: 'data', subtitle: 'Personal contacts' },
];

function Section({
  title,
  icon: Icon,
  items,
  onDragStart,
  onAddNode,
}: {
  title: string;
  icon: typeof Bot;
  items: PaletteItem[];
  onDragStart: (item: PaletteItem) => (e: React.DragEvent) => void;
  onAddNode: (item: PaletteItem) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mb-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-[11px] font-bold uppercase tracking-wide text-ink-500 hover:bg-brand-50"
      >
        <span className="flex items-center gap-1.5">
          <Icon size={12} /> {title}
        </span>
        <ChevronDown size={13} className={clsx('transition-transform', !open && '-rotate-90')} />
      </button>
      {open && (
        <div className="mt-1 flex flex-col gap-1">
          {items.map((item) => (
            <div
              key={item.label}
              draggable
              onDragStart={onDragStart(item)}
              onDoubleClick={() => onAddNode(item)}
              className="cursor-grab rounded-lg border border-transparent px-2.5 py-1.5 text-[12.5px] font-medium text-ink-700 hover:border-brand-200 hover:bg-brand-50 active:cursor-grabbing"
            >
              {item.label}
              <p className="text-[10.5px] font-normal text-ink-500">{item.subtitle}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ComponentPalette({ onAddNode }: { onAddNode: (item: PaletteItem) => void }) {
  const [query, setQuery] = useState('');

  const filter = (items: PaletteItem[]) =>
    items.filter((i) => i.label.toLowerCase().includes(query.toLowerCase()));

  const onDragStart = (item: PaletteItem) => (e: React.DragEvent) => {
    e.dataTransfer.setData('application/mars-node', JSON.stringify(item));
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="flex h-full w-60 shrink-0 flex-col border-r border-brand-100/60 bg-white">
      <div className="border-b border-brand-100/60 p-3">
        <p className="mb-2 text-[13px] font-bold text-ink-900">Components</p>
        <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-surface-sunk px-2.5 py-1.5">
          <Search size={13} className="text-ink-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search..."
            className="w-full bg-transparent text-[12.5px] outline-none placeholder:text-ink-300"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <Section title="Agents" icon={Bot} items={filter(agentItems)} onDragStart={onDragStart} onAddNode={onAddNode} />
        <Section title="Tools" icon={Wrench} items={filter(toolItems)} onDragStart={onDragStart} onAddNode={onAddNode} />
        <Section title="Personal Data" icon={Database} items={filter(dataItems)} onDragStart={onDragStart} onAddNode={onAddNode} />
      </div>
      <div className="border-t border-brand-100/60 p-3 text-[10.5px] text-ink-500">
        드래그해서 캔버스에 놓거나, 더블클릭하면 자동으로 추가됩니다.
        <br />
        연결선을 지우려면 선 위의 × 버튼을 클릭하거나, 선을 선택한 뒤 Delete 키를 누르세요.
      </div>
    </div>
  );
}
