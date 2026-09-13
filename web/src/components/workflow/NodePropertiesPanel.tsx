import { X, Trash2, Plus } from 'lucide-react';
import type { Device, ModelChoice, WorkflowNode } from '@/types';

const modelOptions: ModelChoice[] = [
  'Local LLM (Llama 3.1 8B)',
  'Local LLM (Gemma 2 9B)',
  'Local LLM (Qwen3 8B)',
  'GPT-4o (Cloud)',
  'Claude Sonnet 4.6 (Cloud)',
  'Gemini 1.5 Pro (Cloud)',
];

interface Props {
  node: WorkflowNode;
  devices: Device[];
  onChange: (updated: WorkflowNode) => void;
  onClose: () => void;
  onDelete: () => void;
}

export function NodePropertiesPanel({ node, devices, onChange, onClose, onDelete }: Props) {
  const data = node.data;
  const update = (patch: Partial<typeof data>) => onChange({ ...node, data: { ...data, ...patch } });

  const addVar = (field: 'inputVariables' | 'outputVariables') => {
    const name = window.prompt('변수 이름을 입력하세요');
    if (!name) return;
    update({ [field]: [...(data[field] ?? []), name] } as any);
  };
  const removeVar = (field: 'inputVariables' | 'outputVariables', v: string) => {
    update({ [field]: (data[field] ?? []).filter((x) => x !== v) } as any);
  };

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-brand-100/60 bg-white">
      <div className="flex items-center justify-between border-b border-brand-100/60 px-4 py-3">
        <div>
          <p className="text-[13px] font-bold text-ink-900">{data.label}</p>
          <p className="text-[11px] text-ink-500">Configure node settings</p>
        </div>
        <button onClick={onClose} className="rounded-md p-1 text-ink-500 hover:bg-brand-50">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <div>
          <label className="mb-1 block text-[11px] font-semibold text-ink-700">Node Label</label>
          <input
            value={data.label}
            onChange={(e) => update({ label: e.target.value })}
            className="w-full rounded-lg border border-brand-100 bg-surface-sunk px-2.5 py-2 text-[12.5px] outline-none focus:border-brand-400"
          />
        </div>

        {(data.kind === 'agent' || data.kind === 'tool' || data.kind === 'data') && (
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-ink-700">Assigned Device</label>
            <select
              value={data.device ?? ''}
              onChange={(e) => update({ device: e.target.value })}
              className="w-full rounded-lg border border-brand-100 bg-surface-sunk px-2.5 py-2 text-[12.5px] outline-none focus:border-brand-400"
            >
              <option value="">Select device…</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
              <option value="cloud">Cloud (API)</option>
            </select>
          </div>
        )}

        {data.kind === 'agent' && (
          <>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-ink-700">Model</label>
              <select
                value={data.model ?? ''}
                onChange={(e) => update({ model: e.target.value as ModelChoice })}
                className="w-full rounded-lg border border-brand-100 bg-surface-sunk px-2.5 py-2 text-[12.5px] outline-none focus:border-brand-400"
              >
                {modelOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              {data.device !== 'cloud' && (
                <p className="mt-1 text-[10.5px] text-emerald-600">● Running locally on {devices.find((d) => d.id === data.device)?.name ?? 'device'}</p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-[11px] font-semibold text-ink-700">System Prompt</label>
              <textarea
                value={data.systemPrompt ?? ''}
                onChange={(e) => update({ systemPrompt: e.target.value })}
                rows={5}
                className="w-full resize-none rounded-lg border border-brand-100 bg-surface-sunk px-2.5 py-2 text-[12px] leading-relaxed outline-none focus:border-brand-400"
              />
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className="text-[11px] font-semibold text-ink-700">Temperature</label>
                <span className="text-[11px] font-semibold text-brand-600">{(data.temperature ?? 0.7).toFixed(1)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={data.temperature ?? 0.7}
                onChange={(e) => update({ temperature: Number(e.target.value) })}
                className="w-full accent-brand-600"
              />
              <div className="flex justify-between text-[10px] text-ink-500">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>

            {(['inputVariables', 'outputVariables'] as const).map((field) => (
              <div key={field}>
                <label className="mb-1 block text-[11px] font-semibold text-ink-700">
                  {field === 'inputVariables' ? 'Input Variables' : 'Output Variables'}
                </label>
                <div className="mb-1.5 flex flex-wrap gap-1.5">
                  {(data[field] ?? []).map((v) => (
                    <span
                      key={v}
                      className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-1 text-[11px] font-medium text-brand-700"
                    >
                      {v}
                      <button onClick={() => removeVar(field, v)}>
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                </div>
                <button
                  onClick={() => addVar(field)}
                  className="flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700"
                >
                  <Plus size={12} /> Add variable…
                </button>
              </div>
            ))}
          </>
        )}

        {data.kind === 'tool' && (
          <p className="rounded-lg bg-surface-sunk px-3 py-2 text-[11.5px] text-ink-500">
            이 도구는 할당된 기기에서 실행되며, Agent 노드의 입력 변수로 연결할 수 있습니다.
          </p>
        )}

        {data.kind === 'data' && (
          <p className="rounded-lg bg-surface-sunk px-3 py-2 text-[11.5px] text-ink-500">
            개인 데이터는 선택한 기기에서만 읽어오며 외부로 전송되지 않습니다.
          </p>
        )}
      </div>

      {data.kind !== 'start' && (
        <div className="border-t border-brand-100/60 p-3">
          <button
            onClick={onDelete}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 py-2 text-[12px] font-semibold text-rose-600 hover:bg-rose-100"
          >
            <Trash2 size={13} /> Delete Node
          </button>
        </div>
      )}
    </div>
  );
}
