import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { CloudProvider, Device, GenerationError, GeneratorModels, Service } from '../types'
import { GENERATION_STAGE_LABELS, PROVIDER_LABELS } from '../workflow'

const templates = [
  { title: 'Research report', text: 'Collect reliable sources on a topic, analyze the evidence, and prepare a concise research report.' },
  { title: 'Document review', text: 'Read the supplied documents, identify key issues and risks, then provide a structured review.' },
  { title: 'Data analysis', text: 'Analyze the available data, find meaningful trends, and deliver decisions with supporting evidence.' },
]

function valueFromSpecs(specs: Record<string, unknown>, key: string, fallback: number) {
  const value = specs[key]
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : fallback
}

export default function ServicesPage() {
  const [services, setServices] = useState<Service[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [prompt, setPrompt] = useState('')
  const [selectedResources, setSelectedResources] = useState(['Workers', 'Directories'])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [generatorModels, setGeneratorModels] = useState<GeneratorModels | null>(null)
  const [genLocation, setGenLocation] = useState<'local' | 'cloud'>('local')
  const [genProvider, setGenProvider] = useState<CloudProvider>('openai')
  const [genModel, setGenModel] = useState('')
  const [transferAck, setTransferAck] = useState(false)
  const [genError, setGenError] = useState<GenerationError | null>(null)
  const modelSelectRef = useRef<HTMLSelectElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get<Service[]>('/services').then(setServices).catch(() => {})
    api.get<Device[]>('/devices').then(setDevices).catch(() => {})
    api.get<GeneratorModels>('/services/generator-models').then(setGeneratorModels).catch(() => {})
  }, [])

  // 외부 LLM API는 키를 등록한 제공자만 고를 수 있다
  const configuredCloud = (generatorModels?.cloud ?? []).filter((item) => item.configured)
  const selectedCloud = configuredCloud.find((item) => item.provider === genProvider)
  const genModelOptions = genLocation === 'cloud' ? selectedCloud?.models ?? [] : generatorModels?.local.models ?? []
  const genDefaultModel = genLocation === 'cloud' ? selectedCloud?.default_model : generatorModels?.local.default_model
  const genModelLabel = genLocation === 'cloud'
    ? `외부 LLM API · ${PROVIDER_LABELS[genProvider]} · ${genModel || genDefaultModel || '기본 모델'}`
    : `서버 로컬 LLM · ${genModel || genDefaultModel || '기본 모델'}`

  function chooseLocation(next: 'local' | 'cloud') {
    setGenLocation(next)
    setGenModel('')
    setTransferAck(false)
    if (next === 'cloud' && configuredCloud.length && !selectedCloud) setGenProvider(configuredCloud[0].provider)
  }

  const onlineDevices = devices.filter((device) => device.online)
  const estimate = useMemo(() => ({
    agents: prompt.trim() ? Math.min(5, Math.max(2, Math.ceil(prompt.length / 120) + 1)) : 3,
    steps: prompt.trim() ? Math.min(9, Math.max(3, Math.ceil(prompt.length / 75) + 2)) : 4,
  }), [prompt])

  function toggleResource(resource: string) {
    setSelectedResources((current) => current.includes(resource)
      ? current.filter((item) => item !== resource)
      : [...current, resource])
  }

  async function generate(e: FormEvent) {
    e.preventDefault()
    setError('')
    setGenError(null)
    setLoading(true)
    try {
      const service = await api.post<Service>('/services/generate', {
        prompt,
        location: genLocation,
        provider: genLocation === 'cloud' ? genProvider : 'ollama',
        model: genModel,
        external_transfer_ack: genLocation === 'cloud' && transferAck,
      })
      navigate(`/services/${service.id}/setup`)
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail as { generation_error?: GenerationError } | undefined : undefined
      if (detail?.generation_error) setGenError(detail.generation_error)
      else setError(err instanceof Error ? err.message : 'Unable to create workflow.')
    } finally {
      setLoading(false)
    }
  }

  async function duplicateService(serviceId: number) {
    try {
      const copy = await api.post<Service>(`/services/${serviceId}/duplicate`)
      navigate(`/services/${copy.id}/setup`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '복제 실패')
    }
  }

  // 생성 실패 후 사용자가 고른 경우에만 규칙 기반 기본 워크플로우를 만든다
  async function chooseDefaultWorkflow() {
    if (!genError) return
    setLoading(true)
    try {
      const reason = `${GENERATION_STAGE_LABELS[genError.stage] ?? genError.stage} (${genError.model}): ${genError.message}`
      const service = await api.post<Service>('/services/generate', { prompt, use_fallback: true, fallback_reason: reason })
      navigate(`/services/${service.id}/setup`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create workflow.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="workflow-dashboard">
      <header className="dashboard-header">
        <div>
          <div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> New workflow</div>
          <h1>Create multi-agent workflow</h1>
          <p>Describe the result you need. M.A.R.S will assemble the agents, resources, and execution flow.</p>
        </div>
        <div className="header-summary">
          <span className="live-indicator" /> {onlineDevices.length} worker{onlineDevices.length === 1 ? '' : 's'} online
        </div>
      </header>

      <div className="dashboard-grid">
        <section className="workflow-main">
          <form className="creation-card" onSubmit={generate}>
            <div className="card-topline">
              <div>
                <span className="eyebrow">WORKFLOW BRIEF</span>
                <h2>What should your team accomplish?</h2>
              </div>
              <span className="ai-label">AI assisted</span>
            </div>
            <textarea
              className="workflow-prompt"
              placeholder="Example: Review the project documents, research comparable approaches, and deliver an implementation plan with risks and next steps."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              required
              minLength={5}
            />
            <div className="generator-picker">
              <span className="generator-picker-title">생성 모델</span>
              <label>실행 위치
                <select value={genLocation} onChange={(event) => chooseLocation(event.target.value as 'local' | 'cloud')}>
                  <option value="local">서버 로컬 LLM (Ollama)</option>
                  <option value="cloud" disabled={!configuredCloud.length}>외부 LLM API{configuredCloud.length ? '' : ' · 등록된 키 없음'}</option>
                </select>
              </label>
              {genLocation === 'cloud' && <label>제공자
                <select value={genProvider} onChange={(event) => { setGenProvider(event.target.value as CloudProvider); setGenModel(''); setTransferAck(false) }}>
                  {configuredCloud.map((item) => <option key={item.provider} value={item.provider}>{PROVIDER_LABELS[item.provider]}</option>)}
                </select>
              </label>}
              <label>모델
                <select ref={modelSelectRef} value={genModel} onChange={(event) => setGenModel(event.target.value)}>
                  <option value="">{genLocation === 'cloud' ? '등록된 기본 모델' : '서버 기본 모델'}{genDefaultModel ? ` · ${genDefaultModel}` : ''}</option>
                  {genModelOptions.filter((model) => model !== genDefaultModel).map((model) => <option key={model} value={model}>{model}</option>)}
                </select>
              </label>
            </div>
            {genLocation === 'local' && generatorModels && !generatorModels.local.available && <small className="generator-hint">{generatorModels.local.error} 이대로 생성하면 연결 실패로 안내됩니다.</small>}
            {genLocation === 'cloud' && <div className="external-notice">
              <strong>외부 전송 안내</strong>
              <p>생성 프롬프트가 {PROVIDER_LABELS[genProvider]} API로 전송됩니다. API 키는 서버에만 보관되며, 업로드 파일은 생성 단계에서 전송되지 않습니다.</p>
              <label className="ack-row"><input type="checkbox" checked={transferAck} onChange={(event) => setTransferAck(event.target.checked)} />생성 프롬프트가 외부로 전송되는 것을 확인했습니다.</label>
            </div>}
            {genError && <div className="generation-failure" role="alert">
              <span className="eyebrow">생성 실패 · {GENERATION_STAGE_LABELS[genError.stage] ?? genError.stage}</span>
              <strong>{genError.location === 'cloud' ? PROVIDER_LABELS[genError.provider] : '서버 로컬 LLM'} · {genError.model} 모델로 워크플로우를 만들지 못했습니다.</strong>
              <p>{genError.message}</p>
              <div className="generation-failure-actions">
                <button type="button" className="btn sm ghost" onClick={() => { setGenError(null); modelSelectRef.current?.focus() }}>다른 모델로 다시 시도</button>
                <button type="button" className="btn sm" disabled={loading} onClick={chooseDefaultWorkflow}>기본 워크플로우 사용</button>
              </div>
              <small>기본 워크플로우는 정보 수집 → 분석 → 정리 3단계이며, 생성 프롬프트는 역할 프롬프트에 붙지 않고 서비스 목표로만 전달됩니다.</small>
            </div>}
            <div className="resource-row">
              <span>Attach context</span>
              {['Workers', 'Directories', 'Web research'].map((resource) => (
                <button type="button" key={resource} className={`resource-chip ${selectedResources.includes(resource) ? 'selected' : ''}`} onClick={() => toggleResource(resource)}>
                  <i /> {resource}
                </button>
              ))}
            </div>
            {error && <div className="error">{error}</div>}
            <div className="creation-footer">
              <span>Generation creates an editable Scratch-style workflow.</span>
              <button className="generate-button" disabled={loading || (genLocation === 'cloud' && (!transferAck || !selectedCloud))}>
                <span className="spark">+</span>{loading ? 'Building workflow...' : 'Generate workflow'}
              </button>
            </div>
          </form>

          <section className="templates-section">
            <div className="section-heading"><div><span className="eyebrow">STARTING POINT</span><h2>Use a workflow template</h2></div></div>
            <div className="template-grid">
              {templates.map((template, index) => (
                <button type="button" className="template-card" key={template.title} onClick={() => setPrompt(template.text)}>
                  <span className={`template-icon icon-${index + 1}`}>{index + 1}</span>
                  <strong>{template.title}</strong>
                  <small>{index === 0 ? 'Source collection and synthesis' : index === 1 ? 'Read, assess, and summarize files' : 'Explore data and recommend actions'}</small>
                  <span className="template-action">Use template <b>→</b></span>
                </button>
              ))}
            </div>
          </section>

          <section className="recent-section">
            <div className="section-heading"><div><span className="eyebrow">SAVED WORK</span><h2>Recent workflows</h2></div><span className="count-pill">{services.length}</span></div>
            <div className="recent-list">
              {services.slice(0, 4).map((service) => (
                <div className="recent-workflow-row" key={service.id}>
                  <button type="button" className="recent-workflow" onClick={() => navigate(`/services/${service.id}`)}>
                    <span className="workflow-avatar">{service.name.slice(0, 1).toUpperCase()}</span>
                    <span><strong>{service.name}</strong><small>{service.graph?.nodes?.length ?? 0} blocks · Updated {new Date(service.updated_at).toLocaleDateString()}</small></span>
                    <b>→</b>
                  </button>
                  <div className="recent-workflow-actions">
                    <button type="button" className="btn sm ghost" onClick={() => navigate(`/services/${service.id}/run`)}>다시 실행</button>
                    <button type="button" className="btn sm ghost" onClick={() => duplicateService(service.id)}>복제</button>
                  </div>
                </div>
              ))}
              {services.length === 0 && <div className="empty-workflows">Your generated workflows will appear here.</div>}
            </div>
          </section>
        </section>

        <aside className="assistant-panel">
          <div className="assistant-title"><div className="assistant-orb">M</div><div><span className="eyebrow">M.A.R.S ASSISTANT</span><h2>Workflow plan</h2></div></div>
          <p className="assistant-description">Your workflow will use the available team resources and remain fully editable after generation.</p>
          <div className="estimate-card">
            <div><strong>{estimate.agents}</strong><span>agents</span></div>
            <div><strong>{estimate.steps}</strong><span>steps</span></div>
            <div><strong>{selectedResources.length}</strong><span>sources</span></div>
          </div>
          <div className="assistant-section"><div className="assistant-section-title"><span>Available workers</span><small>{onlineDevices.length}/{devices.length} ready</small></div>
            <div className="worker-list">
              {devices.slice(0, 4).map((device, index) => {
                const cpu = valueFromSpecs(device.specs, 'cpu_percent', 22 + index * 11)
                const ram = valueFromSpecs(device.specs, 'memory_percent', 35 + index * 8)
                return <div className="mini-worker" key={device.id}>
                  <div className={`worker-dot ${device.online ? 'online' : ''}`} /><div className="mini-worker-info"><strong>{device.name}</strong><small>{device.online ? 'Ready for assignment' : 'Offline'}</small></div>
                  <div className="mini-meters"><span><i style={{ width: `${cpu}%` }} /></span><span><i style={{ width: `${ram}%` }} /></span></div>
                </div>
              })}
              {devices.length === 0 && <div className="worker-empty">No workers registered yet.</div>}
            </div>
          </div>
          <div className="assistant-section model-section"><div className="assistant-section-title"><span>Generation model</span><small>{genLocation === 'cloud' ? 'External API' : 'Server local'}</small></div><div className="model-tags"><span>{genModelLabel}</span></div></div>
          <div className="plan-preview"><span className="eyebrow">ESTIMATED FLOW</span><div className="plan-flow"><span>Brief</span><i /><span>Agents</span><i /><span>Result</span></div><small>Generated blocks can be rearranged before running.</small></div>
        </aside>
      </div>
    </div>
  )
}
