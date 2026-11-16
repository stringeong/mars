import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppIcon from '../components/AppIcon'
import { api } from '../api'
import ExecutionGantt from '../components/ExecutionGantt'
import ExecutionStageView from '../components/ExecutionStageView'
import MarkdownView from '../components/MarkdownView'
import { Execution, ExecutionListItem, Task } from '../types'
import { executionStatusLabel, generationLabel, shortDateTime, TASK_STATUS, taskWorkerLabel } from '../workflow'

function statusLabel(status: string) { return executionStatusLabel(status) }

function approvalSources(execution: Execution, approval: Task) {
  const sourceIds = new Set(
    (execution.edges ?? [])
      .filter((edge) => edge.target === approval.node_id)
      .map((edge) => edge.source),
  )
  return execution.tasks.filter((task) => sourceIds.has(task.node_id))
}

export default function ExecutionPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [history, setHistory] = useState<ExecutionListItem[]>([])
  const [error, setError] = useState('')
  // 고르기 전에는 단계 보기. 파일을 나눠 한 단계에 블록이 많으면 워커별로 묶이는 간트 보기가 읽기 쉽다
  const [chosenView, setView] = useState<'stages' | 'gantt' | null>(null)
  const [now, setNow] = useState(Date.now())
  const [retryTask, setRetryTask] = useState<Task | null>(null)
  const [retryPrompt, setRetryPrompt] = useState('')
  const [retryModel, setRetryModel] = useState('')
  const [actionBusy, setActionBusy] = useState(false)

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
  async function approve(task: Task) {
    setActionBusy(true)
    setError('')
    try { setExecution(await api.post<Execution>("/executions/" + id + "/approvals/" + task.id + "/approve")) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '승인 처리에 실패했습니다.') }
    finally { setActionBusy(false) }
  }
  function openRetry(task: Task) {
    // 검토 작업을 다시 실행할 때는 안내문이 아니라 선행 모델 블록의
    // 프롬프트와 모델을 편집한다.
    const source = task.status === "waiting_approval" && execution
      ? approvalSources(execution, task)[0]
      : task
    setRetryTask(task)
    setRetryPrompt(source?.role_prompt ?? "")
    setRetryModel(source?.model ?? "")
  }
  async function retry() {
    if (!retryTask) return
    const approval = retryTask.status === 'waiting_approval'
    const path = approval
      ? "/executions/" + id + "/approvals/" + retryTask.id + "/retry-source"
      : "/executions/" + id + "/tasks/" + retryTask.id + "/retry"
    setActionBusy(true)
    setError('')
    try {
      setExecution(await api.post<Execution>(path, { role_prompt: retryPrompt, model: retryModel }))
      setRetryTask(null)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '재실행을 시작하지 못했습니다.') }
    finally { setActionBusy(false) }
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
  const waitingApprovals = execution.tasks.filter((task) => task.status === 'waiting_approval')
  // 입력 파일: 여러 블록이 같은 파일을 쓰면 한 번만 보여준다 (마우스를 올리면 어느 블록 입력인지 보임)
  const inputChips = [...new Map((execution.input_files ?? []).flatMap((record) => [
    ...record.files.map((file) => [`f${file.id}`, { name: file.name, label: record.label }] as const),
    ...record.directories.map((directory) => [`d${directory.alias}`, { name: `폴더 ${directory.alias}`, label: record.label }] as const),
  ])).values()]
  // 입력을 끝까지 읽지 못하고 끝난 블록: 완료로 표시되더라도 결과에 빠진 내용이 있을 수 있다
  const noticed = execution.tasks.filter((task) => task.notice)
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
      {waitingApprovals.map((approval) => {
        const sources = approvalSources(execution, approval)
        return <section className="result-section failure-section" key={approval.id}>
          <span className="eyebrow">USER REVIEW REQUIRED</span><h2>{approval.agent_name}</h2>
          <p>{approval.role_prompt || '이 결과를 확인한 뒤 다음 단계 진행을 선택하세요.'}</p>
          {sources.map((source) => source.output && <article className="result-box" key={source.id}>{sources.length > 1 && <strong>{source.agent_name}</strong>}<MarkdownView text={source.output} /></article>)}
          <div className="result-actions"><button className="btn" disabled={actionBusy} onClick={() => approve(approval)}>승인하고 계속</button><button className="btn ghost" disabled={actionBusy} onClick={() => openRetry(approval)}>수정 후 다시 실행</button></div>
        </section>
      })}
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
      {noticed.length > 0 && <section className="result-section notice-section"><span className="eyebrow">입력 확인</span><h2>입력 일부가 빠진 채 실행됐어요</h2><p>아래 블록은 입력을 끝까지 읽지 못했어요. 결과에 빠진 내용이 있을 수 있어요.</p><ul>{noticed.flatMap((task) => task.notice!.split('\n').map((line, index) => <li key={`${task.id}-${index}`}><strong>{task.agent_name}</strong><span>{line}</span></li>))}</ul></section>}
      {execution.result && <section className="final-result-card"><div className="result-section-heading"><div><span className="eyebrow">최종 결과</span><h2>최종 결과</h2></div><button className="btn sm ghost" onClick={downloadResult}>다운로드</button></div><article className="result-box"><MarkdownView text={execution.result} /></article></section>}
      {execution.tasks.some((task) => task.output) && <section className="agent-output-section"><span className="eyebrow">에이전트별 출력</span><h2>에이전트별 출력</h2>{execution.tasks.filter((task) => task.output).map((task) => <details key={task.id}><summary><span>{task.agent_name}</span><small>{taskWorkerLabel(task)}</small></summary>{task.notice && <p className="task-notice">{task.notice}</p>}<div className="result-box"><MarkdownView text={task.output!} /></div>{task.executor !== 'manual' && ['done', 'failed'].includes(task.status) && <button className="btn sm ghost" disabled={actionBusy} onClick={() => openRetry(task)}>이 블록 다시 실행</button>}</details>)}</section>}
      {retryTask && <div className="file-library-modal-backdrop" role="presentation"><section className="file-library-modal" role="dialog" aria-modal="true" aria-labelledby="retry-title"><header><div><span className="eyebrow">RETRY BLOCK</span><h2 id="retry-title">{retryTask.status === 'waiting_approval' ? '선행 블록 다시 실행' : retryTask.agent_name + ' 다시 실행'}</h2></div><button className="modal-close" onClick={() => setRetryTask(null)}>×</button></header><p>선택한 블록과 그 뒤쪽 블록 결과는 새 실행 결과로 덮어써집니다.</p><label>역할 프롬프트</label><textarea rows={5} value={retryPrompt} onChange={(event) => setRetryPrompt(event.target.value)} /><label>모델</label><input value={retryModel} onChange={(event) => setRetryModel(event.target.value)} placeholder="비우면 기존 기본 모델" /><footer><span>다른 병렬 분기는 계속 실행됩니다.</span><div><button className="btn sm ghost" disabled={actionBusy} onClick={() => setRetryTask(null)}>취소</button><button className="btn sm" disabled={actionBusy} onClick={retry}>{actionBusy ? '시작 중…' : '다시 실행'}</button></div></footer></section></div>}
    </main>
  </div>
}
