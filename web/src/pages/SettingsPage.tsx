import { FormEvent, useEffect, useState } from 'react'
import { api } from '../api'

type Provider = 'openai' | 'anthropic' | 'gemini'
type ProviderConfig = { provider: Provider; configured: boolean; masked_key: string; has_admin_key: boolean; default_model: string; monthly_budget_usd: number | null; status: string; last_verified_at: string | null }
type Usage = { provider: string; input_tokens: number; output_tokens: number; cached_tokens: number; requests: number }

const names: Record<Provider, string> = { openai: 'OpenAI (GPT)', anthropic: 'Anthropic (Claude)', gemini: 'Google (Gemini)' }
const providerModels: Record<Provider, string[]> = {
  openai: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini', 'gpt-4.1'],
  anthropic: ['claude-sonnet-4-5', 'claude-opus-4-1', 'claude-haiku-3-5'],
  gemini: ['gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-pro'],
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [usage, setUsage] = useState<Usage[]>([])
  const [message, setMessage] = useState('')
  const load = () => Promise.all([api.get<ProviderConfig[]>('/settings/llm-providers'), api.get<Usage[]>('/settings/llm-usage')]).then(([p, u]) => { setProviders(p); setUsage(u) })
  useEffect(() => { load().catch((e) => setMessage(e.message)) }, [])
  return <div className="settings-page">
    <header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> Settings</div><h1>Settings</h1><p>외부 LLM 연결과 M.A.R.S에서 발생한 사용량을 관리합니다.</p></div></header>
    {message && <div className="settings-message">{message}</div>}
    <div className="settings-layout">
      <aside className="settings-tabs"><button className="active">AI Providers</button><button disabled>Profile</button><button disabled>Security</button><button disabled>Notifications</button></aside>
      <div className="settings-content">
        <section className="card"><h2>Cloud AI connections</h2><p className="muted">API 키는 서버에서 암호화되며 Worker로 전달되지 않습니다.</p><div className="provider-grid">{providers.map((provider) => <ProviderCard key={provider.provider} value={provider} onChanged={load} onMessage={setMessage} />)}</div></section>
        <section className="card"><div className="row spread"><div><h2>최근 30일 사용량</h2><p className="muted">M.A.R.S를 통해 실행된 요청만 집계됩니다.</p></div></div><div className="usage-grid">{providers.map((provider) => { const item = usage.find((u) => u.provider === provider.provider); return <div className="usage-card" key={provider.provider}><span>{names[provider.provider]}</span><strong>{((item?.input_tokens || 0) + (item?.output_tokens || 0)).toLocaleString()}</strong><small>tokens · {item?.requests || 0} requests</small><div><em>Input {(item?.input_tokens || 0).toLocaleString()}</em><em>Output {(item?.output_tokens || 0).toLocaleString()}</em></div></div> })}</div></section>
      </div>
    </div>
  </div>
}

function ProviderCard({ value, onChanged, onMessage }: { value: ProviderConfig; onChanged: () => Promise<void>; onMessage: (v: string) => void }) {
  const [apiKey, setApiKey] = useState('')
  const [adminKey, setAdminKey] = useState('')
  const [model, setModel] = useState(value.default_model)
  const [budget, setBudget] = useState(value.monthly_budget_usd?.toString() || '')
  const [busy, setBusy] = useState(false)
  async function save(event: FormEvent) { event.preventDefault(); setBusy(true); try { await api.put(`/settings/llm-providers/${value.provider}`, { api_key: apiKey || null, admin_key: adminKey || null, default_model: model, monthly_budget_usd: budget ? Number(budget) : null }); setApiKey(''); setAdminKey(''); onMessage(`${names[value.provider]} 설정을 저장했습니다.`); await onChanged() } catch (e) { onMessage(e instanceof Error ? e.message : '저장에 실패했습니다.') } finally { setBusy(false) } }
  async function verify() { setBusy(true); try { await api.post(`/settings/llm-providers/${value.provider}/verify`); onMessage('연결을 확인했습니다.'); await onChanged() } catch (e) { onMessage(e instanceof Error ? e.message : '연결 확인에 실패했습니다.') } finally { setBusy(false) } }
  async function remove() { if (!confirm(`${names[value.provider]} 키를 삭제할까요?`)) return; await api.delete(`/settings/llm-providers/${value.provider}`); await onChanged() }
  return <form className="provider-card" onSubmit={save}><div className="provider-heading"><div><strong>{names[value.provider]}</strong><small>{value.configured ? value.masked_key : '연결되지 않음'}</small></div><span className={`provider-status ${value.status}`}>{value.status}</span></div><label>API key<input type="password" autoComplete="new-password" placeholder={value.configured ? '변경할 때만 입력' : 'API 키 입력'} value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></label><label>Admin key <small>(선택)</small><input type="password" autoComplete="new-password" placeholder={value.has_admin_key ? '저장됨 · 변경할 때만 입력' : '조직 전체 사용량 조회용'} value={adminKey} onChange={(e) => setAdminKey(e.target.value)} /></label><label>기본 모델<select value={model} onChange={(e) => setModel(e.target.value)}>{providerModels[value.provider].map((name) => <option value={name} key={name}>{name}</option>)}</select></label><label>월 예산 (USD)<input type="number" min="1" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="선택 사항" /></label><div className="provider-actions"><button className="btn sm" disabled={busy}>{busy ? '처리 중…' : '저장'}</button>{value.configured && <><button className="btn sm ghost" type="button" onClick={verify} disabled={busy}>연결 테스트</button><button className="btn sm danger" type="button" onClick={remove}>삭제</button></>}</div></form>
}
