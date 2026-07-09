import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        await api.post('/auth/register', { username, email, password })
      }
      const token = await api.login(username, password)
      setToken(token.access_token)
      navigate('/services')
    } catch (err) {
      setError(err instanceof Error ? err.message : '요청에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="logo">M.A.R.S</div>
        <div className="tagline">MAS And Resource Sharing — 내 기기로 돌리는 AI 워크플로우</div>
        <form onSubmit={handleSubmit}>
          <label>아이디</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} />
          {mode === 'register' && (
            <>
              <label>이메일</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </>
          )}
          <label>비밀번호</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
          {error && <div className="error">{error}</div>}
          <button className="btn" disabled={loading}>
            {loading ? '처리 중...' : mode === 'login' ? '로그인' : '회원가입'}
          </button>
        </form>
        <div className="auth-switch">
          {mode === 'login' ? (
            <>계정이 없나요? <a onClick={() => setMode('register')}>회원가입</a></>
          ) : (
            <>이미 계정이 있나요? <a onClick={() => setMode('login')}>로그인</a></>
          )}
        </div>
      </div>
    </div>
  )
}
