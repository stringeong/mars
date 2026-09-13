import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Device, ExecutionListItem, Service } from '../types'

export default function DashboardPage() {
  const [services, setServices] = useState<Service[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [executions, setExecutions] = useState<ExecutionListItem[]>([])
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.allSettled([
      api.get<Service[]>('/services').then(setServices),
      api.get<Device[]>('/devices').then(setDevices),
      api.get<ExecutionListItem[]>('/executions').then(setExecutions),
    ])
  }, [])

  const filtered = useMemo(() => services.filter((service) => `${service.name} ${service.description}`.toLowerCase().includes(query.toLowerCase())), [services, query])
  const online = devices.filter((device) => device.online).length
  const running = executions.filter((execution) => execution.status === 'running').length

  return <div className="overview-page">
    <header className="page-heading"><div><div className="breadcrumb">M.A.R.S <span>/</span> Dashboard</div><h1>Dashboard</h1><p>Your workflows, workers, and recent activity at a glance.</p></div><button className="generate-button" onClick={() => navigate('/services')}>+ New workflow</button></header>
    <section className="stat-grid">
      <div className="stat-card"><span>Total workflows</span><strong>{services.length}</strong><small>saved services</small></div>
      <div className="stat-card"><span>Online workers</span><strong>{online}/{devices.length}</strong><small>available devices</small></div>
      <div className="stat-card"><span>Running now</span><strong className={running ? 'accent' : ''}>{running}</strong><small>active executions</small></div>
      <div className="stat-card"><span>Recent runs</span><strong>{executions.length}</strong><small>execution records</small></div>
    </section>
    <section className="dashboard-workflows">
      <div className="section-heading dashboard-section-heading"><div><span className="eyebrow">YOUR WORKSPACE</span><h2>My workflows</h2></div><input className="compact-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search workflows" /></div>
      <div className="dashboard-workflow-grid">
        <button className="new-workflow-card" onClick={() => navigate('/services')}><b>+</b><strong>Create a new workflow</strong><small>Build an editable multi-agent workflow</small></button>
        {filtered.map((service) => <button className="dashboard-workflow-card" key={service.id} onClick={() => navigate(`/services/${service.id}`)}><span className="workflow-avatar">{service.name.slice(0, 1).toUpperCase()}</span><strong>{service.name}</strong><p>{service.description || 'No description provided.'}</p><small>{service.graph.nodes.length} blocks · Updated {new Date(service.updated_at).toLocaleDateString()}</small></button>)}
      </div>
      {!filtered.length && services.length > 0 && <div className="empty-workflows">No workflows match your search.</div>}
    </section>
  </div>
}
