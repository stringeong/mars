import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { ExecutionListItem } from '../types'

const statuses = ['all', 'completed', 'running', 'failed'] as const

export default function HistoryPage() {
  const [items, setItems] = useState<ExecutionListItem[]>([])
  const [filter, setFilter] = useState<(typeof statuses)[number]>('all')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => { api.get<ExecutionListItem[]>('/executions').then(setItems).catch(() => {}) }, [])
  const visibleItems = useMemo(() => items.filter((item) =>
    (filter === 'all' || item.status === filter) && `${item.service_name} ${item.run_prompt}`.toLowerCase().includes(query.toLowerCase()),
  ), [filter, items, query])

  return <div className="history-page">
    <header className="page-topbar">
      <div><div className="breadcrumb">M.A.R.S <span>/</span> Executions</div><h1>Execution history</h1><p>Review runs, inspect agent output, and retry workflows from one place.</p></div>
      <div className="page-stat"><strong>{items.length}</strong><span>total executions</span></div>
    </header>
    <div className="history-layout">
      <aside className="execution-list-panel">
        <div className="list-panel-header"><h2>Execution history</h2><span>{items.length}</span></div>
        <input className="execution-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search executions..." />
        <div className="history-filters">{statuses.map((status) => <button type="button" className={filter === status ? 'active' : ''} key={status} onClick={() => setFilter(status)}>{status === 'all' ? 'All' : status}</button>)}</div>
        <div className="execution-list">
          {visibleItems.map((item) => <button type="button" className="execution-list-item" key={item.id} onClick={() => navigate(`/executions/${item.id}`)}>
            <div><strong>{item.service_name}</strong><span className={`status-pill ${item.status}`}>{item.status}</span></div>
            <p>{item.run_prompt || 'No execution prompt provided.'}</p>
            <small>#{item.id} · {new Date(item.created_at).toLocaleString()}</small>
          </button>)}
          {!visibleItems.length && <div className="list-empty">No matching executions.</div>}
        </div>
      </aside>
      <section className="history-overview">
        <div className="overview-card accent-card"><span className="eyebrow">ORCHESTRATION ACTIVITY</span><h2>Every run leaves an auditable trail.</h2><p>Open an execution to see the sequence of agents, assigned workers, final response, and individual agent outputs.</p><div className="overview-metrics"><div><strong>{items.filter((item) => item.status === 'completed').length}</strong><span>Completed</span></div><div><strong>{items.filter((item) => item.status === 'running').length}</strong><span>Running</span></div><div><strong>{items.filter((item) => item.status === 'failed').length}</strong><span>Needs review</span></div></div></div>
        <div className="history-table-card"><div className="section-heading"><div><span className="eyebrow">ALL ACTIVITY</span><h2>Recent runs</h2></div></div><div className="history-table-wrap"><table><thead><tr><th>Workflow</th><th>Status</th><th>Started</th><th /></tr></thead><tbody>{items.slice(0, 8).map((item) => <tr className="clickable" key={item.id} onClick={() => navigate(`/executions/${item.id}`)}><td><strong>{item.service_name}</strong><small>{item.run_prompt || 'No prompt'}</small></td><td><span className={`status-pill ${item.status}`}>{item.status}</span></td><td>{new Date(item.created_at).toLocaleString()}</td><td>→</td></tr>)}{!items.length && <tr><td colSpan={4} className="empty-cell">Your execution history will appear here.</td></tr>}</tbody></table></div></div>
      </section>
    </div>
  </div>
}
