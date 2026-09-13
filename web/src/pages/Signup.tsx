import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Zap, User, Mail, Lock, Loader2, ArrowRight, CheckCircle2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!name || !email || !password) {
      setError('모든 필드를 입력해주세요.');
      return;
    }
    if (password.length < 4) {
      setError('비밀번호는 4자 이상이어야 합니다.');
      return;
    }
    if (password !== confirmPassword) {
      setError('비밀번호가 일치하지 않습니다.');
      return;
    }
    setLoading(true);
    try {
      await signup(name, email, password);
      // Brand-new accounts land on Devices with an onboarding empty state —
      // no devices, no workflows are pre-connected on their behalf.
      navigate('/devices?welcome=1');
    } catch (err) {
      setError(err instanceof Error ? err.message : '회원가입에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full">
      <div className="relative hidden w-1/2 overflow-hidden bg-gradient-to-br from-brand-600 via-brand-500 to-brand-700 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="flex items-center gap-2 text-white">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15">
            <Zap size={18} strokeWidth={2.5} />
          </div>
          <span className="text-[15px] font-bold">M.A.R.S</span>
        </div>

        <div className="max-w-md text-white">
          <h1 className="text-3xl font-bold leading-tight tracking-tight">
            자연어로 요구사항을 입력하면
            <br />
            M.A.R.S가 워크플로우를 만들어드려요
          </h1>
          <ul className="mt-5 space-y-2.5 text-[13.5px] text-white/85">
            {[
              '자연어 프롬프트 기반 Workflow 자동 생성',
              'Agent별 역할·모델·프롬프트 자동 구성',
              '내 기기와 클라우드 LLM을 함께 쓰는 하이브리드 실행',
            ].map((line) => (
              <li key={line} className="flex items-start gap-2">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-white/80" />
                {line}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-[11px] text-white/60">© 2026 M.A.R.S — Multi-Agent Resource Sharing</p>

        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 left-10 h-56 w-56 rounded-full bg-white/10 blur-3xl" />
      </div>

      <div className="flex w-full items-center justify-center bg-surface px-6 py-10 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white">
              <Zap size={18} strokeWidth={2.5} />
            </div>
            <span className="text-[15px] font-bold text-ink-900">M.A.R.S</span>
          </div>

          <h2 className="text-xl font-bold tracking-tight text-ink-900">계정 만들기</h2>

          <form onSubmit={handleSubmit} className="mt-7 space-y-4">
            <div>
              <label className="mb-1.5 block text-[12.5px] font-semibold text-ink-700">이름</label>
              <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-white px-3 py-2.5 focus-within:border-brand-400">
                <User size={15} className="text-ink-300" />
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full text-[13.5px] outline-none"
                  placeholder="홍길동"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-[12.5px] font-semibold text-ink-700">이메일</label>
              <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-white px-3 py-2.5 focus-within:border-brand-400">
                <Mail size={15} className="text-ink-300" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full text-[13.5px] outline-none"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-[12.5px] font-semibold text-ink-700">비밀번호</label>
              <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-white px-3 py-2.5 focus-within:border-brand-400">
                <Lock size={15} className="text-ink-300" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full text-[13.5px] outline-none"
                  placeholder="••••••••"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-[12.5px] font-semibold text-ink-700">비밀번호 확인</label>
              <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-white px-3 py-2.5 focus-within:border-brand-400">
                <Lock size={15} className="text-ink-300" />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full text-[13.5px] outline-none"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {error && <p className="text-[12.5px] font-medium text-rose-600">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 py-2.5 text-[13.5px] font-semibold text-white shadow-soft transition hover:bg-brand-700 disabled:opacity-60"
            >
              {loading ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
              {loading ? '계정 생성 중…' : '회원가입'}
            </button>
          </form>

          <p className="mt-6 text-center text-[12.5px] text-ink-500">
            이미 계정이 있으신가요?{' '}
            <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
              로그인
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
