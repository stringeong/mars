import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Monitor, Laptop, Smartphone, HardDrive, X, FolderPlus, ShieldCheck, Sparkles, Trash2, Info, Loader2 } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { Card } from '@/components/common/Card';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useData } from '@/context/DataContext';
import { computeSecurityScore, SECURITY_SCORE_EXPLANATION } from '@/lib/security';
import clsx from 'clsx';

const deviceIcon = {
  'Desktop PC': Monitor,
  'Windows Laptop': Laptop,
  'Android Phone': Smartphone,
  'NAS Server': HardDrive,
  iPhone: Smartphone,
};

const scopeLabel = {
  'local-only': 'Local Agents Only',
  'selected-workflows': 'Selected Workflows Only',
  'all-workflows': 'All Workflows',
};

export default function Devices() {
  const { devices, devicesLoading, removeDevice } = useData();
  const [showRegister, setShowRegister] = useState(false);
  const [removingId, setRemovingId] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const isWelcome = searchParams.get('welcome') === '1';

  const dismissWelcome = () => {
    searchParams.delete('welcome');
    setSearchParams(searchParams, { replace: true });
  };

  const handleRemove = async (id) => {
    setRemovingId(id);
    try {
      await removeDevice(id);
    } catch {
      alert('기기 연결 해제에 실패했습니다.');
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <>
      <TopBar
        title="기기 관리"
        breadcrumb={['M.A.R.S', 'Devices']}
        actions={
          devices.length > 0 ? (
            <button
              onClick={() => setShowRegister(true)}
              className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-2 text-[12.5px] font-semibold text-white shadow-soft hover:bg-brand-700"
            >
              <Plus size={15} /> Register Device
            </button>
          ) : undefined
        }
      />

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {isWelcome && (
          <div className="mb-5 flex items-start gap-3 rounded-xl2 border border-brand-200 bg-brand-50 p-4">
            <Sparkles size={18} className="mt-0.5 shrink-0 text-brand-600" />
            <div className="flex-1">
              <p className="text-[13px] font-bold text-ink-900">M.A.R.S에 오신 것을 환영해요!</p>
              <p className="mt-0.5 text-[12px] leading-relaxed text-ink-600">
                아직 연결된 기기가 없어요. 워크플로우가 로컬 파일·캘린더 등을 활용하려면 먼저 기기를 등록해야 합니다.
              </p>
            </div>
            <button onClick={dismissWelcome} className="rounded-md p-1 text-brand-600 hover:bg-brand-100">
              <X size={15} />
            </button>
          </div>
        )}

        {devicesLoading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-500">
            <Loader2 size={16} className="animate-spin" /> 기기 목록을 불러오는 중…
          </div>
        ) : devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl2 border-2 border-dashed border-brand-200 bg-brand-50/30 py-16 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-brand-600 shadow-soft">
              <Monitor size={26} />
            </div>
            <p className="text-[15px] font-bold text-ink-900">연결된 기기가 없습니다</p>
            <p className="mt-1.5 max-w-sm text-[12.5px] leading-relaxed text-ink-500">
              내 PC, 노트북, NAS 등을 등록하면 워크플로우가 해당 기기의 파일과 리소스를 안전하게 활용할 수 있어요.
            </p>
            <button
              onClick={() => setShowRegister(true)}
              className="mt-5 flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2.5 text-[12.5px] font-semibold text-white shadow-soft hover:bg-brand-700"
            >
              <Plus size={15} /> 기기 등록하기
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {devices.map((d) => {
              const Icon = deviceIcon[d.type] ?? Monitor;
              return (
                <Card key={d.id} className="group relative p-5">
                  <button
                    onClick={() => handleRemove(d.id)}
                    disabled={removingId === d.id}
                    title="기기 연결 해제"
                    className="absolute right-3 top-3 rounded-md p-1 text-ink-300 opacity-0 hover:bg-rose-50 hover:text-rose-500 group-hover:opacity-100 disabled:opacity-100"
                  >
                    {removingId === d.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  </button>
                  <div className="mb-3 flex items-start justify-between pr-6">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                        <Icon size={18} />
                      </div>
                      <div>
                        <p className="text-[13.5px] font-bold text-ink-900">{d.name}</p>
                        <p className="text-[11px] text-ink-500">{d.type}</p>
                      </div>
                    </div>
                    <StatusBadge status={d.status} />
                  </div>

                  <div className="mb-3 grid grid-cols-2 gap-2 text-[11px]">
                    <ResourceGauge label="CPU" value={d.resources.cpu} />
                    <ResourceGauge label="RAM" value={d.resources.ram} />
                  </div>

                  <div className="space-y-1 text-[11.5px] text-ink-500">
                    {d.cpuModel && <p>{d.cpuModel}</p>}
                    {(d.ramGb || d.storage) && (
                      <p>
                        {d.ramGb ? `${d.ramGb} GB RAM` : ''}
                        {d.ramGb && d.storage ? ' · ' : ''}
                        {d.storage}
                      </p>
                    )}
                    {d.gpu && <p>{d.gpu}</p>}
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {d.folders.map((f) => (
                      <span key={f} className="rounded-full bg-surface-sunk px-2 py-0.5 text-[10.5px] font-medium text-ink-600">
                        {f}
                      </span>
                    ))}
                  </div>

                  <div className="mt-3 flex items-center justify-between border-t border-brand-100/60 pt-3 text-[10.5px]">
                    <span className="flex items-center gap-1 text-ink-500" title={SECURITY_SCORE_EXPLANATION}>
                      <ShieldCheck
                        size={12}
                        className={
                          d.securityScore === 'High'
                            ? 'text-emerald-500'
                            : d.securityScore === 'Medium'
                              ? 'text-amber-500'
                              : 'text-rose-500'
                        }
                      />
                      Security: {d.securityScore}
                      <Info size={10} className="text-ink-300" />
                    </span>
                    <span className="text-ink-400">{scopeLabel[d.agentAccessScope]}</span>
                  </div>

                  {d.runningAgent && (
                    <div className="mt-3 rounded-lg bg-brand-50 px-2.5 py-1.5 text-[10.5px] font-medium text-brand-700">
                      ▶ Running: {d.runningAgent}
                    </div>
                  )}
                </Card>
              );
            })}

            <button
              onClick={() => setShowRegister(true)}
              className="flex min-h-[180px] flex-col items-center justify-center gap-2 rounded-xl2 border-2 border-dashed border-brand-200 bg-brand-50/40 text-brand-600 transition hover:border-brand-400 hover:bg-brand-50"
            >
              <Plus size={20} />
              <span className="text-[12.5px] font-semibold">새 기기 등록</span>
            </button>
          </div>
        )}
      </div>

      {showRegister && <RegisterDeviceDrawer onClose={() => setShowRegister(false)} />}
    </>
  );
}

