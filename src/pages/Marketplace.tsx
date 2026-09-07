import { useNavigate } from 'react-router-dom';
import { Search, Star, Download } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { promptTemplates } from '@/data/mockData';
import { useData } from '@/context/DataContext';

const authors = ['M.A.R.S Team', '김현정', '강민채', 'Community'];

export default function Marketplace() {
  const navigate = useNavigate();
  const { createWorkflowFromPrompt, devices } = useData();

  const handleUse = (title: string, description: string) => {
    const wf = createWorkflowFromPrompt(`${title}: ${description}`, devices.map((d) => d.id));
    navigate(`/workflows/${wf.id}`);
  };

  return (
    <>
      <TopBar title="마켓플레이스" breadcrumb={['M.A.R.S', 'Marketplace']} />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-5 flex items-center gap-2 rounded-lg border border-brand-100 bg-white px-3 py-2 sm:w-96">
          <Search size={14} className="text-ink-500" />
          <input placeholder="템플릿 검색" className="w-full bg-transparent text-[12.5px] outline-none placeholder:text-ink-300" />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {promptTemplates.map((t, i) => (
            <Card key={t.id} className="flex flex-col p-5">
              <div className="mb-3 flex items-center justify-between">
                <span className="rounded-full bg-brand-50 px-2.5 py-1 text-[10.5px] font-semibold text-brand-600">
                  Template
                </span>
                <span className="flex items-center gap-1 text-[11px] font-medium text-amber-500">
                  <Star size={12} fill="currentColor" /> {(4.3 + (i % 3) * 0.2).toFixed(1)}
                </span>
              </div>
              <h3 className="text-[14px] font-bold text-ink-900">{t.title}</h3>
              <p className="mt-1 flex-1 text-[12px] leading-relaxed text-ink-500">{t.description}</p>
              <p className="mt-3 text-[11px] text-ink-300">by {authors[i % authors.length]}</p>
              <button
                onClick={() => handleUse(t.title, t.description)}
                className="mt-3 flex items-center justify-center gap-1.5 rounded-lg border border-brand-100 py-2 text-[12px] font-semibold text-brand-600 hover:bg-brand-50"
              >
                <Download size={13} /> Use Template
              </button>
            </Card>
          ))}
        </div>
      </div>
    </>
  );
}
