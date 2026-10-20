import { Execution, Task } from '../types'
import { formatClock, formatDuration, taskDuration, taskStatus, taskWorkerLabel, TASK_STATUS } from '../workflow'

type Lane = { key: string; label: string; tasks: Task[] }

const time = (value: string) => new Date(value).getTime()

/** 워커별 레인과 시간축으로 실제로 어떤 블록이 동시에 돌았는지 보여준다. */
export default function ExecutionGantt({ execution, now }: { execution: Execution; now: number }) {
  const started = execution.tasks.filter((task) => task.started_at)
  const waiting = execution.tasks.filter((task) => !task.started_at)
  const active = ['pending', 'running'].includes(execution.status)
  const t0 = Math.min(time(execution.created_at), ...started.map((task) => time(task.started_at!)))
  const ends = started.map((task) => (task.finished_at ? time(task.finished_at) : now))
  const t1 = Math.max(t0 + 1000, active ? now : execution.finished_at ? time(execution.finished_at) : t0, ...ends)
  const span = t1 - t0
  const percent = (value: number) => ((value - t0) / span) * 100

  // 클라우드 작업은 제공자별 레인, 로컬 작업은 배정된 워커별 레인에 둔다
  const lanes = new Map<string, Lane>()
  for (const task of [...started].sort((a, b) => time(a.started_at!) - time(b.started_at!))) {
    const key = task.executor === 'cloud' ? `cloud:${task.provider}` : `device:${task.assigned_device_id ?? 'none'}`
    if (!lanes.has(key)) lanes.set(key, { key, label: taskWorkerLabel(task), tasks: [] })
    lanes.get(key)!.tasks.push(task)
  }
  const ticks = Array.from({ length: 5 }, (_, index) => t0 + (span * index) / 4)
  const usedStatuses = Object.keys(TASK_STATUS).filter((status) => execution.tasks.some((task) => task.status === status))

  return <div className="gantt">
    <div className="gantt-legend" aria-label="상태 범례">
      {usedStatuses.map((status) => <span key={status} className={`task-status ${status}`}><i aria-hidden="true">{TASK_STATUS[status].icon}</i>{TASK_STATUS[status].label}</span>)}
      <small>시작 {new Date(t0).toLocaleTimeString()} 기준 · 전체 {formatDuration(span)}</small>
    </div>
    {lanes.size ? <div className="gantt-chart">
      <div className="gantt-axis">
        <span className="gantt-lane-label" />
        <div className="gantt-track">{ticks.map((tick, index) => <span key={index} className="gantt-tick" style={{ left: `${percent(tick)}%` }}>+{formatDuration(tick - t0)}</span>)}</div>
      </div>
      {[...lanes.values()].map((lane) => <div className="gantt-lane" key={lane.key}>
        <span className="gantt-lane-label" title={lane.label}>{lane.label}</span>
        <div className="gantt-track">
          {ticks.map((tick, index) => <i key={index} className="gantt-gridline" style={{ left: `${percent(tick)}%` }} />)}
          {lane.tasks.map((task) => {
            const start = time(task.started_at!)
            const end = task.finished_at ? time(task.finished_at) : now
            const status = taskStatus(task.status)
            return <div
              key={task.id}
              className={`gantt-bar ${task.status}`}
              style={{ left: `${percent(start)}%`, width: `max(${Math.max(0.6, percent(end) - percent(start))}%, 6px)` }}
              tabIndex={0}
              aria-label={`${task.agent_name}, ${status.label}, ${taskDuration(task, now)}`}
            >
              <span><i aria-hidden="true">{status.icon}</i>{task.agent_name}</span>
              <div className="gantt-tip" role="tooltip">
                <strong>{task.agent_name}</strong>
                <span>{status.icon} {status.label} · {taskWorkerLabel(task)}</span>
                <span>{formatClock(task.started_at)} → {task.finished_at ? formatClock(task.finished_at) : '진행 중'} · {taskDuration(task, now)}</span>
              </div>
            </div>
          })}
        </div>
      </div>)}
    </div> : <p className="muted">아직 시작한 블록이 없습니다.</p>}
    {waiting.length > 0 && <p className="gantt-waiting">아직 시작하지 않은 블록: {waiting.map((task) => `${task.agent_name}(${taskStatus(task.status).label})`).join(', ')}</p>}
  </div>
}