function ResourceGauge({ label, value }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-ink-500">
        <span>{label}</span>
        <span className="font-semibold text-ink-700">{value}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunk">
        <div
          className={clsx('h-full rounded-full', value > 75 ? 'bg-rose-400' : value > 50 ? 'bg-amber-400' : 'bg-brand-500')}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

const deviceTypeOptions = ['Windows Laptop', 'Desktop PC', 'Android Phone', 'NAS Server', 'iPhone'];

function RegisterDeviceDrawer({ onClose }) {
  const { registerDevice } = useData();
  const [name, setName] = useState('My Device');
  const [type, setType] = useState('Windows Laptop');
  const [access, setAccess] = useState('read-only');
  const [scope, setScope] = useState('selected-workflows');
  const [folders, setFolders] = useState(['Documents']);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const allFolders = ['Documents', 'Desktop', 'Research Papers', 'Personal Photos'];

  const toggleFolder = (f) => setFolders((prev) => (prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f]));

  const handleRegister = async () => {
    setError('');
    setSubmitting(true);
    const newDevice = {
      id: '',
      name: name.trim() || '새 기기',
      type,
      status: 'online',
      cpuModel: type === 'NAS Server' ? 'ARM Cortex-A76' : undefined,
      ramGb: undefined,
      storage: undefined,
      network: undefined,
      resources: { cpu: 0, ram: 0 },
      folders,
      fileAccessMode: access,
      agentAccessScope: scope,
      securityScore: computeSecurityScore(access, scope),
      registeredAt: new Date().toISOString().slice(0, 10),
    };
    try {
      await registerDevice(newDevice);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '기기 등록에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-ink-900/30" onClick={onClose}>
      <div className="h-full w-full max-w-md overflow-y-auto bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-brand-100/60 px-5 py-4">
          <div>
            <p className="text-[14px] font-bold text-ink-900">Register Device</p>
            <p className="text-[11px] text-ink-500">새 기기를 M.A.R.S에 연결하고 접근 권한을 설정합니다.</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-ink-500 hover:bg-brand-50">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-6 px-5 py-5">
          <div>
            <label className="mb-1 block text-[12px] font-semibold text-ink-700">Device Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-brand-100 bg-surface-sunk px-3 py-2 text-[13px] outline-none focus:border-brand-400"
              placeholder="예: My Laptop"
            />
          </div>

          <div>
            <label className="mb-1 block text-[12px] font-semibold text-ink-700">Device Type</label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full rounded-lg border border-brand-100 bg-surface-sunk px-3 py-2 text-[13px] outline-none focus:border-brand-400"
            >
              {deviceTypeOptions.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div>
            <p className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-ink-700">
              <FolderPlus size={13} /> Folder Access
            </p>
            <div className="grid grid-cols-2 gap-2">
              {allFolders.map((f) => (
                <label key={f} className="flex items-center gap-2 rounded-lg border border-brand-100 px-3 py-2 text-[12px]">
                  <input type="checkbox" checked={folders.includes(f)} onChange={() => toggleFolder(f)} className="accent-brand-600" />
                  {f}
                </label>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[12px] font-semibold text-ink-700">File Access Mode</p>
            <div className="grid grid-cols-2 gap-2">
              {['read-only', 'read-write'].map((mode) => (
                <button
                  key={mode}
                  onClick={() => setAccess(mode)}
                  className={clsx(
                    'rounded-lg border px-3 py-2 text-[12px] font-semibold',
                    access === mode ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-brand-100 text-ink-600'
                  )}
                >
                  {mode === 'read-only' ? 'Read Only' : 'Read + Write'}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[12px] font-semibold text-ink-700">Agent Access Scope</p>
            <div className="space-y-2">
              {['local-only', 'selected-workflows', 'all-workflows'].map((s) => (
                <label
                  key={s}
                  className={clsx(
                    'flex items-center gap-2 rounded-lg border px-3 py-2 text-[12px]',
                    scope === s ? 'border-brand-500 bg-brand-50' : 'border-brand-100'
                  )}
                >
                  <input type="radio" checked={scope === s} onChange={() => setScope(s)} className="accent-brand-600" />
                  {scopeLabel[s]}
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-xl bg-surface-sunk p-4 text-[11.5px] text-ink-600">
            <p className="mb-1 font-semibold text-ink-700">Registration Summary</p>
            <p>Device: {name || '—'} ({type})</p>
            <p>Selected folders: {folders.length}</p>
            <p>Access mode: {access}</p>
            <p>Security score: {computeSecurityScore(access, scope)}</p>
          </div>

          {error && <p className="text-[12.5px] font-medium text-rose-600">{error}</p>}

          <button
            onClick={handleRegister}
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 py-2.5 text-[12.5px] font-bold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            {submitting ? 'Registering…' : 'Register Device'}
          </button>
        </div>
      </div>
    </div>
  );
}
