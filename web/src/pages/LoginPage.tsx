import { FormEvent, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, setToken } from '../api'

export default function LoginPage() {
  const [searchParams] = useSearchParams()
  // 제품 소개·다운로드 페이지의 '회원가입'은 회원가입 화면으로 바로 연다
  const [mode, setMode] = useState<'login' | 'register'>(searchParams.get('mode') === 'register' ? 'register' : 'login')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  async function handleSubmit(event: FormEvent) {
    event.preventDefault(); setError(''); setLoading(true)
    try { if (mode === 'register') await api.post('/auth/register', { username, email, password }); const token = await api.login(username, password); setToken(token.access_token); navigate('/services') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '요청을 처리하지 못했어요.') }
    finally { setLoading(false) }
  }
  return <div className="auth-page">
    <section className="auth-intro"><div className="auth-brand"><span>M</span> M.A.R.S</div><span className="eyebrow">멀티 에이전트 AI 워크플로우</span><h1>내 컴퓨터들이<br />함께 일하는 AI 팀</h1><p>하고 싶은 일을 문장으로 적으면 역할별 AI 에이전트가 생성되고,<br />내 PC·노트북이 나눠서 실행해요.<br />등록한 폴더의 원본 파일은 그 PC에서만 읽어요.</p><div className="auth-public-links"><Link to="/about">제품 소개 보기 →</Link><Link to="/download">워커 다운로드 →</Link></div><div className="auth-benefits"><div><i>1</i><span><strong>워커 연결</strong><small>이미 가진 컴퓨터를 그대로 활용해요.</small></span></div><div><i>2</i><span><strong>워크플로우 만들기</strong><small>역할별 에이전트를 화면에서 배치해요.</small></span></div><div><i>3</i><span><strong>안전하게 실행</strong><small>워커마다 접근할 수 있는 폴더를 정해요.</small></span></div></div></section>
    <section className="auth-form-side"><div className="auth-card"><div className="auth-card-heading"><span className="eyebrow">M.A.R.S</span><h2>{mode === 'login' ? '로그인' : '회원가입'}</h2><p>{mode === 'login' ? '이어서 워크플로우를 만들고 실행해 보세요.' : '내 기기를 연결하고 첫 워크플로우를 만들어 보세요.'}</p></div><form onSubmit={handleSubmit}><label>아이디</label><input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} autoComplete="username" />{mode === 'register' && <><label>이메일</label><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></>}<label>비밀번호</label><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />{error && <div className="error">{error}</div>}<button className="auth-submit" disabled={loading}>{loading ? '잠시만요…' : mode === 'login' ? '로그인' : '회원가입'} <span>→</span></button></form><div className="auth-switch">{mode === 'login' ? <>처음이신가요? <button type="button" onClick={() => setMode('register')}>회원가입</button></> : <>이미 계정이 있나요? <button type="button" onClick={() => setMode('login')}>로그인</button></>}</div><div className="auth-worker-hint">작업을 실행할 기기가 필요해요. <Link to="/download">워커 다운로드</Link></div></div></section>
  </div>
}
