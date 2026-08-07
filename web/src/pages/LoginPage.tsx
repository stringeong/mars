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
  async function handleSubmit(event: FormEvent) {
    event.preventDefault(); setError(''); setLoading(true)
    try { if (mode === 'register') await api.post('/auth/register', { username, email, password }); const token = await api.login(username, password); setToken(token.access_token); navigate('/services') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to complete the request.') }
    finally { setLoading(false) }
  }
  return <div className="auth-page">
    <section className="auth-intro"><div className="auth-brand"><span>M</span> M.A.R.S</div><span className="eyebrow">MULTI-AGENT RESOURCE SHARING</span><h1>Private AI automation,<br />orchestrated your way.</h1><p>Connect your own workers and directories, then create distributed AI workflows without losing control of your data.</p><div className="auth-benefits"><div><i>1</i><span><strong>Connect workers</strong><small>Use the computing resources you already have.</small></span></div><div><i>2</i><span><strong>Build workflows</strong><small>Arrange specialized agents in a visual canvas.</small></span></div><div><i>3</i><span><strong>Run privately</strong><small>Keep data access scoped to each worker.</small></span></div></div></section>
    <section className="auth-form-side"><div className="auth-card"><div className="auth-card-heading"><span className="eyebrow">WELCOME TO M.A.R.S</span><h2>{mode === 'login' ? 'Sign in to your workspace' : 'Create your workspace'}</h2><p>{mode === 'login' ? 'Continue building and running your workflows.' : 'Start orchestrating your connected resources.'}</p></div><form onSubmit={handleSubmit}><label>Username</label><input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} autoComplete="username" />{mode === 'register' && <><label>Email address</label><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" /></>}<label>Password</label><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />{error && <div className="error">{error}</div>}<button className="auth-submit" disabled={loading}>{loading ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'} <span>→</span></button></form><div className="auth-switch">{mode === 'login' ? <>New to M.A.R.S? <button type="button" onClick={() => setMode('register')}>Create account</button></> : <>Already have an account? <button type="button" onClick={() => setMode('login')}>Sign in</button></>}</div></div></section>
  </div>
}
