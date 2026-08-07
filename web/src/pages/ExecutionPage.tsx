import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Execution, ExecutionListItem } from '../types'

function statusLabel(status: string) { return status.replace(/_/g, ' ') }

export default function ExecutionPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [history, setHistory] = useState<ExecutionListItem[]>([])
  const [error, setError] = useState('')

  async function load() {
    try { setExecution(await api.get<Execution>(`/executions/${id}`)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to load execution.') }
  }
  useEffect(() => {
    load(); api.get<ExecutionListItem[]>('/executions').then(setHistory).catch(() => {})
    const timer = setInterval(() => { if (!execution || ['pending', 'running'].includes(execution.status)) load() }, 3000)
    return () => clearInterval(timer)
  }, [id, execution?.status])

  async function cancel() {
    if (!confirm('Cancel this execution?')) return
    try { setExecution(await api.post<Execution>(`/executions/${id}/cancel`)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to cancel execution.') }
  }
  function downloadResult() {
    if (!execution?.result) return
    const blob = new Blob([execution.result], { type: 'text/markdown' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob); link.download = `mars_result_${execution.id}.md`; link.click(); URL.revokeObjectURL(link.href)
  }
  if (!execution) return <div className="page-loading">{error || 'Loading execution...'}</div>
  const active = ['pending', 'running'].includes(execution.status)

  return <div className="result-viewer-page">
    <aside className="result-history-panel">
      <div className="list-panel-header"><div><span className="eyebrow">EXECUTIONS</span><h2>History</h2></div><button type="button" className="text-button" onClick={() => navigate('/history')}>View all</button></div>
      <div className="compact-history">{history.slice(0, 8).map((item) => <button type="button" key={item.id} className={item.id === execution.id ? 'current' : ''} onClick={() => navigate(`/executions/${item.id}`)}><strong>{item.service_name}</strong><span><i className={`status-dot ${item.status === 'completed' ? '' : 'muted-dot'}`} /> {item.status} · #{item.id}</span></button>)}</div>
    </aside>
    <main className="result-main">
      <header className="result-header"><div><div className="breadcrumb">M.A.R.S <span>/</span> Executions <span>/</span> #{execution.id}</div><div className="result-title-row"><h1>Workflow result</h1><span className={`status-pill large ${execution.status}`}>{statusLabel(execution.status)}</span></div><p>{execution.run_prompt || 'Distributed multi-agent workflow execution'}</p></div><div className="result-actions">{execution.result && <button className="btn ghost" onClick={downloadResult}>Export report</button>}{active && <button className="btn danger" onClick={cancel}>Cancel run</button>}</div></header>
      {error && <div className="error">{error}</div>}
      <section className="run-progress-card"><div className="run-progress-heading"><span><i className={active ? 'pulse-dot' : 'check-dot'} /> {active ? 'Workflow is running' : 'Execution complete'}</span><strong>{execution.progress}%</strong></div><div className="progress-bar"><div style={{ width: `${execution.progress}%` }} /></div></section>
      <section className="result-section"><div className="result-section-heading"><span className="eyebrow">EXECUTION TIMELINE</span><h2>Agent collaboration</h2><p>Each step records the assigned worker and completed output.</p></div><div className="agent-timeline">{execution.tasks.map((task, index) => <div className={`timeline-row ${task.status}`} key={task.id}><div className="timeline-rail"><i>{task.status === 'done' || task.status === 'completed' ? '✓' : index + 1}</i></div><div className="timeline-content"><div><strong>{task.agent_name}</strong><span className={`status-pill ${task.status}`}>{statusLabel(task.status)}</span></div><small>{task.assigned_device_id ? `Worker #${task.assigned_device_id}` : 'Waiting for worker'} {task.finished_at ? ` · finished ${new Date(task.finished_at).toLocaleTimeString()}` : ''}</small>{task.error && <p className="timeline-error">{task.error}</p>}</div></div>)}{!execution.tasks.length && <div className="empty-workflows">No agent tasks were created for this execution.</div>}</div></section>
      {execution.error && <section className="result-section failure-section"><span className="eyebrow">EXECUTION ERROR</span><h2>This run needs attention</h2><p>{execution.error}</p></section>}
      {execution.result && <section className="final-result-card"><div className="result-section-heading"><div><span className="eyebrow">FINAL OUTPUT</span><h2>Generated result</h2></div><button className="btn sm ghost" onClick={downloadResult}>Download</button></div><article className="result-box">{execution.result}</article></section>}
      {execution.tasks.some((task) => task.output) && <section className="agent-output-section"><span className="eyebrow">TRACE OUTPUT</span><h2>Agent outputs</h2>{execution.tasks.filter((task) => task.output).map((task) => <details key={task.id}><summary><span>{task.agent_name}</span><small>{task.assigned_device_id ? `Worker #${task.assigned_device_id}` : 'Auto assigned'}</small></summary><div className="result-box">{task.output}</div></details>)}</section>}
    </main>
    <aside className="execution-detail-panel"><span className="eyebrow">EXECUTION DETAILS</span><h2>Run metadata</h2><dl><div><dt>Status</dt><dd><span className={`status-pill ${execution.status}`}>{statusLabel(execution.status)}</span></dd></div><div><dt>Progress</dt><dd>{execution.progress}%</dd></div><div><dt>Started</dt><dd>{new Date(execution.created_at).toLocaleString()}</dd></div><div><dt>Agents</dt><dd>{execution.tasks.length}</dd></div></dl><div className="mini-flow"><span className="eyebrow">WORKFLOW MAP</span><div><b>Input</b><i /><b>Agents</b><i /><b>Output</b></div><small>Workflow blocks and worker assignments are recorded in the execution trace.</small></div></aside>
  </div>
}
