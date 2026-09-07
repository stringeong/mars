import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  X,
  Calendar,
  Mail,
  Users,
  StickyNote,
  Play,
  Cpu,
  Cloud as CloudIcon,
  Clock,
  DollarSign,
} from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { useData } from '@/context/DataContext';

interface UploadedFile {
  id: string;
  name: string;
  sizeLabel: string;
}

const dataSourceOptions = [
  { id: 'calendar', label: 'Calendar Data', icon: Calendar, connected: true },
  { id: 'email', label: 'Email Data', icon: Mail, connected: true },
  { id: 'contacts', label: 'Contacts', icon: Users, connected: false },
  { id: 'notes', label: 'Notes', icon: StickyNote, connected: false },
];

export default function WorkflowExecuteInput() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { getWorkflow, devices, runExecution } = useData();
  const workflow = id ? getWorkflow(id) : undefined;

  const [taskDescription, setTaskDescription] = useState(workflow?.description ?? '');
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>(['calendar', 'email']);
  const [executing, setExecuting] = useState(false);

  if (!workflow) {
    return <div className="flex flex-1 items-center justify-center text-ink-500">워크플로우를 찾을 수 없습니다.</div>;
  }

  const toggleSource = (id: string) =>
    setSelectedSources((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));

  const handleFileInput = (fileList: FileList | null) => {
    if (!fileList) return;
    const next = Array.from(fileList).map((f) => ({
      id: `${f.name}-${f.size}`,
      name: f.name,
      sizeLabel: `${(f.size / 1024).toFixed(0)} KB`,
    }));
    setFiles((prev) => [...prev, ...next]);
  };

  const agentCount = workflow.nodes.filter((n) => n.data.kind === 'agent').length;
  const cloudNodeCount = workflow.nodes.filter((n) => n.data.device === 'cloud').length;
  const localNodeCount = workflow.nodes.length - cloudNodeCount;
  const estCost = (0.01 + agentCount * 0.015).toFixed(2);
  const estTime = 12 + agentCount * 8;

  const handleExecute = async () => {
    setExecuting(true);
    await new Promise((r) => setTimeout(r, 1400));
    const execution = runExecution(workflow.id, taskDescription || workflow.description);
    setExecuting(false);
    navigate(`/executions/${execution.id}`);
  };

  return (
    <>
      <TopBar title="Workflow Inputs" breadcrumb={['M.A.R.S', 'Marketplace', workflow.name]} />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_320px]">
          <Card className="space-y-6 p-6">
            <div>
              <p className="mb-1.5 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-ink-500">
                Task Description <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[9.5px] text-rose-500">Required</span>
              </p>
              <textarea
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                maxLength={1000}
                rows={4}
                className="w-full resize-none rounded-xl border border-brand-100 bg-surface-sunk px-3.5 py-3 text-[13px] leading-relaxed outline-none focus:border-brand-400"
              />
              <p className="mt-1 text-right text-[11px] text-ink-300">{taskDescription.length} / 1000 characters</p>
            </div>

            <div>
              <p className="mb-1.5 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-ink-500">
                File Upload <span className="text-ink-300 normal-case">{files.length} files</span>
              </p>
              <label className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-brand-200 bg-brand-50/30 py-6 text-center hover:border-brand-400">
                <UploadCloud size={20} className="text-brand-500" />
                <span className="text-[12.5px] font-semibold text-ink-700">Drop files here or Browse</span>
                <span className="text-[11px] text-ink-400">PDF, DOCX, TXT, PPTX</span>
                <input type="file" multiple className="hidden" onChange={(e) => handleFileInput(e.target.files)} />
              </label>

              {files.length > 0 && (
                <div className="mt-3 space-y-2">
                  {files.map((f) => (
                    <div key={f.id} className="flex items-center justify-between rounded-lg border border-brand-100 bg-white px-3 py-2">
                      <span className="flex items-center gap-2 text-[12.5px] text-ink-700">
                        <FileText size={14} className="text-brand-500" /> {f.name}
                        <span className="text-[11px] text-ink-300">{f.sizeLabel}</span>
                      </span>
                      <button onClick={() => setFiles((prev) => prev.filter((x) => x.id !== f.id))} className="text-ink-300 hover:text-rose-500">
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <p className="mb-1.5 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide text-ink-500">
                Personal Data Sources <span className="text-ink-300 normal-case">{selectedSources.length} selected</span>
              </p>
              <div className="grid grid-cols-2 gap-2.5">
                {dataSourceOptions.map((opt) => {
                  const Icon = opt.icon;
                  const selected = selectedSources.includes(opt.id);
                  return (
                    <button
                      key={opt.id}
                      disabled={!opt.connected}
                      onClick={() => toggleSource(opt.id)}
                      className={`flex flex-col items-start gap-1 rounded-xl border px-3 py-2.5 text-left transition ${
                        selected ? 'border-brand-400 bg-brand-50' : 'border-brand-100 bg-white'
                      } ${!opt.connected && 'cursor-not-allowed opacity-50'}`}
                    >
                      <Icon size={15} className={selected ? 'text-brand-600' : 'text-ink-500'} />
                      <span className="text-[12.5px] font-semibold text-ink-900">{opt.label}</span>
                      <span className={`text-[10.5px] font-medium ${opt.connected ? 'text-emerald-600' : 'text-ink-300'}`}>
                        {opt.connected ? 'Connected' : 'Not linked'}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </Card>

          <div className="space-y-4">
            <Card className="p-4">
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-ink-500">Workflow Overview</p>
              <div className="space-y-1.5">
                {workflow.nodes.map((n) => (
                  <div key={n.id} className="flex items-center justify-between rounded-lg bg-surface-sunk px-2.5 py-1.5 text-[11.5px]">
                    <span className="font-medium text-ink-700">{n.data.label}</span>
                    <span className="text-[10px] text-ink-400">{n.data.device === 'cloud' ? 'Cloud' : devices.find((d) => d.id === n.data.device)?.name ?? '—'}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4">
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-ink-500">Estimated Execution</p>
              <div className="grid grid-cols-2 gap-3 text-[12px]">
                <Metric icon={Cpu} label="Local Nodes" value={String(localNodeCount)} />
                <Metric icon={CloudIcon} label="Cloud Nodes" value={String(cloudNodeCount)} />
                <Metric icon={Clock} label="Est. Time" value={`${estTime} sec`} />
                <Metric icon={DollarSign} label="Est. Cost" value={`$${estCost}`} />
              </div>
            </Card>

            <button
              onClick={handleExecute}
              disabled={!taskDescription.trim() || executing}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 py-3 text-[13.5px] font-bold text-white shadow-soft transition hover:bg-brand-700 disabled:opacity-50"
            >
              <Play size={16} /> {executing ? 'Executing…' : 'Execute Workflow'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof Cpu; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-sunk px-2.5 py-2">
      <span className="mb-1 flex items-center gap-1 text-[10.5px] text-ink-500">
        <Icon size={11} /> {label}
      </span>
      <p className="font-bold text-ink-900">{value}</p>
    </div>
  );
}
