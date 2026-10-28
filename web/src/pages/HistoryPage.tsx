import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { ExecutionListItem } from '../types'
import { generationLabel, inputFilesSummary } from '../workflow'

const statuses = ['all', 'completed', 'running', 'failed'] as const
const ACTIVE = ['pending', 'running']

type BulkDeleteResult = { deleted: number[]; skipped: { id: number; reason: string }[] }

export default function HistoryPage() {
  const [items, setItems] = useState<ExecutionListItem[]>([])
  const [filter, setFilter] = useState<(typeof statuses)[number]>('all')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => { api.get<ExecutionListItem[]>('/executions').then(setItems).catch(() => {}) }, [])
  const visibleItems = useMemo(() => items.filter((item) =>
    (filter === 'all' || item.status === filter) && `${item.service_name} ${item.run_prompt}`.toLowerCase().includes(query.toLowerCase()),
  ), [filter, items, query])
  const deletable = visibleItems.filter((item) => !ACTIVE.includes(item.status))
  const allSelected = deletable.length > 0 && deletable.every((item) => selected.has(item.id))

  function toggle(id: number) {
    setSelected((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next })
  }
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(deletable.map((item) => item.id)))
  }
  async function removeSelected() {
    const ids = [...selected]
    if (!ids.length || !confirm(`선택한 실행 이력 ${ids.length}개를 지울까요? 결과와 에이전트 출력도 함께 지워지고 되돌릴 수 없습니다.`)) return
    setDeleting(true)
    try {
      const result = await api.post<BulkDeleteResult>('/executions/delete', { ids })
      const gone = new Set(result.deleted)
      setItems((current) => current.filter((item) => !gone.has(item.id)))
      setSelected(new Set())
      const active = result.skipped.filter((item) => item.reason === 'active').length
      if (active) alert(`실행 중인 이력 ${active}개는 지우지 않았습니다. 먼저 실행을 취소해 주세요.`)
    } catch (cause) {
      alert(cause instanceof Error ? cause.message : '실행 이력을 지우지 못했습니다.')
    } finally { setDeleting(false) }
  }

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
        <div className="history-select-bar">
          <label><input type="checkbox" checked={allSelected} disabled={!deletable.length} onChange={toggleAll} /> 전체 선택</label>
          <button type="button" className="history-delete" disabled={!selected.size || deleting} onClick={removeSelected}>{deleting ? '지우는 중…' : `선택 삭제${selected.size ? ` (${selected.size})` : ''}`}</button>
        </div>
        <div className="execution-list">
          {visibleItems.map((item) => <div className="execution-row" key={item.id}>
            <input type="checkbox" aria-label={`#${item.id} 선택`} checked={selected.has(item.id)} disabled={ACTIVE.includes(item.status)} title={ACTIVE.includes(item.status) ? '실행 중인 이력은 지울 수 없습니다' : undefined} onChange={() => toggle(item.id)} />
            <button type="button" className="execution-list-item" onClick={() => navigate(`/executions/${item.id}`)}>
              <div><strong>{item.service_name}</strong><span className={`status-pill ${item.status}`}>{item.status}</span></div>
              <p>{item.run_prompt || '실행 프롬프트 없음'} · 입력: {inputFilesSummary(item.input_files)}</p>
              <small>#{item.id} · {new Date(item.created_at).toLocaleString()} · 생성 모델: {generationLabel(item.generation_info)}</small>
            </button>
          </div>)}
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
