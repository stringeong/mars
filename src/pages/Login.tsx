import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Zap, Mail, Lock, Loader2, ArrowRight } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password) {
      setError('이메일과 비밀번호를 입력해주세요.');
      return;
    }
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full">
      {/* Left: brand panel */}
      <div className="relative hidden w-1/2 overflow-hidden bg-gradient-to-br from-brand-600 via-brand-500 to-brand-700 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="flex items-center gap-2 text-white">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15">
            <Zap size={18} strokeWidth={2.5} />
          </div>
          <span className="text-[15px] font-bold">M.A.R.S</span>
        </div>

        <div className="max-w-md text-white">
          <h1 className="text-3xl font-bold leading-tight tracking-tight">
            내 기기와 클라우드를 잇는
            <br />
            나만의 Multi-Agent 워크플로우
          </h1>
          <p className="mt-4 text-[14px] leading-relaxed text-white/80">
            자연어로 요구사항을 입력하면 M.A.R.S가 필요한 Agent를 구성하고, 로컬 기기와 클라우드 LLM을 하이브리드로
            연결해 실행합니다.
          </p>
        </div>

        <p className="text-[11px] text-white/60">© 2026 M.A.R.S — Multi-Agent Resource Sharing</p>

        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-16 left-10 h-56 w-56 rounded-full bg-white/10 blur-3xl" />
      </div>

      {/* Right: form */}
      <div className="flex w-full items-center justify-center bg-surface px-6 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white">
              <Zap size={18} strokeWidth={2.5} />
            </div>
            <span className="text-[15px] font-bold text-ink-900">M.A.R.S</span>
          </div>

          <h2 className="text-xl font-bold tracking-tight text-ink-900">다시 오신 것을 환영해요</h2>
          <p className="mt-1 text-[13px] text-ink-500">계정에 로그인하고 워크플로우를 이어서 실행하세요.</p>

          <form onSubmit={handleSubmit} className="mt-7 space-y-4">
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
                  autoComplete="email"
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
                  autoComplete="current-password"
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
              {loading ? '로그인 중…' : '로그인'}
            </button>
          </form>

          <p className="mt-6 text-center text-[12.5px] text-ink-500">
            계정이 없으신가요?{' '}
            <Link to="/signup" className="font-semibold text-brand-600 hover:text-brand-700">
              회원가입
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
