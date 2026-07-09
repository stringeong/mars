import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { ExecutionListItem } from '../types'

const STATUS_LABEL: Record<string, string> = {
  pending: '대기', running: '실행 중', completed: '완료', failed: '실패', cancelled: '중단됨',
}

export default function HistoryPage() {
  const [items, setItems] = useState<ExecutionListItem[]>([])
  const navigate = useNavigate()

  useEffect(() => {
    api.get<ExecutionListItem[]>('/executions').then(setItems).catch(() => {})
  }, [])

  return (
    <div>
      <h1>실행 이력</h1>
      <p className="subtitle">과거 서비스 실행 결과를 다시 확인할 수 있습니다.</p>
      <div className="card">
        <table>
          <thead>
            <tr><th>#</th><th>서비스</th><th>실행 프롬프트</th><th>상태</th><th>실행 시각</th></tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id} className="clickable" onClick={() => navigate(`/executions/${e.id}`)}>
                <td>{e.id}</td>
                <td><strong>{e.service_name}</strong></td>
                <td style={{ color: 'var(--muted)', fontSize: 13 }}>
                  {e.run_prompt.slice(0, 50)}{e.run_prompt.length > 50 ? '…' : ''}
                </td>
                <td><span className={`badge ${e.status}`}>{STATUS_LABEL[e.status] ?? e.status}</span></td>
                <td style={{ fontSize: 13 }}>{new Date(e.created_at).toLocaleString('ko-KR')}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={5} style={{ color: 'var(--muted)' }}>실행 이력이 없습니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
