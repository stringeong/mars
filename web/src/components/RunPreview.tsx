import { useEffect, useMemo, useRef, useState } from 'react'
import { blockId, Demo, DemoBlock } from '../demos'
import { Execution, Task } from '../types'
import { TASK_STATUS, taskWorkerLabel } from '../workflow'
import ExecutionGantt from './ExecutionGantt'
import ExecutionStageView from './ExecutionStageView'

// 미리보기는 실제 걸리는 시간보다 빠르게 돌린다
const SPEED = 6
// 워커가 서버에서 작업을 가져가는 데 걸리는 시간(초)
const PICKUP = 1
const DEVICE_IDS: Record<string, number> = { 데스크톱: 1, 노트북: 2, '회사 PC': 3, '연구실 PC': 4 }

type Planned = DemoBlock & { id: string; stage: number; readyAt: number; start: number; end: number }

/** 실제 실행처럼 단계마다 앞 단계가 끝나길 기다리고, 같은 기기에 몰린 블록은 그 기기가 비길 기다린다.
 *  자동 배정 블록은 이 예시에 나오는 워커 중 가장 먼저 비는 워커가 맡는다 */
function planRun(stages: DemoBlock[][]) {
  const free = new Map<string, number>()
  const tasks: Planned[] = []
  const pool = [...new Set(stages.flat().filter((block) => !block.cloud).map((block) => block.device))]
  let stageReady = 0
  stages.forEach((stage, index) => {
    const ends = stage.map((block, row) => {
      // 외부 API 블록은 기기를 차지하지 않고 제공자에게 간다
      const device = block.autoWorker && !block.cloud
        ? pool.reduce((best, name) => ((free.get(name) ?? 0) < (free.get(best) ?? 0) ? name : best), pool[0] ?? block.device)
        : block.device
      const lane = block.cloud ? `cloud:${block.cloud.provider}` : device
      const start = Math.max(stageReady, free.get(lane) ?? 0) + PICKUP
      const end = start + block.secs
      free.set(lane, end)
      tasks.push({ ...block, device, id: blockId(index, row), stage: index, readyAt: stageReady, start, end })
      return end
    })
    stageReady = Math.max(...ends)
  })
  return { tasks, total: stageReady }
}

function statusAt(task: Planned, t: number) {
  if (t >= task.end) return 'done'
  if (t >= task.start) return 'running'
  return t >= task.readyAt ? 'ready' : 'blocked'
}

/** 실행 결과 화면이 그리는 Execution 모양으로 t초 시점의 상태를 만든다 */
function executionAt(demo: Demo, plan: ReturnType<typeof planRun>, base: number, t: number, started: boolean): Execution {
  const iso = (secs: number) => new Date(base + secs * 1000).toISOString()
  const tasks: Task[] = plan.tasks.map((task, index) => {
    const status = started ? statusAt(task, t) : 'blocked'
    const assigned = status === 'running' || status === 'done'
    const local = !task.cloud
    return {
      id: index + 1,
      node_id: task.id,
      agent_name: task.name,
      status,
      assigned_device_id: assigned && local ? DEVICE_IDS[task.device] ?? 9 : null,
      assigned_device_name: assigned && local ? task.device : null,
      executor: local ? 'local' : 'cloud',
      provider: task.cloud?.provider ?? null,
      output: status === 'done' ? `${task.output}${task.files?.length ? `\n\n읽은 파일: ${task.files.join(', ')}` : ''}` : null,
      error: null,
      started_at: assigned ? iso(task.start) : null,
      finished_at: status === 'done' ? iso(task.end) : null,
    }
  })
  const stages = demo.stages.map((_, index) => plan.tasks.filter((task) => task.stage === index).map((task) => task.id))
  const edges = stages.slice(1).flatMap((ids, index) => stages[index].flatMap((source) => ids.map((target) => ({ source, target }))))
  const done = started && t >= plan.total
  const progress = Math.round((plan.tasks.reduce((sum, task) => sum + Math.min(1, Math.max(0, (t - task.start) / (task.end - task.start))), 0) / plan.tasks.length) * 100)
  return {
    id: 128,
    service_id: 0,
    run_prompt: demo.prompt,
    status: done ? 'completed' : started ? 'running' : 'pending',
    result: done ? demo.result : null,
    error: null,
    created_at: iso(0),
    finished_at: done ? iso(plan.total) : null,
    progress: started ? progress : 0,
    tasks,
    stages,
    edges,
    final_node_ids: plan.tasks.filter((task) => task.final).map((task) => task.id),
  }
}

/** 생성된 워크플로우를 실행하면 보이는 결과 화면(진행률 → 단계·간트 → 최종 결과)을 빠르게 재생한다.
 *  단계 보기·간트 보기는 실제 실행 결과 화면의 컴포넌트를 그대로 쓴다. */
