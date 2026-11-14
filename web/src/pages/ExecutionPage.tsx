import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppIcon from '../components/AppIcon'
import { api } from '../api'
import ExecutionGantt from '../components/ExecutionGantt'
import ExecutionStageView from '../components/ExecutionStageView'
import { Execution, ExecutionListItem } from '../types'
import { executionStatusLabel, generationLabel, shortDateTime, TASK_STATUS, taskWorkerLabel } from '../workflow'

function statusLabel(status: string) { return executionStatusLabel(status) }

export default function ExecutionPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [history, setHistory] = useState<ExecutionListItem[]>([])
  const [error, setError] = useState('')
  // 고르기 전에는 단계 보기. 파일을 나눠 한 단계에 블록이 많으면 워커별로 묶이는 간트 보기가 읽기 쉽다
  const [chosenView, setView] = useState<'stages' | 'gantt' | null>(null)
  const [now, setNow] = useState(Date.now())

  async function load() {
    try { setExecution(await api.get<Execution>(`/executions/${id}`)); setNow(Date.now()) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '실행 정보를 불러오지 못했어요.') }
  }
  useEffect(() => {
    load(); api.get<ExecutionListItem[]>('/executions').then(setHistory).catch(() => {})
    const timer = setInterval(() => { if (!execution || ['pending', 'running'].includes(execution.status)) load() }, 3000)
    return () => clearInterval(timer)
  }, [id, execution?.status])

  async function cancel() {
    if (!confirm('이 실행을 취소할까요?')) return
    try { setExecution(await api.post<Execution>(`/executions/${id}/cancel`)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '실행을 취소하지 못했어요.') }
  }
  async function remove() {
    if (!execution || !confirm(`실행 #${execution.id} 이력을 지울까요? 결과와 에이전트 출력도 함께 지워지고 되돌릴 수 없습니다.`)) return
    try { await api.delete(`/executions/${execution.id}`); navigate('/history') }
    catch (cause) { alert(cause instanceof Error ? cause.message : '실행 이력을 지우지 못했습니다.') }
  }
  function downloadResult() {
    if (!execution?.result) return
    const blob = new Blob([execution.result], { type: 'text/markdown' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob); link.download = `mars_result_${execution.id}.md`; link.click(); URL.revokeObjectURL(link.href)
  }
  if (!execution) return <div className="page-loading">{error || '실행 정보를 불러오는 중…'}</div>
  const active = ['pending', 'running'].includes(execution.status)
  // 입력 파일: 여러 블록이 같은 파일을 쓰면 한 번만 보여준다 (마우스를 올리면 어느 블록 입력인지 보임)
  const inputChips = [...new Map((execution.input_files ?? []).flatMap((record) => [
    ...record.files.map((file) => [`f${file.id}`, { name: file.name, label: record.label }] as const),
    ...record.directories.map((directory) => [`d${directory.alias}`, { name: `폴더 ${directory.alias}`, label: record.label }] as const),
  ])).values()]
  const view = chosenView ?? (Math.max(0, ...(execution.stages ?? []).map((ids) => ids.length)) > 8 ? 'gantt' : 'stages')

  return <div className="result-viewer-page">
    <aside className="result-history-panel">
      <div className="list-panel-header"><div><span className="eyebrow">실행 이력</span><h2>실행 이력</h2></div><button type="button" className="text-button" onClick={() => navigate('/history')}>모두 보기</button></div>
      <div className="compact-history">{history.slice(0, 8).map((item) => <button type="button" key={item.id} className={item.id === execution.id ? 'current' : ''} onClick={() => navigate(`/executions/${item.id}`)}><strong>{item.service_name}</strong><span><i className={`status-dot ${item.status === 'completed' ? '' : 'muted-dot'}`} /> {item.status} · #{item.id}</span></button>)}</div>
    </aside>
    <main className="result-main">
      <header className="result-header result-header-clean">
        <div>
          <div className="breadcrumb">M.A.R.S <span>/</span> 실행 이력 <span>/</span> #{execution.id}</div>
          <div className="result-title-row"><h1>실행 결과</h1><span className={`status-pill large ${execution.status}`}>{statusLabel(execution.status)}</span></div>
          <p className="result-meta">
            <span>{shortDateTime(execution.created_at)} 시작</span>
            <span>에이전트 {execution.tasks.length}개</span>
            <span>입력 파일 {inputChips.length ? `${inputChips.length}개` : '없음'}</span>
            <span>생성 모델 {generationLabel(execution.generation_info)}</span>
          </p>
          {execution.run_prompt && <p className="result-prompt">{execution.run_prompt}</p>}
        </div>
        <div className="result-actions">
          {active
            ? <button className="btn danger" onClick={cancel}>실행 취소</button>
            : <button className="btn" onClick={() => navigate(`/services/${execution.service_id}/run?from=${execution.id}`)}>같은 입력으로 다시 실행</button>}
          {!active && <button type="button" className="icon-btn danger" title="이력 삭제" aria-label="이력 삭제" onClick={remove}><AppIcon name="trash" /></button>}
        </div>
      </header>
      {error && <div className="error">{error}</div>}
      {inputChips.length > 0 && <section className="result-section run-inputs-section"><div className="result-section-heading"><h2>입력 파일</h2></div><div className="run-input-chips">{inputChips.map((chip) => <span key={chip.name} title={chip.label}>{chip.name}</span>)}</div>{(execution.input_files ?? []).filter((record) => record.kind === 'split' && record.pieces).map((record) => <small className="run-input-pieces" key={record.id}>{record.label}: {record.pieces!.map((piece) => `#${piece.index} ${piece.label}`).join(' · ')}</small>)}</section>}
      {active && <section className="run-progress-card"><div className="run-progress-heading"><span><i className={active ? 'pulse-dot' : 'check-dot'} /> {active ? '실행 중이에요' : '실행이 끝났어요'}</span><strong>{execution.progress}%</strong></div><div className="progress-bar"><div style={{ width: `${execution.progress}%` }} /></div></section>}
      <section className="result-section">
        <div className="result-section-heading timeline-heading">
          <div><span className="eyebrow">실행 타임라인</span><h2>에이전트 진행 상황</h2><p>같은 단계의 블록은 동시에 실행돼요.</p></div>
          <div className="view-toggle" role="group" aria-label="타임라인 보기 방식">
            <button type="button" className={view === 'stages' ? 'active' : ''} aria-pressed={view === 'stages'} onClick={() => setView('stages')}>단계 보기</button>
            <button type="button" className={view === 'gantt' ? 'active' : ''} aria-pressed={view === 'gantt'} onClick={() => setView('gantt')}>간트 보기</button>
          </div>
        </div>
        <div className="task-status-summary">{Object.entries(TASK_STATUS).map(([status, meta]) => { const count = execution.tasks.filter((task) => task.status === status).length; return count ? <span key={status} className={`task-status ${status}`}><i aria-hidden="true">{meta.icon}</i>{meta.label} {count}</span> : null })}</div>
        {!execution.tasks.length ? <div className="empty-workflows">이 실행에서 만들어진 에이전트 작업이 없어요.</div>
          : view === 'stages' ? <ExecutionStageView execution={execution} finalNodeIds={new Set(execution.final_node_ids ?? [])} now={now} /> : <ExecutionGantt execution={execution} now={now} />}
        {execution.tasks.filter((task) => task.error).map((task) => <p className="timeline-error" key={task.id}><strong>{task.agent_name}</strong>: {task.error}</p>)}
      </section>
      {execution.error && <section className="result-section failure-section"><span className="eyebrow">실행 오류</span><h2>실행 중 문제가 생겼어요</h2><p>{execution.error}</p></section>}
      {execution.result && <section className="final-result-card"><div className="result-section-heading"><div><span className="eyebrow">최종 결과</span><h2>최종 결과</h2></div><button className="btn sm ghost" onClick={downloadResult}>다운로드</button></div><article className="result-box">{execution.result}</article></section>}
      {execution.tasks.some((task) => task.output) && <section className="agent-output-section"><span className="eyebrow">에이전트별 출력</span><h2>에이전트별 출력</h2>{execution.tasks.filter((task) => task.output).map((task) => <details key={task.id}><summary><span>{task.agent_name}</span><small>{taskWorkerLabel(task)}</small></summary><div className="result-box">{task.output}</div></details>)}</section>}
    </main>
  </div>
}
