import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Search, ClipboardList, Calendar, Target, Brain, Plane, Loader2, Cpu, Cloud } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { useData } from '@/context/DataContext';
import { promptTemplates, cloudModels } from '@/data/mockData';

const templateIcon: Record<string, typeof Search> = {
  search: Search,
  clipboard: ClipboardList,
  calendar: Calendar,
  target: Target,
  brain: Brain,
  plane: Plane,
};

const templatePrompts: Record<string, string> = {
  t1: '최근 AI 연구 논문을 검색하고, NAS에 저장된 제안서 문서를 검토해서 리서치 리포트를 작성해줘.',
  t2: '내 업무 목록과 캘린더 일정을 분석해서 이번 주 프로젝트 계획을 세워줘.',
  t3: '오늘 캘린더를 확인하고 회의 안건과 관련 문서를 요약해줘.',
  t4: '내 이력서와 캘린더, 이메일을 분석해서 커리어 로드맵과 채용 기회를 찾아줘.',
  t5: '최근 노트를 정리하고 개념들을 연결해서 인사이트를 도출해줘.',
  t6: '9월 제주도 3박4일 여행 일정을 조사하고 항공편을 찾아서 일정표를 만들어줘.',
};

export default function WorkflowCreate() {
  const navigate = useNavigate();
  const { devices, createWorkflowFromPrompt } = useData();
  const [description, setDescription] = useState('');
  const [selectedDevices, setSelectedDevices] = useState<string[]>(devices.map((d) => d.id));
  const [generating, setGenerating] = useState(false);

  const charCount = description.length;
  const onlineDevices = useMemo(() => devices.filter((d) => d.status !== 'offline'), [devices]);

  const toggleDevice = (id: string) => {
    setSelectedDevices((prev) => (prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id]));
  };

  const handleGenerate = async () => {
    if (!description.trim()) return;
    setGenerating(true);
    await new Promise((r) => setTimeout(r, 900));
    const wf = createWorkflowFromPrompt(description.trim(), selectedDevices);
    setGenerating(false);
    navigate(`/workflows/${wf.id}`);
  };

  return (
    <>
      <TopBar title="새 워크플로우 만들기" breadcrumb={['M.A.R.S', 'New Workflow']} />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_300px]">
          <Card className="p-6">
            <div className="mb-1 flex items-center gap-2">
              <Sparkles size={16} className="text-brand-600" />
              <h2 className="text-[15px] font-bold text-ink-900">Create Multi-Agent Workflow</h2>
            </div>
            <p className="mb-5 text-[12.5px] text-ink-500">
              작업을 설명하면 M.A.R.S가 필요한 Agent와 작업 순서를 자동으로 구성합니다.
            </p>

            <label className="mb-1.5 block text-[12px] font-semibold uppercase tracking-wide text-ink-500">
              Workflow Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={1000}
              rows={5}
              placeholder="예: 내 캘린더와 이메일을 분석하고, 최신 AI 연구 논문을 검색하고, NAS에 저장된 제안서 문서를 검토해서 프로젝트 계획을 만들어줘."
              className="w-full resize-none rounded-xl border border-brand-100 bg-surface-sunk px-3.5 py-3 text-[13px] leading-relaxed outline-none focus:border-brand-400"
            />
            <p className="mt-1 text-right text-[11px] text-ink-300">{charCount} / 1000 characters</p>

            <p className="mb-2 mt-5 text-[12px] font-semibold uppercase tracking-wide text-ink-500">
              Suggested Templates
            </p>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {promptTemplates.map((t) => {
                const Icon = templateIcon[t.icon] ?? Sparkles;
                return (
                  <button
                    key={t.id}
                    onClick={() => setDescription(templatePrompts[t.id])}
                    className="flex flex-col items-start gap-1.5 rounded-xl border border-brand-100 bg-white p-3 text-left transition hover:border-brand-300 hover:bg-brand-50/60"
                  >
                    <Icon size={16} className="text-brand-600" />
                    <span className="text-[12.5px] font-semibold text-ink-900">{t.title}</span>
                    <span className="text-[11px] leading-snug text-ink-500">{t.description}</span>
                  </button>
                );
              })}
            </div>

            <button
              onClick={handleGenerate}
              disabled={!description.trim() || generating}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 py-3 text-[13.5px] font-bold text-white shadow-soft transition hover:from-brand-700 hover:to-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> Generating Workflow…
                </>
              ) : (
                <>
                  <Sparkles size={16} /> Generate Workflow
                </>
              )}
            </button>
          </Card>

          <div className="space-y-4">
            <Card className="p-4">
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-ink-500">Available Devices</p>
              <div className="space-y-2.5">
                {onlineDevices.map((d) => (
                  <label key={d.id} className="flex cursor-pointer items-center justify-between text-[12.5px]">
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selectedDevices.includes(d.id)}
                        onChange={() => toggleDevice(d.id)}
                        className="accent-brand-600"
                      />
                      <Cpu size={13} className="text-ink-500" /> {d.name}
                    </span>
                    <span className="text-[10.5px] font-medium text-emerald-600">{d.status}</span>
                  </label>
                ))}
              </div>
            </Card>

            <Card className="p-4">
              <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-ink-500">Available Models</p>
              <div className="space-y-2.5">
                {cloudModels.map((m) => (
                  <div key={m.id} className="flex items-center justify-between text-[12.5px]">
                    <span className="flex items-center gap-2">
                      <Cloud size={13} className="text-ink-500" /> {m.name}
                    </span>
                    <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold text-brand-600">
                      CLOUD
                    </span>
                  </div>
                ))}
                <div className="flex items-center justify-between text-[12.5px]">
                  <span className="flex items-center gap-2">
                    <Cpu size={13} className="text-ink-500" /> Local LLM
                  </span>
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
                    LOCAL
                  </span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
