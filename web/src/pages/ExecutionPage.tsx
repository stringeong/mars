import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import ExecutionGantt from '../components/ExecutionGantt'
import ExecutionStageView from '../components/ExecutionStageView'
import { Execution, ExecutionListItem } from '../types'
import { generationLabel, inputFilesSummary, TASK_STATUS, taskWorkerLabel } from '../workflow'

function statusLabel(status: string) { return status.replace(/_/g, ' ') }

export default function ExecutionPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [history, setHistory] = useState<ExecutionListItem[]>([])
  const [error, setError] = useState('')
  const [view, setView] = useState<'stages' | 'gantt'>('stages')
  const [now, setNow] = useState(Date.now())

  async function load() {
    try { setExecution(await api.get<Execution>(`/executions/${id}`)); setNow(Date.now()) }
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
      <header className="result-header"><div><div className="breadcrumb">M.A.R.S <span>/</span> Executions <span>/</span> #{execution.id}</div><div className="result-title-row"><h1>Workflow result</h1><span className={`status-pill large ${execution.status}`}>{statusLabel(execution.status)}</span></div><p>{execution.run_prompt || '실행 프롬프트 없이 입력 파일로 실행했습니다.'}</p></div><div className="result-actions"><button className="btn ghost" onClick={() => navigate(`/services/${execution.service_id}/run?from=${execution.id}`)}>같은 입력으로 다시 실행</button>{execution.result && <button className="btn ghost" onClick={downloadResult}>Export report</button>}{active && <button className="btn danger" onClick={cancel}>Cancel run</button>}</div></header>
      {error && <div className="error">{error}</div>}
      {!!execution.input_files?.length && <section className="result-section run-inputs-section"><div className="result-section-heading"><span className="eyebrow">INPUT FILES</span><h2>이번 실행의 입력 파일</h2></div><ul className="run-input-list">{execution.input_files.map((record) => <li key={`${record.kind}-${record.id}`}><strong>{record.label}</strong><span>{[...record.files.map((file) => file.name), ...record.directories.map((directory) => `디렉터리 ${directory.alias}`)].join(', ') || '없음'}</span></li>)}</ul></section>}
      <section className="run-progress-card"><div className="run-progress-heading"><span><i className={active ? 'pulse-dot' : 'check-dot'} /> {active ? 'Workflow is running' : 'Execution complete'}</span><strong>{execution.progress}%</strong></div><div className="progress-bar"><div style={{ width: `${execution.progress}%` }} /></div></section>
      <section className="result-section">
        <div className="result-section-heading timeline-heading">
          <div><span className="eyebrow">EXECUTION TIMELINE</span><h2>Agent collaboration</h2><p>같은 단계(열)의 블록은 동시에 실행될 수 있습니다. 블록마다 배정 워커, 시작·종료 시각, 소요 시간을 보여줍니다.</p></div>
          <div className="view-toggle" role="group" aria-label="타임라인 보기 방식">
            <button type="button" className={view === 'stages' ? 'active' : ''} aria-pressed={view === 'stages'} onClick={() => setView('stages')}>단계 보기</button>
            <button type="button" className={view === 'gantt' ? 'active' : ''} aria-pressed={view === 'gantt'} onClick={() => setView('gantt')}>간트 보기</button>
          </div>
        </div>
        <div className="task-status-summary">{Object.entries(TASK_STATUS).map(([status, meta]) => { const count = execution.tasks.filter((task) => task.status === status).length; return count ? <span key={status} className={`task-status ${status}`}><i aria-hidden="true">{meta.icon}</i>{meta.label} {count}</span> : null })}</div>
        {!execution.tasks.length ? <div className="empty-workflows">No agent tasks were created for this execution.</div>
          : view === 'stages' ? <ExecutionStageView execution={execution} finalNodeIds={new Set(execution.final_node_ids ?? [])} now={now} /> : <ExecutionGantt execution={execution} now={now} />}
        {execution.tasks.filter((task) => task.error).map((task) => <p className="timeline-error" key={task.id}><strong>{task.agent_name}</strong>: {task.error}</p>)}
      </section>
      {execution.error && <section className="result-section failure-section"><span className="eyebrow">EXECUTION ERROR</span><h2>This run needs attention</h2><p>{execution.error}</p></section>}
      {execution.result && <section className="final-result-card"><div className="result-section-heading"><div><span className="eyebrow">FINAL OUTPUT</span><h2>Generated result</h2></div><button className="btn sm ghost" onClick={downloadResult}>Download</button></div><article className="result-box">{execution.result}</article></section>}
      {execution.tasks.some((task) => task.output) && <section className="agent-output-section"><span className="eyebrow">TRACE OUTPUT</span><h2>Agent outputs</h2>{execution.tasks.filter((task) => task.output).map((task) => <details key={task.id}><summary><span>{task.agent_name}</span><small>{taskWorkerLabel(task)}</small></summary><div className="result-box">{task.output}</div></details>)}</section>}
    </main>
    <aside className="execution-detail-panel"><span className="eyebrow">EXECUTION DETAILS</span><h2>Run metadata</h2><dl><div><dt>Status</dt><dd><span className={`status-pill ${execution.status}`}>{statusLabel(execution.status)}</span></dd></div><div><dt>Progress</dt><dd>{execution.progress}%</dd></div><div><dt>Started</dt><dd>{new Date(execution.created_at).toLocaleString()}</dd></div><div><dt>Agents</dt><dd>{execution.tasks.length}</dd></div><div><dt>생성 모델</dt><dd>{generationLabel(execution.generation_info)}</dd></div><div><dt>입력 파일</dt><dd>{inputFilesSummary(execution.input_files)}</dd></div></dl><div className="mini-flow"><span className="eyebrow">WORKFLOW MAP</span><div><b>Input</b><i /><b>Agents</b><i /><b>Output</b></div><small>Workflow blocks and worker assignments are recorded in the execution trace.</small></div></aside>
  </div>
}