export default function RunPreview({ demo, runKey }: { demo: Demo; runKey: number }) {
  const plan = useMemo(() => planRun(demo.stages), [demo])
  const rootRef = useRef<HTMLDivElement>(null)
  const reduced = useMemo(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false, [])
  const [seen, setSeen] = useState(false)
  const [base, setBase] = useState(() => Date.now())
  const [t, setT] = useState(0)
  const [runId, setRunId] = useState(0)
  const [view, setView] = useState<'stages' | 'gantt'>('stages')

  // 화면에 처음 보이면 저절로 시작한다
  useEffect(() => {
    const element = rootRef.current
    if (!element || !('IntersectionObserver' in window)) { setSeen(true); return }
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) { setSeen(true); observer.disconnect() } }, { threshold: 0.3 })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  // 예시를 바꾸거나 실행을 누르면 처음부터 다시 돈다. 움직임 줄이기 설정이면 끝난 화면을 바로 보여준다
  useEffect(() => {
    if (!seen) return
    setBase(Date.now())
    if (reduced) { setT(plan.total); return }
    setT(0)
    setRunId((id) => id + 1)
  }, [seen, plan, runKey, reduced])
  useEffect(() => {
    if (!runId) return
    const begin = performance.now()
    const timer = window.setInterval(() => {
      const next = ((performance.now() - begin) / 1000) * SPEED
      setT(Math.min(next, plan.total))
      if (next >= plan.total) window.clearInterval(timer)
    }, 100)
    return () => window.clearInterval(timer)
  }, [runId, plan])

  const started = seen && (runId > 0 || t >= plan.total)
  const execution = executionAt(demo, plan, base, t, started)
  const active = ['pending', 'running'].includes(execution.status)
  const now = base + t * 1000
  const sequential = plan.tasks.reduce((sum, task) => sum + task.secs + PICKUP, 0)

  function replay() { setBase(Date.now()); setT(0); setRunId((id) => id + 1) }
  function downloadResult() {
    if (!execution.result) return
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([execution.result], { type: 'text/markdown' }))
    link.download = `mars_result_example_${demo.label}.md`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return <div ref={rootRef} className="mk-window mk-run-window" aria-label="예시: 워크플로우 실행 결과 화면">
    <div className="mk-window-bar" aria-hidden="true"><i /><i /><i /><span>marsflowlab.com/executions/128</span></div>
    <div className="mk-run">
      <header className="result-header">
        <div>
          <div className="result-title-row"><h1>Workflow result</h1><span className={`status-pill large ${execution.status}`}>{execution.status}</span></div>
          <p>{demo.prompt}</p>
        </div>
        <div className="result-actions"><button className="btn ghost" onClick={replay} disabled={active && started}>{active && started ? '실행 중…' : '▶ 다시 실행'}</button></div>
      </header>

      <section className="run-progress-card">
        <div className="run-progress-heading"><span><i className={active ? 'pulse-dot' : 'check-dot'} /> {active ? 'Workflow is running' : 'Execution complete'}</span><strong>{execution.progress}%</strong></div>
        <div className="progress-bar"><div style={{ width: `${execution.progress}%` }} /></div>
        {!active && <small className="mk-run-saved">한 기기로 순서대로 했다면 약 {sequential}초 → 나눠서 {Math.round(plan.total)}초 만에 끝났어요 (미리보기는 {SPEED}배속)</small>}
      </section>

      <section className="result-section">
        <div className="result-section-heading timeline-heading">
          <div><h2>Agent collaboration</h2><p>같은 단계(열)의 블록은 동시에 실행될 수 있습니다. 블록마다 배정 워커, 시작·종료 시각, 소요 시간을 보여줍니다.</p></div>
          <div className="view-toggle" role="group" aria-label="타임라인 보기 방식">
            <button type="button" className={view === 'stages' ? 'active' : ''} aria-pressed={view === 'stages'} onClick={() => setView('stages')}>단계 보기</button>
            <button type="button" className={view === 'gantt' ? 'active' : ''} aria-pressed={view === 'gantt'} onClick={() => setView('gantt')}>간트 보기</button>
          </div>
        </div>
        <div className="task-status-summary">{Object.entries(TASK_STATUS).map(([status, meta]) => { const count = execution.tasks.filter((task) => task.status === status).length; return count ? <span key={status} className={`task-status ${status}`}><i aria-hidden="true">{meta.icon}</i>{meta.label} {count}</span> : null })}</div>
        {view === 'stages'
          ? <ExecutionStageView execution={execution} finalNodeIds={new Set(execution.final_node_ids ?? [])} now={now} fixed />
          : <ExecutionGantt execution={execution} now={now} />}
      </section>

      {execution.result
        ? <section className="final-result-card mk-run-final"><div className="result-section-heading"><div><h2>Generated result</h2></div><button className="btn sm ghost" onClick={downloadResult}>Download</button></div><article className="result-box">{execution.result}</article></section>
        : <section className="final-result-card mk-run-final-wait"><h2>Generated result</h2><p>{started ? '마지막 블록이 끝나면 최종 결과가 여기에 나와요.' : '실행을 시작하면 진행 상황이 실시간으로 바뀌어요.'}</p></section>}

      {execution.tasks.some((task) => task.output) && <section className="agent-output-section"><h2>Agent outputs</h2>{execution.tasks.filter((task) => task.output).map((task) => <details key={task.id}><summary><span>{task.agent_name}</span><small>{taskWorkerLabel(task)}</small></summary><div className="result-box">{task.output}</div></details>)}</section>}
    </div>
  </div>
}
