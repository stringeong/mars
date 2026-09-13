import { useState } from 'react';
import { User, Shield, Bell, CreditCard, LogOut, Check } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { useAuth } from '@/context/AuthContext';
import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';

const tabs = [
  { id: 'profile', label: '프로필', icon: User },
  { id: 'security', label: '보안', icon: Shield },
  { id: 'notifications', label: '알림', icon: Bell },
  { id: 'billing', label: '요금제', icon: CreditCard },
] as const;

export default function Settings() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<(typeof tabs)[number]['id']>('profile');

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <>
      <TopBar title="설정" breadcrumb={['M.A.R.S', 'Settings']} />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[220px_1fr]">
          <div className="space-y-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  'flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[13px] font-medium',
                  tab === t.id ? 'bg-brand-600 text-white shadow-soft' : 'text-ink-700 hover:bg-brand-50'
                )}
              >
                <t.icon size={16} /> {t.label}
              </button>
            ))}
            <button
              onClick={handleLogout}
              className="mt-4 flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[13px] font-medium text-rose-600 hover:bg-rose-50"
            >
              <LogOut size={16} /> 로그아웃
            </button>
          </div>

          <Card className="p-6">
            {tab === 'profile' && <ProfileTab />}

            {tab === 'security' && (
              <div className="max-w-md space-y-4">
                <h2 className="text-[14px] font-bold text-ink-900">보안</h2>
                <ToggleRow label="2단계 인증" description="로그인 시 추가 인증 코드를 요구합니다." defaultOn />
                <ToggleRow label="새 기기 로그인 알림" description="새 기기에서 로그인이 감지되면 알려드립니다." defaultOn />
                <ToggleRow label="Agent 클라우드 전송 최소화" description="가능한 경우 로컬 LLM을 우선 사용합니다." defaultOn />
              </div>
            )}

            {tab === 'notifications' && (
              <div className="max-w-md space-y-4">
                <h2 className="text-[14px] font-bold text-ink-900">알림</h2>
                <ToggleRow label="실행 완료 알림" description="워크플로우 실행이 끝나면 알려드립니다." defaultOn />
                <ToggleRow label="실행 실패 알림" description="실행이 실패하면 즉시 알려드립니다." defaultOn />
                <ToggleRow label="주간 리포트" description="매주 사용량 요약을 이메일로 보내드립니다." />
              </div>
            )}

            {tab === 'billing' && (
              <div className="max-w-md space-y-4">
                <h2 className="text-[14px] font-bold text-ink-900">요금제</h2>
                <div className="rounded-xl bg-surface-sunk p-4">
                  <p className="text-[12px] font-semibold text-brand-600">{user?.plan ?? 'Free'} Plan</p>
                  <p className="text-[20px] font-bold text-ink-900">{user?.plan === 'Pro' ? '$12 / month' : '$0 / month'}</p>
                  <p className="mt-1 text-[11.5px] text-ink-500">10 agents · 5GB NAS storage · Unlimited local devices</p>
                </div>
                <p className="text-[11.5px] text-ink-500">
                  이번 달 클라우드 API 사용 비용: <b>$2.14</b>
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function ProfileTab() {
  const { user, updateProfile } = useAuth();
  const [name, setName] = useState(user?.name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [saved, setSaved] = useState(false);

  const isDirty = name !== (user?.name ?? '') || email !== (user?.email ?? '');

  const handleSave = () => {
    updateProfile({ name: name.trim(), email: email.trim() });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="max-w-md space-y-4">
      <h2 className="text-[14px] font-bold text-ink-900">프로필 정보</h2>
      <Field label="이름" value={name} onChange={setName} />
      <Field label="이메일" value={email} onChange={setEmail} type="email" />
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={!isDirty && !saved}
          className="rounded-lg bg-brand-600 px-4 py-2 text-[12.5px] font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          변경사항 저장
        </button>
        {saved && (
          <span className="flex items-center gap-1 text-[12px] font-medium text-emerald-600">
            <Check size={14} /> 저장되었습니다
          </span>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-[12px] font-semibold text-ink-700">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-brand-100 bg-surface-sunk px-3 py-2 text-[13px] outline-none focus:border-brand-400"
      />
    </div>
  );
}

function ToggleRow({ label, description, defaultOn }: { label: string; description: string; defaultOn?: boolean }) {
  const [on, setOn] = useState(!!defaultOn);
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-brand-100/70 px-4 py-3">
      <div>
        <p className="text-[12.5px] font-semibold text-ink-900">{label}</p>
        <p className="text-[11px] text-ink-500">{description}</p>
      </div>
      <button
        onClick={() => setOn((o) => !o)}
        className={clsx('h-6 w-11 shrink-0 rounded-full transition', on ? 'bg-brand-600' : 'bg-ink-900/15')}
      >
        <span className={clsx('block h-5 w-5 translate-y-0.5 rounded-full bg-white shadow transition-transform', on ? 'translate-x-5' : 'translate-x-0.5')} />
      </button>
    </div>
  );
}
