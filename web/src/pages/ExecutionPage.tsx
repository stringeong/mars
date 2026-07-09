import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { Execution } from '../types'

const STATUS_LABEL: Record<string, string> = {
  pending: '대기', running: '실행 중', completed: '완료', failed: '실패', cancelled: '중단됨',
  blocked: '선행 대기', ready: '할당 대기', done: '완료',
}

export default function ExecutionPage() {
  const { id } = useParams()
  const [execution, setExecution] = useState<Execution | null>(null)
  const [error, setError] = useState('')

  async function load() {
    try {
      setExecution(await api.get<Execution>(`/executions/${id}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(() => {
      setExecution((cur) => {
        if (cur && ['completed', 'failed', 'cancelled'].includes(cur.status)) return cur
        load()
        return cur
      })
    }, 3000) // NF-102: 실행 상태 5초 이내 주기 갱신
    return () => clearInterval(timer)
  }, [id])

  async function cancel() {
    if (!confirm('실행을 중단할까요?')) return
    try {
      setExecution(await api.post<Execution>(`/executions/${id}/cancel`))
    } catch (e) {
      setError(e instanceof Error ? e.message : '중단 실패')
    }
  }

  if (!execution) return <div>{error || '불러오는 중...'}</div>

  const active = ['pending', 'running'].includes(execution.status)

  return (
    <div>
      <div className="row spread">
        <div>
          <h1>실행 #{execution.id}</h1>
          <p className="subtitle">{execution.run_prompt}</p>
        </div>
        <div className="row">
          <span className={`badge ${execution.status}`}>{STATUS_LABEL[execution.status] ?? execution.status}</span>
          {active && <button className="btn danger" onClick={cancel}>중단</button>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <div className="row">
          <div className="progress-bar"><div style={{ width: `${execution.progress}%` }} /></div>
          <strong>{execution.progress}%</strong>
        </div>
      </div>

      <div className="card">
        <h2>작업 현황</h2>
        <table>
          <thead>
            <tr><th>에이전트</th><th>상태</th><th>기기</th><th>완료 시각</th></tr>
          </thead>
          <tbody>
            {execution.tasks.map((t) => (
              <tr key={t.id}>
                <td><strong>{t.agent_name}</strong></td>
                <td><span className={`badge ${t.status}`}>{STATUS_LABEL[t.status] ?? t.status}</span></td>
                <td>{t.assigned_device_id ? `#${t.assigned_device_id}` : '—'}</td>
                <td style={{ fontSize: 13 }}>
                  {t.finished_at ? new Date(t.finished_at).toLocaleTimeString('ko-KR') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {execution.error && (
        <div className="card">
          <h2>오류</h2>
          <div className="error">{execution.error}</div>
        </div>
      )}

      {execution.result && (
        <div className="card">
          <div className="row spread">
            <h2>최종 결과</h2>
            <button
              className="btn sm ghost"
              onClick={() => {
                const blob = new Blob([execution.result ?? ''], { type: 'text/markdown' })
                const a = document.createElement('a')
                a.href = URL.createObjectURL(blob)
                a.download = `mars_result_${execution.id}.md`
                a.click()
              }}
            >
              다운로드
            </button>
          </div>
          <div className="result-box">{execution.result}</div>
        </div>
      )}

      {execution.tasks.some((t) => t.output) && (
        <div className="card">
          <h2>에이전트별 출력</h2>
          {execution.tasks.filter((t) => t.output).map((t) => (
            <details key={t.id} style={{ marginBottom: 8 }}>
              <summary style={{ cursor: 'pointer', fontWeight: 600, padding: '6px 0' }}>{t.agent_name}</summary>
              <div className="result-box">{t.output}</div>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}
