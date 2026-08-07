import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Device, Service } from '../types'

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
  const navigate = useNavigate()

  useEffect(() => {
    api.get<Service[]>('/services').then(setServices).catch(() => {})
    api.get<Device[]>('/devices').then(setDevices).catch(() => {})
  }, [])

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
    setLoading(true)
    try {
      const service = await api.post<Service>('/services/generate', { prompt })
      navigate(`/services/${service.id}`)
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
              <button className="generate-button" disabled={loading}>
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
                <button type="button" className="recent-workflow" key={service.id} onClick={() => navigate(`/services/${service.id}`)}>
                  <span className="workflow-avatar">{service.name.slice(0, 1).toUpperCase()}</span>
                  <span><strong>{service.name}</strong><small>{service.graph?.nodes?.length ?? 0} blocks · Updated {new Date(service.updated_at).toLocaleDateString()}</small></span>
                  <b>→</b>
                </button>
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
          <div className="assistant-section model-section"><div className="assistant-section-title"><span>Agent models</span><small>Auto select</small></div><div className="model-tags"><span>Planner</span><span>Researcher</span><span>Reviewer</span></div></div>
          <div className="plan-preview"><span className="eyebrow">ESTIMATED FLOW</span><div className="plan-flow"><span>Brief</span><i /><span>Agents</span><i /><span>Result</span></div><small>Generated blocks can be rearranged before running.</small></div>
        </aside>
      </div>
    </div>
  )
}
